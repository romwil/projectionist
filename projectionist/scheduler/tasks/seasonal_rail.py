"""Idle task: materialize today's seasonal Explore rail from the holiday calendar."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.feeds import build_seasonal_rail_snapshot
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 6 * 3600  # four times a day — holiday windows shift by day


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted"}
    result = build_seasonal_rail_snapshot(db, limit=12)
    snapshot = result.get("snapshot") or {}
    logger.info(
        "Seasonal rail schedule: date=%s scope=%s items=%s",
        snapshot.get("snapshot_date"),
        snapshot.get("scope_id"),
        snapshot.get("item_count"),
    )
    return result


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="seasonal_rail",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Publishes today's seasonal Explore rail from the household holiday "
                "calendar (asymmetric shoulders + owner rail curation)."
            ),
        )
    )
