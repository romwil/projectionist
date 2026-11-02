"""Idle task: write an on-box household snapshot (PERF-002, OPS-009).

Writes ``DATA_DIR/backups/projectionist-auto-<stamp>.zip`` (settings.json plus a
WAL-safe SQLite copy) and keeps the newest ``DEFAULT_KEEP``. Nothing leaves the
box. Restore is ``python -m projectionist.backups restore`` with the server stopped.

Default interval: 24 hours.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict

from projectionist.backups import DEFAULT_KEEP, create_snapshot_file, prune_snapshots
from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400


async def run(db: Database, settings: Settings, should_stop: Callable[[], bool]) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted"}
    data_dir = Path(db.path).parent
    path = create_snapshot_file(data_dir)
    removed = prune_snapshots(data_dir, keep=DEFAULT_KEEP)
    logger.info("Household backup written: %s (pruned %d)", path.name, len(removed))
    return {"status": "completed", "file": path.name, "pruned": len(removed)}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="household_backup",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            off_loop=True,
            run_fn=run,
            description=(
                "Writes a daily snapshot of settings and the database under "
                "DATA_DIR/backups and keeps the newest seven. Nothing is uploaded."
            ),
        )
    )
