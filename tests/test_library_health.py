"""Tests for library health metrics."""

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.library.health import compute_library_health


class LibraryHealthTests(unittest.TestCase):
    def test_compute_library_health_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Unwatched",
                    "view_count": 0,
                    "added_at": 1,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Watched",
                    "view_count": 2,
                }
            )
            health = compute_library_health(db)
            self.assertEqual(health["total"], 2)
            self.assertEqual(health["unwatched_count"], 1)
            self.assertEqual(health["unwatched_pct"], 50.0)
            self.assertEqual(health["watched_count"], 1)
            self.assertEqual(health["rating_coverage_pct"], 0.0)
            self.assertEqual(health["by_media_type"]["movie"]["total"], 2)
            self.assertEqual(health["by_media_type"]["movie"]["unwatched_count"], 1)
            self.assertEqual(health["by_media_type"]["movie"]["unwatched_pct"], 50.0)
            self.assertEqual(health["by_media_type"]["movie"]["stale_adds"], 1)
            self.assertEqual(health["by_media_type"]["show"]["total"], 0)
            self.assertEqual(health["by_media_type"]["show"]["unwatched_count"], 0)
            self.assertEqual(health["by_media_type"]["show"]["stale_adds"], 0)

    def test_compute_library_health_by_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "m1",
                    "media_type": "movie",
                    "title": "Unwatched Movie",
                    "view_count": 0,
                    "added_at": 1,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "m2",
                    "media_type": "movie",
                    "title": "Watched Movie",
                    "view_count": 1,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "s1",
                    "media_type": "show",
                    "title": "Unwatched Show",
                    "view_count": 0,
                    "added_at": 1,
                }
            )
            health = compute_library_health(db)
            self.assertEqual(health["total"], 3)
            self.assertEqual(health["unwatched_count"], 2)
            self.assertEqual(health["stale_adds"], 2)
            movie = health["by_media_type"]["movie"]
            show = health["by_media_type"]["show"]
            self.assertEqual(movie["total"], 2)
            self.assertEqual(movie["unwatched_count"], 1)
            self.assertEqual(movie["stale_adds"], 1)
            self.assertEqual(show["total"], 1)
            self.assertEqual(show["unwatched_count"], 1)
            self.assertEqual(show["unwatched_pct"], 100.0)
            self.assertEqual(show["stale_adds"], 1)


if __name__ == "__main__":
    unittest.main()
