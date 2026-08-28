"""Atomic Plex link: poll never binds; POST requires password in the same request."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.web.auth import _hash_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class PlexLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-plex-link-session-secret-xx"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        Path(self._tmpdir.name).joinpath("settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True, "invite_only": True},
                    "auth": {
                        "mode": "local",
                        "local_login_enabled": True,
                        "plex_login_enabled": True,
                    },
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        self.client = TestClient(app_mod.app)
        from projectionist.web.jobs import get_job_manager

        self.db = get_job_manager().db
        self.db.create_local_user(
            user_id="local-owner-link",
            display_name="owner",
            password_hash=_hash_password("password123"),
            role="owner",
        )
        login = self.client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in ("PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER", "PROJECTIONIST_SESSION_SECRET", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _start_pin(self, pin_id: int = 42) -> None:
        with patch(
            "projectionist.web.auth.create_plex_pin",
            return_value={
                "id": pin_id,
                "code": "ABCD",
                "auth_url": "https://app.plex.tv/auth#?pin=ABCD",
                "expires_in": 900,
            },
        ):
            started = self.client.post("/api/auth/plex/pin")
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["id"], pin_id)

    def test_peek_poll_never_binds_or_replaces_session(self) -> None:
        self._start_pin()
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-99", "title": "Should Not Bind", "email": "p@ex.com"},
        ):
            poll = self.client.get("/api/auth/plex/pin/42?peek=1")
        self.assertEqual(poll.status_code, 200, poll.text)
        body = poll.json()
        self.assertTrue(body["authorized"])
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["bound"])
        self.assertTrue(body["pending"] is False)
        self.assertIsNone(body.get("user"))
        set_cookie = poll.headers.get("set-cookie") or ""
        self.assertNotIn("curatorx_session=", set_cookie)
        row = self.db.get_user("local-owner-link")
        self.assertFalse(row["plex_user_id"])
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["id"], "local-owner-link")

    def test_unauthenticated_login_poll_sets_session(self) -> None:
        self.db.upsert_plex_user(
            user_id="plex-login-1",
            display_name="PIN Member",
            email="pin@ex.com",
            plex_user_id="plex-login-1",
            role="member",
        )
        self.client.cookies.clear()
        self._start_pin(51)
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-login-1", "title": "PIN Member", "email": "pin@ex.com"},
        ):
            poll = self.client.get("/api/auth/plex/pin/51")
        self.assertEqual(poll.status_code, 200, poll.text)
        body = poll.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["id"], "plex-login-1")
        self.assertIn("curatorx_session", poll.cookies)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["id"], "plex-login-1")

    def test_leftover_session_login_poll_replaces_cookie(self) -> None:
        self.db.upsert_plex_user(
            user_id="plex-login-2",
            display_name="Second",
            email="second@ex.com",
            plex_user_id="plex-login-2",
            role="member",
        )
        leftover = self.client.get("/api/auth/me")
        self.assertEqual(leftover.json()["user"]["id"], "local-owner-link")
        self._start_pin(52)
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-login-2", "title": "Second", "email": "second@ex.com"},
        ):
            poll = self.client.get("/api/auth/plex/pin/52")
        self.assertEqual(poll.status_code, 200, poll.text)
        body = poll.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["id"], "plex-login-2")
        self.assertIn("curatorx_session", poll.cookies)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user"]["id"], "plex-login-2")
        self.assertFalse(self.db.get_user("local-owner-link")["plex_user_id"])

    def test_login_poll_new_plex_identity_requires_invite(self) -> None:
        self._start_pin(53)
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-new", "title": "Newbie", "email": "n@ex.com"},
        ):
            poll = self.client.get("/api/auth/plex/pin/53")
        self.assertEqual(poll.status_code, 403, poll.text)
        self.assertIn("invite", str(poll.json().get("detail", "")).lower())
        self.assertIsNone(self.db.get_user_by_plex_id("plex-new"))
        self.assertFalse(self.db.get_user("local-owner-link")["plex_user_id"])

    def test_link_requires_password_and_binds_once(self) -> None:
        self._start_pin()
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-77", "title": "Owner", "email": "o@ex.com"},
        ):
            denied = self.client.post(
                "/api/auth/plex/link",
                json={"pin_id": 42, "password": "wrong-password"},
            )
            self.assertEqual(denied.status_code, 401, denied.text)
            self.assertFalse(self.db.get_user("local-owner-link")["plex_user_id"])
            linked = self.client.post(
                "/api/auth/plex/link",
                json={"pin_id": 42, "password": "password123"},
            )
        self.assertEqual(linked.status_code, 200, linked.text)
        self.assertTrue(linked.json()["linked"])
        self.assertEqual(str(self.db.get_user("local-owner-link")["plex_user_id"]), "plex-77")

    def test_claimed_plex_user_id_is_rejected(self) -> None:
        self.db.create_local_user(
            user_id="local-other",
            display_name="other",
            password_hash=_hash_password("password123"),
            role="member",
        )
        self.db.bind_plex_user_id("local-other", plex_user_id="plex-claimed")
        self._start_pin(9)
        with patch(
            "projectionist.web.auth.fetch_plex_pin",
            return_value={"authToken": "plex-auth-token"},
        ), patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-claimed", "title": "Taken", "email": "t@ex.com"},
        ):
            resp = self.client.post(
                "/api/auth/plex/link",
                json={"pin_id": 9, "password": "password123"},
            )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertFalse(self.db.get_user("local-owner-link")["plex_user_id"])


if __name__ == "__main__":
    unittest.main()
