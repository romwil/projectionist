"""P1/P2 CoverageDeficitAudit — stage real coverage exceptions for Admin visibility.

Consumes ``telemetry_events`` with ``event_type=coverage_deficit``. Never
auto-commits enrichment — stages for owner review. Approve runs targeted
enrichment (or queues theme tagging for unmapped keywords); reject clears
without side effects.

**What is an exception.** Missing plot / TMDB metadata / embeddings is *backlog*
that the scheduled retrieval tasks fill on their own (with backoff and batch
caps — see :mod:`projectionist.library.knowledge_fetch`). Those kinds are staged
here only after automatic retrieval was tried and **exhausted**; a stale
telemetry event for a gap that is merely "not fetched yet" (or already filled)
is ignored, and any such row left over from older versions is resolved on the
next run. Unrecognised theme keywords stay as before: they need a human mapping.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.library.knowledge_fetch import (
    AUTO_RETRIEVED_KINDS,
    gap_is_open,
    get_state,
    list_exhausted,
)
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
#: Confidence for a retrieval that was tried, retried with backoff, and gave up.
EXHAUSTED_CONFIDENCE = 0.75
#: Deficit kinds that are never owner exceptions (derived locally, nothing to fetch).
NON_EXCEPTION_KINDS = frozenset({"motif"})
#: Staged status for rows made obsolete because the gap closed or was never a failure.
STATUS_RESOLVED = "resolved"


def _candidate_of(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        data = json.loads(row.get("candidate_data_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _item_id_of(entity_type: str, entity_key: Any) -> Optional[int]:
    if str(entity_type or "").casefold() != "library_item":
        return None
    try:
        return int(entity_key)
    except (TypeError, ValueError):
        return None


def _row_epoch(value: Any) -> float:
    """Parse a SQLite ``CURRENT_TIMESTAMP`` (UTC) into epoch seconds (0 on failure)."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except (TypeError, ValueError):
        return 0.0


def owner_already_answered(
    db: Database, item_id: int, kind: str, last_failure_at: float
) -> bool:
    """True when the owner approved/dismissed this exception after its latest failure.

    Keeps a retried-but-still-failing (or dismissed) title from re-appearing
    until retrieval fails again.
    """
    for status in ("approved", "rejected"):
        for row in db.list_staged_augmentations(
            status=status, task_name=TASK_NAME, limit=1000
        ):
            if str(row.get("target_entity_id") or "") != str(item_id):
                continue
            if str(_candidate_of(row).get("deficit_kind") or "") != kind:
                continue
            if _row_epoch(row.get("updated_at")) + 2 >= float(last_failure_at or 0):
                return True
    return False


def resolve_non_exceptions(db: Database) -> int:
    """Mark pending rows resolved when they are no longer real exceptions.

    A pending ``synopsis`` / ``metadata`` / ``embedding`` row stays only while
    automatic retrieval is exhausted *and* the gap is still open. Everything else
    (never failed, since filled, or a derived motif gap) was just backlog.
    """
    resolved = 0
    pending = db.list_staged_augmentations(
        status="pending", task_name=TASK_NAME, limit=1000
    )
    for row in pending:
        candidate = _candidate_of(row)
        kind = str(candidate.get("deficit_kind") or "")
        if kind not in AUTO_RETRIEVED_KINDS and kind not in NON_EXCEPTION_KINDS:
            continue
        keep = False
        item_id = _item_id_of(row.get("target_entity_type"), row.get("target_entity_id"))
        if kind in AUTO_RETRIEVED_KINDS and item_id is not None:
            state = get_state(db, item_id, kind)
            keep = bool(state and state.get("exhausted")) and gap_is_open(db, kind, item_id)
        if keep:
            continue
        candidate["resolved_reason"] = (
            "filled_automatically" if kind in AUTO_RETRIEVED_KINDS else "not_an_exception"
        )
        db.update_staged_augmentation_status(
            int(row["id"]),
            status=STATUS_RESOLVED,
            candidate_data_json=json.dumps(candidate, default=str, separators=(",", ":")),
        )
        resolved += 1
    return resolved


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
        events = await run_db(
            self.db.list_closed_loop_events,
            event_type=EVENT_COVERAGE_DEFICIT,
            min_hit_count=self.min_hit_count,
            limit=self.limit,
        )
        # Exhausted retrievals are exceptions on their own: they do not need to
        # be observed twice, so read them straight from the retry ledger.
        exhausted = await run_db(list_exhausted, self.db, None, limit=self.limit)
        for row in exhausted:
            payload = {
                "deficit_kind": row["kind"],
                "context_source": "knowledge_retrieval",
                "title": row.get("title"),
                "item_id": row["item_id"],
                "tmdb_id": row.get("tmdb_id"),
                "attempts": row.get("attempts"),
                "failure": row.get("last_outcome"),
                "failure_detail": row.get("last_detail"),
                "retrieval_exhausted": True,
            }
            # Same entity may be exhausted for more than one kind; keep each.
            events.append(
                {
                    "entity_type": "library_item",
                    "entity_key": str(row["item_id"]),
                    "hit_count": int(row.get("attempts") or 1),
                    "payload_json": json.dumps(payload, default=str),
                }
            )
        return events

    async def _already_staged(
        self, entity_type: str, entity_key: str, deficit_kind: str = ""
    ) -> bool:
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
            if str(row.get("target_entity_id") or "").casefold() != key:
                continue
            staged_kind = str(_candidate_of(row).get("deficit_kind") or "")
            if deficit_kind and staged_kind and staged_kind != deficit_kind:
                continue
            return True
        return False

    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entity_key = str(signal.get("entity_key") or "").strip()
        entity_type = str(signal.get("entity_type") or "").strip().lower()
        if not entity_key or not entity_type:
            return None

        hit_count = int(signal.get("hit_count") or 0)
        payload_raw = signal.get("payload_json")
        try:
            payload = json.loads(payload_raw) if payload_raw else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        deficit_kind = str(payload.get("deficit_kind") or "unknown")
        if deficit_kind in NON_EXCEPTION_KINDS:
            return None

        if deficit_kind in AUTO_RETRIEVED_KINDS:
            # Missing-but-fetchable knowledge is backlog. Only a retrieval that was
            # tried and exhausted, for a gap that is still open, is an exception.
            item_id = _item_id_of(entity_type, entity_key)
            if item_id is None:
                return None
            state = await run_db(get_state, self.db, item_id, deficit_kind)
            if not state or not state.get("exhausted"):
                return None
            if not await run_db(gap_is_open, self.db, deficit_kind, item_id):
                return None
            if await run_db(
                owner_already_answered,
                self.db,
                item_id,
                deficit_kind,
                float(state.get("last_attempt_at") or 0),
            ):
                return None
            confidence = EXHAUSTED_CONFIDENCE
            hit_count = max(hit_count, int(state.get("attempts") or 1))
            payload = {
                **payload,
                "attempts": state.get("attempts"),
                "failure": state.get("last_outcome"),
                "failure_detail": state.get("last_detail"),
                "retrieval_exhausted": True,
            }
        else:
            confidence = confidence_for_coverage_hits(hit_count)
            if confidence < 0.60:
                return None

        if await self._already_staged(entity_type, entity_key, deficit_kind):
            return None

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
    # Drop leftovers that were only ever "not fetched yet" (or are now filled).
    resolved = await run_db(resolve_non_exceptions, db)
    task = CoverageDeficitAudit(db)
    stats = await task.execute_run()
    logger.info(
        "coverage_deficit_audit: processed=%s staged=%s skipped=%s errors=%s resolved=%s",
        stats.get("processed"),
        stats.get("staged"),
        stats.get("skipped"),
        stats.get("errors"),
        resolved,
    )
    return {"status": "completed", "resolved": resolved, **stats}


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P2",
        run_fn=run,
        description=(
            "Surfaces knowledge gaps that need a person: unmapped theme keywords, and "
            "plot or title details that automatic retrieval tried and could not find. "
            "Gaps that are simply not fetched yet are filled by the scheduled tasks and "
            "never listed. It never changes built-in knowledge automatically."
        ),
    )
