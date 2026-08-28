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
from unittest.mock import patch

from projectionist.web.auth import _hash_password, _verify_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


class LocalAuthTests(unittest.TestCase):
    """Integration tests for POST /api/auth/local/register and /api/auth/local/login."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-local-auth-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
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

    def _seed_owner(self, username: str = "alice", password: str = "password123"):
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.create_local_user(
            user_id=f"local-{username}",
            display_name=username,
            password_hash=_hash_password(password),
            role="owner",
        )

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
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_register_is_forbidden(self) -> None:
        self._enable_local_auth()
        resp = self._register("alice", "password123")
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn("join link", resp.json()["detail"].lower())

    def test_register_second_user_requires_owner(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        self.client.cookies.clear()
        second = self._register("bob", "password456")
        self.assertEqual(second.status_code, 403)

    def test_register_second_user_as_owner(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        first = self._login("alice", "password123")
        self.assertEqual(first.status_code, 200)
        cookie = self._extract_session_cookie(first)
        second = self._register("bob", "password456", session_cookie=cookie)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["user"]["role"], "member")

    def test_register_duplicate_username(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        first = self._login("alice", "password123")
        cookie = self._extract_session_cookie(first)
        resp = self._register("alice", "differentpw", session_cookie=cookie)
        self.assertEqual(resp.status_code, 409)

    def test_register_short_password_rejected(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        first = self._login("alice", "password123")
        cookie = self._extract_session_cookie(first)
        resp = self._register("bob", "short", session_cookie=cookie)
        self.assertIn(resp.status_code, (400, 422))

    # -- Login --

    def test_login_success(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        resp = self._login("alice", "password123")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["display_name"], "alice")
        self.assertIsNotNone(self._extract_session_cookie(resp))

    def test_login_wrong_password(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
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
        self._seed_owner()
        login = self._login("alice", "password123")
        self.assertEqual(login.status_code, 200, login.text)
        cookie = self._extract_session_cookie(login)
        self.assertIsNotNone(cookie, "Session cookie should be set on login")
        resp = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"]["display_name"], "alice")

    def test_logout_revokes_replayed_session_cookie(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        login = self._login("alice", "password123")
        cookie = self._extract_session_cookie(login)
        self.assertIsNotNone(cookie)
        me = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"},
        )
        self.assertEqual(me.status_code, 200)
        self.client.cookies.set(SESSION_COOKIE_NAME, cookie)
        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        replay = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"},
        )
        self.assertEqual(replay.status_code, 401)

    def test_password_rotation_invalidates_session(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        login = self._login("alice", "password123")
        cookie = self._extract_session_cookie(login)
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.update_user_password("local-alice", _hash_password("newpassword123"))
        replay = self.client.get(
            "/api/auth/me",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"},
        )
        self.assertEqual(replay.status_code, 401)

    def test_disabled_local_user_is_generic_401(self) -> None:
        self._enable_local_auth()
        self._seed_owner()
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.set_user_disabled("local-alice", True)
        resp = self._login("alice", "password123")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "Invalid username or password")
        self.assertNotIn("disabled", resp.json()["detail"].lower())

    def test_unknown_user_still_runs_dummy_verify(self) -> None:
        self._enable_local_auth()
        with patch("projectionist.web.auth._verify_password", return_value=False) as verify:
            resp = self._login("nobody-here", "password123")
        self.assertEqual(resp.status_code, 401)
        verify.assert_called()
        self.assertEqual(verify.call_args.args[0], "password123")

    def test_oversized_login_json_is_413(self) -> None:
        blob = b'{"username":"' + b"x" * 70_000 + b'","password":"password123"}'
        resp = self.client.post(
            "/api/auth/local/login",
            content=blob,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 413)
        self.assertIn("too large", resp.text.lower())

    def test_unknown_vs_wrong_password_login_latency_overlap(self) -> None:
        """Unknown usernames must not skip PBKDF2 (no 10× timing oracle)."""
        import time as time_mod

        self._enable_local_auth()
        self._seed_owner()
        unknown: list[float] = []
        wrong: list[float] = []
        for _ in range(2):
            started = time_mod.perf_counter()
            self._login("no-such-user", "password123")
            unknown.append(time_mod.perf_counter() - started)
            started = time_mod.perf_counter()
            self._login("alice", "definitely-wrong-password")
            wrong.append(time_mod.perf_counter() - started)
        unknown_mean = sum(unknown) / len(unknown)
        wrong_mean = sum(wrong) / len(wrong)
        slower = max(unknown_mean, wrong_mean)
        faster = min(unknown_mean, wrong_mean) or 1e-9
        self.assertLess(slower / faster, 10.0)

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
