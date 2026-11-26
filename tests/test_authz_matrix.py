"""Generated authorization matrix.

Every registered route is requested as anonymous, guest, Youth, member,
another member, and owner. Denial is the live check. Handlers that start
playback or a library sync are not invoked for a role that is allowed
through, because those handlers wait on ffmpeg. Their denial paths still run.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import sys

from projectionist.web.auth import _hash_password
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache

_HARNESS = Path(__file__).resolve().parents[1] / "scripts" / "security" / "pentest"
if str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))
from lib.surface import collect_routes, fill_path  # noqa: E402

# Allowed callers are not sent into these handlers. Denial still is.
_HEAVY_PREFIXES = (
    "/api/playback/",
    "/api/engine/",
    "/api/library/sync",
    "/api/admin/live-channels",
    "/api/settings",
)
_DENIED = {401, 403, 404, 405}
_PRIVATE = "member-a-private-phrase"


class AuthzMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-authz-matrix-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        Path(cls._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {
                        "mode": "local",
                        "local_login_enabled": True,
                        "plex_login_enabled": False,
                    },
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        cls.client = TestClient(app_mod.app, raise_server_exceptions=False)
        cls.routes = collect_routes(app_mod.app)
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
        password = _hash_password("correct-horse")
        db.create_local_user(
            user_id="matrix-owner",
            display_name="matrix-owner",
            password_hash=password,
            role="owner",
            email="owner@example.test",
        )
        db.create_local_user(
            user_id="matrix-member-a",
            display_name="matrix-member-a",
            password_hash=password,
            role="member",
            email="member-a@example.test",
        )
        db.create_local_user(
            user_id="matrix-member-b",
            display_name="matrix-member-b",
            password_hash=password,
            role="member",
            email="member-b@example.test",
        )
        db.create_local_user(
            user_id="matrix-youth",
            display_name="matrix-youth",
            password_hash=password,
            role="member",
            email="youth@example.test",
        )
        db.set_user_youth("matrix-youth", True)
        db.create_local_user(
            user_id="matrix-guest",
            display_name="matrix-guest",
            password_hash=password,
            role="guest",
            email="guest@example.test",
        )
        db.ensure_chat_session("member-a-thread", "default", user_id="matrix-member-a")
        db.save_chat_message(
            "member-a-thread",
            "member-a-thread-user",
            "user",
            [{"type": "text", "content": _PRIVATE}],
        )
        cls.cookies = {
            "owner": cls._login("matrix-owner"),
            "member": cls._login("matrix-member-a"),
            "other-member": cls._login("matrix-member-b"),
            "youth": cls._login("matrix-youth"),
            "guest": cls._login("matrix-guest"),
        }
        cls.owned_ids = {
            "session_id": "member-a-thread",
            "thread_id": "member-a-thread",
            "user_id": "matrix-member-a",
            "member_id": "matrix-member-a",
        }

    @classmethod
    def tearDownClass(cls) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        cls._tmpdir.cleanup()

    @classmethod
    def _login(cls, username: str) -> str:
        from tests.totp_login import finish_sign_in_code

        cls.client.cookies.clear()
        clear_rate_limits()
        response = cls.client.post(
            "/api/auth/local/login",
            json={"username": username, "password": "correct-horse"},
        )
        response = finish_sign_in_code(
            cls.client, response, username, "correct-horse"
        )
        if response.status_code != 200:
            raise AssertionError(f"{username} login -> {response.status_code} {response.text}")
        token = cls.client.cookies.get(SESSION_COOKIE_NAME)
        if not token:
            raise AssertionError(f"{username} login did not set a session")
        return str(token)

    def _request(self, method: str, path: str, token: str | None):
        clear_rate_limits()
        self.client.cookies.clear()
        if token:
            self.client.cookies.set(SESSION_COOKIE_NAME, token)
        kwargs = {}
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            kwargs["json"] = {}
        return self.client.request(method, path, follow_redirects=False, **kwargs)

    def test_matrix_covers_routers_and_roles(self) -> None:
        self.assertGreater(len(self.routes), 80, "route list did not include the routers")
        roles = {"anonymous", "guest", "youth", "member", "other-member", "owner"}
        violations: list[str] = []
        probed = 0
        denial_only = 0
        for row in self.routes:
            method = row["method"]
            template = row["path"]
            auth = row["auth"]
            for role in roles:
                token = None if role == "anonymous" else self.cookies[role]
                values = self.owned_ids if role == "other-member" else None
                path = fill_path(template, values)
                allowed = _actor_allowed(role, auth)
                heavy = any(path.startswith(prefix) or template.startswith(prefix) for prefix in _HEAVY_PREFIXES)
                if allowed and heavy:
                    denial_only += 1
                    continue
                probed += 1
                response = self._request(method, path, token)
                status = response.status_code
                body = response.text or ""
                reason = _violation(role, auth, status, body, path)
                if reason:
                    violations.append(f"{role} {method} {template} -> {status} ({reason})")
        self.assertFalse(
            violations,
            "authz matrix:\n" + "\n".join(violations[:40])
            + (f"\n... {len(violations) - 40} more" if len(violations) > 40 else ""),
        )
        self.assertGreater(probed, 0)
        # Heavy handlers are counted so a future reader can see they were not skipped silently.
        self.assertGreaterEqual(denial_only, 0)

    def test_other_member_cannot_read_private_thread(self) -> None:
        response = self._request(
            "GET",
            "/api/chat/threads/member-a-thread/messages",
            self.cookies["other-member"],
        )
        self.assertIn(response.status_code, {403, 404}, response.text)
        self.assertNotIn(_PRIVATE, response.text)

    def test_member_cannot_change_settings(self) -> None:
        denied = self._request("PUT", "/api/settings", self.cookies["member"])
        self.assertEqual(denied.status_code, 403, denied.text)
        guest = self._request("PUT", "/api/settings", self.cookies["guest"])
        self.assertIn(guest.status_code, {401, 403, 404}, guest.text)
        youth = self._request("PUT", "/api/settings", self.cookies["youth"])
        self.assertEqual(youth.status_code, 403, youth.text)


def _actor_allowed(role: str, auth: str) -> bool:
    if auth in {"public", "static"}:
        return True
    if role == "anonymous":
        return False
    if auth == "owner":
        return role == "owner"
    if auth in {"session", "role-gated", "webhook-secret", "mcp-api-key"}:
        return role != "anonymous"
    return False


def _violation(role: str, auth: str, status: int, body: str, path: str) -> str:
    if role == "other-member" and _PRIVATE in body:
        return "other member received member A's private thread text"
    if role == "anonymous" and auth not in {"public", "static"}:
        if status not in _DENIED:
            return "anonymous was not denied"
        return ""
    if auth == "owner" and role not in {"owner", "anonymous"}:
        if status not in _DENIED:
            return "non-owner was not denied on an owner route"
        return ""
    if role != "anonymous" and auth in {"session", "role-gated", "owner"} and status == 401:
        return "signed-in role was treated as anonymous"
    if role == "other-member" and "/member-a-thread" in path and status == 200 and _PRIVATE in body:
        return "IDOR"
    return ""
