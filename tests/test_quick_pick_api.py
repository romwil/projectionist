"""API contract tests for GET /api/library/quick-pick (Surprise Me)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class QuickPickApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_quick_pick_empty_library_returns_null_item(self) -> None:
        resp = self.client.get("/api/library/quick-pick")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["item"])
        self.assertIn("unwatched", body["why"].lower())

    def test_quick_pick_returns_unwatched_title(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-watched",
                "media_type": "movie",
                "title": "Already Seen",
                "year": 2001,
                "view_count": 3,
                "genres": ["Drama"],
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-fresh",
                "media_type": "movie",
                "title": "Fresh Pick",
                "year": 2020,
                "view_count": 0,
                "genres": ["Science Fiction"],
                "runtime_minutes": 116,
                "summary": "A surprise.",
            }
        )

        resp = self.client.get("/api/library/quick-pick")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body["item"])
        self.assertEqual(body["item"]["title"], "Fresh Pick")
        self.assertTrue(body["item"]["in_library"])
        self.assertIn("overview", body["item"])
        self.assertEqual(body["item"]["genres"], ["Science Fiction"])
        self.assertIn("why", body)
        self.assertTrue(body["why"])

    def test_quick_pick_treats_null_view_count_as_unwatched(self) -> None:
        item_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-null-views",
                "media_type": "movie",
                "title": "Null Views",
                "year": 2011,
                "genres": ["Comedy"],
            }
        )
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE library_items SET view_count = NULL WHERE id = ?",
                (item_id,),
            )

        resp = self.client.get("/api/library/quick-pick")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body["item"])
        self.assertEqual(body["item"]["title"], "Null Views")
        self.assertEqual(body["item"]["view_count"], 0)

    def test_quick_pick_tolerates_malformed_genres_json(self) -> None:
        item_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-bad-genres",
                "media_type": "movie",
                "title": "Broken Genres",
                "year": 1999,
                "view_count": 0,
            }
        )
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE library_items SET genres = ? WHERE id = ?",
                ("not-json", item_id),
            )

        resp = self.client.get("/api/library/quick-pick")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body["item"])
        self.assertEqual(body["item"]["title"], "Broken Genres")
        self.assertEqual(body["item"]["genres"], [])
        self.assertEqual(body["why"], "Unwatched pick for you")

    def test_quick_pick_genre_filter_or_match(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-horror",
                "media_type": "movie",
                "title": "Horror Only",
                "year": 2018,
                "view_count": 0,
                "genres": ["Horror"],
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-drama",
                "media_type": "movie",
                "title": "Drama Only",
                "year": 2019,
                "view_count": 0,
                "genres": ["Drama"],
            }
        )

        resp = self.client.get("/api/library/quick-pick", params={"genre": "Horror"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["item"]["title"], "Horror Only")


if __name__ == "__main__":
    unittest.main()
