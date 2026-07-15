"""CA release readiness — novice/edge paths and polished errors."""

from __future__ import annotations

import importlib
import os
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings
from curatorx.connectors.http import optional_int
from curatorx.connectors.plex import PlexClient, PlexLibraryItem
from curatorx.library.db import Database
from curatorx.library.sync import _row_from_plex_item, sync_library
from curatorx.reviews.plex_sync import sync_review_rating_to_plex
from curatorx.reviews.store import save_review
from curatorx.web.job_progress import format_job_progress, friendly_job_error
from curatorx.web.webhooks import handle_plex_webhook


class JobProgressContractTests(unittest.TestCase):
    def test_format_job_progress_returns_percent_message_and_label(self) -> None:
        percent, message, label = format_job_progress("movies", 1, 2, "Fetching Plex movies")
        self.assertIsInstance(percent, int)
        self.assertGreaterEqual(percent, 0)
        self.assertLessEqual(percent, 99)
        self.assertTrue(message)
        self.assertTrue(label)

    def test_friendly_job_error_strips_noise(self) -> None:
        text = friendly_job_error(RuntimeError("HTTP 500 from http://plex: connection refused"))
        self.assertIn("connection refused", text.lower())
        self.assertNotIn("HTTP 500", text)


class OptionalIntEdgeTests(unittest.TestCase):
    def test_float_like_and_empty(self) -> None:
        self.assertEqual(optional_int("9.0"), 9)
        self.assertEqual(optional_int("9.7"), 9)
        self.assertEqual(optional_int("10.0"), 10)
        self.assertIsNone(optional_int(None))
        self.assertIsNone(optional_int(""))

    def test_invalid_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            optional_int("not-a-number")


class PlexParseMissingFieldsTests(unittest.TestCase):
    def test_parse_video_tolerates_missing_optional_fields(self) -> None:
        client = PlexClient("http://plex.test:32400", "token")
        element = ET.fromstring('<Video ratingKey="42" title="Bare Bones" type="movie" />')
        item = client._parse_video(element, "movie")
        self.assertEqual(item.rating_key, "42")
        self.assertEqual(item.title, "Bare Bones")
        self.assertIsNone(item.year)
        self.assertIsNone(item.user_rating_stars)
        self.assertEqual(item.view_count, 0)
        self.assertIsNone(item.duration_ms)

    def test_row_from_plex_item_with_sparse_fields(self) -> None:
        item = PlexLibraryItem(
            rating_key="sparse-1",
            media_type="movie",
            title="Sparse",
            year=None,
            user_rating_stars=None,
        )
        row = _row_from_plex_item(
            item,
            PlexClient("http://plex.test", "t"),
            None,
            None,
            in_radarr=False,
            in_sonarr=False,
        )
        self.assertEqual(row["rating_key"], "sparse-1")
        self.assertIsNone(row["year"])
        self.assertIsNone(row["plex_user_rating_stars"])


class EmptyLibrarySyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_library_with_empty_plex_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "empty.db")
            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            with patch.object(PlexClient, "movie_items", return_value=[]), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "curatorx.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "curatorx.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "curatorx.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)
            self.assertEqual(result["items_synced"], 0)
            self.assertEqual(db.all_library_items(), [])


class PlexSyncReasonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "sync.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_missing_rating_key_reason(self) -> None:
        saved = save_review(self.db, stars=4, title="No Key", media_type="movie")
        result = sync_review_rating_to_plex(
            self.db,
            Settings(plex_url="http://plex.test", plex_token="t", sync_reviews_to_plex=True),
            saved,
        )
        self.assertFalse(result["synced"])
        self.assertEqual(result["reason"], "missing_rating_key")

    def test_plex_not_configured_reason(self) -> None:
        saved = save_review(
            self.db,
            stars=4,
            title="Arrival",
            media_type="movie",
            rating_key="rk-1",
        )
        result = sync_review_rating_to_plex(
            self.db,
            Settings(sync_reviews_to_plex=True),
            saved,
        )
        self.assertFalse(result["synced"])
        self.assertEqual(result["reason"], "plex_not_configured")

    def test_plex_error_reason(self) -> None:
        saved = save_review(
            self.db,
            stars=4,
            title="Arrival",
            media_type="movie",
            rating_key="rk-2",
        )
        with patch(
            "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
            return_value=None,
        ), patch.object(PlexClient, "set_user_rating", side_effect=RuntimeError("plex down")):
            result = sync_review_rating_to_plex(
                self.db,
                Settings(plex_url="http://plex.test", plex_token="t", sync_reviews_to_plex=True),
                saved,
            )
        self.assertFalse(result["synced"])
        self.assertEqual(result["reason"], "plex_error")


class CaApiFixture(unittest.TestCase):
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
        self.app_mod = app_mod

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()


class AuthDisabledDefaultTests(CaApiFixture):
    def test_features_auth_disabled_bootstrap_owner(self) -> None:
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["auth"]["mode"], "disabled")
        self.assertFalse(body["features"]["multi_user_enabled"])
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["role"], "owner")

    def test_library_stats_and_reviews_without_login_cookie(self) -> None:
        stats = self.client.get("/api/library/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total"], 0)

        reviews = self.client.get("/api/reviews")
        self.assertEqual(reviews.status_code, 200)
        self.assertEqual(reviews.json()["count"], 0)

        create = self.client.post(
            "/api/reviews",
            json={"title": "Solo", "media_type": "movie", "stars": 4},
        )
        self.assertEqual(create.status_code, 200)


class LibraryApiContractTests(CaApiFixture):
    def test_library_stats_zeros_before_sync(self) -> None:
        resp = self.client.get("/api/library/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["movies"], 0)
        self.assertEqual(body["shows"], 0)
        self.assertEqual(body["total"], 0)
        self.assertIsNone(body["last_sync"])

    def test_library_sync_start_queues_job(self) -> None:
        with patch(
            "curatorx.web.jobs.sync_library",
            new=AsyncMock(return_value={"items_synced": 0, "embeddings": 0}),
        ):
            resp = self.client.post("/api/library/sync")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertIn("id", body)
            self.assertEqual(body["job_type"], "library_sync")
            self.assertIn(body["status"], ("queued", "running", "completed"))
            deadline = time.time() + 2
            while time.time() < deadline:
                status = self.client.get(f"/api/jobs/{body['id']}")
                if status.status_code == 200 and status.json().get("status") == "completed":
                    break
                time.sleep(0.05)


class FeatureFlagSafetyTests(CaApiFixture):
    def test_seerr_off_does_not_break_core_apis(self) -> None:
        features = self.client.get("/api/features")
        self.assertFalse(features.json()["features"]["seerr_enabled"])

        requests = self.client.get("/api/requests")
        self.assertEqual(requests.status_code, 400)
        self.assertIn("not enabled", requests.json()["detail"].lower())

        propose = self.client.post(
            "/api/actions/propose",
            json={"action": "request_seerr", "media_type": "movie", "tmdb_id": 1, "title": "X"},
        )
        self.assertEqual(propose.status_code, 400)

        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    def test_multi_user_off_keeps_owner_apis_open(self) -> None:
        features = self.client.get("/api/features")
        self.assertFalse(features.json()["features"]["multi_user_enabled"])

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["id"], "bootstrap-owner")

        users = self.client.get("/api/users")
        self.assertEqual(users.status_code, 200)
        self.assertGreaterEqual(users.json()["count"], 1)


class MessageFeedbackEdgeTests(CaApiFixture):
    def _seed_assistant(self, session_id: str, message_id: str) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.create_chat_thread(session_id, thread_title="Feedback")
        db.save_chat_message(
            session_id,
            message_id,
            "assistant",
            [{"type": "text", "content": "Try something quieter tonight."}],
        )

    def test_not_helpful_records_negative_preference(self) -> None:
        import curatorx.web.jobs as jobs

        session_id = "fb-not-helpful"
        message_id = "asst-not-helpful"
        self._seed_assistant(session_id, message_id)
        resp = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": "not_helpful"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["feedback"]["feedback"], "not_helpful")
        facts = jobs.get_job_manager().db.preference_facts(limit=10)
        self.assertTrue(any(f["signal_type"] == "negative" for f in facts))

    def test_invalid_feedback_type_rejected(self) -> None:
        self._seed_assistant("fb-bad", "asst-bad")
        resp = self.client.post(
            "/api/chat/messages/asst-bad/feedback",
            json={"session_id": "fb-bad", "feedback": "meh"},
        )
        self.assertEqual(resp.status_code, 422)


class WebhookEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "hooks.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_ignored_event(self) -> None:
        result = handle_plex_webhook(self.db, {"event": "media.play", "Metadata": {}})
        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "ignored_event")

    def test_missing_metadata(self) -> None:
        result = handle_plex_webhook(self.db, {"event": "media.stop"})
        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "missing_metadata")

    def test_missing_rating_key(self) -> None:
        result = handle_plex_webhook(
            self.db,
            {
                "event": "media.stop",
                "Metadata": {
                    "type": "movie",
                    "title": "No Key",
                    "viewOffset": 5_400_000,
                    "duration": 6_000_000,
                },
            },
        )
        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "missing_rating_key")


class ArrConfirmFriendlyErrorTests(CaApiFixture):
    def test_confirm_remove_returns_friendly_not_found(self) -> None:
        import curatorx.web.jobs as jobs

        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
            },
        )
        token = "remove-friendly-token"
        jobs.get_job_manager().db.save_pending_action(
            token,
            "remove_arr",
            {
                "action": "remove_arr",
                "media_type": "movie",
                "arr_id": 99,
                "tmdb_id": 5156,
                "title": "Rust",
                "delete_files": True,
            },
        )
        movie = MagicMock()
        movie.id = 99
        movie.title = "Rust"
        movie.tmdb_id = 5156
        with patch(
            "curatorx.agent.tools.RadarrClient.movie_by_tmdb_id",
            return_value=movie,
        ), patch(
            "curatorx.agent.tools.RadarrClient.delete_movie",
            side_effect=RuntimeError(
                'HTTP 404 from http://radarr/api/v3/movie/99: '
                '{"message":"Movie with ID 99 does not exist"}'
            ),
        ):
            resp = self.client.post(
                "/api/actions/confirm",
                json={"token": token, "confirmed": True},
            )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertEqual(detail, "Action confirmation failed")
        self.assertNotIn("HTTP 404", detail)
        self.assertNotIn("NzbDrone", detail)

    def test_confirm_expired_token_is_friendly(self) -> None:
        resp = self.client.post(
            "/api/actions/confirm",
            json={"token": "does-not-exist", "confirmed": True},
        )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertEqual(detail, "Action confirmation failed")
        self.assertNotIn("RuntimeError", detail)


class ReviewApiEdgeTests(CaApiFixture):
    def test_create_review_without_plex_sync_still_saves(self) -> None:
        resp = self.client.post(
            "/api/reviews",
            json={
                "title": "Local Only",
                "media_type": "movie",
                "stars": 3,
                "rating_key": "local-1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["stars"], 3)
        # Default install has sync_reviews_to_plex off / plex unset → no sync flag.
        self.assertFalse(body.get("plex_rating_synced"))


if __name__ == "__main__":
    unittest.main()
