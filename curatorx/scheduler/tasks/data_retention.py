"""Idle task: prune old time-series data to bound SQLite growth.

Deletes rows from accumulating tables that exceed their configured retention
period, then optionally VACUUMs the database if a significant number of rows
were removed.

Tables pruned:
    - ``system_telemetry_stream`` — default 90-day retention
    - ``interaction_telemetry``   — default 90-day retention
    - ``daily_anniversaries``     — default 30-day retention (rebuilt daily)

Runs at most once per day regardless of scheduler cycle frequency.
Default interval: 24 hours.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
VACUUM_THRESHOLD = 1000

DEFAULT_TELEMETRY_RETENTION_DAYS = 90
DEFAULT_INTERACTION_RETENTION_DAYS = 90
DEFAULT_ANNIVERSARY_RETENTION_DAYS = 30


def _get_retention_setting(settings: Settings, key: str, default: int) -> int:
    """Read a retention-days value from settings.json extras, falling back to default."""
    raw = getattr(settings, key, None)
    if raw is not None:
        try:
            return max(1, int(raw))
        except (ValueError, TypeError):
            pass
    return default


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    telemetry_days = _get_retention_setting(
        settings, "telemetry_retention_days", DEFAULT_TELEMETRY_RETENTION_DAYS
    )
    interaction_days = _get_retention_setting(
        settings, "interaction_retention_days", DEFAULT_INTERACTION_RETENTION_DAYS
    )
    anniversary_days = _get_retention_setting(
        settings, "anniversary_retention_days", DEFAULT_ANNIVERSARY_RETENTION_DAYS
    )

    total_pruned = 0
    pruned_details: Dict[str, int] = {}

    if should_stop():
        return {"status": "interrupted"}

    count = db.prune_telemetry(telemetry_days)
    pruned_details["system_telemetry_stream"] = count
    total_pruned += count

    if should_stop():
        return {"status": "interrupted", "pruned": pruned_details, "total_pruned": total_pruned}

    count = db.prune_interaction_telemetry(interaction_days)
    pruned_details["interaction_telemetry"] = count
    total_pruned += count

    if should_stop():
        return {"status": "interrupted", "pruned": pruned_details, "total_pruned": total_pruned}

    count = db.prune_daily_anniversaries(anniversary_days)
    pruned_details["daily_anniversaries"] = count
    total_pruned += count

    vacuumed = False
    if total_pruned >= VACUUM_THRESHOLD:
        try:
            db.vacuum()
            vacuumed = True
            logger.info("Data retention: VACUUM completed after pruning %d rows", total_pruned)
        except Exception:
            logger.exception("Data retention: VACUUM failed (non-fatal)")

    for table, rows in pruned_details.items():
        if rows > 0:
            logger.info("Data retention: pruned %d rows from %s", rows, table)

    if total_pruned == 0:
        logger.info("Data retention: no rows to prune")

    return {
        "status": "completed",
        "pruned": pruned_details,
        "total_pruned": total_pruned,
        "vacuumed": vacuumed,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="data_retention",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
        )
    )
