"""Tests for personal review store and API."""

from __future__ import annotations

import importlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.reviews.store import (
    dismiss_prompt,
    get_reviews,
    list_pending_prompts,
    mark_prompts_surfaced,
    queue_rating_prompt,
    save_review,
    scan_for_rating_prompts,
)


class ReviewStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "reviews.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _seed_near_complete_movie(self, *, rating_key: str = "movie-1", title: str = "Inception") -> None:
        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_items (
                    rating_key, media_type, title, view_offset_ms, duration_ms, updated_at
                ) VALUES (?, 'movie', ?, 5400000, 6000000, ?)
                """,
                (rating_key, title, now),
            )

    def test_save_and_get_review(self) -> None:
        saved = save_review(
            self.db,
            stars=4,
            title="Inception",
            media_type="movie",
            rating_key="movie-1",
            tmdb_id=27205,
            review_text="Mind-bending and rewatchable",
            review_tags=["great-score"],
            prompted_by="user",
        )
        self.assertEqual(saved["stars"], 4)
        self.assertEqual(saved["title"], "Inception")

        items = get_reviews(self.db, rating_key="movie-1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["review_text"], "Mind-bending and rewatchable")
        self.assertEqual(items[0]["review_tags"], ["great-score"])

    def test_save_review_accepts_half_stars(self) -> None:
        saved = save_review(
            self.db,
            stars=4.5,
            title="Ghost in the Shell 2.0",
            media_type="movie",
            rating_key="gits-2",
        )
        self.assertEqual(saved["stars"], 4.5)
        items = get_reviews(self.db, rating_key="gits-2")
        self.assertEqual(items[0]["stars"], 4.5)

    def test_list_titles_to_rate_prefers_viewed_unrated(self) -> None:
        from curatorx.reviews.store import list_titles_to_rate

        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_items (
                    rating_key, media_type, title, view_count, last_viewed_at, updated_at
                ) VALUES ('viewed-1', 'movie', 'Heat', 2, ?, ?)
                """,
                (now, now),
            )
        items = list_titles_to_rate(self.db, limit=5)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Heat")
        self.assertEqual(items[0]["reason"], "watched_no_review")

    def test_scan_queues_near_complete_without_review(self) -> None:
        self._seed_near_complete_movie()
        queued = scan_for_rating_prompts(self.db)
        self.assertEqual(queued, 1)

        prompts = list_pending_prompts(self.db)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["title"], "Inception")
        self.assertGreaterEqual(prompts[0]["completion_pct"], 85.0)

    def test_scan_skips_reviewed_title(self) -> None:
        self._seed_near_complete_movie()
        save_review(
            self.db,
            stars=5,
            title="Inception",
            media_type="movie",
            rating_key="movie-1",
        )
        queued = scan_for_rating_prompts(self.db)
        self.assertEqual(queued, 0)
        self.assertEqual(list_pending_prompts(self.db), [])

    def test_dismiss_prompt_hides_pending_item(self) -> None:
        self._seed_near_complete_movie()
        scan_for_rating_prompts(self.db)
        prompt = list_pending_prompts(self.db)[0]
        dismissed = dismiss_prompt(self.db, prompt["id"])
        self.assertIsNotNone(dismissed["dismissed_at"])
        self.assertEqual(list_pending_prompts(self.db), [])

    def test_save_review_links_prompt(self) -> None:
        self._seed_near_complete_movie()
        scan_for_rating_prompts(self.db)
        prompt = list_pending_prompts(self.db)[0]
        save_review(
            self.db,
            stars=3,
            title="Inception",
            media_type="movie",
            rating_key="movie-1",
            prompt_id=prompt["id"],
            prompted_by="near_complete",
        )
        self.assertEqual(list_pending_prompts(self.db), [])

    def test_mark_prompts_surfaced_sets_prompted_at(self) -> None:
        self._seed_near_complete_movie()
        scan_for_rating_prompts(self.db)
        prompt = list_pending_prompts(self.db)[0]
        self.assertIsNone(prompt["prompted_at"])
        marked = mark_prompts_surfaced(self.db, [prompt["id"]])
        self.assertEqual(marked, 1)
        updated = list_pending_prompts(self.db)[0]
        self.assertIsNotNone(updated["prompted_at"])

    def test_scan_uses_tautulli_when_local_progress_missing(self) -> None:
        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_items (
                    rating_key, media_type, title, updated_at
                ) VALUES ('tautulli-movie', 'movie', 'Arrival', ?)
                """,
                (now,),
            )
        settings = Settings(tautulli_url="http://tautulli.local", tautulli_api_key="test-key")
        with patch("curatorx.connectors.tautulli.TautulliClient") as mock_client_cls:
            mock_client_cls.return_value.get_metadata.return_value = {
                "view_offset": 5_000_000,
                "duration": 5_500_000,
            }
            queued = scan_for_rating_prompts(self.db, settings)
        self.assertEqual(queued, 1)
        prompts = list_pending_prompts(self.db)
        self.assertEqual(prompts[0]["title"], "Arrival")

    def test_queue_rating_prompt_respects_reviewed_title(self) -> None:
        save_review(
            self.db,
            stars=4,
            title="Inception",
            media_type="movie",
            rating_key="movie-reviewed",
        )
        queued = queue_rating_prompt(
            self.db,
            rating_key="movie-reviewed",
            media_type="movie",
            title="Inception",
            completion_pct=92.0,
        )
        self.assertFalse(queued)


class ReviewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_create_and_list_reviews(self) -> None:
        create = self.client.post(
            "/api/reviews",
            json={
                "title": "The Matrix",
                "media_type": "movie",
                "stars": 5,
                "rating_key": "matrix-1",
                "review_text": "Still holds up",
            },
        )
        self.assertEqual(create.status_code, 200)
        body = create.json()
        self.assertEqual(body["stars"], 5)
        self.assertEqual(body["title"], "The Matrix")

        listed = self.client.get("/api/reviews")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)

    def test_review_prompts_flow(self) -> None:
        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_items (
                    rating_key, media_type, title, view_offset_ms, duration_ms, updated_at
                ) VALUES ('prompt-movie', 'movie', 'Arrival', 5000000, 5500000, ?)
                """,
                (now,),
            )
        scan_for_rating_prompts(self.db)

        prompts = self.client.get("/api/reviews/prompts")
        self.assertEqual(prompts.status_code, 200)
        items = prompts.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertIsNotNone(items[0]["prompted_at"])
        prompt_id = items[0]["id"]

        dismissed = self.client.post(f"/api/reviews/prompts/{prompt_id}/dismiss")
        self.assertEqual(dismissed.status_code, 200)
        self.assertIsNotNone(dismissed.json()["dismissed_at"])

        empty = self.client.get("/api/reviews/prompts")
        self.assertEqual(empty.json()["count"], 0)

    def test_create_review_rejects_invalid_stars(self) -> None:
        resp = self.client.post(
            "/api/reviews",
            json={"title": "Bad", "media_type": "movie", "stars": 0},
        )
        self.assertEqual(resp.status_code, 422)

    def test_create_review_accepts_half_stars(self) -> None:
        resp = self.client.post(
            "/api/reviews",
            json={
                "title": "Heat",
                "media_type": "movie",
                "stars": 4.5,
                "rating_key": "heat-half",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stars"], 4.5)


if __name__ == "__main__":
    unittest.main()
