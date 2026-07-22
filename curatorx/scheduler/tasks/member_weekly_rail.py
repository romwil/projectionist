"""Idle task: build per-member weekly For-you rails (rides digest cadence)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.taste import deliver_member_weekly_rails

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 7 * 86400  # weekly — same cadence as digest / newsletter


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_member_weekly_rails(db, settings)
    logger.info(
        "Member weekly rails: built=%s empty=%s llm_used=%s/%s",
        result.get("built"),
        result.get("empty"),
        result.get("llm_calls_used"),
        result.get("llm_cap"),
    )
    return {"status": "completed", **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="member_weekly_rail",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Builds each member's personalized weekly For-you rail with persona-voiced "
                "whys (template voice; hard-capped LLM budget reserved)."
            ),
        )
    )
