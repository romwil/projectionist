"""Unit tests for scheduled-task progress / ETA helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.scheduler.progress import estimate_progress, progress_for_definition
from curatorx.scheduler.engine import TaskDefinition


class ProgressEstimateTests(unittest.TestCase):
    def test_estimate_scales_with_interval(self) -> None:
        base = estimate_progress(
            remaining=100,
            items_per_cycle=25,
            interval_seconds=21600,
            library_size=500,
            scope="metadata_backlog",
        )
        assert base is not None
        self.assertEqual(base["estimated_cycles"], 4)
        self.assertEqual(base["estimated_seconds"], 86400)

        faster = estimate_progress(
            remaining=100,
            items_per_cycle=25,
            interval_seconds=3600,
            library_size=500,
            scope="metadata_backlog",
        )
        assert faster is not None
        self.assertEqual(faster["estimated_seconds"], 14400)

    def test_progress_for_metadata_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            defn = TaskDefinition(
                name="metadata_enrichment",
                run_interval_seconds=21600,
                items_per_cycle=25,
                progress_scope="metadata_backlog",
                description="Trickle metadata",
            )
            progress = progress_for_definition(db, defn, interval_seconds=21600)
            assert progress is not None
            self.assertEqual(progress["remaining_items"], 0)
            self.assertEqual(progress["estimated_seconds"], 0)
            self.assertEqual(progress["items_per_cycle"], 25)

    def test_neighbors_backlog_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self.assertEqual(db.count_items_missing_neighbors(), 0)
            defn = TaskDefinition(
                name="plot_neighbors",
                run_interval_seconds=43200,
                items_per_cycle=15,
                progress_scope="neighbors_backlog",
            )
            progress = progress_for_definition(db, defn, interval_seconds=43200)
            assert progress is not None
            self.assertEqual(progress["scope"], "neighbors_backlog")
            self.assertEqual(progress["remaining_items"], 0)

    def test_measured_eta_overrides_theoretical(self) -> None:
        progress = estimate_progress(
            remaining=100,
            items_per_cycle=25,
            interval_seconds=21600,
            library_size=500,
            scope="neighbors_backlog",
            items_per_hour=50,
        )
        assert progress is not None
        self.assertEqual(progress["eta_source"], "measured")
        self.assertEqual(progress["estimated_seconds"], 7200)


if __name__ == "__main__":
    unittest.main()
