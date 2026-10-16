"""Owner preference for the typed DELETE library-removal gate."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class AskDeleteConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-ask-delete-confirmation-secret"
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
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
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_ALLOW_OPEN_JOIN",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login_as(self, plex_id: int, title: str) -> None:
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": plex_id, "title": title, "email": f"{title}@example.com"},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"token-{plex_id}"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_default_asks_for_delete(self) -> None:
        pref = self.client.get("/api/settings/ask-delete-confirmation")
        self.assertEqual(pref.status_code, 200, pref.text)
        self.assertTrue(pref.json()["ask_delete_confirmation"])

        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200, settings.text)
        self.assertTrue(settings.json()["ask_delete_confirmation"])

    def test_dont_ask_again_persists_and_admin_can_turn_it_back_on(self) -> None:
        turned_off = self.client.put(
            "/api/settings/ask-delete-confirmation",
            json={"ask_delete_confirmation": False},
        )
        self.assertEqual(turned_off.status_code, 200, turned_off.text)
        self.assertFalse(turned_off.json()["ask_delete_confirmation"])

        again = self.client.get("/api/settings/ask-delete-confirmation")
        self.assertFalse(again.json()["ask_delete_confirmation"])
        stored = json.loads((Path(self._tmpdir.name) / "settings.json").read_text(encoding="utf-8"))
        self.assertFalse(stored["ask_delete_confirmation"])

        # A partial settings save must not silently turn the confirmation back on.
        partial = self.client.put("/api/settings", json={"sync_reviews_to_plex": False})
        self.assertEqual(partial.status_code, 200, partial.text)
        self.assertFalse(partial.json()["ask_delete_confirmation"])

        restored = self.client.put(
            "/api/settings",
            json={"ask_delete_confirmation": True, "sync_reviews_to_plex": False},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()["ask_delete_confirmation"])
        self.assertTrue(self.client.get("/api/settings").json()["ask_delete_confirmation"])

    def test_removal_proceeds_without_typed_word_when_setting_is_off(self) -> None:
        import projectionist.web.jobs as jobs

        jobs.get_job_manager().db.upsert_library_item(
            {
                "rating_key": "rk-skip-delete",
                "media_type": "movie",
                "title": "The Sacrifice",
                "year": 2026,
                "summary": "Test",
                "genres": [],
                "cast": [],
                "directors": [],
                "keywords": [],
                "tmdb_id": 88001,
            }
        )
        pref = self.client.put(
            "/api/settings/ask-delete-confirmation",
            json={"ask_delete_confirmation": False},
        )
        self.assertEqual(pref.status_code, 200, pref.text)

        removed = self.client.post(
            "/api/library/items/delete",
            json={"rating_keys": ["rk-skip-delete"], "mode": "index"},
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()["deleted"], 1)
        self.assertNotIn("confirm", removed.json())

    def test_member_cannot_disable_confirmation(self) -> None:
        enabled = self.client.put(
            "/api/settings",
            json={
                "features": {
                    "multi_user_enabled": True,
                    "open_auto_provision": True,
                    "seerr_enabled": False,
                },
                "auth": {"mode": "plex", "plex_login_enabled": True},
                "ask_delete_confirmation": True,
            },
        )
        self.assertEqual(enabled.status_code, 200, enabled.text)

        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")

        denied = self.client.put(
            "/api/settings/ask-delete-confirmation",
            json={"ask_delete_confirmation": False},
        )
        self.assertEqual(denied.status_code, 403, denied.text)

        self.client.post("/api/auth/logout")
        self._login_as(1, "Owner")
        still_on = self.client.get("/api/settings/ask-delete-confirmation")
        self.assertEqual(still_on.status_code, 200, still_on.text)
        self.assertTrue(still_on.json()["ask_delete_confirmation"])
