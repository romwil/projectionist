"""Tests for first-start idle task bootstrap sequencing."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.bootstrap import (
    BOOTSTRAP_COMPLETED_KEY,
    is_bootstrap_completed,
    run_idle_bootstrap,
    select_bootstrap_tasks,
)
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition, TaskState


def _make_db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


async def _noop_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    return {"status": "completed", "processed": 1}


class SelectBootstrapTasksTests(unittest.TestCase):
    def test_selects_never_run_foundational_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Needs Plot",
                    "year": 2001,
                    "summary": "A short Plex summary with enough text for embeddings.",
                }
            )
            # metadata backlog is typically non-zero for a fresh title without TMDB fill
            states = [
                TaskState(name="summary_motifs", last_run_at=None),
                TaskState(name="keyword_theme_tagging", last_run_at=None),
                TaskState(name="long_synopsis_enrichment", last_run_at=None),
                TaskState(name="semantic_embeddings", last_run_at=None),
                TaskState(name="metadata_enrichment", last_run_at=None),
            ]
            selected = select_bootstrap_tasks(db, Settings(), states)
            self.assertIn("summary_motifs", selected)
            self.assertIn("keyword_theme_tagging", selected)
            self.assertIn("long_synopsis_enrichment", selected)
            self.assertIn("semantic_embeddings", selected)
            # Order is foundational sequence
            self.assertEqual(
                selected,
                [name for name in selected],
            )
            order = [
                "metadata_enrichment",
                "summary_motifs",
                "keyword_theme_tagging",
                "long_synopsis_enrichment",
                "semantic_embeddings",
            ]
            idxs = [order.index(name) for name in selected]
            self.assertEqual(idxs, sorted(idxs))

    def test_skips_synopsis_when_source_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            states = [
                TaskState(name="summary_motifs", last_run_at=None),
                TaskState(name="long_synopsis_enrichment", last_run_at=None),
            ]
            selected = select_bootstrap_tasks(
                db, Settings(long_synopsis_source="off"), states
            )
            self.assertIn("summary_motifs", selected)
            self.assertNotIn("long_synopsis_enrichment", selected)

    def test_skips_tasks_that_already_ran(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            states = [
                TaskState(name="summary_motifs", last_run_at=1_700_000_000.0),
                TaskState(name="keyword_theme_tagging", last_run_at=None),
            ]
            selected = select_bootstrap_tasks(db, Settings(), states)
            self.assertNotIn("summary_motifs", selected)
            self.assertIn("keyword_theme_tagging", selected)

    def test_skips_embeddings_when_any_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            item_id = db.upsert_library_item(
                {
                    "rating_key": "9",
                    "media_type": "movie",
                    "title": "Already Embedded",
                    "year": 1999,
                    "summary": "Has plot text.",
                }
            )
            db.set_embedding(item_id, [0.1, 0.2, 0.3])
            states = [TaskState(name="semantic_embeddings", last_run_at=None)]
            selected = select_bootstrap_tasks(db, Settings(), states)
            self.assertNotIn("semantic_embeddings", selected)


class RunIdleBootstrapTests(unittest.TestCase):
    def test_marks_completed_and_does_not_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, data_dir, idle_threshold_minutes=0)
            ran: List[str] = []

            async def tracking_task(
                _db: Database, _settings: Settings, should_stop: Callable[[], bool]
            ) -> Dict[str, Any]:
                del should_stop
                ran.append("summary_motifs")
                return {"status": "completed"}

            scheduler.register(
                TaskDefinition(
                    name="summary_motifs",
                    run_interval_seconds=3600,
                    run_fn=tracking_task,
                )
            )
            scheduler.register(
                TaskDefinition(
                    name="keyword_theme_tagging",
                    run_interval_seconds=3600,
                    run_fn=_noop_task,
                )
            )

            first = asyncio.run(run_idle_bootstrap(scheduler))
            self.assertEqual(first["status"], "completed")
            self.assertIn("summary_motifs", first["tasks"])
            self.assertTrue(is_bootstrap_completed(db))
            self.assertEqual(db.get_config(BOOTSTRAP_COMPLETED_KEY), "1")

            ran.clear()
            second = asyncio.run(run_idle_bootstrap(scheduler))
            self.assertEqual(second["status"], "already_completed")
            self.assertEqual(ran, [])

    def test_empty_selection_marks_completed_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, data_dir, idle_threshold_minutes=0)
            # Register tasks that already have last_run_at via a prior trigger.
            scheduler.register(
                TaskDefinition(
                    name="summary_motifs",
                    run_interval_seconds=3600,
                    run_fn=_noop_task,
                )
            )
            asyncio.run(scheduler.trigger_task("summary_motifs"))

            result = asyncio.run(run_idle_bootstrap(scheduler))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["tasks"], [])
            self.assertTrue(is_bootstrap_completed(db))


if __name__ == "__main__":
    unittest.main()
