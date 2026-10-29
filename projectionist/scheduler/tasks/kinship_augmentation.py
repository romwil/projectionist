"""Kinship-miss closed-loop helper for IdleScheduler enrichment tasks.

Wave 4: enrichment jobs consume ``telemetry_events`` (``kinship_miss`` /
``preferred_item_ids``) via ``BaseAugmentationTask``. High-hit demand that
still needs this task's work is staged for Admin visibility. Writers stay in
each task's ``run()`` — ``enable_direct_commit`` stays off (P1 never
auto-commits; P2/P3 wait for a proven opt-in).

The 1.37.57 miss queue is unchanged; this only reads it.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.scheduler.tasks.base_augmentation import (
    STAGE_CONFIDENCE_FLOOR,
    BaseAugmentationTask,
)
from projectionist.telemetry.kinship_miss import EVENT_KINSHIP_MISS

MIN_HIT_COUNT_STAGE = 2
DEFAULT_SIGNAL_LIMIT = 50


def confidence_for_demand_hits(hit_count: int) -> float:
    """Map demand hits to a stageable confidence (never forces commit_direct)."""
    hits = max(0, int(hit_count))
    if hits < MIN_HIT_COUNT_STAGE:
        return 0.0
    # 2→0.60, 5→0.72, 10→0.89 — capped below auto-commit floor.
    score = 0.52 + (hits * 0.04)
    return min(0.89, max(0.60, score))


def parse_signal_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def item_id_from_signal(signal: Dict[str, Any]) -> Optional[int]:
    raw = str(signal.get("entity_key") or "").strip()
    try:
        item_id = int(raw)
    except (TypeError, ValueError):
        return None
    return item_id if item_id > 0 else None


def with_stage_stats(result: Dict[str, Any], stats: Dict[str, int]) -> Dict[str, Any]:
    """Attach closed-loop stage counters without clobbering task-specific keys."""
    out = dict(result)
    out["staged"] = int(stats.get("staged") or 0)
    out["stage_direct_commits"] = int(stats.get("direct_commits") or 0)
    for key, value in stats.items():
        out[f"stage_{key}"] = value
    return out


class KinshipMissAugmentationTask(BaseAugmentationTask):
    """P2 enrichment that reads kinship-miss signals as ``preferred_item_ids``.

    Subclasses set ``action`` and override ``item_still_needs``. Set
    ``stage_when_needed = False`` for full-pass jobs that consume demand for
    ordering only (do not flood ``staged_augmentations``).
    """

    enable_direct_commit = False
    action: str = "enrich"
    stage_when_needed: bool = True

    def __init__(
        self,
        db: Database,
        task_name: str,
        *,
        min_hit_count: int = MIN_HIT_COUNT_STAGE,
        limit: int = DEFAULT_SIGNAL_LIMIT,
        target_priority: str = "P2",
    ) -> None:
        super().__init__(db, task_name=task_name, target_priority=target_priority)
        self.min_hit_count = max(1, int(min_hit_count))
        self.limit = max(1, min(int(limit), 1000))

    def item_still_needs(self, item_id: int) -> bool:
        """Return True when this task still has work for ``item_id``."""
        del item_id
        return True

    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        return await run_db(
            self.db.list_closed_loop_events,
            event_type=EVENT_KINSHIP_MISS,
            entity_type="title",
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
        for row in pending:
            if str(row.get("target_entity_type") or "").casefold() != "title":
                continue
            if str(row.get("target_entity_id") or "").casefold() == key:
                return True
        return False

    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.stage_when_needed:
            return None
        item_id = item_id_from_signal(signal)
        if item_id is None:
            return None
        entity_key = str(item_id)
        if await self._already_staged(entity_key):
            return None
        needs = await run_db(self.item_still_needs, item_id)
        if not needs:
            return None

        hit_count = int(signal.get("hit_count") or 0)
        confidence = confidence_for_demand_hits(hit_count)
        if confidence < STAGE_CONFIDENCE_FLOOR:
            return None

        payload = parse_signal_payload(signal.get("payload_json"))
        candidate = {
            "item_id": item_id,
            "hit_count": hit_count,
            "reason": payload.get("reason") or "kinship_miss",
            "context_source": payload.get("context_source") or "discovery",
            "action": self.action,
        }
        return {
            "target_entity_type": "title",
            "target_entity_id": entity_key,
            "candidate_data": candidate,
            "confidence": confidence,
        }


async def stage_kinship_demand(
    task: KinshipMissAugmentationTask,
    should_stop: Callable[[], bool],
) -> tuple[Dict[str, int], Optional[str]]:
    """Run the closed-loop stage pass. Returns ``(stats, interrupt_status)``."""
    empty = {"processed": 0, "direct_commits": 0, "staged": 0, "errors": 0, "skipped": 0}
    if should_stop():
        return empty, "interrupted"
    stats = await task.execute_run()
    if should_stop():
        return stats, "interrupted"
    return stats, None
