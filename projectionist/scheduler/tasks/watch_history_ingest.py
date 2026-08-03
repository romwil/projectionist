"""Idle task: ingest Plex watch history into the watch tracker ledger."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.watch_tracker.correlate import correlate_after_ingest
from projectionist.watch_tracker.plex_history import history_page
from projectionist.watch_tracker.store import get_ingest_cursor, ingest_watch_events, set_ingest_cursor

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60
PAGE_SIZE = 250
MAX_PAGES = 40  # 10k rows bound
OVERLAP_MS = 10 * 60 * 1000
INITIAL_LOOKBACK_MS = 90 * 86400 * 1000


def _plex_client(settings: Settings):
    plex = settings.plex
    base = str(getattr(plex, "base_url", "") or "").strip()
    token = str(getattr(plex, "token", "") or "").strip()
    if not base or not token:
        return None
    from projectionist.connectors.plex import PlexClient

    return PlexClient(
        base_url=base,
        token=token,
        movie_section=getattr(plex, "movie_section", None),
        tv_section=getattr(plex, "tv_section", None),
    )


async def run(
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
    max_seen = high_water or 0
    affected_users: set[str] = set()

    try:
        start = 0
        for _ in range(MAX_PAGES):
            if should_stop():
                return {"status": "interrupted", "fetched": fetched, "inserted": inserted}
            page, events = history_page(client, start=start, size=PAGE_SIZE, since_ms=since_ms)
            if not events:
                break
            result = ingest_watch_events(db, events)
            fetched += result.fetched
            inserted += result.inserted
            deduped += result.deduped
            mapped += result.mapped
            unmapped += result.unmapped
            for ev in events:
                max_seen = max(max_seen, int(ev.occurred_at_ms))
                # user mapping happens inside ingest; collect from DB after batch if needed
            # Collect mapped user ids for correlation
            with db.connect() as conn:
                for ev in events:
                    row = conn.execute(
                        """
                        SELECT user_id FROM watch_events
                        WHERE source = 'plex_history' AND source_event_id = ?
                        LIMIT 1
                        """,
                        (ev.source_event_id,),
                    ).fetchone()
                    if row and row["user_id"]:
                        affected_users.add(str(row["user_id"]))
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
        corr = correlate_after_ingest(db, user_ids=sorted(affected_users) or None)
        return {
            "status": "ok",
            "source": "plex_history",
            "fetched": fetched,
            "inserted": inserted,
            "deduped": deduped,
            "mapped": mapped,
            "unmapped": unmapped,
            "high_watermark_ms": max_seen or now_ms,
            "correlation": corr,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("watch history ingest failed")
        set_ingest_cursor(
            db,
            source="plex_history",
            server_machine_id=machine_id,
            last_error=str(exc),
            success=False,
        )
        return {"status": "error", "error": str(exc), "fetched": fetched, "inserted": inserted}


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
