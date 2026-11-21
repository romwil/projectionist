"""Jobs-engine task: dry-run the playback planner across the library.

The report records which tier would play each title. It does not transcode,
remux, or extract captions. Cached probes from the media source are enough.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.engine.playability import TASK_NAME, run_library_report
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 12 * 60 * 60
TIMEOUT_SECONDS = 30 * 60


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Page-view tests must not open Plex or walk the library from this task.
        return {"status": "skipped", "processed": 0, "has_more": False}
    from projectionist.engine.routes import describe_title
    from projectionist.logging_config import resolve_data_dir

    data_dir = getattr(run, "data_dir", None) or resolve_data_dir()

    def locate(rating_key: str):
        return describe_title(settings, db, data_dir, rating_key)

    report = run_library_report(
        db,
        settings,
        data_dir,
        locate=locate,
        should_stop=should_stop,
    )
    count = int(report.get("title_count") or 0)
    logger.info(
        "Playability report titles=%s complete=%s",
        count,
        report.get("complete"),
    )
    return {
        "status": "completed" if report.get("complete") else "interrupted",
        "processed": count,
        "has_more": not bool(report.get("complete")),
    }


def register(scheduler: IdleScheduler) -> None:
    run.data_dir = scheduler._data_dir  # type: ignore[attr-defined]
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            timeout_seconds=TIMEOUT_SECONDS,
            run_fn=run,
            off_loop=True,
            description=(
                "Walks the library and records which tier would play each title: "
                "serve the file, remux, audio-only, captions that are not ready yet, "
                "picture captions, ask the media source to transcode, or not playable "
                "through the engine. It uses the cached probe and does not transcode."
            ),
        )
    )
