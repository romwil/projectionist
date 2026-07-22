"""Idle task: opt-in Enthusiast “you have to see this” nudges."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.nudges import deliver_enthusiast_nudges
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 7 * 86400  # weekly — same cadence as digest / newsletter


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_enthusiast_nudges(db, settings)
    logger.info(
        "Enthusiast nudges: delivered=%s emailed=%s pick=%s",
        result.get("delivered"),
        result.get("emailed"),
        result.get("pick"),
    )
    return {"status": "completed", **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="enthusiast_nudge",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Sends opt-in “you have to see this” nudges (inbox + optional email), "
                "optionally reacting to recently watched / continue-watching context — "
                "not live Plex sessions."
            ),
        )
    )
