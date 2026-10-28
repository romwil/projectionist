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
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
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
        self.assertNotEqual(body["why"], "Unwatched pick for you")

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
        self.assertEqual(body["why"], "")
        self.assertNotIn("Unwatched pick for you", str(body.get("why") or ""))

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

    def test_quick_pick_does_not_always_repeat_named_bridge(self) -> None:
        from projectionist.library.plot_kinship import plot_link_json, specific_plot_link
        from projectionist.watch_tracker.models import WatchEventInput
        from projectionist.watch_tracker.store import ingest_watch_events

        bake = "Amateur bakers compete around a signature bake inside a failing colony."
        spy = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."
        seed_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "summary": bake,
                "view_count": 0,
                "genres": ["Crime"],
            }
        )
        named_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-thief",
                "media_type": "movie",
                "title": "Thief",
                "year": 1981,
                "summary": spy,
                "view_count": 0,
                "genres": ["Crime"],
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-random",
                "media_type": "movie",
                "title": "Random Unwatched",
                "year": 2020,
                "summary": "A surprise with no named bridge.",
                "view_count": 0,
                "genres": ["Comedy"],
            }
        )
        self.db.upsert_plex_user(
            user_id="viewer-a",
            display_name="Viewer A",
            email=None,
            plex_user_id="plex-a",
            role="member",
        )
        ingest_watch_events(
            self.db,
            [
                WatchEventInput(
                    source="plex_history",
                    source_event_id="heat-played",
                    source_event_kind="history_played",
                    server_machine_id="server",
                    source_user_key="plex-a",
                    rating_key="rk-heat",
                    media_type="movie",
                    occurred_at_ms=1_704_067_200_000,
                    terminal=True,
                ),
            ],
        )
        link = specific_plot_link(seed_text=bake, peer_text=spy, shelf_labels=set())
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (seed_id, named_id, 0.92, 0.8, 1 if link else 0, plot_link_json(link) or "{}"),
            )

        titles = set()
        for _ in range(30):
            resp = self.client.get("/api/library/quick-pick")
            self.assertEqual(resp.status_code, 200)
            item = resp.json().get("item") or {}
            title = str(item.get("title") or "")
            if title:
                titles.add(title)
        self.assertIn("Random Unwatched", titles)
        self.assertGreater(len(titles), 1)


if __name__ == "__main__":
    unittest.main()
