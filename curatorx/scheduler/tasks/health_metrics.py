"""Idle task: pre-compute and cache library health metrics.

Calls the existing ``compute_library_health()`` and stores the result in the
``curator_system_config`` key-value store under ``cached_health_metrics``.
This avoids re-scanning the library on every ``/api/library/health`` request.

Default interval: 6 hours.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.health import compute_library_health
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours
CACHE_KEY = "cached_health_metrics"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}

    health = compute_library_health(db)
    db.set_config(CACHE_KEY, json.dumps(health))

    logger.info(
        "Health metrics cached: total=%s, unwatched=%s",
        health.get("total"),
        health.get("unwatched_count"),
    )
    return {"status": "completed", "total": health.get("total", 0)}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="health_metrics",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
        )
    )
