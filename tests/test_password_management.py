"""Phase 3 (SEC-011, OPS-016): self-service password change, owner reset of a
member's password, and explicit "sign out everywhere".
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.auth import _hash_password
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


class PasswordManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-password-mgmt-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self._enable_local_auth()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
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

    def _extract_session_cookie(self, resp):
        raw = resp.headers.get("set-cookie") or ""
        for part in raw.split(","):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                return part.split("=", 1)[1].split(";")[0]
        return resp.cookies.get(SESSION_COOKIE_NAME)

    def _seed_local_user(self, user_id: str, username: str, password: str, role: str = "owner"):
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.create_local_user(
            user_id=user_id,
            display_name=username,
            password_hash=_hash_password(password),
            role=role,
        )

    def _login(self, username: str, password: str):
        return self.client.post(
            "/api/auth/local/login",
            json={"username": username, "password": password},
        )

    def _cookie_headers(self, cookie: str) -> dict:
        return {"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"}

    # -- Self-service password change --

    def test_change_password_success_keeps_caller_signed_in(self) -> None:
        self._seed_local_user("local-alice", "alice", "password123")
        login = self._login("alice", "password123")
        cookie = self._extract_session_cookie(login)

        resp = self.client.post(
            "/api/auth/password",
            json={"current_password": "password123", "new_password": "newpassword456"},
            headers=self._cookie_headers(cookie),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        new_cookie = self._extract_session_cookie(resp)
        self.assertIsNotNone(new_cookie)

        # Old cookie is dead (session epoch bumped) ...
        stale = self.client.get("/api/auth/me", headers=self._cookie_headers(cookie))
        self.assertEqual(stale.status_code, 401)

        # ... but the freshly minted cookie from this response still works.
        fresh = self.client.get("/api/auth/me", headers=self._cookie_headers(new_cookie))
        self.assertEqual(fresh.status_code, 200, fresh.text)

        # And the new password actually took.
        relogin = self._login("alice", "newpassword456")
        self.assertEqual(relogin.status_code, 200)

    def test_change_password_wrong_current_password_rejected(self) -> None:
        self._seed_local_user("local-alice", "alice", "password123")
        login = self._login("alice", "password123")
        cookie = self._extract_session_cookie(login)

        resp = self.client.post(
            "/api/auth/password",
            json={"current_password": "not-it", "new_password": "newpassword456"},
            headers=self._cookie_headers(cookie),
        )
        self.assertEqual(resp.status_code, 401)

    def test_change_password_too_short_rejected(self) -> None:
        self._seed_local_user("local-alice", "alice", "password123")
        login = self._login("alice", "password123")
        cookie = self._extract_session_cookie(login)

        resp = self.client.post(
            "/api/auth/password",
            json={"current_password": "password123", "new_password": "short"},
            headers=self._cookie_headers(cookie),
        )
        self.assertEqual(resp.status_code, 422)

    def test_change_password_requires_auth(self) -> None:
        resp = self.client.post(
            "/api/auth/password",
            json={"current_password": "x", "new_password": "newpassword456"},
        )
        self.assertEqual(resp.status_code, 401)

    # -- Owner reset of a member's password --

    def test_owner_resets_member_password(self) -> None:
        self._seed_local_user("local-owner", "owner", "ownerpass123", role="owner")
        self._seed_local_user("local-bob", "bob", "oldpassword123", role="member")
        owner_login = self._login("owner", "ownerpass123")
        owner_cookie = self._extract_session_cookie(owner_login)

        resp = self.client.post(
            "/api/users/local-bob/reset-password",
            json={"new_password": "brandnewpass456"},
            headers=self._cookie_headers(owner_cookie),
        )
        self.assertEqual(resp.status_code, 200, resp.text)

        old_login = self._login("bob", "oldpassword123")
        self.assertEqual(old_login.status_code, 401)
        new_login = self._login("bob", "brandnewpass456")
        self.assertEqual(new_login.status_code, 200)

    def test_member_cannot_reset_another_users_password(self) -> None:
        self._seed_local_user("local-owner", "owner", "ownerpass123", role="owner")
        self._seed_local_user("local-bob", "bob", "oldpassword123", role="member")
        self._seed_local_user("local-carol", "carol", "carolpass123", role="member")
        bob_login = self._login("bob", "oldpassword123")
        bob_cookie = self._extract_session_cookie(bob_login)

        resp = self.client.post(
            "/api/users/local-carol/reset-password",
            json={"new_password": "brandnewpass456"},
            headers=self._cookie_headers(bob_cookie),
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_cannot_reset_password_for_plex_only_member(self) -> None:
        from projectionist.web.jobs import get_job_manager

        self._seed_local_user("local-owner", "owner", "ownerpass123", role="owner")
        get_job_manager().db.upsert_plex_user(
            user_id="plex-member",
            display_name="PlexMember",
            email=None,
            plex_user_id="12345",
            role="member",
        )
        owner_login = self._login("owner", "ownerpass123")
        owner_cookie = self._extract_session_cookie(owner_login)

        resp = self.client.post(
            "/api/users/plex-member/reset-password",
            json={"new_password": "brandnewpass456"},
            headers=self._cookie_headers(owner_cookie),
        )
        self.assertEqual(resp.status_code, 400)

    # -- Sign out everywhere --

    def test_sign_out_everywhere_kills_other_sessions_not_this_one(self) -> None:
        self._seed_local_user("local-alice", "alice", "password123")
        session_a = self._extract_session_cookie(self._login("alice", "password123"))
        session_b = self._extract_session_cookie(self._login("alice", "password123"))

        resp = self.client.post(
            "/api/auth/sign-out-everywhere",
            headers=self._cookie_headers(session_a),
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        refreshed_a = self._extract_session_cookie(resp)
        self.assertIsNotNone(refreshed_a)

        # Session B (not refreshed) is now dead.
        dead = self.client.get("/api/auth/me", headers=self._cookie_headers(session_b))
        self.assertEqual(dead.status_code, 401)

        # The refreshed session A cookie still works.
        alive = self.client.get("/api/auth/me", headers=self._cookie_headers(refreshed_a))
        self.assertEqual(alive.status_code, 200)


if __name__ == "__main__":
    unittest.main()
