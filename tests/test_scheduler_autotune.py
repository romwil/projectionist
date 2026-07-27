"""Unit tests for idle-task auto-tune batch/interval adjustments."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.scheduler.autotune import (
    BATCH_BOUNDS,
    evaluate_autotune,
    resolve_batch_size,
)


class AutotuneEvaluationTests(unittest.TestCase):
    def test_raises_batch_when_fast_and_backlogged(self) -> None:
        decision = evaluate_autotune(
            name="plot_neighbors",
            status="completed",
            duration_ms=20_000,
            timeout_seconds=300,
            items_per_cycle=15,
            interval_seconds=43200,
            items_processed=15,
            remaining_items=4000,
            has_more=True,
        )
        self.assertTrue(decision.changed)
        self.assertGreater(decision.items_per_cycle or 0, 15)
        self.assertIn("headroom_raise_batch", decision.reasons or [])
        # Large backlog vs 7d horizon should also shorten interval.
        self.assertLess(decision.run_interval_seconds or 43200, 43200)
        self.assertIn("backlog_eta_shorten_interval", decision.reasons or [])

    def test_lowers_batch_near_timeout(self) -> None:
        decision = evaluate_autotune(
            name="metadata_enrichment",
            status="completed",
            duration_ms=270_000,
            timeout_seconds=300,
            items_per_cycle=40,
            interval_seconds=21600,
            items_processed=40,
            remaining_items=200,
            has_more=True,
        )
        self.assertTrue(decision.changed)
        self.assertLess(decision.items_per_cycle or 40, 40)
        self.assertIn("near_timeout_lower_batch", decision.reasons or [])

    def test_respects_batch_caps(self) -> None:
        lo, hi = BATCH_BOUNDS["llm_logline_enrichment"]
        decision = evaluate_autotune(
            name="llm_logline_enrichment",
            status="completed",
            duration_ms=5_000,
            timeout_seconds=300,
            items_per_cycle=hi,
            interval_seconds=86400,
            items_processed=hi,
            remaining_items=5000,
            has_more=True,
        )
        self.assertLessEqual(decision.items_per_cycle or hi, hi)
        self.assertGreaterEqual(decision.items_per_cycle or lo, lo)

    def test_skips_non_autotune_tasks(self) -> None:
        decision = evaluate_autotune(
            name="health_metrics",
            status="completed",
            duration_ms=1000,
            timeout_seconds=300,
            items_per_cycle=10,
            interval_seconds=3600,
            items_processed=1,
            remaining_items=100,
        )
        self.assertFalse(decision.changed)

    def test_resolve_batch_reads_persisted_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_tasks (
                        name TEXT PRIMARY KEY,
                        enabled INTEGER DEFAULT 1,
                        run_interval_seconds INTEGER NOT NULL,
                        items_per_cycle INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO scheduled_tasks (name, enabled, run_interval_seconds, items_per_cycle)
                    VALUES ('plot_neighbors', 1, 3600, 42)
                    """
                )
            self.assertEqual(resolve_batch_size(db, "plot_neighbors", 15), 42)
            self.assertEqual(resolve_batch_size(db, "plot_neighbors", 15), 42)


class OptimizeRatesTests(unittest.TestCase):
    def test_optimize_rates_dry_run_and_apply(self) -> None:
        from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
        from projectionist.scheduler.run_history import append_task_run, ensure_run_history_table

        async def _noop(db, settings, should_stop):  # noqa: ARG001
            return {"status": "completed", "seeds": 15, "has_more": True}

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db = Database(data_dir / "test.db")
            with db.connect() as conn:
                ensure_run_history_table(conn)
            scheduler = IdleScheduler(db, data_dir)
            scheduler.register(
                TaskDefinition(
                    name="plot_neighbors",
                    run_interval_seconds=43200,
                    enabled=True,
                    timeout_seconds=300,
                    run_fn=_noop,
                    items_per_cycle=15,
                    progress_scope="neighbors_backlog",
                )
            )
            scheduler.update_task(
                "plot_neighbors",
                run_interval_seconds=43200,
                items_per_cycle=15,
            )
            append_task_run(
                db,
                name="plot_neighbors",
                started_at=1_700_000_000,
                finished_at=1_700_000_020,
                duration_ms=20_000,
                status="completed",
                trigger="schedule",
                items_processed=15,
                metrics={"has_more": True},
            )

            preview = scheduler.optimize_autotune_rates(dry_run=True)
            self.assertTrue(preview["dry_run"])
            self.assertGreaterEqual(preview["changed_count"], 1)
            plot = next(row for row in preview["changed"] if row["name"] == "plot_neighbors")
            self.assertFalse(plot["applied"])
            self.assertGreater(plot["items_per_cycle_after"] or 0, 15)

            # Dry-run must not persist.
            after_preview = scheduler.update_task("plot_neighbors")
            self.assertEqual(after_preview["items_per_cycle"], 15)

            applied = scheduler.optimize_autotune_rates(dry_run=False)
            self.assertFalse(applied["dry_run"])
            plot_applied = next(
                row for row in applied["changed"] if row["name"] == "plot_neighbors"
            )
            self.assertTrue(plot_applied["applied"])
            state = scheduler.update_task("plot_neighbors")
            self.assertEqual(state["items_per_cycle"], plot_applied["items_per_cycle_after"])


if __name__ == "__main__":
    unittest.main()
