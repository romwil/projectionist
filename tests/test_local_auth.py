"""Tests for local-password authentication (Item 28).

Covers registration, login, wrong-password rejection, session cookie
creation, and owner-only registration enforcement.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.web.auth import _hash_password, _verify_password, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


class LocalAuthTests(unittest.TestCase):
    """Integration tests for POST /api/auth/local/register and /api/auth/local/login."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-local-auth-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
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

    def _enable_local_auth(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True},
            "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
            "llm_provider": "ollama",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _register(self, username: str, password: str, session_cookie=None):
        headers = {}
        if session_cookie:
            headers["Cookie"] = f"{SESSION_COOKIE_NAME}={session_cookie}"
        return self.client.post(
            "/api/auth/local/register",
            json={"username": username, "password": password},
            headers=headers if headers else None,
        )

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/local/login",
            json={"username": username, "password": password},
        )

    def _extract_session_cookie(self, resp):
        raw = resp.headers.get("set-cookie") or ""
        for part in raw.split(","):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                return part.split("=", 1)[1].split(";")[0]
        # httpx may also expose cookies directly
        return resp.cookies.get(SESSION_COOKIE_NAME)

    # -- Password hashing unit tests --

    def test_hash_and_verify_password(self) -> None:
        hashed = _hash_password("hunter2")
        self.assertIn("$", hashed)
        self.assertTrue(_verify_password("hunter2", hashed))
        self.assertFalse(_verify_password("wrong", hashed))

    def test_verify_rejects_malformed_hash(self) -> None:
        self.assertFalse(_verify_password("x", "nohex"))
        self.assertFalse(_verify_password("x", ""))

    def test_constant_time_comparison(self) -> None:
        """_verify_password uses hmac.compare_digest — smoke test that the right
        password passes and a wrong one fails (timing is hard to test in CI)."""
        h = _hash_password("correct")
        self.assertTrue(_verify_password("correct", h))
        self.assertFalse(_verify_password("incorrect", h))

    # -- Registration --

    def test_register_fails_when_local_login_disabled(self) -> None:
        resp = self._register("alice", "password123")
        self.assertEqual(resp.status_code, 400)

    def test_register_first_user_becomes_owner(self) -> None:
        self._enable_local_auth()
        resp = self._register("alice", "password123")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["role"], "owner")
        self.assertEqual(body["user"]["display_name"], "alice")
        self.assertIsNotNone(self._extract_session_cookie(resp))

    def test_register_second_user_requires_owner(self) -> None:
        self._enable_local_auth()
        first = self._register("alice", "password123")
        self.assertEqual(first.status_code, 200)
        # Clear any cookies the test client picked up, then try unauthenticated
        self.client.cookies.clear()
        second = self._register("bob", "password456")
        self.assertEqual(second.status_code, 401)

    def test_register_second_user_as_owner(self) -> None:
        self._enable_local_auth()
        first = self._register("alice", "password123")
        self.assertEqual(first.status_code, 200)
        cookie = self._extract_session_cookie(first)
        second = self._register("bob", "password456", session_cookie=cookie)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["user"]["role"], "member")

    def test_register_duplicate_username(self) -> None:
        self._enable_local_auth()
        first = self._register("alice", "password123")
        cookie = self._extract_session_cookie(first)
        resp = self._register("alice", "differentpw", session_cookie=cookie)
        self.assertEqual(resp.status_code, 409)

    def test_register_short_password_rejected(self) -> None:
        self._enable_local_auth()
        resp = self._register("alice", "short")
        self.assertIn(resp.status_code, (400, 422))

    # -- Login --

    def test_login_success(self) -> None:
        self._enable_local_auth()
        reg = self._register("alice", "password123")
        self.assertEqual(reg.status_code, 200, reg.text)
        resp = self._login("alice", "password123")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["display_name"], "alice")
        self.assertIsNotNone(self._extract_session_cookie(resp))

    def test_login_wrong_password(self) -> None:
        self._enable_local_auth()
        reg = self._register("alice", "password123")
        self.assertEqual(reg.status_code, 200, reg.text)
        resp = self._login("alice", "wrong")
        self.assertEqual(resp.status_code, 401)

    def test_login_unknown_user(self) -> None:
        self._enable_local_auth()
        resp = self._login("nobody", "anything")
        self.assertEqual(resp.status_code, 401)

    def test_login_disabled_when_feature_off(self) -> None:
        resp = self._login("alice", "password123")
        self.assertEqual(resp.status_code, 400)

    # -- Session cookie --

    def test_session_cookie_works_for_api(self) -> None:
        self._enable_local_auth()
        reg = self._register("alice", "password123")
        self.assertEqual(reg.status_code, 200, reg.text)
        cookie = self._extract_session_cookie(reg)
        self.assertIsNotNone(cookie, "Session cookie should be set on registration")
        resp = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"]["display_name"], "alice")

    # -- Features endpoint includes auth_methods --

    def test_features_includes_auth_methods(self) -> None:
        self._enable_local_auth()
        resp = self.client.get("/api/features")
        body = resp.json()
        self.assertIn("auth_methods", body)
        self.assertIn("local", body["auth_methods"])
        self.assertNotIn("plex", body["auth_methods"])


if __name__ == "__main__":
    unittest.main()
