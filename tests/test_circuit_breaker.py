"""Tests for the scheduler circuit breaker: timeout, failure counting, quarantine, and reset."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import (
    DEFAULT_QUARANTINE_COOLDOWN_SECONDS,
    QUARANTINE_THRESHOLD,
    IdleScheduler,
    QuarantineInfo,
    TaskDefinition,
    _HeartbeatHandle,
)


def _make_db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


async def _noop_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    return {"status": "completed"}


async def _error_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    raise RuntimeError("intentional failure")


async def _hanging_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    await asyncio.sleep(60)
    return {"status": "completed"}


async def _heartbeat_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    for _ in range(5):
        should_stop()
        await asyncio.sleep(0.01)
    return {"status": "completed"}


async def _slow_with_heartbeats(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Takes ~4s total but heartbeats every 0.5s — should survive a 2s timeout."""
    for _ in range(8):
        should_stop()
        await asyncio.sleep(0.5)
    return {"status": "completed"}


async def _slow_no_heartbeats(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Takes ~4s with no heartbeats — should timeout with a 2s timeout."""
    await asyncio.sleep(4)
    return {"status": "completed"}


async def _heartbeat_then_hang(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    """Heartbeats for ~1.5s then hangs — should timeout ~2s after the last heartbeat."""
    for _ in range(3):
        should_stop()
        await asyncio.sleep(0.5)
    await asyncio.sleep(60)
    return {"status": "completed"}


class QuarantineInfoTests(unittest.TestCase):
    """Unit tests for the QuarantineInfo dataclass."""

    def test_not_quarantined_initially(self) -> None:
        qi = QuarantineInfo()
        self.assertFalse(qi.is_quarantined)
        self.assertEqual(qi.consecutive_failures, 0)

    def test_record_failure_below_threshold(self) -> None:
        qi = QuarantineInfo()
        for i in range(QUARANTINE_THRESHOLD - 1):
            result = qi.record_failure(f"error {i}")
            self.assertFalse(result)
        self.assertFalse(qi.is_quarantined)
        self.assertEqual(qi.consecutive_failures, QUARANTINE_THRESHOLD - 1)

    def test_quarantine_after_threshold_failures(self) -> None:
        qi = QuarantineInfo()
        for i in range(QUARANTINE_THRESHOLD - 1):
            qi.record_failure(f"error {i}")
        result = qi.record_failure("final error")
        self.assertTrue(result)
        self.assertTrue(qi.is_quarantined)
        self.assertEqual(qi.last_error, "final error")

    def test_success_resets_failure_counter(self) -> None:
        qi = QuarantineInfo()
        qi.record_failure("error 1")
        qi.record_failure("error 2")
        qi.record_success()
        self.assertEqual(qi.consecutive_failures, 0)
        self.assertFalse(qi.is_quarantined)

    def test_release_clears_quarantine(self) -> None:
        qi = QuarantineInfo()
        for i in range(QUARANTINE_THRESHOLD):
            qi.record_failure(f"error {i}")
        self.assertTrue(qi.is_quarantined)
        qi.release()
        self.assertFalse(qi.is_quarantined)
        self.assertEqual(qi.consecutive_failures, 0)

    def test_cooldown_auto_releases(self) -> None:
        qi = QuarantineInfo(cooldown_seconds=0)
        for i in range(QUARANTINE_THRESHOLD):
            qi.record_failure(f"error {i}")
        self.assertFalse(qi.is_quarantined)

    def test_remaining_seconds(self) -> None:
        qi = QuarantineInfo(cooldown_seconds=3600)
        self.assertIsNone(qi.remaining_seconds)
        for i in range(QUARANTINE_THRESHOLD):
            qi.record_failure(f"error {i}")
        remaining = qi.remaining_seconds
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 3500)


class HeartbeatTests(unittest.TestCase):
    def test_heartbeat_resets_timestamp(self) -> None:
        hb = _HeartbeatHandle()
        initial = hb.last_heartbeat
        time.sleep(0.01)
        hb.heartbeat()
        self.assertGreater(hb.last_heartbeat, initial)


class TaskTimeoutTests(unittest.TestCase):
    """Tests for per-task timeout enforcement."""

    def test_hanging_task_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="hangs",
                    run_interval_seconds=3600,
                    timeout_seconds=1,
                    run_fn=_hanging_task,
                )
            )
            result = asyncio.run(scheduler.trigger_task("hangs"))
            self.assertEqual(result["status"], "error")
            self.assertIn("timed out", result["error"])

    def test_fast_task_completes_within_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="fast",
                    run_interval_seconds=3600,
                    timeout_seconds=10,
                    run_fn=_noop_task,
                )
            )
            result = asyncio.run(scheduler.trigger_task("fast"))
            self.assertEqual(result["status"], "completed")


class FailureCountingTests(unittest.TestCase):
    """Tests for consecutive failure tracking and quarantine via the scheduler."""

    def test_single_failure_does_not_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="flaky", run_interval_seconds=3600, run_fn=_error_task)
            )
            asyncio.run(scheduler.trigger_task("flaky"))
            qinfo = scheduler._quarantine["flaky"]
            self.assertEqual(qinfo.consecutive_failures, 1)
            self.assertFalse(qinfo.is_quarantined)

    def test_quarantine_after_consecutive_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="broken", run_interval_seconds=3600, run_fn=_error_task)
            )
            for _ in range(QUARANTINE_THRESHOLD):
                asyncio.run(scheduler.trigger_task("broken"))
            qinfo = scheduler._quarantine["broken"]
            self.assertTrue(qinfo.is_quarantined)
            self.assertEqual(qinfo.consecutive_failures, QUARANTINE_THRESHOLD)

    def test_success_resets_failure_counter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="recovers", run_interval_seconds=3600, run_fn=_error_task)
            )
            asyncio.run(scheduler.trigger_task("recovers"))
            asyncio.run(scheduler.trigger_task("recovers"))
            self.assertEqual(scheduler._quarantine["recovers"].consecutive_failures, 2)

            scheduler._definitions["recovers"].run_fn = _noop_task
            asyncio.run(scheduler.trigger_task("recovers"))
            self.assertEqual(scheduler._quarantine["recovers"].consecutive_failures, 0)

    def test_quarantined_task_skipped_in_stale_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="skip_me", run_interval_seconds=60, run_fn=_error_task)
            )
            for _ in range(QUARANTINE_THRESHOLD):
                asyncio.run(scheduler.trigger_task("skip_me"))
            stale = scheduler._stale_tasks()
            self.assertNotIn("skip_me", [d.name for d in stale])


class QuarantineResetTests(unittest.TestCase):
    """Tests for the admin quarantine reset endpoint."""

    def test_reset_clears_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="fixable", run_interval_seconds=60, run_fn=_error_task)
            )
            for _ in range(QUARANTINE_THRESHOLD):
                asyncio.run(scheduler.trigger_task("fixable"))
            self.assertTrue(scheduler._quarantine["fixable"].is_quarantined)

            result = scheduler.reset_quarantine("fixable")
            self.assertIsNotNone(result)
            self.assertFalse(result["is_quarantined"])
            self.assertEqual(result["consecutive_failures"], 0)
            self.assertFalse(scheduler._quarantine["fixable"].is_quarantined)

    def test_reset_nonexistent_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            result = scheduler.reset_quarantine("ghost")
            self.assertIsNone(result)

    def test_reset_allows_task_to_run_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="bounced", run_interval_seconds=1, run_fn=_error_task)
            )
            for _ in range(QUARANTINE_THRESHOLD):
                asyncio.run(scheduler.trigger_task("bounced"))
            self.assertEqual(len([d for d in scheduler._stale_tasks() if d.name == "bounced"]), 0)

            scheduler.reset_quarantine("bounced")
            time.sleep(1.1)
            stale_names = [d.name for d in scheduler._stale_tasks()]
            self.assertIn("bounced", stale_names)


class AdminAPIQuarantineFieldTests(unittest.TestCase):
    """Tests that get_task_states includes quarantine info."""

    def test_quarantine_in_task_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="observable", run_interval_seconds=3600, run_fn=_noop_task)
            )
            states = scheduler.get_task_states()
            state = next(s for s in states if s["name"] == "observable")
            self.assertIn("quarantine", state)
            self.assertFalse(state["quarantine"]["is_quarantined"])
            self.assertEqual(state["quarantine"]["consecutive_failures"], 0)

    def test_quarantine_visible_after_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="failing", run_interval_seconds=3600, run_fn=_error_task)
            )
            for _ in range(QUARANTINE_THRESHOLD):
                asyncio.run(scheduler.trigger_task("failing"))
            states = scheduler.get_task_states()
            state = next(s for s in states if s["name"] == "failing")
            self.assertTrue(state["quarantine"]["is_quarantined"])
            self.assertEqual(state["quarantine"]["consecutive_failures"], QUARANTINE_THRESHOLD)
            self.assertIn("intentional failure", state["quarantine"]["last_error"])


class HeartbeatDeadlineTests(unittest.TestCase):
    """Tests that heartbeats actually extend the timeout deadline."""

    def test_heartbeat_extends_timeout(self) -> None:
        """A task that takes 4s but heartbeats every 0.5s should survive a 2s timeout."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="slow_hb",
                    run_interval_seconds=3600,
                    timeout_seconds=2,
                    run_fn=_slow_with_heartbeats,
                )
            )
            result = asyncio.run(scheduler.trigger_task("slow_hb"))
            self.assertEqual(result["status"], "completed")

    def test_no_heartbeat_causes_timeout(self) -> None:
        """A task that takes 4s with no heartbeats should timeout at 2s."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="slow_no_hb",
                    run_interval_seconds=3600,
                    timeout_seconds=2,
                    run_fn=_slow_no_heartbeats,
                )
            )
            t0 = time.time()
            result = asyncio.run(scheduler.trigger_task("slow_no_hb"))
            elapsed = time.time() - t0
            self.assertEqual(result["status"], "error")
            self.assertIn("timed out", result["error"])
            self.assertLess(elapsed, 3.5, "Should timeout around 2s, not wait the full 4s")

    def test_heartbeat_stops_then_timeout(self) -> None:
        """A task that heartbeats for 1.5s then hangs should timeout ~2s after the last heartbeat."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="hb_then_hang",
                    run_interval_seconds=3600,
                    timeout_seconds=2,
                    run_fn=_heartbeat_then_hang,
                )
            )
            t0 = time.time()
            result = asyncio.run(scheduler.trigger_task("hb_then_hang"))
            elapsed = time.time() - t0
            self.assertEqual(result["status"], "error")
            self.assertIn("timed out", result["error"])
            self.assertGreater(elapsed, 2.5, "Should run ~1.5s of heartbeats + ~2s timeout")
            self.assertLess(elapsed, 6.0, "Should not wait for the full 60s hang")


if __name__ == "__main__":
    unittest.main()
