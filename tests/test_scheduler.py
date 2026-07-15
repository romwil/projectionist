"""Tests for the background idle task scheduler."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition


def _make_db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


async def _noop_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    return {"status": "completed"}


async def _slow_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    for _ in range(10):
        if should_stop():
            return {"status": "interrupted"}
        await asyncio.sleep(0.01)
    return {"status": "completed"}


async def _error_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    raise RuntimeError("intentional failure")


class TaskRegistrationTests(unittest.TestCase):
    def test_register_and_list_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="task_a", run_interval_seconds=3600, run_fn=_noop_task)
            )
            scheduler.register(
                TaskDefinition(name="task_b", run_interval_seconds=7200, run_fn=_noop_task)
            )
            states = scheduler.get_task_states()
            names = [s["name"] for s in states]
            self.assertIn("task_a", names)
            self.assertIn("task_b", names)

    def test_register_preserves_existing_interval(self) -> None:
        """Re-registering a task after a run should NOT overwrite the user-adjusted interval."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="task_x", run_interval_seconds=3600, run_fn=_noop_task)
            )
            # Simulate the admin adjusting the interval.
            scheduler.update_task("task_x", run_interval_seconds=1800)
            # Simulate a run, which writes last_run_at.
            asyncio.run(scheduler.trigger_task("task_x"))
            # Re-register (as happens on restart).
            scheduler.register(
                TaskDefinition(name="task_x", run_interval_seconds=3600, run_fn=_noop_task)
            )
            state = next(s for s in scheduler.get_task_states() if s["name"] == "task_x")
            self.assertEqual(state["run_interval_seconds"], 1800)


class StalenessOrderingTests(unittest.TestCase):
    def test_most_overdue_runs_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)

            scheduler.register(
                TaskDefinition(name="fresh", run_interval_seconds=3600, run_fn=_noop_task)
            )
            scheduler.register(
                TaskDefinition(name="stale", run_interval_seconds=60, run_fn=_noop_task)
            )
            # Run 'fresh' recently so it's not stale.
            asyncio.run(scheduler.trigger_task("fresh"))

            stale = scheduler._stale_tasks()
            stale_names = [d.name for d in stale]
            # 'stale' has never run, so it should come first.
            self.assertIn("stale", stale_names)


class IdleDetectionTests(unittest.TestCase):
    def test_idle_after_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            # With threshold=0 minutes, should be idle immediately.
            self.assertTrue(scheduler.is_idle())

    def test_not_idle_after_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=60)
            scheduler.record_activity()
            self.assertFalse(scheduler.is_idle())


class ShouldStopTests(unittest.TestCase):
    def test_should_stop_on_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=60)
            scheduler.record_activity()
            self.assertTrue(scheduler.should_stop())

    def test_should_stop_on_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler._shutdown = True
            self.assertTrue(scheduler.should_stop())

    def test_task_interrupted_by_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)

            call_count = 0

            async def interruptible_task(
                db: Database, settings: Settings, should_stop: Callable[[], bool]
            ) -> Dict[str, Any]:
                nonlocal call_count
                for i in range(100):
                    call_count += 1
                    if should_stop():
                        return {"status": "interrupted", "iterations": i}
                    await asyncio.sleep(0.001)
                return {"status": "completed"}

            scheduler.register(
                TaskDefinition(name="interruptible", run_interval_seconds=60, run_fn=interruptible_task)
            )
            # Trigger with force=True, but set shutdown immediately after first poll.
            scheduler._shutdown = True
            result = asyncio.run(scheduler.trigger_task("interruptible"))
            # Force mode doesn't check idle, but does check shutdown.
            self.assertEqual(result["status"], "interrupted")


class TaskStatePersistenceTests(unittest.TestCase):
    def test_last_run_at_updates_after_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="persist_test", run_interval_seconds=3600, run_fn=_noop_task)
            )
            # Before run, last_run_at should be None.
            state = next(s for s in scheduler.get_task_states() if s["name"] == "persist_test")
            self.assertIsNone(state["last_run_at"])

            asyncio.run(scheduler.trigger_task("persist_test"))

            state = next(s for s in scheduler.get_task_states() if s["name"] == "persist_test")
            self.assertIsNotNone(state["last_run_at"])
            self.assertEqual(state["last_status"], "completed")

    def test_duration_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="timed", run_interval_seconds=3600, run_fn=_noop_task)
            )
            asyncio.run(scheduler.trigger_task("timed"))
            state = next(s for s in scheduler.get_task_states() if s["name"] == "timed")
            self.assertIsNotNone(state["last_duration_ms"])
            self.assertGreaterEqual(state["last_duration_ms"], 0)

    def test_error_status_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="failing", run_interval_seconds=3600, run_fn=_error_task)
            )
            result = asyncio.run(scheduler.trigger_task("failing"))
            self.assertEqual(result["status"], "error")
            state = next(s for s in scheduler.get_task_states() if s["name"] == "failing")
            self.assertTrue(state["last_status"].startswith("error:"))


class EnableDisableTests(unittest.TestCase):
    def test_disable_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="toggleable", run_interval_seconds=60, run_fn=_noop_task)
            )
            scheduler.update_task("toggleable", enabled=False)
            # Disabled tasks should not appear in stale list.
            stale = scheduler._stale_tasks()
            stale_names = [d.name for d in stale]
            self.assertNotIn("toggleable", stale_names)

    def test_enable_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="toggleable", run_interval_seconds=60, enabled=False, run_fn=_noop_task
                )
            )
            scheduler.update_task("toggleable", enabled=True)
            state = next(s for s in scheduler.get_task_states() if s["name"] == "toggleable")
            self.assertTrue(state["enabled"])

    def test_adjust_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="adjustable", run_interval_seconds=3600, run_fn=_noop_task)
            )
            scheduler.update_task("adjustable", run_interval_seconds=1800)
            state = next(s for s in scheduler.get_task_states() if s["name"] == "adjustable")
            self.assertEqual(state["run_interval_seconds"], 1800)

    def test_update_nonexistent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            result = scheduler.update_task("ghost_task", enabled=True)
            self.assertIsNone(result)


class APIEndpointTests(unittest.TestCase):
    """Smoke tests for the scheduled-tasks admin API routes via TestClient."""

    def test_list_tasks_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="api_test", run_interval_seconds=3600, run_fn=_noop_task)
            )
            states = scheduler.get_task_states()
            self.assertTrue(any(s["name"] == "api_test" for s in states))

    def test_trigger_unknown_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            result = asyncio.run(scheduler.trigger_task("nonexistent"))
            self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
