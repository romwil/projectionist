"""Idle trickle: rebuild ``title_relations`` from DB (Stage 4 v1).

No LLM required. Collection edges come from ``tmdb_collection_id``;
optional mirrors pull ``item_neighbors`` and shared Directing/Writing credits.

Default interval: 12 hours.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.relations import refresh_title_relations
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted", "total": 0}

    counts = refresh_title_relations(
        db,
        include_neighbors=True,
        include_shared_crew=True,
    )
    if should_stop():
        return {"status": "interrupted", **counts}

    logger.info(
        "Title relations refresh: collection=%s neighbor=%s shared_crew=%s total=%s",
        counts["collection"],
        counts["neighbor"],
        counts["shared_crew"],
        counts["total"],
    )
    return {"status": "completed", **counts}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="title_relations_refresh",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
        )
    )
