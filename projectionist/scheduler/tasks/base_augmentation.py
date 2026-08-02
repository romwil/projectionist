"""Universal base class for closed-loop IdleScheduler enrichment tasks.

See ``docs/superpowers/specs/2026-08-01-closed-loop-augmentation.md``.

Routing rules (locked amendments):

- **P1 / taxonomy:** never auto ``commit_direct``. High confidence still stages
  for Admin approve → ``DATA_DIR`` overlay.
- **P2 / P3:** ``commit_direct`` only when a subclass sets
  ``enable_direct_commit = True`` *and* implements a safe idempotent writer.
  Prefer staging until pilots prove confidence.
"""

from __future__ import annotations

import abc
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

# Severity → default IdleScheduler interval (seconds).
# P0 elevated (near-immediate relative to idle poll); P3 deep-idle only.
INTERVAL_BY_SEVERITY: Dict[str, int] = {
    "P0": 60,
    "P1": 3600,
    "P2": 7200,
    "P3": 86400,
}

STAGE_CONFIDENCE_FLOOR = 0.60
DIRECT_COMMIT_CONFIDENCE_FLOOR = 0.90


def normalize_severity(priority: str) -> str:
    """Return canonical ``P0``–``P3`` tier string (defaults to ``P3``)."""
    tier = str(priority or "").strip().upper()
    if tier in INTERVAL_BY_SEVERITY:
        return tier
    return "P3"


def interval_for_severity(priority: str) -> int:
    """Map a severity tier to a default ``run_interval_seconds``."""
    return INTERVAL_BY_SEVERITY[normalize_severity(priority)]


def severity_task_definition(
    *,
    name: str,
    priority: str,
    run_fn: Callable[[Database, Settings, Callable[[], bool]], Awaitable[Dict[str, Any]]],
    description: str = "",
    enabled: bool = True,
    run_interval_seconds: Optional[int] = None,
    **kwargs: Any,
) -> TaskDefinition:
    """Build a ``TaskDefinition`` with interval derived from severity.

    Thin IdleScheduler composition helper — does not register the task.
    Callers may override ``run_interval_seconds`` explicitly.
    """
    tier = normalize_severity(priority)
    interval = (
        int(run_interval_seconds)
        if run_interval_seconds is not None
        else interval_for_severity(tier)
    )
    return TaskDefinition(
        name=name,
        run_interval_seconds=max(60, interval),
        enabled=enabled,
        run_fn=run_fn,
        description=description or f"Closed-loop {tier} augmentation task ({name}).",
        **kwargs,
    )


def register_severity_task(
    scheduler: IdleScheduler,
    *,
    name: str,
    priority: str,
    run_fn: Callable[[Database, Settings, Callable[[], bool]], Awaitable[Dict[str, Any]]],
    description: str = "",
    enabled: bool = True,
    run_interval_seconds: Optional[int] = None,
    **kwargs: Any,
) -> TaskDefinition:
    """Register a severity-tiered task with ``IdleScheduler``; return the definition."""
    definition = severity_task_definition(
        name=name,
        priority=priority,
        run_fn=run_fn,
        description=description,
        enabled=enabled,
        run_interval_seconds=run_interval_seconds,
        **kwargs,
    )
    scheduler.register(definition)
    return definition


class BaseAugmentationTask(abc.ABC):
    """Universal base class for closed-loop scheduled enrichment tasks."""

    # Subclasses for P2/P3 with proven safe writers may set True.
    enable_direct_commit: bool = False

    def __init__(self, db: Database, task_name: str, target_priority: str) -> None:
        self.db = db
        self.task_name = task_name
        self.target_priority = normalize_severity(target_priority)

    @abc.abstractmethod
    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        """Query ``telemetry_events`` for actionable signals in this task's domain."""

    @abc.abstractmethod
    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process one telemetry signal.

        Returns a payload with:
          - ``target_entity_type``: str
          - ``target_entity_id``: str
          - ``candidate_data``: dict
          - ``confidence``: float (0.0–1.0)
        or ``None`` to skip.
        """

    async def commit_direct(self, payload: Dict[str, Any]) -> None:
        """Apply high-confidence updates to the primary graph.

        Default raises. Opt-in subclasses for future P2/P3 safe writers must
        override this *and* set ``enable_direct_commit = True``. P1 must not.
        """
        raise NotImplementedError(
            f"{self.task_name}: commit_direct is reserved for future P2/P3 "
            "tasks with safe idempotent writers (enable_direct_commit=True). "
            "P1/taxonomy stages only."
        )

    def _may_commit_direct(self) -> bool:
        """P1 never auto-commits. P2/P3 require explicit subclass opt-in."""
        if self.target_priority == "P1":
            return False
        return bool(self.enable_direct_commit) and self.target_priority in ("P2", "P3", "P0")

    async def stage_candidate(self, payload: Dict[str, Any]) -> int:
        """Persist a candidate row to ``staged_augmentations``; returns row id."""
        candidate = payload.get("candidate_data")
        if not isinstance(candidate, dict):
            candidate = {"value": candidate}
        # Sync sqlite write — keep IdleScheduler's event loop free.
        return await run_db(
            self.db.insert_staged_augmentation,
            task_name=self.task_name,
            priority_tier=self.target_priority,
            target_entity_type=str(payload["target_entity_type"]),
            target_entity_id=str(payload["target_entity_id"]),
            candidate_data_json=json.dumps(candidate, default=str, separators=(",", ":")),
            confidence_score=float(payload.get("confidence") or 0.0),
        )

    async def execute_run(self) -> Dict[str, int]:
        """Execute the full signal processing lifecycle."""
        signals = await self.fetch_telemetry_signals()
        stats = {"processed": 0, "direct_commits": 0, "staged": 0, "errors": 0, "skipped": 0}

        for signal in signals:
            stats["processed"] += 1
            try:
                outcome = await self.process_signal(signal)
                if not outcome:
                    stats["skipped"] += 1
                    continue

                confidence = float(outcome.get("confidence") or 0.0)
                if confidence >= DIRECT_COMMIT_CONFIDENCE_FLOOR and self._may_commit_direct():
                    await self.commit_direct(outcome)
                    stats["direct_commits"] += 1
                elif confidence >= STAGE_CONFIDENCE_FLOOR:
                    # Includes high-confidence P1: stage only, never auto-promote.
                    await self.stage_candidate(outcome)
                    stats["staged"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as err:  # noqa: BLE001 — keep processing other signals
                stats["errors"] += 1
                logger.error(
                    "[%s] Signal processing failed for id=%s: %s",
                    self.task_name,
                    signal.get("id"),
                    err,
                )

        return stats
