"""Unit tests for BaseAugmentationTask confidence / severity routing."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import (
    INTERVAL_BY_SEVERITY,
    BaseAugmentationTask,
    interval_for_severity,
    register_severity_task,
    severity_task_definition,
)


class _StubTask(BaseAugmentationTask):
    """Configurable stub that returns canned process outcomes."""

    def __init__(
        self,
        db: Database,
        *,
        priority: str = "P1",
        outcomes: Optional[List[Optional[Dict[str, Any]]]] = None,
        enable_direct_commit: bool = False,
    ) -> None:
        super().__init__(db, task_name="stub_augmentation", target_priority=priority)
        self.enable_direct_commit = enable_direct_commit
        self._outcomes = list(outcomes or [])
        self.direct_commits: List[Dict[str, Any]] = []
        self._signals = [
            {"id": idx + 1, "entity_key": f"signal-{idx}"} for idx in range(len(self._outcomes))
        ]

    async def fetch_telemetry_signals(self) -> List[Dict[str, Any]]:
        return list(self._signals)

    async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        idx = int(signal["id"]) - 1
        return self._outcomes[idx]

    async def commit_direct(self, payload: Dict[str, Any]) -> None:
        self.direct_commits.append(payload)


def _candidate(confidence: float, entity_id: str = "facet:x") -> Dict[str, Any]:
    return {
        "target_entity_type": "facet",
        "target_entity_id": entity_id,
        "candidate_data": {"alias": entity_id},
        "confidence": confidence,
    }


class BaseAugmentationRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_p1_high_confidence_stages_never_commits(self) -> None:
        task = _StubTask(
            self.db,
            priority="P1",
            outcomes=[_candidate(0.95)],
            enable_direct_commit=True,  # even if subclass opts in, P1 must stage
        )
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)
        self.assertEqual(task.direct_commits, [])
        staged = self.db.list_staged_augmentations(task_name="stub_augmentation")
        self.assertEqual(len(staged), 1)
        self.assertAlmostEqual(float(staged[0]["confidence_score"]), 0.95)

    def test_mid_confidence_stages(self) -> None:
        task = _StubTask(self.db, priority="P1", outcomes=[_candidate(0.70)])
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)

    def test_low_confidence_skips(self) -> None:
        task = _StubTask(self.db, priority="P1", outcomes=[_candidate(0.40)])
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["staged"], 0)
        self.assertEqual(self.db.list_staged_augmentations(task_name="stub_augmentation"), [])

    def test_none_outcome_skips(self) -> None:
        task = _StubTask(self.db, priority="P1", outcomes=[None])
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["skipped"], 1)

    def test_p2_opt_in_direct_commit(self) -> None:
        task = _StubTask(
            self.db,
            priority="P2",
            outcomes=[_candidate(0.95, entity_id="title:1")],
            enable_direct_commit=True,
        )
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["direct_commits"], 1)
        self.assertEqual(stats["staged"], 0)
        self.assertEqual(len(task.direct_commits), 1)

    def test_p2_without_opt_in_stages_high_confidence(self) -> None:
        task = _StubTask(
            self.db,
            priority="P2",
            outcomes=[_candidate(0.95, entity_id="title:2")],
            enable_direct_commit=False,
        )
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["direct_commits"], 0)
        self.assertEqual(stats["staged"], 1)

    def test_process_error_counted(self) -> None:
        class BoomTask(_StubTask):
            async def process_signal(self, signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                raise RuntimeError("boom")

        task = BoomTask(self.db, priority="P1", outcomes=[_candidate(0.9)])
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["staged"], 0)


class SeverityHelperTests(unittest.TestCase):
    def test_interval_matrix(self) -> None:
        self.assertEqual(interval_for_severity("P0"), INTERVAL_BY_SEVERITY["P0"])
        self.assertEqual(interval_for_severity("p1"), INTERVAL_BY_SEVERITY["P1"])
        self.assertEqual(interval_for_severity("P3"), INTERVAL_BY_SEVERITY["P3"])
        self.assertEqual(interval_for_severity("nope"), INTERVAL_BY_SEVERITY["P3"])

    def test_severity_task_definition_intervals(self) -> None:
        async def _noop(db, settings, should_stop):  # noqa: ANN001
            return {"status": "ok"}

        p0 = severity_task_definition(name="p0_task", priority="P0", run_fn=_noop)
        p3 = severity_task_definition(name="p3_task", priority="P3", run_fn=_noop)
        self.assertEqual(p0.run_interval_seconds, INTERVAL_BY_SEVERITY["P0"])
        self.assertEqual(p3.run_interval_seconds, INTERVAL_BY_SEVERITY["P3"])

    def test_register_severity_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "sched.db")
            try:
                scheduler = IdleScheduler(db, Path(tmp))

                async def _noop(db_, settings, should_stop):  # noqa: ANN001
                    return {"status": "ok"}

                defn = register_severity_task(
                    scheduler,
                    name="closed_loop_p1_demo",
                    priority="P1",
                    run_fn=_noop,
                    description="demo",
                )
                self.assertEqual(defn.run_interval_seconds, INTERVAL_BY_SEVERITY["P1"])
                self.assertIn("closed_loop_p1_demo", scheduler._definitions)
            finally:
                db.close()


class StageCandidatePersistenceTests(unittest.TestCase):
    def test_stage_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            try:
                task = _StubTask(db, priority="P1", outcomes=[])
                row_id = asyncio.run(
                    task.stage_candidate(
                        {
                            "target_entity_type": "facet",
                            "target_entity_id": "noir",
                            "candidate_data": {"alias": "film-noir"},
                            "confidence": 0.8,
                        }
                    )
                )
                self.assertGreater(row_id, 0)
                staged = db.list_staged_augmentations()[0]
                data = json.loads(staged["candidate_data_json"])
                self.assertEqual(data["alias"], "film-noir")
                self.assertEqual(staged["priority_tier"], "P1")
            finally:
                db.close()

    def test_stage_candidate_offloads_via_run_db(self) -> None:
        """stage_candidate must not call sync sqlite on the event-loop thread."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            try:
                task = _StubTask(db, priority="P1", outcomes=[])
                with mock.patch(
                    "projectionist.scheduler.tasks.base_augmentation.run_db",
                    new_callable=mock.AsyncMock,
                ) as run_db_mock:
                    run_db_mock.return_value = 99
                    row_id = asyncio.run(
                        task.stage_candidate(
                            {
                                "target_entity_type": "facet",
                                "target_entity_id": "noir",
                                "candidate_data": {"alias": "film-noir"},
                                "confidence": 0.8,
                            }
                        )
                    )
                self.assertEqual(row_id, 99)
                run_db_mock.assert_awaited_once()
                passed = run_db_mock.await_args.args[0]
                self.assertIs(passed.__self__, db)
                self.assertIs(passed.__func__, type(db).insert_staged_augmentation)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
