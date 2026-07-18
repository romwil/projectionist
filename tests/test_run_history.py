"""Tests for durable scheduled-task run history and rate aggregation."""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.scheduler.run_history import (
    aggregate_task_rate,
    append_task_run,
    extract_items_processed,
    list_task_runs,
    prune_scheduled_task_runs,
)


async def _enrich_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    return {"status": "completed", "enriched": 7, "errors": 0, "has_more": True}


class RunHistoryPersistenceTests(unittest.TestCase):
    def test_extract_items_prefers_enriched(self) -> None:
        self.assertEqual(extract_items_processed({"enriched": 5, "errors": 1}), 5)
        self.assertEqual(extract_items_processed({"seeds": 12, "processed": 300}), 12)
        self.assertIsNone(extract_items_processed({"status": "completed"}))

    def test_append_list_prune_and_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = time.time()
            append_task_run(
                db,
                name="metadata_enrichment",
                started_at=now - 7200,
                finished_at=now - 7100,
                duration_ms=1800,
                status="completed",
                trigger="schedule",
                metrics={"enriched": 10},
                items_processed=10,
            )
            append_task_run(
                db,
                name="metadata_enrichment",
                started_at=now - 3600,
                finished_at=now - 3500,
                duration_ms=2200,
                status="completed",
                trigger="schedule",
                metrics={"enriched": 15},
                items_processed=15,
            )
            append_task_run(
                db,
                name="metadata_enrichment",
                started_at=now - 1000,
                finished_at=now - 900,
                duration_ms=500,
                status="error: boom",
                trigger="manual",
                error="boom",
                items_processed=0,
            )
            # Old row outside retention.
            append_task_run(
                db,
                name="metadata_enrichment",
                started_at=now - (100 * 86400),
                finished_at=now - (100 * 86400) + 10,
                duration_ms=100,
                status="completed",
                trigger="schedule",
                items_processed=3,
            )

            runs = list_task_runs(db, "metadata_enrichment", limit=10)
            self.assertGreaterEqual(len(runs), 3)

            rate = aggregate_task_rate(
                db,
                "metadata_enrichment",
                lookback_hours=24,
                interval_seconds=3600,
            )
            self.assertEqual(rate["completed_count"], 2)
            self.assertEqual(rate["error_count"], 1)
            self.assertEqual(rate["items_processed_total"], 25)
            self.assertIsNotNone(rate["items_per_hour"])
            self.assertGreater(float(rate["items_per_hour"]), 0)
            self.assertIsNotNone(rate["duration_p50_ms"])
            self.assertIsNotNone(rate["duration_p95_ms"])
            self.assertAlmostEqual(float(rate["success_rate"] or 0), 2 / 3, places=3)

            pruned = prune_scheduled_task_runs(db, 30)
            self.assertEqual(pruned, 1)
            remaining = list_task_runs(db, "metadata_enrichment", limit=20)
            self.assertEqual(len(remaining), 3)

    def test_scheduler_persists_history_on_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(
                    name="metadata_enrichment",
                    run_interval_seconds=3600,
                    run_fn=_enrich_task,
                    items_per_cycle=25,
                    progress_scope="metadata_backlog",
                )
            )
            result = asyncio.run(scheduler.trigger_task("metadata_enrichment"))
            self.assertEqual(result["status"], "completed")

            history = scheduler.get_task_history("metadata_enrichment")
            self.assertEqual(history["count"], 1)
            run = history["runs"][0]
            self.assertEqual(run["items_processed"], 7)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["trigger"], "manual")

            rate = scheduler.get_task_rate("metadata_enrichment")
            self.assertEqual(rate["items_processed_total"], 7)
            self.assertIsNotNone(rate["items_per_hour"])

            states = scheduler.get_task_states()
            meta = next(item for item in states if item["name"] == "metadata_enrichment")
            self.assertIsInstance(meta.get("rate"), dict)
            # Fast productive run with backlog → auto-tune may raise batch above default.
            self.assertGreaterEqual(int(meta["items_per_cycle"]), 25)
            self.assertTrue(
                history["runs"][0]["metrics"].get("autotune_changed")
                or meta["items_per_cycle"] == 25
            )


if __name__ == "__main__":
    unittest.main()
