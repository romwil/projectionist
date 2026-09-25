"""Idle task: named-member whisper inbox (one 12-word why per member per week)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.whisper import deliver_member_whispers
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 6 * 3600


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_member_whispers(db, settings)
    logger.info(
        "Whisper inbox created=%s considered=%s skipped=%s",
        result.get("created"),
        result.get("considered"),
        result.get("skipped"),
    )
    return {"status": "completed", "count": int(result.get("created") or 0), **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="whisper_inbox",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Leaves each named household member a whisper with a 12-word why "
                "(not a download-complete ping; not owner-only Good News)."
            ),
        )
    )
