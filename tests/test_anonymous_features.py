"""SEC-022: a signed-out caller learns how to sign in, and nothing about the house."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_ANONYMOUS_KEYS = {
    "features",
    "auth_methods",
    "sign_in",
    "setup_state",
    "authenticated",
    "user",
    "api_contract",
    "capabilities",
}


class AnonymousFeaturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in ("DATA_DIR", "PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER", "PROJECTIONIST_SETUP_STATE"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _write(self, payload: dict) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_single_owner_on_the_lan_still_gets_the_household_payload(self) -> None:
        body = self.client.get("/api/features").json()
        self.assertTrue(body["authenticated"])
        self.assertIn("addresses", body)
        self.assertIn("household_domain", body)
        self.assertIn("arr", body)
        self.assertNotIn("version", body)

    def test_a_signed_out_caller_gets_only_the_sign_in_card(self) -> None:
        self._write(
            {
                "features": {"multi_user_enabled": True},
                "household_domain": "films.example.com",
                "llm_provider": "ollama",
                "network": {"public_base_url": "https://films.example.com"},
                "radarr_url": "http://radarr.local:7878",
                "radarr_api_key": "radarr-secret",
            }
        )
        response = self.client.get("/api/features")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), _ANONYMOUS_KEYS)
        self.assertEqual(
            set(body["features"]),
            {"multi_user_enabled", "access_requests_enabled"},
        )
        self.assertFalse(body["authenticated"])
        self.assertIsNone(body["user"])
        self.assertIn("capabilities", body)
        self.assertNotIn("addresses", body)
        self.assertNotIn("household_domain", body)
        self.assertNotIn("arr", body)
        self.assertNotIn("version", body)
        self.assertNotIn("films.example.com", response.text)
        self.assertNotIn("radarr-secret", response.text)
