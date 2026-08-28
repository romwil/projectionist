"""Owner purge-candidate delete: default full remove + optional index undo."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from projectionist.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache, create_session_token

_STACK_ENV_KEYS = (
    "PLEX_URL",
    "PLEX_TOKEN",
    "RADARR_URL",
    "RADARR_API_KEY",
    "SONARR_URL",
    "SONARR_API_KEY",
)


class PurgeCandidatesDeleteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-purge-delete-session-secret"
        self._saved_stack_env = {key: os.environ.pop(key, None) for key in _STACK_ENV_KEYS}
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        for key in _STACK_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in self._saved_stack_env.items():
            if value is not None:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )

    def _seed_item(
        self,
        rating_key: str = "rk-purge-1",
        title: str = "Purge Me",
        *,
        tmdb_id: int = 424242,
    ) -> None:
        import projectionist.web.jobs as jobs

        jobs.get_job_manager().db.upsert_library_item(
            {
                "rating_key": rating_key,
                "media_type": "movie",
                "title": title,
                "year": 2024,
                "summary": "Test",
                "genres": [],
                "cast": [],
                "directors": [],
                "keywords": [],
                "tmdb_id": tmdb_id,
            }
        )

    def test_default_purge_delete_calls_arr_and_is_not_undoable(self) -> None:
        self._seed_item("rk-full-purge", title="Full Purge Me", tmdb_id=101)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "llm_provider": "ollama",
                    "radarr_url": "http://radarr.test",
                    "radarr_api_key": "radarr-key",
                    "plex_url": "http://plex.test",
                    "plex_token": "plex-token",
                }
            ),
            encoding="utf-8",
        )
        with (
            patch(
                "projectionist.library.full_remove.resolve_arr_removal_target",
                return_value={"arr_id": 55, "title": "Full Purge Me", "tmdb_id": 101},
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch("projectionist.library.full_remove.PlexClient") as plex_cls,
        ):
            radarr = MagicMock()
            radarr.movie_by_id.return_value = None
            radarr_cls.return_value = radarr
            plex = MagicMock()
            plex_cls.return_value = plex
            resp = self.client.post(
                "/api/library/purge-candidates/delete",
                json={"rating_keys": ["rk-full-purge"]},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mode"], "full")
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["errors"], [])
        self.assertFalse(body["undoable"])
        self.assertIsNone(body["action_id"])
        self.assertIn("totals", body)
        self.assertEqual(body["totals"]["files"], 0)
        self.assertEqual(body["totals"]["folders"], 0)
        self.assertEqual(body["totals"]["bytes_freed"], 0)
        radarr.delete_movie.assert_called_once_with(55, delete_files=True, add_exclusion=True)
        plex.delete_metadata.assert_called_once_with("rk-full-purge")

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Full Purge Me")
        self.assertEqual(len(remaining), 0)

    def test_explicit_index_mode_is_undoable(self) -> None:
        self._seed_item("rk-index-purge", title="Index Purge Me")
        resp = self.client.post(
            "/api/library/purge-candidates/delete",
            json={"rating_keys": ["rk-index-purge"], "mode": "index"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mode"], "index")
        self.assertEqual(body["deleted"], 1)
        self.assertTrue(body["undoable"])
        self.assertIsNotNone(body["action_id"])

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Index Purge Me")
        self.assertEqual(len(remaining), 0)

    def test_unknown_mode_rejected(self) -> None:
        resp = self.client.post(
            "/api/library/purge-candidates/delete",
            json={"rating_keys": ["rk-1"], "mode": "yeet"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_member_cannot_purge_candidates_delete(self) -> None:
        self._enable_multi_user()
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        import projectionist.web.jobs as jobs

        member_id = "plex-99"
        jobs.get_job_manager().db.upsert_plex_user(
            user_id=member_id,
            display_name="Member",
            email="member@example.com",
            plex_user_id="99",
            role="member",
        )
        self._seed_item("rk-member-purge")
        member_client = TestClient(self.app_mod.app)
        member_client.cookies.set(SESSION_COOKIE_NAME, create_session_token(member_id))
        resp = member_client.post(
            "/api/library/purge-candidates/delete",
            json={"rating_keys": ["rk-member-purge"], "mode": "index"},
        )
        self.assertEqual(resp.status_code, 403)
        remaining = jobs.get_job_manager().db.search_keyword("Purge Me")
        self.assertEqual(len(remaining), 1)


if __name__ == "__main__":
    unittest.main()
