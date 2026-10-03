"""Schedule / skip / coalesce behavior of the idle scheduler (1.37.28 audit).

Covers: effective cadence (interrupted retry, catch-up drain, failure backoff,
skipped floor), off-loop execution, retired no-consumer tasks, and the registry
invariants that keep owner-visible task names honest.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler import cadence
from projectionist.scheduler.autotune import evaluate_autotune
from projectionist.scheduler.cadence import (
    BACKOFF_CAP_SECONDS,
    INTERRUPTED_RETRY_SECONDS,
    SKIPPED_MIN_INTERVAL_SECONDS,
    effective_cadence,
    is_productive_catch_up,
)
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.scheduler.tasks import RETIRED_TASKS, register_all


def _db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


async def _noop(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    return {"status": "completed"}


def _persist(
    db: Database,
    name: str,
    *,
    ago: float,
    status: str,
    metrics: Dict[str, Any] | None = None,
) -> None:
    summary = json.dumps({"summary_line": "x", "metrics": metrics or {}, "status": status})
    with db.connect() as conn:
        conn.execute(
            "UPDATE scheduled_tasks SET last_run_at = ?, last_status = ?, last_run_summary = ?"
            " WHERE name = ?",
            (str(time.time() - ago), status, summary, name),
        )


class EffectiveCadencePureTests(unittest.TestCase):
    def test_steady_state_uses_configured_interval(self) -> None:
        c = effective_cadence(interval_seconds=21600, last_status="completed")
        self.assertEqual(c.interval_seconds, 21600)
        self.assertIsNone(c.reason)

    def test_interrupted_retries_at_next_idle_window_not_a_week_later(self) -> None:
        c = effective_cadence(interval_seconds=7 * 86400, last_status="interrupted")
        self.assertEqual(c.interval_seconds, INTERRUPTED_RETRY_SECONDS)
        self.assertEqual(c.reason, cadence.REASON_INTERRUPTED)

    def test_interrupted_never_lengthens_a_short_interval(self) -> None:
        c = effective_cadence(interval_seconds=120, last_status="interrupted")
        self.assertEqual(c.interval_seconds, 120)

    def test_catch_up_only_when_flagged_and_gap_shorter(self) -> None:
        summary = {"metrics": {"catching_up": True, "has_more": True}}
        c = effective_cadence(
            interval_seconds=21600,
            last_status="completed",
            last_run_summary=summary,
            catchup_gap_seconds=300,
        )
        self.assertEqual((c.interval_seconds, c.reason), (300, cadence.REASON_CATCH_UP))

        # has_more alone (no productive-run flag) must not accelerate.
        c = effective_cadence(
            interval_seconds=21600,
            last_status="completed",
            last_run_summary={"metrics": {"has_more": True}},
            catchup_gap_seconds=300,
        )
        self.assertEqual(c.interval_seconds, 21600)

        # Tasks without a gap (LLM spend) never accelerate.
        c = effective_cadence(
            interval_seconds=86400,
            last_status="completed",
            last_run_summary=summary,
            catchup_gap_seconds=None,
        )
        self.assertEqual(c.interval_seconds, 86400)

        # Owner interval already shorter than the gap wins.
        c = effective_cadence(
            interval_seconds=120,
            last_status="completed",
            last_run_summary=summary,
            catchup_gap_seconds=300,
        )
        self.assertEqual(c.interval_seconds, 120)

    def test_catch_up_requires_substantial_progress(self) -> None:
        # 1 of 25 processed → likely re-hitting unresolvable titles → no drain.
        self.assertFalse(
            is_productive_catch_up(
                has_more=True, items_processed=1, batch_size=25, catchup_gap_seconds=300
            )
        )
        self.assertTrue(
            is_productive_catch_up(
                has_more=True, items_processed=13, batch_size=25, catchup_gap_seconds=300
            )
        )
        self.assertFalse(
            is_productive_catch_up(
                has_more=False, items_processed=25, batch_size=25, catchup_gap_seconds=300
            )
        )
        self.assertFalse(
            is_productive_catch_up(
                has_more=True, items_processed=25, batch_size=25, catchup_gap_seconds=None
            )
        )

    def test_failure_backoff_doubles_and_caps(self) -> None:
        waits = [
            effective_cadence(
                interval_seconds=900, last_status="degraded", failure_streak=n
            ).interval_seconds
            for n in (1, 2, 3, 4, 10)
        ]
        self.assertEqual(waits[:3], [1800, 3600, 7200])
        self.assertEqual(waits[3], 900 * 8)  # multiplier cap
        self.assertTrue(all(w <= BACKOFF_CAP_SECONDS for w in waits))
        self.assertEqual(waits[-1], 900 * 8 if 900 * 8 <= BACKOFF_CAP_SECONDS else BACKOFF_CAP_SECONDS)

    def test_backoff_never_stretches_long_intervals_past_configured(self) -> None:
        c = effective_cadence(
            interval_seconds=7 * 86400, last_status="error: boom", failure_streak=3
        )
        self.assertEqual(c.interval_seconds, 7 * 86400)
        self.assertIsNone(c.reason)

    def test_skipped_has_floor_for_fast_tasks_only(self) -> None:
        c = effective_cadence(interval_seconds=900, last_status="skipped")
        self.assertEqual(c.interval_seconds, SKIPPED_MIN_INTERVAL_SECONDS)
        c = effective_cadence(interval_seconds=86400, last_status="skipped")
        self.assertEqual(c.interval_seconds, 86400)


class SchedulerDueTests(unittest.TestCase):
    def _sched(self, tmp: str, **defn_kwargs: Any) -> IdleScheduler:
        scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
        scheduler.register(
            TaskDefinition(
                name="t", run_interval_seconds=21600, run_fn=_noop, **defn_kwargs
            )
        )
        return scheduler

    def _due(self, scheduler: IdleScheduler) -> bool:
        return "t" in [d.name for d in scheduler._stale_tasks()]

    def test_interrupted_task_is_due_again_soon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sched(tmp)
            _persist(s._db, "t", ago=INTERRUPTED_RETRY_SECONDS + 5, status="interrupted")
            self.assertTrue(self._due(s))
            _persist(s._db, "t", ago=30, status="interrupted")
            self.assertFalse(self._due(s))

    def test_completed_task_waits_full_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sched(tmp)
            _persist(s._db, "t", ago=3600, status="completed")
            self.assertFalse(self._due(s))

    def test_catching_up_task_is_due_after_gap_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sched(tmp, catchup_gap_seconds=300, items_per_cycle=25)
            _persist(
                s._db,
                "t",
                ago=400,
                status="completed",
                metrics={"catching_up": True, "has_more": True},
            )
            self.assertTrue(self._due(s))
            row = next(r for r in s.get_task_states() if r["name"] == "t")
            self.assertEqual(row["effective_run_interval_seconds"], 300)
            self.assertEqual(row["schedule_reason"], "catching_up")
            self.assertEqual(row["run_interval_seconds"], 21600)  # configured value untouched
            self.assertTrue(row["overdue"])
            self.assertAlmostEqual(row["next_run_at"], row["last_run_at"] + 300, delta=1)

    def test_degraded_streak_backs_off_using_history(self) -> None:
        from projectionist.scheduler.run_history import append_task_run

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="t", run_interval_seconds=900, run_fn=_noop)
            )
            now = time.time()
            for i in range(3):  # three consecutive degraded runs
                append_task_run(
                    scheduler._db,
                    name="t",
                    started_at=now - 5000 + i,
                    finished_at=now - 5000 + i + 1,
                    duration_ms=1,
                    status="degraded",
                    trigger="schedule",
                )
            _persist(scheduler._db, "t", ago=1000, status="degraded")
            # streak 3 → 900 * 8 = 7200s wait; 1000s elapsed → not due.
            self.assertFalse(self._due(scheduler))
            _persist(scheduler._db, "t", ago=7300, status="degraded")
            self.assertTrue(self._due(scheduler))


class FinalizeRunSignalTests(unittest.TestCase):
    def _run(self, result: Dict[str, Any], **defn_kwargs: Any) -> Dict[str, Any]:
        async def task(db, settings, should_stop):
            return result

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="t", run_interval_seconds=21600, run_fn=task, **defn_kwargs
                )
            )
            asyncio.run(scheduler.trigger_task("t"))
            state = next(s for s in scheduler._load_all_states() if s.name == "t")
            return (state.last_run_summary or {}).get("metrics") or {}

    def test_full_batch_with_backlog_marks_catching_up(self) -> None:
        metrics = self._run(
            {"status": "completed", "enriched": 25, "batch_size": 25, "has_more": True},
            catchup_gap_seconds=300,
            items_per_cycle=25,
        )
        self.assertTrue(metrics.get("has_more"))
        self.assertTrue(metrics.get("catching_up"))

    def test_sliver_of_progress_does_not_mark_catching_up(self) -> None:
        metrics = self._run(
            {"status": "completed", "enriched": 1, "batch_size": 25, "has_more": True},
            catchup_gap_seconds=300,
            items_per_cycle=25,
        )
        self.assertTrue(metrics.get("has_more"))
        self.assertNotIn("catching_up", metrics)

    def test_no_gap_no_catch_up(self) -> None:
        metrics = self._run(
            {"status": "completed", "enriched": 5, "batch_size": 5, "has_more": True},
            items_per_cycle=5,
        )
        self.assertNotIn("catching_up", metrics)

    def test_caught_up_clears_signal(self) -> None:
        metrics = self._run(
            {"status": "completed", "enriched": 3, "batch_size": 25, "has_more": False},
            catchup_gap_seconds=300,
            items_per_cycle=25,
        )
        self.assertNotIn("has_more", metrics)
        self.assertNotIn("catching_up", metrics)


class AutotuneCatchUpEtaTests(unittest.TestCase):
    def test_draining_backlog_does_not_shorten_interval_for_a_delay_that_never_happens(self) -> None:
        kwargs = dict(
            name="metadata_enrichment",
            status="completed",
            duration_ms=20_000,
            timeout_seconds=300,
            items_per_cycle=50,
            interval_seconds=21600,
            items_processed=50,
            remaining_items=3000,
            has_more=True,
        )
        without_gap = evaluate_autotune(**kwargs)
        self.assertIn("backlog_eta_shorten_interval", without_gap.reasons or [])
        with_gap = evaluate_autotune(**kwargs, catchup_gap_seconds=300)
        self.assertNotIn("backlog_eta_shorten_interval", with_gap.reasons or [])


class OffLoopTests(unittest.TestCase):
    """Blocking task bodies must not freeze the web server's event loop."""

    def _worst_loop_lag(self, *, off_loop: bool) -> float:
        async def blocking(db, settings, should_stop):
            time.sleep(0.4)  # stands in for a full-library scan / sync HTTP call
            return {"status": "completed"}

        async def scenario(scheduler: IdleScheduler) -> float:
            worst = 0.0
            stop = False

            async def ticker() -> None:
                nonlocal worst
                last = time.perf_counter()
                while not stop:
                    await asyncio.sleep(0.01)
                    now = time.perf_counter()
                    worst = max(worst, now - last - 0.01)
                    last = now

            tick = asyncio.create_task(ticker())
            await asyncio.sleep(0.05)
            await scheduler.trigger_task("t")
            stop = True
            await tick
            return worst

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="t",
                    run_interval_seconds=3600,
                    run_fn=blocking,
                    off_loop=off_loop,
                )
            )
            return asyncio.run(scenario(scheduler))

    def test_on_loop_blocking_task_stalls_the_loop(self) -> None:
        self.assertGreater(self._worst_loop_lag(off_loop=False), 0.3)

    def test_off_loop_blocking_task_keeps_loop_responsive(self) -> None:
        self.assertLess(self._worst_loop_lag(off_loop=True), 0.15)

    def test_off_loop_runs_on_worker_thread_with_context_and_result(self) -> None:
        seen: Dict[str, Any] = {}

        async def task(db, settings, should_stop):
            from projectionist.scheduler.run_log import emit_task_event

            seen["thread"] = threading.current_thread().name
            emit_task_event("from worker thread")
            return {"status": "completed", "enriched": 2}

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="t", run_interval_seconds=3600, run_fn=task, off_loop=True)
            )
            result = asyncio.run(scheduler.trigger_task("t"))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 2)
            self.assertNotEqual(seen["thread"], threading.main_thread().name)
            events = scheduler.run_log.get_events(task="t")["events"]
            self.assertTrue(any("from worker thread" in e["message"] for e in events))

    def test_off_loop_exception_is_reported_like_on_loop(self) -> None:
        async def boom(db, settings, should_stop):
            raise RuntimeError("worker boom")

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(name="t", run_interval_seconds=3600, run_fn=boom, off_loop=True)
            )
            result = asyncio.run(scheduler.trigger_task("t"))
            self.assertEqual(result["status"], "error")
            self.assertIn("worker boom", result["error"])

    def test_watchdog_timeout_flips_should_stop_for_thread_tasks(self) -> None:
        """A worker thread cannot be hard-cancelled; ``should_stop`` must tell it to quit."""
        captured: Dict[str, Any] = {}

        async def silent(db, settings, should_stop):
            captured["stop"] = should_stop
            time.sleep(1.3)  # blocks without polling → no heartbeat → watchdog fires
            return {"status": "completed"}

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp), idle_threshold_minutes=0)
            scheduler.register(
                TaskDefinition(
                    name="t",
                    run_interval_seconds=3600,
                    run_fn=silent,
                    off_loop=True,
                    timeout_seconds=1,
                )
            )
            result = asyncio.run(scheduler.trigger_task("t"))
            self.assertEqual(result["status"], "error")
            self.assertIn("timed out", result["error"])
            # force=True ignores idleness, so only the watchdog flag can make this True.
            self.assertTrue(captured["stop"]())


class RetiredTasksTests(unittest.TestCase):
    def test_registry_no_longer_exposes_unconsumed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp))
            register_all(scheduler)
            for name in RETIRED_TASKS:
                self.assertNotIn(name, scheduler._definitions)
            self.assertEqual(set(RETIRED_TASKS), {"health_metrics", "recommendation_warmup"})

    def test_retired_state_and_history_rows_are_deleted_on_upgrade(self) -> None:
        from projectionist.scheduler.run_history import append_task_run, list_task_runs

        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            old = IdleScheduler(db, Path(tmp))
            # Simulate a pre-1.37.28 install that had both tasks registered + run.
            for name in RETIRED_TASKS:
                old.register(TaskDefinition(name=name, run_interval_seconds=3600, run_fn=_noop))
                append_task_run(
                    db,
                    name=name,
                    started_at=time.time() - 10,
                    finished_at=time.time() - 9,
                    duration_ms=1000,
                    status="completed",
                    trigger="schedule",
                )

            upgraded = IdleScheduler(db, Path(tmp))
            register_all(upgraded)
            names = {s["name"] for s in upgraded.get_task_states()}
            for name in RETIRED_TASKS:
                self.assertNotIn(name, names)
                self.assertEqual(list_task_runs(db, name, limit=5), [])
            self.assertIn("taste_refresh", names)

    def test_retire_never_removes_a_registered_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp))
            scheduler.register(TaskDefinition(name="keep", run_interval_seconds=3600, run_fn=_noop))
            self.assertEqual(scheduler.retire_tasks(["keep"]), [])
            self.assertIn("keep", {s["name"] for s in scheduler.get_task_states()})


class RegistryInvariantTests(unittest.TestCase):
    def _registry(self) -> Dict[str, TaskDefinition]:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp))
            register_all(scheduler)
            return dict(scheduler._definitions)

    def test_catch_up_is_opt_in_and_never_for_paid_llm_calls(self) -> None:
        reg = self._registry()
        with_gap = {n for n, d in reg.items() if d.catchup_gap_seconds}
        self.assertEqual(
            with_gap,
            {"metadata_enrichment", "plot_neighbors", "semantic_embeddings", "long_synopsis_enrichment"},
        )
        self.assertNotIn("llm_logline_enrichment", with_gap)
        for name in with_gap:
            self.assertLess(reg[name].catchup_gap_seconds, reg[name].run_interval_seconds)
            self.assertGreaterEqual(reg[name].catchup_gap_seconds, 60)

    def test_sync_heavy_tasks_run_off_the_event_loop(self) -> None:
        reg = self._registry()
        must_be_off = {
            "summary_motifs",
            "keyword_theme_tagging",
            "taste_refresh",
            "title_relations_refresh",
            "anniversary_scanner",
            "purge_candidates",
            "gap_analysis",
            "watch_history_ingest",
            "weekly_digest",
            "data_retention",
            "plot_neighbors",
            "metadata_enrichment",
            "long_synopsis_enrichment",
        }
        for name in must_be_off:
            self.assertTrue(reg[name].off_loop, f"{name} must not run on the web event loop")

    def test_loop_bound_async_tasks_stay_on_main_loop(self) -> None:
        reg = self._registry()
        # These await provider clients created on the main loop.
        for name in ("semantic_embeddings", "llm_logline_enrichment"):
            self.assertFalse(reg[name].off_loop)


class ColdPathCostTests(unittest.TestCase):
    def test_plot_neighbors_does_not_decode_all_vectors(self) -> None:
        from projectionist.scheduler.tasks import plot_neighbors

        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            with patch.object(
                Database, "get_embeddings", side_effect=AssertionError("decoded every vector")
            ):
                result = asyncio.run(
                    plot_neighbors.run(db, Settings(), lambda: False)
                )
            self.assertEqual(result["reason"], "need_at_least_two_embeddings")

    def test_embedding_item_ids_matches_get_embeddings_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            ids = []
            for i in range(3):
                item_id = db.upsert_library_item(
                    {"rating_key": f"rk{i}", "media_type": "movie", "title": f"T{i}", "summary": "plot"}
                )
                ids.append(item_id)
            db.set_embeddings([(i, [0.1, 0.2], f"h{i}") for i in ids], embedding_model="test")
            self.assertEqual(db.embedding_item_ids(), sorted(i for i, _ in db.get_embeddings()))


class ProgressCacheTests(unittest.TestCase):
    def test_progress_counts_are_memoized_briefly(self) -> None:
        from projectionist.scheduler import progress

        class Defn:
            items_per_cycle = 10
            progress_scope = "metadata_backlog"

        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            progress.clear_progress_cache()
            calls = {"n": 0}
            real = Database.count_items_needing_metadata_enrichment

            def counting(self_db):
                calls["n"] += 1
                return real(self_db)

            with patch.object(Database, "count_items_needing_metadata_enrichment", counting):
                for _ in range(5):
                    progress.progress_for_definition(db, Defn(), interval_seconds=3600)
                self.assertEqual(calls["n"], 1)
                with patch.object(progress, "PROGRESS_CACHE_TTL_SECONDS", 0):
                    progress.progress_for_definition(db, Defn(), interval_seconds=3600)
                    progress.progress_for_definition(db, Defn(), interval_seconds=3600)
                self.assertEqual(calls["n"], 3)
            progress.clear_progress_cache()


if __name__ == "__main__":
    unittest.main()
