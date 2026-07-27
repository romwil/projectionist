"""Owner-only library index delete by rating_key."""

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


# Env keys that load_merged_settings may inherit from a prior test's dotenv load
# (empty settings.json does not override non-empty env for these fields).
_STACK_ENV_KEYS = (
    "PLEX_URL",
    "PLEX_TOKEN",
    "RADARR_URL",
    "RADARR_API_KEY",
    "SONARR_URL",
    "SONARR_API_KEY",
)


class LibraryItemsDeleteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-library-delete-session-secret"
        # Isolate from maintainer .env leaked into os.environ by earlier tests.
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
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
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
        rating_key: str = "rk-delete-1",
        title: str = "Delete Me",
        *,
        media_type: str = "movie",
        tmdb_id: int = 424242,
        tvdb_id: int | None = None,
    ) -> None:
        import projectionist.web.jobs as jobs

        item = {
            "rating_key": rating_key,
            "media_type": media_type,
            "title": title,
            "year": 2024,
            "summary": "Test",
            "genres": [],
            "cast": [],
            "directors": [],
            "keywords": [],
            "tmdb_id": tmdb_id,
        }
        if tvdb_id is not None:
            item["tvdb_id"] = tvdb_id
        jobs.get_job_manager().db.upsert_library_item(item)

    def test_implicit_owner_can_delete_library_items(self) -> None:
        self._seed_item()
        resp = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-delete-1"]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body.get("mode"), "index")

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Delete Me")
        self.assertEqual(len(remaining), 0)

    def test_delete_requires_non_empty_rating_keys(self) -> None:
        resp = self.client.post("/api/library/items/delete", json={"rating_keys": []})
        self.assertEqual(resp.status_code, 400)
        blank = self.client.post("/api/library/items/delete", json={"rating_keys": ["  ", ""]})
        self.assertEqual(blank.status_code, 400)

    def test_delete_rejects_unknown_mode(self) -> None:
        resp = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-1"], "mode": "yeet"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_member_cannot_delete_library_items(self) -> None:
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
        self._seed_item("rk-member-block")
        member_client = TestClient(self.app_mod.app)
        member_client.cookies.set(SESSION_COOKIE_NAME, create_session_token(member_id))
        resp = member_client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-member-block"]},
        )
        self.assertEqual(resp.status_code, 403)
        remaining = jobs.get_job_manager().db.search_keyword("Delete Me")
        self.assertEqual(len(remaining), 1)

    def test_member_cannot_full_remove(self) -> None:
        self._enable_multi_user()
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        import projectionist.web.jobs as jobs

        member_id = "plex-88"
        jobs.get_job_manager().db.upsert_plex_user(
            user_id=member_id,
            display_name="Member",
            email="member2@example.com",
            plex_user_id="88",
            role="member",
        )
        self._seed_item("rk-member-full")
        member_client = TestClient(self.app_mod.app)
        member_client.cookies.set(SESSION_COOKIE_NAME, create_session_token(member_id))
        resp = member_client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-member-full"], "mode": "full"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_session_can_delete_when_multi_user_enabled(self) -> None:
        self._enable_multi_user()
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 11, "title": "Owner"},
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        self.assertEqual(login.status_code, 200)
        self._seed_item("rk-owner-ok", title="Owner Delete")
        resp = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-owner-ok"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], 1)

    def test_full_remove_calls_arr_and_plex_then_deletes_index(self) -> None:
        self._seed_item("rk-full-1", title="Full Remove Me", tmdb_id=101)
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
                return_value={"arr_id": 55, "title": "Full Remove Me", "tmdb_id": 101},
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch("projectionist.library.full_remove.PlexClient") as plex_cls,
        ):
            radarr = MagicMock()
            radarr_cls.return_value = radarr
            plex = MagicMock()
            plex_cls.return_value = plex
            resp = self.client.post(
                "/api/library/items/delete",
                json={"rating_keys": ["rk-full-1"], "mode": "full"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mode"], "full")
        self.assertEqual(body["deleted"], 1)
        self.assertEqual(body["errors"], [])
        radarr.delete_movie.assert_called_once_with(55, delete_files=True, add_exclusion=True)
        plex.delete_metadata.assert_called_once_with("rk-full-1")

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Full Remove Me")
        self.assertEqual(len(remaining), 0)

    def test_full_remove_leaves_index_when_arr_missing(self) -> None:
        self._seed_item("rk-full-miss", title="Not In Arr", tmdb_id=202)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "llm_provider": "ollama",
                    "radarr_url": "http://radarr.test",
                    "radarr_api_key": "radarr-key",
                }
            ),
            encoding="utf-8",
        )
        from projectionist.connectors.arr_errors import ArrTitleNotFoundError

        with patch(
            "projectionist.library.full_remove.resolve_arr_removal_target",
            side_effect=ArrTitleNotFoundError("Radarr", title="Not In Arr", external_id=202),
        ):
            resp = self.client.post(
                "/api/library/items/delete",
                json={"rating_keys": ["rk-full-miss"], "mode": "full"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["deleted"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("not in Radarr", body["errors"][0]["error"])

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Not In Arr")
        self.assertEqual(len(remaining), 1)

    def test_full_remove_errors_when_radarr_not_configured(self) -> None:
        self._seed_item("rk-no-radarr", title="No Radarr", tmdb_id=303)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps({"llm_provider": "ollama", "radarr_url": "", "radarr_api_key": ""}),
            encoding="utf-8",
        )
        resp = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-no-radarr"], "mode": "full"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["deleted"], 0)
        self.assertEqual(len(body["errors"]), 1)
        self.assertIn("Radarr is not configured", body["errors"][0]["error"])

        import projectionist.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("No Radarr")
        self.assertEqual(len(remaining), 1)


if __name__ == "__main__":
    unittest.main()
