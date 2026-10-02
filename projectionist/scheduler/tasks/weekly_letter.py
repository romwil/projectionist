"""Idle task: weekly household letter → owner inbox (optional email)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.weekly_letter import deliver_weekly_letter
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

# Checked a few times a day; delivery itself is once per ISO week (deduped).
INTERVAL_SECONDS = 6 * 3600


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_weekly_letter(db, settings)
    if result.get("delivered"):
        logger.info(
            "Weekly letter delivered=%s emailed=%s week=%s",
            result.get("delivered"),
            result.get("emailed"),
            result.get("week"),
        )
    return {"status": "completed", "count": int(result.get("delivered") or 0), **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="weekly_letter",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Delivers the weekly household letter to the owner's inbox "
                "(and email when the owner opted in and mail is configured)."
            ),
        )
    )
