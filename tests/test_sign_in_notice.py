"""SEC-025: a new browser tells the owner, and the owner can remove it."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.web.account_throttle import clear_account_throttle
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache
from projectionist.web.sign_in_notice import SIGN_IN_TITLE
from tests.totp_login import finish_sign_in_code


class SignInNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-sign-in-notice-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_account_throttle()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "local_login_enabled": True, "plex_login_enabled": False},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        from projectionist.web.auth import _hash_password

        self.db = app_mod._db()
        self.db.create_local_user(
            user_id="ada",
            display_name="Ada",
            password_hash=_hash_password("correct-horse"),
            role="owner",
            email="ada@example.com",
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login(self, client: TestClient, user_agent: str):
        headers = {"User-Agent": user_agent}
        started = client.post(
            "/api/auth/local/login",
            json={"username": "Ada", "password": "correct-horse"},
            headers=headers,
        )
        return finish_sign_in_code(
            client,
            started,
            "Ada",
            "correct-horse",
            headers=headers,
        )

    def _letters(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT title FROM user_notifications WHERE user_id = ?",
                ("ada",),
            ).fetchall()
        return [str(row["title"]) for row in rows]

    def test_a_new_browser_is_noticed_once_and_can_be_removed(self) -> None:
        with (
            patch("projectionist.web.sign_in_notice.mail_configured", return_value=True),
            patch("projectionist.web.sign_in_notice.send_mail") as send_mail,
        ):
            first = self._login(self.client, "BrowserA")
            self.assertEqual(first.status_code, 200, first.text)
            send_mail.assert_called()
            self.assertEqual(send_mail.call_args.kwargs["to_email"], "ada@example.com")
            self.assertIn(SIGN_IN_TITLE, send_mail.call_args.kwargs["subject"])

            again = self._login(self.client, "BrowserA")
            self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(send_mail.call_count, 1)
            self.assertEqual(self._letters().count(SIGN_IN_TITLE), 1)
            first_cookie = self.client.cookies.get(SESSION_COOKIE_NAME)

            second = self._login(self.client, "BrowserB")
            self.assertEqual(second.status_code, 200, second.text)
            self.assertEqual(self._letters().count(SIGN_IN_TITLE), 2)
            self.assertEqual(send_mail.call_count, 2)
            second_cookie = self.client.cookies.get(SESSION_COOKIE_NAME)

        other = TestClient(self.app_mod.app)
        other.cookies.set(SESSION_COOKIE_NAME, second_cookie)
        self.client.cookies.set(SESSION_COOKIE_NAME, first_cookie)

        listed = self.client.get("/api/devices")
        self.assertEqual(listed.status_code, 200, listed.text)
        browsers = [row for row in listed.json()["devices"] if row["kind"] == "browser"]
        self.assertEqual(len(browsers), 2)
        other_id = next(row["id"] for row in browsers if "BrowserB" in row["label"])
        revoked = self.client.post(f"/api/devices/{other_id}/revoke")
        self.assertEqual(revoked.status_code, 200, revoked.text)
        blocked = other.get("/api/auth/me")
        self.assertEqual(blocked.status_code, 401, blocked.text)
        still = self.client.get("/api/auth/me")
        self.assertEqual(still.status_code, 200, still.text)
