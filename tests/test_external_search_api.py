"""Tests for the GET /api/search/external ("Search beyond the collection") endpoint."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


def _movie_page():
    return {
        "total_results": 2,
        "results": [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "overview": "A hacker discovers reality is a simulation.",
                "vote_average": 8.2,
            },
            {
                "id": 604,
                "title": "The Matrix Reloaded",
                "release_date": "2003-05-15",
                "overview": "Neo continues the fight.",
                "vote_average": 7.0,
            },
        ],
    }


class ExternalSearchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["CURATORX_SESSION_SECRET"] = "test-external-search-session-secret"
        os.environ["LLM_PROVIDER"] = "ollama"
        # Keep TMDB config driven purely by settings.json so the not-configured
        # case is deterministic even if another test leaked TMDB_API_KEY.
        self._prev_tmdb_env = os.environ.pop("TMDB_API_KEY", None)
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()

        self._settings_path = Path(self._tmpdir.name) / "settings.json"
        self._write_settings(tmdb=True)

        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        app_mod.DATA_DIR = Path(self._tmpdir.name)
        self.client = TestClient(app_mod.app)
        self._jobs = jobs
        self._app_mod = app_mod

        self._login(10, "Owner")

        db = jobs.get_job_manager().db
        # Owned title so de-dupe flags one of the two search hits as in_library.
        db.upsert_library_item(
            {
                "rating_key": "rk-matrix",
                "media_type": "movie",
                "title": "The Matrix",
                "year": 1999,
                "tmdb_id": 603,
            }
        )
        db.upsert_plex_user(
            user_id="plex-20",
            display_name="Member",
            email="member@example.com",
            plex_user_id="20",
            role="member",
        )
        db.upsert_plex_user(
            user_id="plex-30",
            display_name="Guest",
            email="guest@example.com",
            plex_user_id="30",
            role="guest",
        )

    def tearDown(self) -> None:
        self._jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "CURATORX_SESSION_SECRET", "DATA_DIR"):
            os.environ.pop(key, None)
        if self._prev_tmdb_env is not None:
            os.environ["TMDB_API_KEY"] = self._prev_tmdb_env
        self._tmpdir.cleanup()

    def _write_settings(self, *, tmdb: bool) -> None:
        payload = {
            "features": {"multi_user_enabled": True},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
            "onboarding_complete": True,
        }
        if tmdb:
            payload["tmdb_api_key"] = "test-tmdb-key"
        self._settings_path.write_text(json.dumps(payload), encoding="utf-8")

    def _login(self, plex_id: int, title: str) -> None:
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": plex_id, "title": title, "email": f"{title}@example.com"},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"token-{plex_id}"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def _mock_tmdb(self, mock_cls):
        mock_tmdb = mock_cls.return_value
        mock_tmdb.search_movie_page.return_value = _movie_page()
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""
        return mock_tmdb

    @patch("curatorx.library.external_search.TMDBClient")
    def test_success_returns_titlecard_items(self, mock_cls) -> None:
        self._mock_tmdb(mock_cls)
        resp = self.client.get("/api/search/external", params={"q": "the matrix", "media_type": "movie"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["query"], "the matrix")
        self.assertEqual(body["media_type"], "movie")
        self.assertEqual(body["returned"], 2)
        titles = {item["title"] for item in body["items"]}
        self.assertEqual(titles, {"The Matrix", "The Matrix Reloaded"})
        for item in body["items"]:
            self.assertIn("already_queued", item)
            self.assertIn("in_library", item)

    @patch("curatorx.library.external_search.TMDBClient")
    def test_dedupe_flags_owned_title_in_library(self, mock_cls) -> None:
        self._mock_tmdb(mock_cls)
        resp = self.client.get("/api/search/external", params={"q": "the matrix"})
        self.assertEqual(resp.status_code, 200, resp.text)
        by_id = {item["tmdb_id"]: item for item in resp.json()["items"]}
        self.assertTrue(by_id[603]["in_library"])  # owned
        self.assertFalse(by_id[604]["in_library"])  # not owned

    def test_tmdb_not_configured_returns_clear_non_leaky_error(self) -> None:
        self._write_settings(tmdb=False)
        resp = self.client.get("/api/search/external", params={"q": "the matrix"})
        self.assertEqual(resp.status_code, 503, resp.text)
        detail = resp.json()["detail"]
        self.assertNotIn("TMDB", detail)
        self.assertNotIn("api", detail.lower())
        self.assertIn("beyond the collection", detail.lower())

    def test_empty_query_rejected(self) -> None:
        resp = self.client.get("/api/search/external", params={"q": "   "})
        self.assertEqual(resp.status_code, 400)

    @patch("curatorx.library.external_search.TMDBClient")
    def test_member_gets_public_schema(self, mock_cls) -> None:
        self._mock_tmdb(mock_cls)
        self.client.post("/api/auth/logout")
        self._login(20, "Member")
        resp = self.client.get("/api/search/external", params={"q": "the matrix"})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["returned"], 2)
        for item in body["items"]:
            # Public schema drops internal fields but keeps the acquisition flags
            # a member card needs (in_library + already_queued).
            self.assertNotIn("rating_key", item)
            self.assertNotIn("in_radarr", item)
            self.assertNotIn("in_sonarr", item)
            self.assertIn("in_library", item)
            self.assertIn("already_queued", item)

    @patch("curatorx.library.external_search.TMDBClient")
    def test_guest_can_search_beyond_collection(self, mock_cls) -> None:
        self._mock_tmdb(mock_cls)
        self.client.post("/api/auth/logout")
        self._login(30, "Guest")
        resp = self.client.get("/api/search/external", params={"q": "the matrix"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["returned"], 2)


if __name__ == "__main__":
    unittest.main()
