"""Idle task: keep a week of Live programme titles published.

Plex reads a guide file that used to cover about half a day. When that slice
ended, the grid showed Unknown Airing and playback stopped. This task keeps
seven days on the file and reloads the next week before the current one runs out.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

# Often enough to notice a window inside the two-day refill lead.
INTERVAL_SECONDS = 6 * 3600
TASK_NAME = "live_guide_week"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    from projectionist.live_channels.guide_horizon import maintain_guide_week

    result = maintain_guide_week(settings, db, should_stop=should_stop)
    if result.get("skipped"):
        return {"status": "skipped", **result}
    if result.get("extended") or result.get("rolled") or result.get("refilled"):
        logger.info(
            "Live guide week extended=%s rolled=%s hours_ahead=%s refilled=%s",
            result.get("extended"),
            result.get("rolled"),
            result.get("hours_ahead"),
            len(result.get("refilled") or []),
        )
    return {"status": "completed", **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            off_loop=True,
            run_fn=run,
            description=(
                "Keeps about a week of Live TV programme titles published, and "
                "loads the next week before the current one runs out. "
                "After this is installed, use Refresh Plex map once so Plex "
                "picks up the longer guide."
            ),
        )
    )
