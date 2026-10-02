"""Idle trickle: fill ``long_synopsis`` from Wikipedia or OMDb.

Never overwrites Plex ``summary`` / TMDB ``tmdb_overview`` / ``tagline``.

Default source is ``wikipedia`` (free, no API key, deeper plot text without an LLM).
Owners disable the trickle with ``long_synopsis_source=off`` (preferred); empty /
``none`` / ``disabled`` also skip. Values: ``wikipedia`` / ``omdb`` / ``auto`` / ``off``.

Default interval: 12 hours. Small batches + pause between requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Dict, Optional, Tuple

from projectionist.config_store import Settings
from projectionist.connectors.omdb import OMDbClient
from projectionist.connectors.wikipedia import fetch_extract
from projectionist.library.db import Database
from projectionist.library.knowledge_fetch import KIND_SYNOPSIS, FetchRunTracker
from projectionist.scheduler.autotune import resolve_batch_size
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.scheduler.run_log import emit_task_event
from projectionist.scheduler.tasks.coverage_signals import emit_synopsis_backlog_signals

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
DEFAULT_BATCH_SIZE = 10
REQUEST_PAUSE_SECONDS = 1.5
_MAX_SYNOPSIS_CHARS = 4000
TASK_NAME = "long_synopsis_enrichment"
VALID_SOURCES = frozenset({"wikipedia", "omdb", "auto"})
# Preferred disable value is ``off``; empty / none / disabled also disable.
DISABLED_SOURCES = frozenset({"", "off", "none", "disabled"})


def _normalize_source(raw: Any) -> str:
    return str(raw or "").strip().lower()


def resolve_synopsis_source(settings: Settings) -> Tuple[str, Optional[str]]:
    """Return ``(source, skip_reason)``.

    Missing/unset settings default to ``wikipedia``. Explicit empty or ``off``
    (also ``none`` / ``disabled``) disables the trickle.
    """
    source = _normalize_source(getattr(settings, "long_synopsis_source", "wikipedia"))
    if source in DISABLED_SOURCES:
        return "", "no_synopsis_source_configured"
    if source not in VALID_SOURCES:
        return "", "invalid_synopsis_source"
    if source == "omdb" and not str(getattr(settings, "omdb_api_key", "") or "").strip():
        return "", "no_omdb_api_key"
    return source, None


def _clean_synopsis(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) > _MAX_SYNOPSIS_CHARS:
        cleaned = cleaned[: _MAX_SYNOPSIS_CHARS - 1].rstrip() + "…"
    return cleaned


def _fetch_for_row(
    row: Any,
    *,
    source: str,
    omdb: Optional[OMDbClient],
) -> Tuple[str, str]:
    """Return ``(synopsis, provenance_label)`` or empty strings."""
    title = str(row["title"] or "")
    year = row["year"]
    media_type = str(row["media_type"] or "movie")
    imdb_id = ""
    keys = row.keys() if hasattr(row, "keys") else []
    if "imdb_id" in keys:
        imdb_id = str(row["imdb_id"] or "").strip()

    # An outage must not look like "no plot exists": remember whether any source
    # actually answered, and raise only when none did.
    answered = False
    last_error: Optional[BaseException] = None

    if source in {"wikipedia", "auto"}:
        try:
            extract = _clean_synopsis(
                fetch_extract(
                    title,
                    year=year if year is not None else None,
                    media_type=media_type,
                    strict=True,
                )
            )
            answered = True
            if extract:
                return extract, "wikipedia"
        except RuntimeError as error:
            last_error = error

    if source in {"omdb", "auto"} and omdb is not None:
        plot = ""
        omdb_errors = 0
        omdb_calls = 0
        if imdb_id:
            omdb_calls += 1
            try:
                plot = omdb.plot_by_imdb(imdb_id)
            except RuntimeError as error:
                omdb_errors += 1
                last_error = error
        if not plot:
            omdb_calls += 1
            try:
                plot = omdb.plot_by_title(
                    title, year=int(year) if year is not None else None
                )
            except RuntimeError as error:
                omdb_errors += 1
                last_error = error
        if omdb_errors < omdb_calls:
            answered = True
        plot = _clean_synopsis(plot)
        if plot:
            return plot, "omdb"

    if not answered and last_error is not None:
        raise last_error
    return "", ""


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted", "enriched": 0}

    source, skip_reason = resolve_synopsis_source(settings)
    if skip_reason:
        return {
            "status": "skipped",
            "reason": skip_reason,
            "enriched": 0,
            "note": (
                "Default is wikipedia. Set long_synopsis_source to off to disable, "
                "or omdb/auto (OMDB_API_KEY required for omdb). Never invents plot."
            ),
        }

    batch_size = resolve_batch_size(db, TASK_NAME, DEFAULT_BATCH_SIZE)
    # Parked titles (backoff / exhausted) are skipped, so the batch cap bounds
    # upstream calls per run no matter how large the gap is.
    backlog = db.items_needing_long_synopsis(limit=batch_size)
    if not backlog:
        coverage_signals = emit_synopsis_backlog_signals(db, limit=5)
        return {
            "status": "completed",
            "enriched": 0,
            "remaining": 0,
            "coverage_signals": coverage_signals,
        }

    omdb: Optional[OMDbClient] = None
    omdb_key = str(getattr(settings, "omdb_api_key", "") or "").strip()
    if source in {"omdb", "auto"} and omdb_key:
        omdb = OMDbClient(omdb_key)

    tracker = FetchRunTracker(db, KIND_SYNOPSIS)
    enriched = 0
    emit_task_event(
        f"Fetching long synopsis for {len(backlog)} titles ({source})",
        batch_size=len(backlog),
        source=source,
    )

    interrupted = False
    for idx, row in enumerate(backlog):
        if should_stop():
            interrupted = True
            break

        item_id = int(row["id"])
        try:
            synopsis, provenance = _fetch_for_row(row, source=source, omdb=omdb)
        except Exception as error:
            logger.debug("Long synopsis fetch failed id=%s: %s", item_id, error)
            if tracker.error(item_id, error):
                break
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)
            continue

        if synopsis and provenance:
            db.set_long_synopsis(item_id, synopsis, provenance)
            tracker.success(item_id)
            enriched += 1
            if enriched == 1 or enriched % 5 == 0:
                emit_task_event(
                    f"Enriched {enriched}/{len(backlog)}",
                    enriched=enriched,
                    errors=tracker.errors,
                    misses=tracker.misses,
                )
        else:
            tracker.miss(item_id, "no plot text found upstream")

        if idx + 1 < len(backlog):
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    run_stats = tracker.finish()
    if run_stats["breaker_tripped"]:
        emit_task_event(
            f"Pausing long-synopsis fetch: {run_stats['breaker_reason']}",
            enriched=enriched,
            errors=run_stats["errors"],
        )

    # Only titles whose automatic retrieval is *exhausted* are surfaced to the
    # owner. A title that is merely "not fetched yet" is backlog, not an exception.
    coverage_signals = emit_synopsis_backlog_signals(db, limit=min(batch_size, 5))

    remaining = db.count_items_needing_long_synopsis()
    logger.info(
        "Long synopsis trickle: enriched=%s errors=%s misses=%s remaining=%s source=%s",
        enriched,
        run_stats["errors"],
        run_stats["misses"],
        remaining,
        source,
    )
    return {
        "status": "interrupted" if interrupted else "completed",
        "enriched": enriched,
        "errors": run_stats["errors"],
        "misses": run_stats["misses"],
        "exhausted": run_stats["newly_exhausted"],
        "breaker_tripped": run_stats["breaker_tripped"],
        "batch_size": batch_size,
        "source": source,
        "has_more": remaining > 0,
        "coverage_signals": coverage_signals,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Longer plot text from Wikipedia (default) or OMDb into long_synopsis "
                f"(never overwrites Plex/TMDB). About {DEFAULT_BATCH_SIZE} titles per run; "
                "set long_synopsis_source=off to disable, or omdb/auto when preferred."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
            progress_scope="long_synopsis_backlog",
        )
    )
