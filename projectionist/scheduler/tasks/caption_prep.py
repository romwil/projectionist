"""Jobs-engine task: turn embedded text captions into WebVTT before Play.

Picture captions are marked and skipped. A title that is not ready yet stays
on the queue so the next play can use the file. The play request itself does
not wait on this work.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.engine.caption_prep import TASK_NAME, drain_caption_queue
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 30 * 60
CATCHUP_GAP_SECONDS = 60
BATCH_SIZE = 1
# One large file may take the extract limit. Leave a minute of slack.
TIMEOUT_SECONDS = 16 * 60


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        # Page-view tests must not open Plex or ffmpeg from this task.
        return {"status": "skipped", "processed": 0, "has_more": False, "batch_size": BATCH_SIZE}
    from projectionist.logging_config import resolve_data_dir

    data_dir = getattr(run, "data_dir", None) or resolve_data_dir()
    # New arrivals are queued by the library scan. This task only drains, so a
    # scan cannot refill a 200-deep backlog ahead of the title being watched.

    def locate(rating_key: str):
        from projectionist.engine.routes import describe_title

        return describe_title(settings, db, data_dir, rating_key, background=True)

    if should_stop():
        return {"status": "interrupted", "processed": 0, "has_more": True, "batch_size": BATCH_SIZE}
    result = drain_caption_queue(
        data_dir=data_dir,
        locate=locate,
        should_stop=should_stop,
        limit=BATCH_SIZE,
    )
    logger.info(
        "Caption prep processed=%s has_more=%s",
        result.get("processed"),
        result.get("has_more"),
    )
    return result


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
                "Extracts text captions to WebVTT before Play, so a large subtitle "
                "track is ready when a session opens. Picture captions are left for "
                "later. One title at a time. The queue is new arrivals, Continue "
                "Watching, For you, and the title page. A library scan does not "
                "enqueue the whole library. The title being played goes first."
            ),
            items_per_cycle=BATCH_SIZE,
            catchup_gap_seconds=CATCHUP_GAP_SECONDS,
        )
    )
