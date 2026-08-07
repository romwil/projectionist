"""Tests for the anniversary scanner idle task."""

import asyncio
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.tasks.anniversary_scanner import run as anniversary_run, _months_ago


def _make_db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


def _settings() -> Settings:
    return Settings()


def _never_stop() -> bool:
    return False


def _today_release_iso(*, years_ago: int) -> str:
    today = date.today()
    return date(today.year - years_ago, today.month, today.day).isoformat()


class AnniversaryDetectionTests(unittest.TestCase):
    def test_release_anniversary_detected(self) -> None:
        """A movie released exactly N years ago today should be detected."""
        today = date.today()
        release_iso = _today_release_iso(years_ago=5)
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Anniversary Film",
                    "year": today.year - 5,
                    "release_date": release_iso,
                    "view_count": 3,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["found"], 1)

            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM daily_anniversaries WHERE scanned_date = ?",
                    (today.isoformat(),),
                ).fetchall()
                self.assertTrue(any("5 years ago" in str(r["anniversary_text"]) for r in rows))

    def test_no_anniversary_different_day(self) -> None:
        """Year-only or wrong month+day must not create a release anniversary."""
        today = date.today()
        other_month = (today.month % 12) + 1
        other_day = min(today.day, 28)
        wrong_iso = date(today.year - 3, other_month, other_day).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "2a",
                    "media_type": "movie",
                    "title": "Year Only",
                    "year": today.year - 3,
                    "view_count": 1,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2b",
                    "media_type": "movie",
                    "title": "Wrong Day",
                    "year": today.year - 3,
                    "release_date": wrong_iso,
                    "view_count": 1,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM daily_anniversaries
                    WHERE scanned_date = ? AND anniversary_type = 'release_anniversary'
                    """,
                    (today.isoformat(),),
                ).fetchall()
                self.assertEqual(len(rows), 0)

    def test_year_only_not_release_anniversary(self) -> None:
        """Year alone must never invent today's month+day as a release anniversary."""
        today = date.today()
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "2c",
                    "media_type": "movie",
                    "title": "Year Only Explicit",
                    "year": today.year - 7,
                    "view_count": 2,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["found"], 0)
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM daily_anniversaries
                    WHERE scanned_date = ? AND anniversary_type = 'release_anniversary'
                    """,
                    (today.isoformat(),),
                ).fetchall()
                self.assertEqual(len(rows), 0)

    def test_same_year_not_anniversary(self) -> None:
        """A movie released this year (even matching month+day) is not an anniversary."""
        today = date.today()
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "3",
                    "media_type": "movie",
                    "title": "This Year Film",
                    "year": today.year,
                    "release_date": today.isoformat(),
                    "view_count": 0,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM daily_anniversaries
                    WHERE scanned_date = ? AND anniversary_type = 'release_anniversary'
                    """,
                    (today.isoformat(),),
                ).fetchall()
                item_ids = [int(r["item_id"]) for r in rows]
                item = db.all_library_items()[0]
                self.assertNotIn(int(item["id"]), item_ids)


class WatchedAnniversaryTests(unittest.TestCase):
    def test_watched_months_ago_detected(self) -> None:
        """An item watched exactly 3 months ago today should be detected."""
        today = date.today()
        target = _months_ago(today, 3)
        watched_ts = int(time.mktime(target.timetuple()))
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "4",
                    "media_type": "movie",
                    "title": "Watched 3 Months Ago",
                    "year": 2020,
                    "view_count": 1,
                    "last_viewed_at": watched_ts,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM daily_anniversaries
                    WHERE scanned_date = ? AND anniversary_type = 'watched_anniversary'
                    """,
                    (today.isoformat(),),
                ).fetchall()
                self.assertTrue(any("3 months ago" in str(r["anniversary_text"]) for r in rows))


class EdgeCaseTests(unittest.TestCase):
    def test_missing_release_year(self) -> None:
        """Items with no year should not crash the scanner."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "5",
                    "media_type": "movie",
                    "title": "No Year",
                    "year": None,
                    "view_count": 0,
                }
            )
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")

    def test_feb29_handling(self) -> None:
        """The _months_ago helper should clamp Feb 29 safely."""
        # Feb 29 → 1 month back = Jan 29 (always valid).
        result = _months_ago(date(2024, 2, 29), 1)
        self.assertEqual(result, date(2024, 1, 29))

        # Mar 31 → 1 month back = Feb 29 in leap year.
        result = _months_ago(date(2024, 3, 31), 1)
        self.assertEqual(result, date(2024, 2, 29))

        # Mar 31 → 1 month back = Feb 28 in non-leap year.
        result = _months_ago(date(2023, 3, 31), 1)
        self.assertEqual(result, date(2023, 2, 28))

    def test_months_ago_wraps_year(self) -> None:
        """Going back more than 12 months should wrap the year correctly."""
        result = _months_ago(date(2025, 3, 15), 12)
        self.assertEqual(result, date(2024, 3, 15))

    def test_empty_library(self) -> None:
        """Scanner should complete cleanly with an empty library."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            result = asyncio.run(anniversary_run(db, _settings(), _never_stop))
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["found"], 0)

    def test_clears_previous_results_for_today(self) -> None:
        """Running twice on the same day should not duplicate results."""
        today = date.today()
        release_iso = _today_release_iso(years_ago=10)
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "6",
                    "media_type": "movie",
                    "title": "Double Run",
                    "year": today.year - 10,
                    "release_date": release_iso,
                    "view_count": 1,
                }
            )
            asyncio.run(anniversary_run(db, _settings(), _never_stop))
            asyncio.run(anniversary_run(db, _settings(), _never_stop))
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM daily_anniversaries WHERE scanned_date = ?",
                    (today.isoformat(),),
                ).fetchall()
                # Should not have duplicates.
                item_ids = [int(r["item_id"]) for r in rows if r["anniversary_type"] == "release_anniversary"]
                self.assertEqual(len(item_ids), len(set(item_ids)))
                self.assertEqual(len(item_ids), 1)

    def test_interruption(self) -> None:
        """Scanner should return interrupted status when should_stop returns True."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            for i in range(150):
                db.upsert_library_item(
                    {
                        "rating_key": str(i),
                        "media_type": "movie",
                        "title": f"Film {i}",
                        "year": 2000 + (i % 20),
                        "view_count": 0,
                    }
                )

            call_count = 0

            def stop_after_one() -> bool:
                nonlocal call_count
                call_count += 1
                return call_count > 1

            result = asyncio.run(anniversary_run(db, _settings(), stop_after_one))
            self.assertEqual(result["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
