"""Optional idle trickle: fill ``long_synopsis`` from Wikipedia or OMDb.

Never overwrites Plex ``summary`` / TMDB ``tmdb_overview`` / ``tagline``.
Operators must set ``long_synopsis_source`` (``wikipedia`` / ``omdb`` / ``auto``);
without a usable source the task skips with a clear ``outcome_reason``.

Default interval: 12 hours. Small batches + pause between requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Dict, Optional, Tuple

from curatorx.config_store import Settings
from curatorx.connectors.omdb import OMDbClient
from curatorx.connectors.wikipedia import fetch_extract
from curatorx.library.db import Database
from curatorx.scheduler.autotune import resolve_batch_size
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.scheduler.run_log import emit_task_event

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
DEFAULT_BATCH_SIZE = 10
REQUEST_PAUSE_SECONDS = 1.5
_MAX_SYNOPSIS_CHARS = 4000
TASK_NAME = "long_synopsis_enrichment"
VALID_SOURCES = frozenset({"wikipedia", "omdb", "auto"})


def _normalize_source(raw: Any) -> str:
    return str(raw or "").strip().lower()


def resolve_synopsis_source(settings: Settings) -> Tuple[str, Optional[str]]:
    """Return ``(source, skip_reason)``. Empty source → skip."""
    source = _normalize_source(getattr(settings, "long_synopsis_source", ""))
    if not source or source in {"off", "none", "disabled"}:
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

    if source in {"wikipedia", "auto"}:
        extract = _clean_synopsis(
            fetch_extract(title, year=year if year is not None else None, media_type=media_type)
        )
        if extract:
            return extract, "wikipedia"

    if source in {"omdb", "auto"} and omdb is not None:
        plot = ""
        if imdb_id:
            try:
                plot = omdb.plot_by_imdb(imdb_id)
            except RuntimeError:
                plot = ""
        if not plot:
            try:
                plot = omdb.plot_by_title(
                    title, year=int(year) if year is not None else None
                )
            except RuntimeError:
                plot = ""
        plot = _clean_synopsis(plot)
        if plot:
            return plot, "omdb"

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
                "Set long_synopsis_source to wikipedia, omdb, or auto "
                "(and OMDB_API_KEY when using omdb). Never invents plot."
            ),
        }

    batch_size = resolve_batch_size(db, TASK_NAME, DEFAULT_BATCH_SIZE)
    backlog = db.items_needing_long_synopsis(limit=batch_size)
    if not backlog:
        return {"status": "completed", "enriched": 0, "remaining": 0}

    omdb: Optional[OMDbClient] = None
    omdb_key = str(getattr(settings, "omdb_api_key", "") or "").strip()
    if source in {"omdb", "auto"} and omdb_key:
        omdb = OMDbClient(omdb_key)

    enriched = 0
    errors = 0
    misses = 0
    emit_task_event(
        f"Fetching long synopsis for {len(backlog)} titles ({source})",
        batch_size=len(backlog),
        source=source,
    )

    for idx, row in enumerate(backlog):
        if should_stop():
            return {
                "status": "interrupted",
                "enriched": enriched,
                "errors": errors,
                "misses": misses,
            }

        try:
            synopsis, provenance = _fetch_for_row(row, source=source, omdb=omdb)
        except Exception as error:
            errors += 1
            logger.debug(
                "Long synopsis fetch failed id=%s: %s",
                row["id"],
                error,
            )
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)
            continue

        if synopsis and provenance:
            db.set_long_synopsis(int(row["id"]), synopsis, provenance)
            enriched += 1
            if enriched == 1 or enriched % 5 == 0:
                emit_task_event(
                    f"Enriched {enriched}/{len(backlog)}",
                    enriched=enriched,
                    errors=errors,
                    misses=misses,
                )
        else:
            misses += 1

        if idx + 1 < len(backlog):
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    remaining = db.count_items_needing_long_synopsis()
    logger.info(
        "Long synopsis trickle: enriched=%s errors=%s misses=%s remaining=%s source=%s",
        enriched,
        errors,
        misses,
        remaining,
        source,
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "errors": errors,
        "misses": misses,
        "batch_size": batch_size,
        "source": source,
        "has_more": remaining > 0,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Optional longer plot text from Wikipedia extract or OMDb into "
                f"long_synopsis (never overwrites Plex/TMDB). About "
                f"{DEFAULT_BATCH_SIZE} titles per run when long_synopsis_source is set; "
                "skips cleanly when the source is off or OMDb lacks a key."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
            progress_scope="long_synopsis_backlog",
        )
    )
