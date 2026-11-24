"""SEC-019: owner passwords need a sign-in code. New passwords skip the common list."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.account_throttle import GENERIC_LOGIN_DETAIL, clear_account_throttle
from projectionist.web.passwords import COMMON_PASSWORD_DETAIL, SHORT_PASSWORD_DETAIL, password_rejection
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME
from projectionist.web.totp import SIGN_IN_CODE_REQUIRED, current_code, totp_matches


class PasswordListTests(unittest.TestCase):
    def test_short_and_common_passwords_are_refused(self) -> None:
        self.assertEqual(password_rejection("short"), SHORT_PASSWORD_DETAIL)
        self.assertEqual(password_rejection("password123"), COMMON_PASSWORD_DETAIL)
        self.assertEqual(password_rejection("Password123"), COMMON_PASSWORD_DETAIL)
        self.assertIsNone(password_rejection("correct-horse"))

    def test_rfc6238_sha1_vector(self) -> None:
        from projectionist.web.totp import totp_at

        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(totp_at(secret, 59 // 30), "287082")
        self.assertEqual(totp_at(secret, 1111111109 // 30), "081804")


class OwnerSignInCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-owner-totp-secret"
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
            role="owner",
        )
        self.db.create_local_user(
            user_id="beau",
            display_name="Beau",
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
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login(self, username: str, password: str = "correct-horse", **extra: object):
        body = {"username": username, "password": password, **extra}
        return self.client.post("/api/auth/local/login", json=body)

    def test_wrong_password_matches_a_missing_account(self) -> None:
        missing = self._login("nobody", "not-the-password")
        known = self._login("Ada", "not-the-password")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json(), known.json())
        self.assertEqual(missing.json()["detail"], GENERIC_LOGIN_DETAIL)
        self.assertNotIn("secret", missing.json())

    def test_owner_password_sets_up_a_code_before_a_session(self) -> None:
        setup = self._login("Ada")
        self.assertEqual(setup.status_code, 401, setup.text)
        body = setup.json()
        self.assertEqual(body["detail"], "Set up a sign-in code to finish signing in.")
        self.assertTrue(body["secret"])
        self.assertEqual(len(body["recovery_codes"]), 8)
        self.assertNotIn("correct-horse", json.dumps(body))
        self.assertIsNone(setup.cookies.get(SESSION_COOKIE_NAME))

        code = current_code(body["secret"])
        self.assertTrue(totp_matches(body["secret"], code))
        clear_rate_limits()
        signed_in = self._login("Ada", code=code)
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        self.assertTrue(signed_in.json()["authenticated"])

        clear_rate_limits()
        again = self._login("Ada")
        self.assertEqual(again.status_code, 401)
        self.assertEqual(again.json(), {"detail": SIGN_IN_CODE_REQUIRED})
        self.assertNotIn("secret", again.json())

        clear_rate_limits()
        with_code = self._login("Ada", code=current_code(body["secret"]))
        self.assertEqual(with_code.status_code, 200, with_code.text)

    def test_recovery_code_works_once(self) -> None:
        setup = self._login("Ada")
        recovery = setup.json()["recovery_codes"][0]
        clear_rate_limits()
        self._login("Ada", code=current_code(setup.json()["secret"]))
        self.client.cookies.clear()
        clear_rate_limits()
        used = self._login("Ada", code=recovery)
        self.assertEqual(used.status_code, 200, used.text)
        self.client.cookies.clear()
        clear_rate_limits()
        replay = self._login("Ada", code=recovery)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()["detail"], "That sign-in code isn't valid.")

    def test_member_password_signs_in_until_the_owner_requires_a_code(self) -> None:
        member = self._login("Beau")
        self.assertEqual(member.status_code, 200, member.text)
        self.client.cookies.clear()
        settings = json.loads((Path(self._tmpdir.name) / "settings.json").read_text(encoding="utf-8"))
        settings["auth"]["require_totp"] = True
        (Path(self._tmpdir.name) / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        clear_rate_limits()
        challenged = self._login("Beau")
        self.assertEqual(challenged.status_code, 401, challenged.text)
        self.assertIn("secret", challenged.json())

    def test_a_new_common_password_is_refused(self) -> None:
        self._login("Beau")
        changed = self.client.post(
            "/api/auth/password",
            json={"current_password": "correct-horse", "new_password": "password123"},
        )
        self.assertEqual(changed.status_code, 400, changed.text)
        self.assertEqual(changed.json()["detail"], COMMON_PASSWORD_DETAIL)
