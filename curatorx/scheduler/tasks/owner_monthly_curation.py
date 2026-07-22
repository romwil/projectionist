"""Idle task: owner monthly collection-curation update."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.newsletters import deliver_owner_monthly_curation
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 86400  # ~monthly


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    result = deliver_owner_monthly_curation(db, settings)
    logger.info(
        "Owner monthly curation delivered=%s emailed=%s month=%s",
        result.get("delivered"),
        result.get("emailed"),
        result.get("month"),
    )
    return {"status": "completed", "count": int(result.get("delivered") or 0), **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="owner_monthly_curation",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Delivers a monthly collection-curation update to owners via the "
                "shared notification inbox (and email when configured)."
            ),
        )
    )
