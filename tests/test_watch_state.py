"""Tests for mark watched/unwatched (DB + mocked Plex scrobble)."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import FeatureFlags, Settings
from curatorx.connectors.plex import PlexClient
from curatorx.library.db import Database
from curatorx.library.watch_state import set_library_item_watched, sync_watched_to_plex
from curatorx.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache, create_session_token


class WatchStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "watch.db")
        self.db.upsert_library_item(
            {
                "rating_key": "movie-1",
                "media_type": "movie",
                "title": "Heat",
                "view_count": 0,
            }
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_mark_watched_and_unwatched_updates_db(self) -> None:
        watched = set_library_item_watched(self.db, "movie-1", watched=True)
        self.assertTrue(watched["watched"])
        self.assertEqual(watched["view_count"], 1)
        self.assertIsNotNone(watched["last_viewed_at"])

        unwatched = set_library_item_watched(self.db, "movie-1", watched=False)
        self.assertFalse(unwatched["watched"])
        self.assertEqual(unwatched["view_count"], 0)
        self.assertIsNone(unwatched["last_viewed_at"])

    def test_mark_watched_unknown_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            set_library_item_watched(self.db, "missing", watched=True)

    def test_watched_timestamp_types_match_db_conventions(self) -> None:
        set_library_item_watched(self.db, "movie-1", watched=True)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT last_viewed_at, updated_at FROM library_items WHERE rating_key = ?",
                ("movie-1",),
            ).fetchone()
        # last_viewed_at is INTEGER epoch seconds; updated_at is a REAL epoch timestamp.
        self.assertIsInstance(row["last_viewed_at"], int)
        self.assertIsInstance(row["updated_at"], float)

        set_library_item_watched(self.db, "movie-1", watched=False)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT last_viewed_at, updated_at FROM library_items WHERE rating_key = ?",
                ("movie-1",),
            ).fetchone()
        self.assertIsNone(row["last_viewed_at"])
        self.assertIsInstance(row["updated_at"], float)


class PlexScrobbleClientTests(unittest.TestCase):
    def test_scrobble_and_unscrobble_endpoints(self) -> None:
        client = PlexClient("http://plex.test:32400", "secret-token")
        captured: list[dict[str, str]] = []

        def fake_request_empty(url: str, *, method: str = "PUT", timeout: int = 30) -> None:
            captured.append({"url": url, "method": method, "timeout": str(timeout)})

        with patch("curatorx.connectors.plex.request_empty", side_effect=fake_request_empty):
            client.scrobble("12345")
            client.unscrobble("12345")

        self.assertEqual(captured[0]["method"], "GET")
        self.assertIn("/:/scrobble?", captured[0]["url"])
        self.assertIn("key=12345", captured[0]["url"])
        self.assertIn("identifier=com.plexapp.plugins.library", captured[0]["url"])
        self.assertEqual(captured[1]["method"], "GET")
        self.assertIn("/:/unscrobble?", captured[1]["url"])


class WatchStateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-watch-state-session-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test:32400",
                    "plex_token": "server-token",
                    "features": {"multi_user_enabled": False},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "summary": "Test",
                "genres": [],
                "cast": [],
                "directors": [],
                "keywords": [],
                "view_count": 0,
            }
        )

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test:32400",
                    "plex_token": "server-token",
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )

    def test_api_mark_watched_updates_db_and_calls_plex(self) -> None:
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            resp = self.client.post(
                "/api/library/items/watched",
                json={"rating_key": "rk-heat", "watched": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["view_count"], 1)
        self.assertTrue(body["watched"])
        self.assertTrue(body["plex_synced"])
        mock_scrobble.assert_called_once_with("rk-heat")

        with patch.object(PlexClient, "unscrobble") as mock_unscrobble:
            resp = self.client.post(
                "/api/library/items/watched",
                json={"rating_key": "rk-heat", "watched": False},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["view_count"], 0)
        mock_unscrobble.assert_called_once_with("rk-heat")

    def test_api_member_can_mark_watched(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        member_id = "plex-member-1"
        self.db.upsert_plex_user(
            user_id=member_id,
            display_name="Member",
            email="member@example.com",
            plex_user_id="88",
            role="member",
        )
        member_client = TestClient(self.app_mod.app)
        member_client.cookies.set(SESSION_COOKIE_NAME, create_session_token(member_id))
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            resp = member_client.post(
                "/api/library/items/watched",
                json={"rating_key": "rk-heat", "watched": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["watched"])
        mock_scrobble.assert_called_once_with("rk-heat")

    def test_api_unauthenticated_forbidden_when_multi_user(self) -> None:
        self._enable_multi_user()
        anon_client = TestClient(self.app_mod.app)
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            resp = anon_client.post(
                "/api/library/items/watched",
                json={"rating_key": "rk-heat", "watched": True},
            )
        self.assertEqual(resp.status_code, 401)
        mock_scrobble.assert_not_called()
        row = self.db.library_item_by_rating_key("rk-heat")
        self.assertEqual(int(row["view_count"] or 0), 0)

    def test_api_mark_watched_unknown_rating_key_returns_404(self) -> None:
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            resp = self.client.post(
                "/api/library/items/watched",
                json={"rating_key": "does-not-exist", "watched": True},
            )
        self.assertEqual(resp.status_code, 404, resp.text)
        mock_scrobble.assert_not_called()

    def test_api_guest_forbidden_when_multi_user(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        guest_id = "plex-guest-1"
        self.db.upsert_plex_user(
            user_id=guest_id,
            display_name="Guest",
            email="guest@example.com",
            plex_user_id="77",
            role="guest",
        )
        guest_client = TestClient(self.app_mod.app)
        guest_client.cookies.set(SESSION_COOKIE_NAME, create_session_token(guest_id))
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            resp = guest_client.post(
                "/api/library/items/watched",
                json={"rating_key": "rk-heat", "watched": True},
            )
        self.assertEqual(resp.status_code, 403)
        mock_scrobble.assert_not_called()
        row = self.db.library_item_by_rating_key("rk-heat")
        self.assertEqual(int(row["view_count"] or 0), 0)

    def test_sync_watched_to_plex_handles_errors(self) -> None:
        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="tok",
            features=FeatureFlags(multi_user_enabled=False),
        )
        with patch.object(PlexClient, "scrobble", side_effect=RuntimeError("boom")):
            result = sync_watched_to_plex(
                self.db,
                settings,
                "rk-heat",
                watched=True,
                user_id=None,
            )
        self.assertFalse(result["plex_synced"])
        self.assertEqual(result["plex_reason"], "plex_error")

    def test_sync_watched_to_plex_not_configured(self) -> None:
        settings = Settings(
            plex_url="",
            plex_token="",
            features=FeatureFlags(multi_user_enabled=False),
        )
        with patch.object(PlexClient, "scrobble") as mock_scrobble:
            result = sync_watched_to_plex(
                self.db,
                settings,
                "rk-heat",
                watched=True,
                user_id=None,
            )
        self.assertFalse(result["plex_synced"])
        self.assertEqual(result["plex_reason"], "plex_not_configured")
        mock_scrobble.assert_not_called()


if __name__ == "__main__":
    unittest.main()
