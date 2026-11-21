"""Jobs-engine slot for the library playability report.

The walk runs only when the owner refreshes Settings → Playback. This task
stays registered so an older install can be turned off, and it does not walk
the library on startup, on a timer, or when Settings is opened.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.engine.playability import TASK_NAME
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

INTERVAL_SECONDS = 12 * 60 * 60
TIMEOUT_SECONDS = 30 * 60


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    # The owner starts this from Settings. A schedule, a startup, and a library
    # scan must not walk the library.
    return {"status": "skipped", "processed": 0, "has_more": False}


def register(scheduler: IdleScheduler) -> None:
    run.data_dir = scheduler._data_dir  # type: ignore[attr-defined]
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=False,
            timeout_seconds=TIMEOUT_SECONDS,
            run_fn=run,
            off_loop=True,
            description=(
                "Records which tier would play each title. It runs only when the "
                "owner refreshes Settings → Playback. It does not start on a timer, "
                "at startup, or when the library is scanned, and it does not transcode."
            ),
        )
    )
    # An install that already stored this task as enabled keeps that row.
    # Turn it off on startup so the timer cannot walk the library.
    scheduler.update_task(TASK_NAME, enabled=False)
