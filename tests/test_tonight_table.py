"""Tonight's table — two unwatched under 2h, one comfort, not leftover rails."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import (
    TONIGHT_MAX_RUNTIME_MINUTES,
    feed_afterglow,
    feed_revisit_these,
    feed_tonight_table,
    feed_unfinished,
)


class TonightTableFeedTests(unittest.TestCase):
    def test_two_unwatched_and_one_comfort_under_two_hours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            db.upsert_library_item(
                {
                    "rating_key": "short-unwatched-a",
                    "media_type": "movie",
                    "title": "Ninety Minute New",
                    "year": 2024,
                    "runtime_minutes": 90,
                    "vote_average": 8.1,
                    "view_count": 0,
                    "genres": ["Thriller"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "short-unwatched-b",
                    "media_type": "movie",
                    "title": "Eighty Minute New",
                    "year": 2023,
                    "runtime_minutes": 80,
                    "vote_average": 7.4,
                    "view_count": 0,
                    "genres": ["Drama"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "comfort-rewatch",
                    "media_type": "movie",
                    "title": "Cozy Classic",
                    "year": 1998,
                    "runtime_minutes": 102,
                    "vote_average": 7.8,
                    "view_count": 3,
                    "last_viewed_at": now - 200 * 86400,
                    "genres": ["Comedy", "Family"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "too-long",
                    "media_type": "movie",
                    "title": "Three Hour Epic",
                    "year": 2021,
                    "runtime_minutes": 185,
                    "vote_average": 9.0,
                    "view_count": 0,
                    "genres": ["Drama"],
                }
            )
            payload = feed_tonight_table(db, limit=3)
            titles = [item["title"] for item in payload["items"]]
            self.assertEqual(payload["feed"], "tonight-table")
            self.assertEqual(payload["seats"]["max_runtime_minutes"], TONIGHT_MAX_RUNTIME_MINUTES)
            self.assertIn("Ninety Minute New", titles)
            self.assertIn("Eighty Minute New", titles)
            self.assertIn("Cozy Classic", titles)
            self.assertNotIn("Three Hour Epic", titles)
            seats = {item["title"]: item["table_seat"] for item in payload["items"]}
            self.assertEqual(seats["Ninety Minute New"], "unwatched")
            self.assertEqual(seats["Eighty Minute New"], "unwatched")
            self.assertEqual(seats["Cozy Classic"], "comfort")
            comfort = next(item for item in payload["items"] if item["table_seat"] == "comfort")
            self.assertIn("Comfort", comfort["why"])
            self.assertLessEqual(len(payload["items"]), 3)

    def test_distinct_from_afterglow_unfinished_and_revisit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            db.upsert_library_item(
                {
                    "rating_key": "fresh-finish",
                    "media_type": "movie",
                    "title": "Just Finished",
                    "year": 2024,
                    "runtime_minutes": 95,
                    "view_count": 1,
                    "last_viewed_at": now - 3600,
                    "genres": ["Comedy"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "leftover",
                    "media_type": "movie",
                    "title": "Forty Minutes Left",
                    "year": 2022,
                    "runtime_minutes": 100,
                    "view_count": 0,
                    "view_offset_ms": 3_600_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": now - 86400,
                    "genres": ["Drama"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "idle-show",
                    "media_type": "show",
                    "title": "Idle Show",
                    "year": 2018,
                    "total_episode_count": 10,
                    "unwatched_episode_count": 4,
                    "last_viewed_at": now - 80 * 86400,
                    "genres": ["Comedy"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "tonight-new",
                    "media_type": "movie",
                    "title": "Fresh Ninety",
                    "year": 2025,
                    "runtime_minutes": 90,
                    "view_count": 0,
                    "vote_average": 8.0,
                    "genres": ["Mystery"],
                }
            )
            tonight = feed_tonight_table(db, limit=3)
            tonight_titles = {item["title"] for item in tonight["items"]}
            unfinished = {item["title"] for item in feed_unfinished(db, limit=12)["items"]}
            afterglow = {item["title"] for item in feed_afterglow(db, limit=12)["items"]}
            revisit = {item["title"] for item in feed_revisit_these(db, limit=20)["items"]}
            self.assertIn("Fresh Ninety", tonight_titles)
            self.assertNotIn("Just Finished", tonight_titles)
            self.assertNotIn("Forty Minutes Left", tonight_titles)
            self.assertNotIn("Idle Show", tonight_titles)
            self.assertTrue(tonight_titles.isdisjoint(unfinished))
            self.assertTrue(tonight_titles.isdisjoint(afterglow))
            self.assertTrue(tonight_titles.isdisjoint(revisit))

    def test_honest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            payload = feed_tonight_table(db, limit=3)
            self.assertEqual(payload["items"], [])
            self.assertIn("unwatched", (payload["note"] or "").lower())
            self.assertIn("comfort", (payload["note"] or "").lower())
