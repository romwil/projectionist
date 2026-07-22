"""Idle task: notify when gap / watchlist titles arrive in the library."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.arrivals import notify_arrivals
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 6 * 3600  # every 6 hours


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = notify_arrivals(db, settings)
    logger.info(
        "Arrival notifications created=%s emailed=%s scanned=%s",
        result.get("created"),
        result.get("emailed"),
        result.get("scanned"),
    )
    return {"status": "completed", "count": int(result.get("created") or 0), **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="arrival_notifications",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Notifies members when gap-analysis or watchlist titles land in the "
                "library (inbox + optional email)."
            ),
        )
    )
