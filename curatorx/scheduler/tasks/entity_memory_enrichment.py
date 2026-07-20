"""Idle, low-volume refresh of public repository-memory research snapshots."""

from __future__ import annotations

from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.research.title_research import research_company, research_person, research_title
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

TASK_NAME = "entity_memory_enrichment"
INTERVAL_SECONDS = 86400
STALE_AFTER_SECONDS = 30 * 86400
DEFAULT_BATCH_SIZE = 5


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Refresh a tiny stale-entity batch using only configured official providers."""
    if should_stop():
        return {"status": "interrupted", "enriched": 0}
    if not (settings.tmdb_api_key or "").strip():
        return {"status": "skipped", "reason": "no_tmdb_api_key", "enriched": 0}

    entities = db.repository_entities_due_for_enrichment(
        older_than_seconds=STALE_AFTER_SECONDS, limit=DEFAULT_BATCH_SIZE
    )
    enriched = 0
    skipped = 0
    for entity in entities:
        if should_stop():
            return {"status": "interrupted", "enriched": enriched, "skipped": skipped}
        tmdb_id = entity["external_ids"].get("tmdb_id")
        try:
            tmdb_id = int(tmdb_id) if tmdb_id is not None else None
        except (TypeError, ValueError):
            tmdb_id = None
        entity_type = entity["entity_type"]
        if entity_type == "person":
            research_person(settings, name=entity["name"], tmdb_id=tmdb_id, db=db)
        elif entity_type == "company" and tmdb_id:
            research_company(settings, name=entity["name"], tmdb_id=tmdb_id, db=db)
        elif entity_type == "title":
            research_title(settings, title=entity["name"], tmdb_id=tmdb_id, db=db)
        else:
            skipped += 1
            continue
        enriched += 1
    return {
        "status": "completed",
        "enriched": enriched,
        "skipped": skipped,
        "has_more": len(entities) == DEFAULT_BATCH_SIZE,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Refreshes a five-entity daily batch of stale, public repository research "
                "from configured official APIs. Private user memory is never read or written."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
        )
    )
