"""Env-seeded owner + first-owner race close (review finding H2)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.web import auth
from projectionist.web.session_tokens import clear_session_secret_cache

_OWNER_ENV_KEYS = ("PROJECTIONIST_OWNER_USERNAME", "PROJECTIONIST_OWNER_PASSWORD",
                   "PROJECTIONIST_OWNER_USERNAME", "PROJECTIONIST_OWNER_PASSWORD")


class OwnerSeedingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.db.ensure_bootstrap_owner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _clear_owner_env(self, env: dict) -> None:
        for key in _OWNER_ENV_KEYS:
            env.pop(key, None)

    def test_bootstrap_owner_is_not_a_real_owner(self) -> None:
        self.assertFalse(auth.has_real_owner(self.db))

    def test_seed_noop_without_password(self) -> None:
        with patch.dict(os.environ, {}, clear=False) as env:
            self._clear_owner_env(env)
            self.assertIsNone(auth.seed_env_owner(self.db))
        self.assertFalse(auth.has_real_owner(self.db))

    def test_seed_creates_local_owner(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PROJECTIONIST_OWNER_PASSWORD": "correct horse battery",
                "PROJECTIONIST_OWNER_USERNAME": "boss",
            },
            clear=False,
        ):
            user_id = auth.seed_env_owner(self.db)
        self.assertIsNotNone(user_id)
        self.assertTrue(auth.has_real_owner(self.db))
        row = self.db.get_user_by_display_name("boss")
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "owner")
        self.assertTrue(auth._verify_password("correct horse battery", str(row["password_hash"])))

    def test_seed_defaults_username_to_owner(self) -> None:
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "supersecretpw"}, clear=False) as env:
            env.pop("PROJECTIONIST_OWNER_USERNAME", None)
            env.pop("PROJECTIONIST_OWNER_USERNAME", None)
            auth.seed_env_owner(self.db)
        self.assertIsNotNone(self.db.get_user_by_display_name(auth.DEFAULT_OWNER_USERNAME))

    def test_seed_rejects_short_password(self) -> None:
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "short"}, clear=False):
            self.assertIsNone(auth.seed_env_owner(self.db))

    def test_seed_idempotent(self) -> None:
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "supersecretpw"}, clear=False):
            first = auth.seed_env_owner(self.db)
            second = auth.seed_env_owner(self.db)
        self.assertEqual(first, second)
        owners = [
            u
            for u in self.db.list_users(limit=100)
            if u.get("role") == "owner" and u.get("id") != BOOTSTRAP_OWNER_ID
        ]
        self.assertEqual(len(owners), 1)

    def test_rotating_password_updates_owner(self) -> None:
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "originalpassword"}, clear=False):
            user_id = auth.seed_env_owner(self.db)
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "rotatedpassword"}, clear=False):
            again = auth.seed_env_owner(self.db)
        self.assertEqual(user_id, again)
        row = self.db.get_user(user_id)
        self.assertTrue(auth._verify_password("rotatedpassword", str(row["password_hash"])))
        self.assertFalse(auth._verify_password("originalpassword", str(row["password_hash"])))

    def test_seed_does_not_clobber_different_owner(self) -> None:
        self.db.upsert_plex_user(
            user_id="plex-1",
            display_name="Existing",
            email=None,
            plex_user_id="1",
            role="owner",
            avatar_url=None,
            seerr_user_id=None,
            seerr_permissions=None,
        )
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "supersecretpw"}, clear=False):
            self.assertIsNone(auth.seed_env_owner(self.db))
        self.assertIsNone(self.db.get_user_by_display_name(auth.DEFAULT_OWNER_USERNAME))

    def test_seed_does_not_promote_member_when_real_owner_exists(self) -> None:
        """Matching username must not become a second owner via env seed."""
        self.db.upsert_plex_user(
            user_id="plex-1",
            display_name="Existing",
            email=None,
            plex_user_id="1",
            role="owner",
            avatar_url=None,
            seerr_user_id=None,
            seerr_permissions=None,
        )
        self.db.create_local_user(
            user_id="local-member",
            display_name="boss",
            password_hash=auth._hash_password("memberpassword"),
            role="member",
        )
        with patch.dict(
            os.environ,
            {
                "PROJECTIONIST_OWNER_USERNAME": "boss",
                "PROJECTIONIST_OWNER_PASSWORD": "supersecretpw",
            },
            clear=False,
        ):
            self.assertIsNone(auth.seed_env_owner(self.db))
        row = self.db.get_user_by_display_name("boss")
        self.assertIsNotNone(row)
        self.assertEqual(row["role"], "member")
        self.assertTrue(auth._verify_password("memberpassword", str(row["password_hash"])))
        owners = [
            u
            for u in self.db.list_users(limit=100)
            if u.get("role") == "owner" and u.get("id") != BOOTSTRAP_OWNER_ID
        ]
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0]["id"], "plex-1")

    def test_seed_promotes_matching_member_when_no_real_owner(self) -> None:
        self.db.create_local_user(
            user_id="local-member",
            display_name="boss",
            password_hash=auth._hash_password("oldpassword"),
            role="member",
        )
        with patch.dict(
            os.environ,
            {
                "PROJECTIONIST_OWNER_USERNAME": "boss",
                "PROJECTIONIST_OWNER_PASSWORD": "newownerpw",
            },
            clear=False,
        ):
            user_id = auth.seed_env_owner(self.db)
        self.assertEqual(user_id, "local-member")
        row = self.db.get_user("local-member")
        self.assertEqual(row["role"], "owner")
        self.assertTrue(auth._verify_password("newownerpw", str(row["password_hash"])))

    def test_seed_syncs_password_when_existing_is_already_owner(self) -> None:
        self.db.create_local_user(
            user_id="local-owner",
            display_name="boss",
            password_hash=auth._hash_password("oldownerpw"),
            role="owner",
        )
        with patch.dict(
            os.environ,
            {
                "PROJECTIONIST_OWNER_USERNAME": "boss",
                "PROJECTIONIST_OWNER_PASSWORD": "rotatedownerpw",
            },
            clear=False,
        ):
            user_id = auth.seed_env_owner(self.db)
        self.assertEqual(user_id, "local-owner")
        row = self.db.get_user("local-owner")
        self.assertEqual(row["role"], "owner")
        self.assertTrue(auth._verify_password("rotatedownerpw", str(row["password_hash"])))
        owners = [
            u
            for u in self.db.list_users(limit=100)
            if u.get("role") == "owner" and u.get("id") != BOOTSTRAP_OWNER_ID
        ]
        self.assertEqual(len(owners), 1)


class NewUserRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.db.ensure_bootstrap_owner()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_real_user_claims_owner_legacy(self) -> None:
        self.assertEqual(auth.resolve_new_user_role(self.db), "owner")

    def test_subsequent_users_are_members_after_seed(self) -> None:
        with patch.dict(os.environ, {"PROJECTIONIST_OWNER_PASSWORD": "supersecretpw"}, clear=False):
            auth.seed_env_owner(self.db)
        self.assertEqual(auth.resolve_new_user_role(self.db), "member")


class OwnerSeedingIntegrationTests(unittest.TestCase):
    """Enable multi-user → seed env owner → local login is owner; later Plex is member."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(
            os.environ,
            {
                "DATA_DIR": self._tmp.name,
                "PROJECTIONIST_SKIP_DOTENV": "1",
                "LLM_PROVIDER": "ollama",
                "PROJECTIONIST_SESSION_SECRET": "integration-owner-seed-secret-value",
                "PROJECTIONIST_OWNER_USERNAME": "boss",
                "PROJECTIONIST_OWNER_PASSWORD": "seededownerpw",
            },
            clear=False,
        )
        self._env.start()
        clear_session_secret_cache()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        self.client.close()
        self._env.stop()
        self._tmp.cleanup()

    def _enable_multi_user(self) -> None:
        resp = self.client.put(
            "/api/settings",
            json={
                "features": {"multi_user_enabled": True, "seerr_enabled": False},
                "auth": {"mode": "plex", "plex_login_enabled": True},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_enable_multi_user_seeds_owner_and_closes_race(self) -> None:
        self._enable_multi_user()

        login = self.client.post(
            "/api/auth/local/login", json={"username": "boss", "password": "seededownerpw"}
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user"]["role"], "owner")
        self.client.post("/api/auth/logout")

        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 99, "title": "Neighbor", "email": "n@example.com"},
        ):
            plex = self.client.post("/api/auth/plex", json={"auth_token": "neighbor-token"})
        # Invite-only may be on; neighbor without invite should be 403, or member if open.
        self.assertIn(plex.status_code, (200, 403), plex.text)
        if plex.status_code == 200:
            self.assertEqual(plex.json()["user"]["role"], "member")


if __name__ == "__main__":
    unittest.main()
