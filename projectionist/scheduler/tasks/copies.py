"""Overnight copies made ahead of time (ENG-014).

One encode at a time, from 01:00 to 06:00 household time, and only after the
owner has chosen a folder. Tests do not start an encode.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

TASK_NAME = "ahead_of_time_copies"
INTERVAL_SECONDS = 15 * 60
TIMEOUT_SECONDS = 5 * 60 * 60


async def run(db: Database, settings: Settings, should_stop: Callable[[], bool]) -> Dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {"status": "skipped", "processed": 0, "has_more": False}
    if should_stop():
        return {"status": "interrupted", "processed": 0, "has_more": False}
    folder = str(getattr(getattr(settings, "engine", None), "copy_output_dir", "") or "").strip()
    if not folder:
        return {"status": "skipped", "processed": 0, "has_more": False}
    now = datetime.now().astimezone()
    from projectionist.engine.copies import in_copy_window, run_copy_pass

    if not in_copy_window(now):
        return {"status": "asleep", "processed": 0, "has_more": False}
    from projectionist.logging_config import resolve_data_dir

    data_dir = Path(getattr(run, "data_dir", None) or resolve_data_dir())
    from projectionist.engine.playability import load_playability_report

    report = load_playability_report(data_dir)
    ahead = report.get("copy_ahead") if isinstance(report, dict) else None
    titles = ahead.get("titles") if isinstance(ahead, dict) else []
    from projectionist.engine.copies import apply_copy_requests, load_copy_requests

    titles = apply_copy_requests(list(titles or []), load_copy_requests(data_dir))

    def source_for(rating_key: str) -> Path:
        from projectionist.engine.routes import describe_title

        asset = describe_title(settings, db, data_dir, rating_key, background=True)
        path = str(getattr(asset, "local_path", "") or "")
        if not path:
            raise FileNotFoundError(rating_key)
        return Path(path)

    def runner(command: list[str], destination: Path) -> str:
        from projectionist.engine.media_slot import run_prepared_command

        def _run(cmd: list[str]) -> int:
            completed = subprocess.run(cmd, check=False)
            return int(completed.returncode)

        code = run_prepared_command(command, _run)
        if code == 0 and destination.is_file() and destination.stat().st_size > 0:
            return "complete"
        return "partial"

    result = run_copy_pass(
        list(titles or []),
        Path(folder),
        budget_bytes=int(settings.engine.copy_budget_bytes),
        now=now,
        runner=runner,
        source_for=source_for,
    )
    worked = bool(result.get("rating_key"))
    return {
        "status": str(result.get("status") or "idle"),
        "processed": 1 if worked else 0,
        "has_more": str(result.get("status") or "") in {"ready", "partial"},
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
                "Makes a compatible copy of titles the playability report would "
                "ask the media source to transcode. Above 1080p first, then the "
                "most-watched, until the owner's disk budget. One encode at a time, "
                "from 1:00 a.m. to 6:00 a.m. A partial file is not played."
            ),
            items_per_cycle=1,
        )
    )
