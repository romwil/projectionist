"""P1 FacetTaxonomyAudit — stage unmapped facet tokens for Admin promote.

Consumes closed-loop ``telemetry_events`` with
``event_type=unmapped_token`` / ``entity_type=facet``. Never auto-commits into
the packaged taxonomy seed; high confidence still stages only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.facets.registry import get_registry
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import (
    BaseAugmentationTask,
    register_severity_task,
)

logger = logging.getLogger(__name__)

TASK_NAME = "facet_taxonomy_audit"
MIN_HIT_COUNT = 3
DEFAULT_LIMIT = 100


def confidence_for_hit_count(hit_count: int) -> float:
    """Map aggregated miss hits to a stageable confidence (always < 0.90)."""
    hits = max(0, int(hit_count))
    if hits < MIN_HIT_COUNT:
        return 0.0
    # 3→0.60, 5→0.70, 10→0.85, capped below direct-commit floor.
    score = 0.50 + (hits * 0.04)
    return min(0.89, max(0.60, score))


def suggest_concept_for_token(token: str) -> Dict[str, str]:
    """Soft-suggest an existing concept by unique substring on labels/names."""
    wanted = str(token or "").strip()
    if not wanted:
        return {}
    lookup = wanted.casefold()
    reg = get_registry()
    hits: List[tuple[str, str]] = []  # (concept_id, primary_name)
    for concept in reg.concepts.values():
        labels = [concept.id, concept.label, *concept.names]
        for label in labels:
            label_cf = str(label or "").casefold()
            if not label_cf:
                continue
            if lookup == label_cf or lookup in label_cf or label_cf in lookup:
                primary = concept.names[0] if concept.names else (concept.label or concept.id)
                hits.append((concept.id, primary))
                break
    # Deduplicate by concept id.
    uniq: Dict[str, str] = {}
    for cid, name in hits:
        uniq.setdefault(cid, name)
    if len(uniq) != 1:
        return {}
    concept_id, primary = next(iter(uniq.items()))
    return {
        "suggested_concept_id": concept_id,
        "suggested_canonical_name": primary,
    }


class FacetTaxonomyAudit(BaseAugmentationTask):
    """P1 specialization: unmapped facet tokens → staged_augmentations only."""

    enable_direct_commit = False

    def __init__(
        self,
        db: Database,
        *,
        min_hit_count: int = MIN_HIT_COUNT,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        super().__init__(db, task_name=TASK_NAME, target_priority="P1")
        self.min_hit_count = max(1, int(min_hit_count))
        self.limit = max(1, min(int(limit), 1000))

    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        return await run_db(
            self.db.list_closed_loop_events,
            event_type="unmapped_token",
            entity_type="facet",
            priority_tier="P1",
            min_hit_count=self.min_hit_count,
            limit=self.limit,
        )

    async def _already_staged(self, entity_key: str) -> bool:
        pending = await run_db(
            self.db.list_staged_augmentations,
            status="pending",
            task_name=self.task_name,
            limit=500,
        )
        key = entity_key.casefold()
        return any(str(row.get("target_entity_id") or "").casefold() == key for row in pending)

    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entity_key = str(signal.get("entity_key") or "").strip()
        if not entity_key:
            return None
        if await self._already_staged(entity_key):
            return None

        hit_count = int(signal.get("hit_count") or 0)
        confidence = confidence_for_hit_count(hit_count)
        if confidence < 0.60:
            return None

        payload_raw = signal.get("payload_json")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        suggestion = suggest_concept_for_token(entity_key)
        candidate = {
            "alias": entity_key,
            "hit_count": hit_count,
            "context_source": payload.get("context_source") or "resolve",
            "media_type": payload.get("media_type"),
            "raw": payload.get("raw") or entity_key,
            **suggestion,
        }
        return {
            "target_entity_type": "facet",
            "target_entity_id": entity_key,
            "candidate_data": candidate,
            "confidence": confidence,
        }


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted", "processed": 0, "staged": 0}
    task = FacetTaxonomyAudit(db)
    stats = await task.execute_run()
    logger.info(
        "facet_taxonomy_audit: processed=%s staged=%s skipped=%s errors=%s",
        stats.get("processed"),
        stats.get("staged"),
        stats.get("skipped"),
        stats.get("errors"),
    )
    return {"status": "completed", **stats}


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P1",
        run_fn=run,
        description=(
            "Finds frequently used genre or tag names the library does not recognize "
            "and queues suggested mappings for owner review. Saving a mapping affects "
            "only this installation; built-in definitions stay unchanged."
        ),
    )
