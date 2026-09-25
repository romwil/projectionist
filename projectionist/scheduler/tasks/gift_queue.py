"""Idle task: deliver due house gifts on the newsletter / nudge cadence."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.house.gifts import deliver_due_gifts
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 7 * 86400  # weekly — same cadence as digest / newsletter / nudge


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_due_gifts(db, settings)
    logger.info(
        "House gifts: delivered=%s emailed=%s skipped_future=%s",
        result.get("delivered"),
        result.get("emailed"),
        result.get("skipped_future"),
    )
    return result


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="gift_queue",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Delivers owner-queued house gifts (inbox + optional email) on the "
                "same weekly cadence as the member newsletter and enthusiast nudge. "
                "One gift at a time — never a household blast."
            ),
        )
    )
