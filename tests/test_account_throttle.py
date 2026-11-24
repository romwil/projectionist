"""SEC-018: per-account sign-in lock and a generic failure."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.account_throttle import (
    BASE_LOCK_SECONDS,
    GENERIC_INVITE_DETAIL,
    GENERIC_LOGIN_DETAIL,
    MAX_LOCK_SECONDS,
    account_throttle,
    clear_account_throttle,
    invite_key,
    lock_seconds_for_round,
    login_key,
)
from projectionist.web.rate_limit import clear_rate_limits


class LockScheduleTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_account_throttle()

    def test_rounds_double_until_a_day(self) -> None:
        self.assertEqual(lock_seconds_for_round(1), BASE_LOCK_SECONDS)
        self.assertEqual(lock_seconds_for_round(2), BASE_LOCK_SECONDS * 2)
        self.assertEqual(lock_seconds_for_round(20), MAX_LOCK_SECONDS)

    def test_tenth_failure_locks_and_success_clears(self) -> None:
        key = login_key("Ada")
        for _ in range(9):
            self.assertIsNone(account_throttle.record_failure(key, now=0))
        self.assertEqual(account_throttle.record_failure(key, now=0), BASE_LOCK_SECONDS)
        self.assertTrue(account_throttle.locked(key, now=1))
        self.assertIsNone(account_throttle.record_failure(key, now=1))
        self.assertFalse(account_throttle.locked(key, now=BASE_LOCK_SECONDS))
        account_throttle.record_success(key)
        self.assertIsNone(account_throttle.record_failure(key, now=BASE_LOCK_SECONDS))

    def test_second_round_is_twice_as_long(self) -> None:
        key = invite_key("not-a-token")
        for index in range(20):
            started = account_throttle.record_failure(key, now=0 if index < 10 else 10**9)
        self.assertEqual(started, BASE_LOCK_SECONDS * 2)


class SignInLockHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-account-throttle-session-secret"
        os.environ.pop("PROJECTIONIST_TRUST_PROXY_HEADERS", None)
        os.environ.pop("PROJECTIONIST_TRUSTED_PROXIES", None)
        from projectionist.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        clear_rate_limits()
        clear_account_throttle()
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {
                        "mode": "local",
                        "plex_login_enabled": False,
                        "local_login_enabled": True,
                    },
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
            role="member",
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_rate_limits()
        clear_account_throttle()
        from projectionist.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "DATA_DIR",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_TRUST_PROXY_HEADERS",
            "PROJECTIONIST_TRUSTED_PROXIES",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login(self, username: str, password: str = "wrong-password"):
        return self.client.post(
            "/api/auth/local/login",
            json={"username": username, "password": password},
        )

    def test_missing_and_known_accounts_fail_the_same_way(self) -> None:
        missing = self._login("nobody")
        known = self._login("Ada")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(known.status_code, 401)
        self.assertEqual(missing.json(), known.json())
        self.assertEqual(missing.json()["detail"], GENERIC_LOGIN_DETAIL)

    def test_lock_uses_the_same_error_and_is_on_the_security_log(self) -> None:
        key = login_key("Ada")
        for _ in range(9):
            account_throttle.record_failure(key, now=0)
        locked = self._login("Ada")
        self.assertEqual(locked.status_code, 401)
        self.assertEqual(locked.json()["detail"], GENERIC_LOGIN_DETAIL)
        clear_rate_limits()
        again = self._login("nobody-else")
        self.assertEqual(again.status_code, 401)
        still = self._login("Ada")
        self.assertEqual(still.status_code, 401)
        self.assertEqual(still.json(), locked.json())
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT event, outcome, detail_json FROM security_audit_log "
                "WHERE event = 'sign_in_locked'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["outcome"], "locked")
        detail = json.loads(row["detail_json"])
        self.assertEqual(detail["kind"], "username")
        self.assertEqual(detail["subject"], "Ada")
        self.assertEqual(detail["lock_minutes"], 15)
        self.assertNotIn("password", json.dumps(detail).lower())

    def test_invite_failures_share_one_message_and_lock_one_invite(self) -> None:
        from projectionist.web.auth import _hash_password

        self.db.create_local_user(
            user_id="local-owner",
            display_name="owner",
            password_hash=_hash_password("password123"),
            role="owner",
        )
        login = self._login("owner", "password123")
        self.assertEqual(login.status_code, 200, login.text)
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "member", "allowed_methods": ["local"]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token"]
        self.client.cookies.clear()
        clear_rate_limits()

        garbage = self.client.post(
            "/api/invites/redeem/local",
            json={"token": "not-a-real-token", "username": "sam", "password": "password123"},
        )
        self.assertEqual(garbage.status_code, 400)
        self.assertEqual(garbage.json()["detail"], GENERIC_INVITE_DETAIL)

        key = invite_key(token)
        for _ in range(9):
            account_throttle.record_failure(key, now=0)
        clear_rate_limits()
        failed = self.client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "owner", "password": "password123"},
        )
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(failed.json()["detail"], GENERIC_INVITE_DETAIL)
        clear_rate_limits()
        locked = self.client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "sam", "password": "password123"},
        )
        self.assertEqual(locked.json(), garbage.json())
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT detail_json FROM security_audit_log WHERE event = 'sign_in_locked' "
                "AND detail_json LIKE '%invite%'"
            ).fetchone()
        self.assertIsNotNone(row)
        detail = json.loads(row["detail_json"])
        self.assertNotIn(token, json.dumps(detail))
