"""Owner-only library index delete by rating_key."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache, create_session_token


class LibraryItemsDeleteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-library-delete-session-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

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

    def _seed_item(self, rating_key: str = "rk-delete-1", title: str = "Delete Me") -> None:
        import curatorx.web.jobs as jobs

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
                "tmdb_id": 424242,
            }
        )

    def test_implicit_owner_can_delete_library_items(self) -> None:
        self._seed_item()
        resp = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-delete-1"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["deleted"], 1)

        import curatorx.web.jobs as jobs

        remaining = jobs.get_job_manager().db.search_keyword("Delete Me")
        self.assertEqual(len(remaining), 0)

    def test_delete_requires_non_empty_rating_keys(self) -> None:
        resp = self.client.post("/api/library/items/delete", json={"rating_keys": []})
        self.assertEqual(resp.status_code, 400)
        blank = self.client.post("/api/library/items/delete", json={"rating_keys": ["  ", ""]})
        self.assertEqual(blank.status_code, 400)

    def test_member_cannot_delete_library_items(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        import curatorx.web.jobs as jobs

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

    def test_owner_session_can_delete_when_multi_user_enabled(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
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
