"""Idle trickle: rebuild ``title_relations`` from DB (Stage 4 v1).

No LLM required. Collection edges come from ``tmdb_collection_id``;
optional mirrors pull ``item_neighbors`` and shared Directing/Writing credits.

Default interval: 12 hours.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.relations import refresh_title_relations
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import register_severity_task
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    stage_kinship_demand,
    with_stage_stats,
)

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
TASK_NAME = "title_relations_refresh"


class TitleRelationsAugmentation(KinshipMissAugmentationTask):
    """Stage kinship-miss titles that still have no outgoing title_relations."""

    action = "refresh_title_relations"

    def __init__(self, db: Database) -> None:
        super().__init__(db, task_name=TASK_NAME)

    def item_still_needs(self, item_id: int) -> bool:
        with self.db.connect() as conn:
            item = conn.execute(
                "SELECT 1 FROM library_items WHERE id = ?",
                (int(item_id),),
            ).fetchone()
            if item is None:
                return False
            rel = conn.execute(
                "SELECT 1 FROM title_relations WHERE from_id = ? LIMIT 1",
                (int(item_id),),
            ).fetchone()
        return rel is None


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    augmenter = TitleRelationsAugmentation(db)
    stage_stats, interrupted = await stage_kinship_demand(augmenter, should_stop)
    if interrupted:
        return with_stage_stats({"status": "interrupted", "total": 0}, stage_stats)

    counts = refresh_title_relations(
        db,
        include_neighbors=True,
        include_shared_crew=True,
    )
    if should_stop():
        return with_stage_stats({"status": "interrupted", **counts}, stage_stats)

    logger.info(
        "Title relations refresh: collection=%s neighbor=%s shared_crew=%s total=%s",
        counts["collection"],
        counts["neighbor"],
        counts["shared_crew"],
        counts["total"],
    )
    return with_stage_stats({"status": "completed", **counts}, stage_stats)


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P2",
        run_fn=run,
        run_interval_seconds=INTERVAL_SECONDS,
        enabled=True,
        off_loop=True,
        description=(
            "Refreshes title connections from collections, similar plots, and shared "
            "cast or crew already present in the library. Rebuilds the complete "
            "connection set each run."
        ),
    )
