"""Idle task: snapshot the weekly in-app library digest.

Assembles a "This week in your library" summary from existing stats, health,
coverage, issues, and recent additions, then stores it keyed by the current
weekly bucket. The Admin dashboard reads the latest snapshot — no email
transport is involved (in-app delivery).

Default interval: 7 days.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.digest import snapshot_weekly_digest
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 7 * 86400  # weekly


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}

    digest = snapshot_weekly_digest(db, settings)
    payload = digest.get("payload") or {}
    logger.info(
        "Weekly digest snapshot saved: week_start=%s total=%s new=%s open_issues=%s",
        digest.get("week_start"),
        (payload.get("library") or {}).get("total"),
        (payload.get("new_this_week") or {}).get("count"),
        (payload.get("issues") or {}).get("open"),
    )
    return {
        "status": "completed",
        "count": int((payload.get("new_this_week") or {}).get("count") or 0),
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="weekly_digest",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Snapshots a weekly 'This week in your library' digest (new additions, "
                "health, knowledge coverage, open issues) for the Admin dashboard."
            ),
        )
    )
