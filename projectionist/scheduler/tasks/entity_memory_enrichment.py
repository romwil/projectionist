"""Idle, low-volume refresh of public repository-memory research snapshots.

Phase C P2 pilot: consume ``telemetry_events`` with
``event_type=metadata_demand`` to prioritize enrichment, and stage high-hit
demand rows via ``BaseAugmentationTask`` for Admin visibility. Taxonomy / P1
auto-commit remains disabled. Direct research writes use the existing
idempotent ``research_*`` helpers (not confidence-gated ``commit_direct``).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.research.title_research import research_company, research_person, research_title
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import (
    BaseAugmentationTask,
    register_severity_task,
)
from projectionist.telemetry.demand import EVENT_METADATA_DEMAND

logger = logging.getLogger(__name__)

TASK_NAME = "entity_memory_enrichment"
INTERVAL_SECONDS = 86400
STALE_AFTER_SECONDS = 30 * 86400
DEFAULT_BATCH_SIZE = 5
MIN_HIT_COUNT_STAGE = 2
DEFAULT_SIGNAL_LIMIT = 50


def confidence_for_demand_hits(hit_count: int) -> float:
    """Map demand hits to a stageable confidence (never forces commit_direct)."""
    hits = max(0, int(hit_count))
    if hits < MIN_HIT_COUNT_STAGE:
        return 0.0
    # 2→0.60, 5→0.72, 10→0.89 — capped below auto-commit floor for clarity.
    score = 0.52 + (hits * 0.04)
    return min(0.89, max(0.60, score))


def _parse_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _entity_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(record.get("entity_id") or ""),
        "entity_type": str(record.get("entity_type") or ""),
        "name": str(record.get("name") or ""),
        "external_ids": (
            dict(record["external_ids"])
            if isinstance(record.get("external_ids"), dict)
            else {}
        ),
        "last_fetched_at": record.get("fetched_at"),
    }


def entities_from_demand_signals(
    db: Database,
    *,
    limit: int = DEFAULT_BATCH_SIZE,
    min_hit_count: int = 1,
) -> List[Dict[str, Any]]:
    """Resolve P2 ``metadata_demand`` signals into enrichable entity dicts.

    Prefers known repository rows (by payload name + entity_type). Unknown-name
    demand still yields a lightweight stub so ``research_*`` can create a snapshot.
    """
    capped = max(1, min(int(limit), 50))
    signals = db.list_closed_loop_events(
        event_type=EVENT_METADATA_DEMAND,
        priority_tier="P2",
        min_hit_count=max(1, int(min_hit_count)),
        limit=DEFAULT_SIGNAL_LIMIT,
    )
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for signal in signals:
        if len(out) >= capped:
            break
        entity_type = str(signal.get("entity_type") or "").strip().lower()
        if entity_type not in {"title", "person", "company"}:
            continue
        payload = _parse_payload(signal.get("payload_json"))
        name = str(payload.get("name") or signal.get("entity_key") or "").strip()
        if not name:
            continue
        dedupe = f"{entity_type}:{name.casefold()}"
        if dedupe in seen:
            continue
        seen.add(dedupe)

        record = db.get_repository_entity(name, entity_type)
        if record:
            out.append(_entity_from_record(record))
            continue
        # Unknown entity demand — research by name (optional tmdb_id in payload).
        external_ids: Dict[str, Any] = {}
        raw_tmdb = payload.get("tmdb_id")
        if raw_tmdb is not None:
            try:
                external_ids["tmdb_id"] = int(raw_tmdb)
            except (TypeError, ValueError):
                pass
        out.append(
            {
                "id": str(payload.get("entity_id") or ""),
                "entity_type": entity_type,
                "name": name,
                "external_ids": external_ids,
                "last_fetched_at": None,
                "from_demand_stub": True,
            }
        )
    return out


class EntityMemoryDemandPilot(BaseAugmentationTask):
    """P2 specialization: stage high-hit metadata demand (never auto-commits)."""

    enable_direct_commit = False

    def __init__(
        self,
        db: Database,
        *,
        min_hit_count: int = MIN_HIT_COUNT_STAGE,
        limit: int = DEFAULT_SIGNAL_LIMIT,
    ) -> None:
        super().__init__(db, task_name=TASK_NAME, target_priority="P2")
        self.min_hit_count = max(1, int(min_hit_count))
        self.limit = max(1, min(int(limit), 1000))

    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        return await run_db(
            self.db.list_closed_loop_events,
            event_type=EVENT_METADATA_DEMAND,
            priority_tier="P2",
            min_hit_count=self.min_hit_count,
            limit=self.limit,
        )

    async def _already_staged(self, entity_type: str, entity_key: str) -> bool:
        pending = await run_db(
            self.db.list_staged_augmentations,
            status="pending",
            task_name=self.task_name,
            limit=500,
        )
        key = entity_key.casefold()
        kind = entity_type.casefold()
        for row in pending:
            if str(row.get("target_entity_type") or "").casefold() != kind:
                continue
            if str(row.get("target_entity_id") or "").casefold() == key:
                return True
        return False

    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entity_key = str(signal.get("entity_key") or "").strip()
        entity_type = str(signal.get("entity_type") or "").strip().lower()
        if not entity_key or entity_type not in {"title", "person", "company"}:
            return None
        if await self._already_staged(entity_type, entity_key):
            return None

        hit_count = int(signal.get("hit_count") or 0)
        confidence = confidence_for_demand_hits(hit_count)
        if confidence < 0.60:
            return None

        payload = _parse_payload(signal.get("payload_json"))
        name = str(payload.get("name") or entity_key).strip()
        candidate = {
            "name": name,
            "entity_type": entity_type,
            "hit_count": hit_count,
            "reason": payload.get("reason") or "sparse_or_stale",
            "context_source": payload.get("context_source") or "recall",
            "entity_id": payload.get("entity_id"),
            "action": "refresh_repository_research",
        }
        return {
            "target_entity_type": entity_type,
            "target_entity_id": entity_key,
            "candidate_data": candidate,
            "confidence": confidence,
        }


def _merge_entity_batches(
    preferred: List[Dict[str, Any]],
    fallback: List[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for entity in [*preferred, *fallback]:
        if len(merged) >= limit:
            break
        name = str(entity.get("name") or "").strip()
        kind = str(entity.get("entity_type") or "").strip().lower()
        if not name or not kind:
            continue
        key = f"{kind}:{name.casefold()}"
        if key in seen:
            continue
        seen.add(key)
        merged.append(entity)
    return merged


def _enrich_entity(settings: Settings, db: Database, entity: Dict[str, Any]) -> bool:
    """Run the existing safe research writer for one entity. Returns True if attempted."""
    tmdb_id = entity.get("external_ids", {}).get("tmdb_id") if isinstance(
        entity.get("external_ids"), dict
    ) else None
    try:
        tmdb_id = int(tmdb_id) if tmdb_id is not None else None
    except (TypeError, ValueError):
        tmdb_id = None
    entity_type = str(entity.get("entity_type") or "")
    name = str(entity.get("name") or "").strip()
    if not name:
        return False
    if entity_type == "person":
        research_person(settings, name=name, tmdb_id=tmdb_id, db=db)
        return True
    if entity_type == "company" and tmdb_id:
        research_company(settings, name=name, tmdb_id=tmdb_id, db=db)
        return True
    if entity_type == "title":
        research_title(settings, title=name, tmdb_id=tmdb_id, db=db)
        return True
    return False


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Stage demand signals, then refresh a tiny demand-first entity batch."""
    if should_stop():
        return {"status": "interrupted", "enriched": 0, "staged": 0}

    pilot = EntityMemoryDemandPilot(db)
    stage_stats = await pilot.execute_run()
    if should_stop():
        return {
            "status": "interrupted",
            "enriched": 0,
            "staged": stage_stats.get("staged", 0),
            **{f"stage_{k}": v for k, v in stage_stats.items()},
        }

    if not (settings.tmdb_api_key or "").strip():
        return {
            "status": "skipped",
            "reason": "no_tmdb_api_key",
            "enriched": 0,
            "staged": stage_stats.get("staged", 0),
            **{f"stage_{k}": v for k, v in stage_stats.items()},
        }

    demand_entities = entities_from_demand_signals(db, limit=DEFAULT_BATCH_SIZE)
    stale_needed = max(0, DEFAULT_BATCH_SIZE - len(demand_entities))
    stale_entities: List[Dict[str, Any]] = []
    if stale_needed:
        stale_entities = db.repository_entities_due_for_enrichment(
            older_than_seconds=STALE_AFTER_SECONDS, limit=stale_needed
        )
    entities = _merge_entity_batches(
        demand_entities, stale_entities, limit=DEFAULT_BATCH_SIZE
    )

    enriched = 0
    skipped = 0
    for entity in entities:
        if should_stop():
            return {
                "status": "interrupted",
                "enriched": enriched,
                "skipped": skipped,
                "staged": stage_stats.get("staged", 0),
                "demand_prioritized": len(demand_entities),
            }
        if _enrich_entity(settings, db, entity):
            enriched += 1
        else:
            skipped += 1

    logger.info(
        "entity_memory_enrichment: enriched=%s skipped=%s staged=%s demand=%s",
        enriched,
        skipped,
        stage_stats.get("staged", 0),
        len(demand_entities),
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "skipped": skipped,
        "staged": stage_stats.get("staged", 0),
        "demand_prioritized": len(demand_entities),
        "has_more": len(entities) == DEFAULT_BATCH_SIZE,
        **{f"stage_{k}": v for k, v in stage_stats.items()},
    }


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P2",
        run_fn=run,
        run_interval_seconds=INTERVAL_SECONDS,
        description=(
            "Researches missing title, person, or studio details through trusted media "
            "sources. Frequently requested subjects move to the front of each small "
            "batch. Private member notes are never read or changed."
        ),
        items_per_cycle=DEFAULT_BATCH_SIZE,
    )
