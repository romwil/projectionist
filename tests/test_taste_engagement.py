"""Tests for P3c taste, weekly rail, and engagement substrate."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.taste import build_weekly_rail_for_user, deliver_member_weekly_rails
from curatorx.engagement import engagement_summary, sync_review_challenges
from curatorx.config_store import Settings
from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


class TasteEngagementDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")
        self.user_id = "bootstrap-owner"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_user_taste_override_merges_over_lens(self) -> None:
        self.db.set_lens_taste_weight(DEFAULT_LENS_ID, "noir", 0.7, explicit_lock=False)
        self.db.set_user_taste_weight(self.user_id, "noir", 0.95, explicit_lock=True)
        profile = self.db.get_effective_taste_profile(self.user_id, limit=10)
        noir = next(c for c in profile if c["cluster_tag"] == "noir")
        self.assertEqual(noir["weight"], 0.95)
        self.assertTrue(noir["explicit_lock"])
        self.assertEqual(noir["source"], "user")

    def test_weekly_rail_persists_items_with_why(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-br",
                "media_type": "movie",
                "title": "Blade Runner",
                "year": 1982,
                "genres": ["Science Fiction", "Noir"],
                "keywords": ["cyberpunk"],
                "view_count": 0,
                "vote_average": 8.1,
            }
        )
        self.db.set_user_taste_weight(self.user_id, "noir", 0.9, explicit_lock=True)
        rail = build_weekly_rail_for_user(
            self.db,
            Settings(),
            user={"id": self.user_id, "display_name": "Will", "role": "owner"},
        )
        self.assertTrue(rail["items"])
        self.assertTrue(all(item.get("why") for item in rail["items"]))
        latest = self.db.get_latest_user_weekly_rail(self.user_id)
        assert latest is not None
        self.assertEqual(latest["id"], rail["id"])

    def test_engagement_summary_seeds_challenges(self) -> None:
        summary = engagement_summary(self.db, user_id=self.user_id)
        self.assertIn("challenges", summary)
        self.assertTrue(any(c["slug"] == "rate-5-films" for c in summary["challenges"]))
        self.assertTrue(any(e["slug"] == "taste-weights" for e in summary["explainers"]))
        badges = self.db.list_engagement_badges()
        self.assertGreaterEqual(len(badges), 3)

    def test_review_challenge_progress(self) -> None:
        with self.db.connect() as conn:
            for i in range(5):
                conn.execute(
                    """
                    INSERT INTO user_title_reviews (
                        id, media_type, title, stars, created_at, updated_at, user_id
                    ) VALUES (?, 'movie', ?, 5, 1.0, 1.0, ?)
                    """,
                    (f"rev-{i}", f"Film {i}", self.user_id),
                )
        result = sync_review_challenges(self.db, self.user_id)
        self.assertEqual(result["review_count"], 5)
        progress = self.db.get_user_challenge_progress(self.user_id)
        rate5 = next(c for c in progress if c["slug"] == "rate-5-films")
        self.assertEqual(rate5["progress"], 5)
        self.assertIsNotNone(rate5["completed_at"])


class TasteEngagementApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-taste-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        self._tmpdir.cleanup()

    def test_taste_get_and_patch(self) -> None:
        self.db.set_lens_taste_weight(DEFAULT_LENS_ID, "comedy", 0.6)
        resp = self.client.get("/api/taste")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("clusters", body)
        patch = self.client.patch(
            "/api/taste",
            json={"clusters": [{"cluster_tag": "comedy", "weight": 0.85, "explicit_lock": True}]},
        )
        self.assertEqual(patch.status_code, 200)
        comedy = next(c for c in patch.json()["clusters"] if c["cluster_tag"] == "comedy")
        self.assertAlmostEqual(comedy["weight"], 0.85)
        self.assertTrue(comedy["explicit_lock"])

    def test_engagement_summary_endpoint(self) -> None:
        resp = self.client.get("/api/engagement/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("badges", body)
        self.assertIn("challenges", body)
        self.assertIn("explainers", body)

    def test_for_you_feed_and_generate(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-mx",
                "media_type": "movie",
                "title": "The Matrix",
                "year": 1999,
                "genres": ["Science Fiction", "Action"],
                "keywords": ["cyberpunk"],
                "view_count": 0,
                "vote_average": 8.5,
            }
        )
        self.db.set_user_taste_weight("bootstrap-owner", "science fiction", 0.9, explicit_lock=True)
        gen = self.client.post("/api/admin/weekly-rail/generate")
        self.assertEqual(gen.status_code, 200)
        feed = self.client.get("/api/library/feeds/for-you")
        self.assertEqual(feed.status_code, 200)
        payload = feed.json()
        self.assertEqual(payload.get("feed"), "for-you")
        self.assertIn("items", payload)

    def test_deliver_weekly_rails_helper(self) -> None:
        result = deliver_member_weekly_rails(self.db, Settings())
        self.assertIn("built", result)
        self.assertEqual(result["llm_cap"], 5)


if __name__ == "__main__":
    unittest.main()
