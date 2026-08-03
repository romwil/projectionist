"""P1/P2 CoverageDeficitAudit — stage high-hit coverage gaps for Admin visibility.

Consumes ``telemetry_events`` with ``event_type=coverage_deficit``. Never
auto-commits enrichment — stages for owner review. Approve runs targeted
enrichment (or queues theme tagging for unmapped keywords); reject clears
without side effects.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import (
    BaseAugmentationTask,
    register_severity_task,
)
from projectionist.telemetry.coverage import EVENT_COVERAGE_DEFICIT

logger = logging.getLogger(__name__)

TASK_NAME = "coverage_deficit_audit"
MIN_HIT_COUNT = 2
DEFAULT_LIMIT = 100


def confidence_for_coverage_hits(hit_count: int) -> float:
    hits = max(0, int(hit_count))
    if hits < MIN_HIT_COUNT:
        return 0.0
    score = 0.52 + (hits * 0.04)
    return min(0.89, max(0.60, score))


class CoverageDeficitAudit(BaseAugmentationTask):
    """Stage high-hit coverage deficits (themes, motifs, metadata, etc.)."""

    enable_direct_commit = False

    def __init__(
        self,
        db: Database,
        *,
        min_hit_count: int = MIN_HIT_COUNT,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        super().__init__(db, task_name=TASK_NAME, target_priority="P2")
        self.min_hit_count = max(1, int(min_hit_count))
        self.limit = max(1, min(int(limit), 1000))

    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        return await run_db(
            self.db.list_closed_loop_events,
            event_type=EVENT_COVERAGE_DEFICIT,
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
        if not entity_key or not entity_type:
            return None
        if await self._already_staged(entity_type, entity_key):
            return None

        hit_count = int(signal.get("hit_count") or 0)
        confidence = confidence_for_coverage_hits(hit_count)
        if confidence < 0.60:
            return None

        payload_raw = signal.get("payload_json")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        deficit_kind = str(payload.get("deficit_kind") or "unknown")
        candidate = {
            "deficit_kind": deficit_kind,
            "hit_count": hit_count,
            "context_source": payload.get("context_source") or "idle_task",
            "entity_key": entity_key,
            **{k: v for k, v in payload.items() if k not in {"deficit_kind", "context_source"}},
        }
        return {
            "target_entity_type": entity_type,
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
    task = CoverageDeficitAudit(db)
    stats = await task.execute_run()
    logger.info(
        "coverage_deficit_audit: processed=%s staged=%s skipped=%s errors=%s",
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
        priority="P2",
        run_fn=run,
        description=(
            "P2 coverage audit: aggregates coverage_deficit telemetry (themes, "
            "motifs, synopsis, embeddings, metadata) and stages high-hit gaps "
            "for Admin Knowledge Ops visibility — never auto-writes enrichment."
        ),
    )
