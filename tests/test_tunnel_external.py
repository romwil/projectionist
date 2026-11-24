"""SEC-020: a public address keeps household login on, and setup stays closed outside."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.account_throttle import clear_account_throttle
from projectionist.web.ingress import LOGIN_STAYS_ON_DETAIL, SETUP_EXTERNAL_DETAIL
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.setup_mode import SETUP_STATE_ACTIVE, SETUP_STATE_KEY
from tests.totp_login import finish_sign_in_code


class _AppCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-tunnel-external-secret"
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        os.environ.pop("PROJECTIONIST_TRUSTED_PROXIES", None)
        os.environ.pop("PROJECTIONIST_OWNER_PASSWORD", None)
        from projectionist.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        clear_rate_limits()
        clear_account_throttle()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = app_mod._db()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_rate_limits()
        clear_account_throttle()
        from projectionist.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_TRUSTED_PROXIES",
            "PROJECTIONIST_OWNER_PASSWORD",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _write_settings(self, *, multi_user: bool, public_url: str) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": multi_user},
                    "auth": {
                        "mode": "local",
                        "plex_login_enabled": False,
                        "local_login_enabled": True,
                    },
                    "llm_provider": "ollama",
                    "network": {"public_base_url": public_url},
                }
            ),
            encoding="utf-8",
        )


class HouseholdLoginStaysOnTests(_AppCase):
    def test_a_public_address_refuses_turning_login_off(self) -> None:
        from projectionist.web.auth import _hash_password

        self._write_settings(multi_user=True, public_url="https://films.example.com")
        self.db.create_local_user(
            user_id="ada",
            display_name="Ada",
            password_hash=_hash_password("correct-horse"),
            role="owner",
        )
        clear_rate_limits()
        login = self.client.post(
            "/api/auth/local/login",
            json={"username": "Ada", "password": "correct-horse"},
        )
        signed_in = finish_sign_in_code(self.client, login, "Ada", "correct-horse")
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        refused = self.client.put(
            "/api/settings",
            json={"features": {"multi_user_enabled": False}, "llm_provider": "ollama"},
        )
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(refused.json()["detail"], LOGIN_STAYS_ON_DETAIL)
        self.assertTrue(self.app_mod._settings().features.multi_user_enabled)

    def test_clearing_the_address_first_lets_login_turn_off(self) -> None:
        from projectionist.web.auth import _hash_password

        self._write_settings(multi_user=True, public_url="https://films.example.com")
        self.db.create_local_user(
            user_id="ada",
            display_name="Ada",
            password_hash=_hash_password("correct-horse"),
            role="owner",
        )
        clear_rate_limits()
        login = self.client.post(
            "/api/auth/local/login",
            json={"username": "Ada", "password": "correct-horse"},
        )
        signed_in = finish_sign_in_code(self.client, login, "Ada", "correct-horse")
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        cleared = self.client.put("/api/network/public-base-url", json={"public_base_url": ""})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        turned_off = self.client.put(
            "/api/settings",
            json={"features": {"multi_user_enabled": False}, "llm_provider": "ollama"},
        )
        self.assertEqual(turned_off.status_code, 200, turned_off.text)
        self.assertFalse(self.app_mod._settings().features.multi_user_enabled)


class SetupStaysClosedTests(_AppCase):
    def test_an_external_request_does_not_reopen_setup(self) -> None:
        self._write_settings(multi_user=False, public_url="https://films.example.com")
        os.environ["PROJECTIONIST_TRUSTED_PROXIES"] = "172.17.0.1"
        os.environ["PROJECTIONIST_OWNER_PASSWORD"] = "correct-horse"
        self.db.set_config(SETUP_STATE_KEY, SETUP_STATE_ACTIVE)
        external = TestClient(self.app_mod.app, client=("172.17.0.1", 50000))
        headers = {"cf-ray": "9abc-EWR", "cf-connecting-ip": "203.0.113.8"}
        features = external.get("/api/features", headers=headers)
        self.assertEqual(features.status_code, 404, features.text)
        self.assertEqual(self.db.get_config(SETUP_STATE_KEY), SETUP_STATE_ACTIVE)
        unlock = external.post(
            "/api/setup/unlock",
            json={"passcode": "correct-horse"},
            headers=headers,
        )
        self.assertEqual(unlock.status_code, 403, unlock.text)
        self.assertEqual(unlock.json()["detail"], SETUP_EXTERNAL_DETAIL)
        self.assertEqual(self.db.get_config(SETUP_STATE_KEY), SETUP_STATE_ACTIVE)
