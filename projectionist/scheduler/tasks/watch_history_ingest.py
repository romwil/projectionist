"""Idle task: ingest Plex watch history into the watch tracker ledger."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.watch_tracker.plex_history import normalize_plex_history
from projectionist.watch_tracker.store import get_ingest_cursor, ingest_watch_events, set_ingest_cursor

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60
PAGE_SIZE = 250
MAX_PAGES = 40  # 10k rows bound
OVERLAP_MS = 10 * 60 * 1000
INITIAL_LOOKBACK_MS = 90 * 86400 * 1000


def _plex_client(settings: Settings):
    base = str(settings.plex_url or "").strip()
    token = str(settings.plex_token or "").strip()
    if not base or not token:
        return None
    from projectionist.connectors.plex import PlexClient

    return PlexClient(
        base_url=base,
        token=token,
        movie_section=settings.plex_movie_section or None,
        tv_section=settings.plex_tv_section or None,
    )


def run_history_ingest(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    client = _plex_client(settings)
    if client is None:
        return {"status": "skipped", "reason": "plex_not_configured"}
    try:
        machine_id = client.machine_identifier()
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "reason": "plex_unreachable", "error": str(exc)}

    try:
        from projectionist.watch_tracker.identity import sync_plex_watch_identities

        sync_plex_watch_identities(
            db,
            plex_url=str(settings.plex_url or ""),
            plex_token=str(settings.plex_token or ""),
            server_machine_id=machine_id,
            repair=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("watch identity alias refresh failed (continuing ingest)")

    cursor = get_ingest_cursor(db, source="plex_history", server_machine_id=machine_id)
    now_ms = int(time.time() * 1000)
    high_water = int(cursor["high_watermark_ms"]) if cursor and cursor.get("high_watermark_ms") else None
    since_ms: Optional[int]
    if high_water:
        since_ms = max(0, high_water - OVERLAP_MS)
    else:
        since_ms = max(0, now_ms - INITIAL_LOOKBACK_MS)

    fetched = 0
    inserted = 0
    deduped = 0
    mapped = 0
    unmapped = 0
    skipped = 0
    missing_identity = 0
    max_seen = high_water or 0

    try:
        start = 0
        for _ in range(MAX_PAGES):
            if should_stop():
                return {"status": "interrupted", "fetched": fetched, "inserted": inserted}
            page = client.history_page(start=start, size=PAGE_SIZE, since_ms=since_ms)
            events = [
                normalize_plex_history(item, server_machine_id=machine_id)
                for item in page.items
            ]
            fetched += page.size
            skipped += page.skipped
            missing_identity += page.missing_identity
            if page.size <= 0:
                break
            if events:
                result = ingest_watch_events(db, events)
                inserted += result.inserted
                deduped += result.deduped
                mapped += result.mapped
                unmapped += result.unmapped
                for ev in events:
                    max_seen = max(max_seen, int(ev.occurred_at_ms))
            start += page.size
            if page.size < PAGE_SIZE:
                break
            if page.total_size is not None and start >= int(page.total_size):
                break

        set_ingest_cursor(
            db,
            source="plex_history",
            server_machine_id=machine_id,
            high_watermark_ms=max_seen or now_ms,
            success=True,
        )
        return {
            "status": "ok",
            "source": "plex_history",
            "fetched": fetched,
            "inserted": inserted,
            "deduped": deduped,
            "mapped": mapped,
            "unmapped": unmapped,
            "skipped": skipped,
            "missing_identity": missing_identity,
            "high_watermark_ms": max_seen or now_ms,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("watch history ingest failed")
        raw_error = str(exc)
        unsupported = "HTTP 404" in raw_error or "HTTP 405" in raw_error
        safe_error = (
            "Plex history endpoint is unsupported"
            if unsupported
            else f"Plex history page failed ({type(exc).__name__})"
        )
        set_ingest_cursor(
            db,
            source="plex_history",
            server_machine_id=machine_id,
            last_error=safe_error,
            success=False,
        )
        return {
            "status": "degraded",
            "source": "plex_history",
            "reason": (
                "history_endpoint_unsupported"
                if unsupported
                else "history_page_failed"
            ),
            "error": safe_error,
            "fetched": fetched,
            "inserted": inserted,
            "deduped": deduped,
            "mapped": mapped,
            "unmapped": unmapped,
            "skipped": skipped,
            "missing_identity": missing_identity,
        }


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    return run_history_ingest(db, settings, should_stop)


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="watch_history_ingest",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Ingests Plex watch history into the per-user watch ledger "
                "(normalized events only — not household view counts)."
            ),
        )
    )
