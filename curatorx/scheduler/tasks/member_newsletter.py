"""Idle task: fan out opt-in weekly member newsletters after the digest snapshot."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.newsletters import deliver_weekly_newsletters
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 7 * 86400


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_weekly_newsletters(db, settings)
    logger.info(
        "Weekly newsletters delivered=%s emailed=%s",
        result.get("delivered"),
        result.get("emailed"),
    )
    return {"status": "completed", "count": int(result.get("delivered") or 0), **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="member_newsletter",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Sends the opt-in weekly member newsletter (persona-voiced) to inbox "
                "and email for members who subscribed in Account settings."
            ),
        )
    )
