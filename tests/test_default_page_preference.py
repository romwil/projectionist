"""BD-5: default-page preference round-trip and llm_configured feature flag."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class DefaultPagePreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-default-page-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
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
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("OPENAI_API_KEY", None)
        self._tmpdir.cleanup()

    def test_default_page_defaults_to_auto(self) -> None:
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"].get("default_page"), "auto")

    def test_default_page_round_trips_chat_and_explore(self) -> None:
        patched = self.client.patch("/api/auth/me", json={"default_page": "explore"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["user"]["default_page"], "explore")

        again = self.client.get("/api/auth/me")
        self.assertEqual(again.json()["user"]["default_page"], "explore")

        back = self.client.patch("/api/auth/me", json={"default_page": "chat"})
        self.assertEqual(back.status_code, 200)
        self.assertEqual(back.json()["user"]["default_page"], "chat")

    def test_default_page_rejects_unknown_value(self) -> None:
        resp = self.client.patch("/api/auth/me", json={"default_page": "admin"})
        self.assertEqual(resp.status_code, 422)

    def test_features_reports_llm_not_configured_by_default(self) -> None:
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["features"]["llm_configured"])

    def test_features_reports_llm_configured_for_ollama(self) -> None:
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        importlib.reload(self.app_mod)
        client = TestClient(self.app_mod.app)

        resp = client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["features"]["llm_configured"])


if __name__ == "__main__":
    unittest.main()
