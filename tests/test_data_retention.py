"""Tests for the data retention pruning system."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.scheduler.tasks import data_retention


def _make_db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


def _seed_telemetry(db: Database, count: int, *, days_old: int = 0) -> None:
    """Insert telemetry rows. If days_old > 0, backdate them."""
    offset = f"-{days_old} days" if days_old > 0 else "+0 seconds"
    with db.connect() as conn:
        for i in range(count):
            conn.execute(
                """
                INSERT OR IGNORE INTO system_telemetry_stream
                    (id, event_class, payload_json, timestamp)
                VALUES (?, 'test_event', '{}', datetime('now', ?))
                """,
                (f"evt-{days_old}-{i}", offset),
            )


def _seed_interaction_telemetry(db: Database, count: int, *, days_old: int = 0) -> None:
    """Insert interaction_telemetry rows."""
    import uuid
    offset = f"-{days_old} days" if days_old > 0 else "+0 seconds"
    with db.connect() as conn:
        for i in range(count):
            conn.execute(
                """
                INSERT OR IGNORE INTO interaction_telemetry
                    (id, title_id, lens_id, source, event_type, timestamp)
                VALUES (?, ?, 'general', 'test', 'view', datetime('now', ?))
                """,
                (str(uuid.uuid4()), f"title-{i}", offset),
            )


def _seed_daily_anniversaries(db: Database, count: int, *, days_old: int = 0) -> None:
    """Insert daily_anniversaries rows with a backdated scanned_date."""
    from datetime import date, timedelta
    target_date = (date.today() - timedelta(days=days_old)).isoformat()
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_anniversaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                anniversary_type TEXT NOT NULL,
                anniversary_text TEXT NOT NULL,
                scanned_date TEXT NOT NULL
            )
            """
        )
        for i in range(count):
            conn.execute(
                """
                INSERT INTO daily_anniversaries (item_id, anniversary_type, anniversary_text, scanned_date)
                VALUES (?, 'release_anniversary', 'test', ?)
                """,
                (i + 1, target_date),
            )


class PruneTelemetryTests(unittest.TestCase):
    def test_prune_deletes_old_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 5, days_old=100)
            _seed_telemetry(db, 3, days_old=10)
            deleted = db.prune_telemetry(retention_days=90)
            self.assertEqual(deleted, 5)
            with db.connect() as conn:
                remaining = conn.execute("SELECT COUNT(*) FROM system_telemetry_stream").fetchone()[0]
            self.assertEqual(remaining, 3)

    def test_prune_respects_retention_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 10, days_old=50)
            deleted = db.prune_telemetry(retention_days=90)
            self.assertEqual(deleted, 0)

    def test_prune_empty_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            deleted = db.prune_telemetry(retention_days=90)
            self.assertEqual(deleted, 0)


class PruneInteractionTelemetryTests(unittest.TestCase):
    def test_prune_deletes_old_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_interaction_telemetry(db, 4, days_old=200)
            _seed_interaction_telemetry(db, 2, days_old=5)
            deleted = db.prune_interaction_telemetry(retention_days=90)
            self.assertEqual(deleted, 4)
            with db.connect() as conn:
                remaining = conn.execute("SELECT COUNT(*) FROM interaction_telemetry").fetchone()[0]
            self.assertEqual(remaining, 2)

    def test_prune_respects_retention_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_interaction_telemetry(db, 5, days_old=30)
            deleted = db.prune_interaction_telemetry(retention_days=90)
            self.assertEqual(deleted, 0)


class PruneDailyAnniversariesTests(unittest.TestCase):
    def test_prune_deletes_old_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_daily_anniversaries(db, 3, days_old=60)
            _seed_daily_anniversaries(db, 2, days_old=5)
            deleted = db.prune_daily_anniversaries(retention_days=30)
            self.assertEqual(deleted, 3)

    def test_prune_respects_retention_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_daily_anniversaries(db, 5, days_old=10)
            deleted = db.prune_daily_anniversaries(retention_days=30)
            self.assertEqual(deleted, 0)


class VacuumTests(unittest.TestCase):
    def test_vacuum_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 50, days_old=200)
            db.prune_telemetry(retention_days=90)
            db.vacuum()


class DataRetentionTaskTests(unittest.TestCase):
    """Integration test: the data_retention scheduled task prunes and reports."""

    def test_task_prunes_old_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 10, days_old=200)
            _seed_interaction_telemetry(db, 5, days_old=200)

            settings = Settings()
            result = asyncio.run(
                data_retention.run(db, settings, lambda: False)
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["pruned"]["system_telemetry_stream"], 10)
            self.assertEqual(result["pruned"]["interaction_telemetry"], 5)
            self.assertEqual(result["total_pruned"], 15)

    def test_task_skips_recent_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 5, days_old=10)
            _seed_interaction_telemetry(db, 3, days_old=10)

            settings = Settings()
            result = asyncio.run(
                data_retention.run(db, settings, lambda: False)
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["total_pruned"], 0)
            self.assertFalse(result["vacuumed"])

    def test_vacuum_runs_when_threshold_exceeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            _seed_telemetry(db, 1100, days_old=200)

            settings = Settings()
            result = asyncio.run(
                data_retention.run(db, settings, lambda: False)
            )
            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["vacuumed"])
            self.assertGreaterEqual(result["total_pruned"], 1000)

    def test_task_respects_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            settings = Settings()
            result = asyncio.run(
                data_retention.run(db, settings, lambda: True)
            )
            self.assertEqual(result["status"], "interrupted")

    def test_task_registered_in_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            data_retention.register(scheduler)
            names = [s["name"] for s in scheduler.get_task_states()]
            self.assertIn("data_retention", names)


if __name__ == "__main__":
    unittest.main()
