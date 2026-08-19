"""Invite-only household join (1.26)."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from projectionist.config_store import FeatureFlags, Settings, invite_required_for_new_users
from projectionist.invites import (
    create_household_invite,
    lookup_pending_invite,
    redeem_local_invite,
)
from projectionist.library.db import Database
from projectionist.web.auth import (
    authenticate_plex_user,
    clear_pin_bindings,
    clear_oidc_states,
)
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class InviteRequiredHelperTests(unittest.TestCase):
    def test_defaults_invite_only_when_multi_user(self) -> None:
        settings = Settings(features=FeatureFlags(multi_user_enabled=True))
        self.assertTrue(invite_required_for_new_users(settings))

    def test_open_auto_provision_requires_allow_open_join_env(self) -> None:
        settings = Settings(
            features=FeatureFlags(multi_user_enabled=True, open_auto_provision=True)
        )
        self.assertTrue(invite_required_for_new_users(settings))
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        try:
            self.assertFalse(invite_required_for_new_users(settings))
        finally:
            os.environ.pop("PROJECTIONIST_ALLOW_OPEN_JOIN", None)

    def test_public_profile_always_invite_only(self) -> None:
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        try:
            settings = Settings(
                features=FeatureFlags(
                    multi_user_enabled=True,
                    household_profile="public",
                    invite_only=False,
                    open_auto_provision=True,
                )
            )
            self.assertTrue(invite_required_for_new_users(settings))
        finally:
            os.environ.pop("PROJECTIONIST_ALLOW_OPEN_JOIN", None)

    def test_invite_only_off_disables_gate(self) -> None:
        settings = Settings(
            features=FeatureFlags(multi_user_enabled=True, invite_only=False)
        )
        self.assertFalse(invite_required_for_new_users(settings))


class InviteDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SESSION_SECRET"] = "test-invite-db-session-secret-xx"
        clear_session_secret_cache()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.create_local_user(
            user_id="owner-1",
            display_name="Owner",
            password_hash="x",
            role="owner",
        )

    def tearDown(self) -> None:
        clear_session_secret_cache()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def test_create_lookup_redeem_replay(self) -> None:
        created = create_household_invite(
            self.db,
            Settings(),
            owner_id="owner-1",
            role="member",
            allowed_methods=["local"],
            send_email=False,
        )
        raw = created["token"]
        invite = lookup_pending_invite(self.db, raw)
        self.assertEqual(invite["status"], "pending")
        redeemed = redeem_local_invite(
            self.db,
            Settings(auth=Settings().auth),
            raw_token=raw,
            username="joiner",
            password="password123",
        )
        # Force local login flag for redeem helper path that ignores settings.auth;
        # redeem_local_invite doesn't check local_login — that's the API layer.
        self.assertEqual(redeemed["user"]["role"], "member")
        with self.assertRaises(ValueError):
            lookup_pending_invite(self.db, raw)

    def test_concurrent_local_redeem_one_wins(self) -> None:
        import threading

        from projectionist.library.db import InviteConflict

        created = create_household_invite(
            self.db,
            Settings(),
            owner_id="owner-1",
            role="member",
            allowed_methods=["local"],
            send_email=False,
        )
        invite_id = str(created["invite"]["id"])
        wins: list[int] = []
        conflicts: list[int] = []
        unexpected: list[BaseException] = []

        def worker(index: int) -> None:
            try:
                self.db.create_local_user_and_redeem_invite(
                    invite_id=invite_id,
                    user_id=f"local-race-{index}",
                    display_name=f"racer{index}",
                    password_hash="ab$cd",
                    role="member",
                )
                wins.append(index)
            except InviteConflict:
                conflicts.append(index)
            except BaseException as error:  # noqa: BLE001
                unexpected.append(error)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertEqual(unexpected, [])
        self.assertEqual(len(wins), 1)
        self.assertEqual(len(conflicts), 7)
        users = [
            user
            for user in self.db.list_users(limit=50)
            if str(user.get("display_name") or "").startswith("racer")
        ]
        self.assertEqual(len(users), 1)
        invite = self.db.get_invite(invite_id)
        self.assertEqual(invite["status"], "redeemed")

    def test_denied_email_soft_blocks(self) -> None:
        row = self.db.create_access_request(display_name="No", email="blocked@example.com")
        self.db.resolve_access_request(row["id"], status="denied", resolved_by="owner-1")
        created = create_household_invite(
            self.db,
            Settings(),
            owner_id="owner-1",
            email="blocked@example.com",
            allowed_methods=["local"],
            send_email=False,
        )
        with self.assertRaises(ValueError) as ctx:
            redeem_local_invite(
                self.db,
                Settings(),
                raw_token=created["token"],
                username="blocked-user",
                password="password123",
            )
        self.assertIn("denied", str(ctx.exception).lower())

    def test_garbage_hmac_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            lookup_pending_invite(self.db, "not-a-real-token")
        with self.assertRaises(ValueError):
            lookup_pending_invite(self.db, "deadbeef.raw.badmac")

    def test_guest_role_rejected(self) -> None:
        with self.assertRaises(ValueError):
            create_household_invite(
                self.db,
                Settings(),
                owner_id="owner-1",
                role="guest",
                allowed_methods=["local"],
                send_email=False,
            )


class InviteApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SESSION_SECRET"] = "test-session-secret-invite-only-xx"
        os.environ["LLM_PROVIDER"] = "ollama"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        clear_oidc_states()

        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {
                        "multi_user_enabled": True,
                        "invite_only": True,
                        "open_auto_provision": False,
                    },
                    "auth": {
                        "mode": "local",
                        "plex_login_enabled": True,
                        "local_login_enabled": True,
                        "oidc_enabled": False,
                    },
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        clear_oidc_states()
        for key in (
            "CURATORX_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _register_owner(self) -> None:
        from projectionist.web.auth import _hash_password

        self.db.create_local_user(
            user_id="local-owner-invite",
            display_name="owner",
            password_hash=_hash_password("password123"),
            role="owner",
        )
        resp = self.client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_owner_create_revoke_authz(self) -> None:
        # Member cannot create invites.
        self._register_owner()
        # Create a second local user via invite redeem path first requires owner invite;
        # use open mode temporarily for a member session is heavy — instead assert 401 without session.
        self.client.cookies.clear()
        denied = self.client.post("/api/admin/invites", json={"role": "member"})
        self.assertEqual(denied.status_code, 401)

        # Owner can create + revoke.
        login = self.client.post(
            "/api/auth/local/login",
            json={"username": "owner", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "member", "is_youth": True, "allowed_methods": ["local"]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertTrue(body["token"])
        invite_id = body["invite"]["id"]
        revoked = self.client.post(f"/api/admin/invites/{invite_id}/revoke")
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(revoked.json()["invite"]["status"], "revoked")

    def test_local_redeem_and_replay_fails(self) -> None:
        self._register_owner()
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "member", "allowed_methods": ["local"]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token"]
        self.client.cookies.clear()

        valid = self.client.get("/api/invites/validate", params={"token": token})
        self.assertEqual(valid.status_code, 200, valid.text)

        redeem = self.client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "alex", "password": "password123"},
        )
        self.assertEqual(redeem.status_code, 200, redeem.text)
        self.assertTrue(redeem.json()["authenticated"])

        replay = self.client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "alex2", "password": "password123"},
        )
        self.assertEqual(replay.status_code, 409, replay.text)

    def test_garbage_token_validate_fails_closed(self) -> None:
        resp = self.client.get("/api/invites/validate", params={"token": "garbage.not.real"})
        self.assertEqual(resp.status_code, 400)

    def test_guest_invite_rejected(self) -> None:
        self._register_owner()
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "guest", "allowed_methods": ["local"]},
        )
        self.assertIn(created.status_code, (400, 422), created.text)

    def test_denied_cannot_redeem(self) -> None:
        self._register_owner()
        req = self.client.post(
            "/api/access-requests",
            json={"display_name": "Denied", "email": "nope@example.com"},
        )
        self.assertEqual(req.status_code, 200, req.text)
        request_id = req.json()["request"]["id"]
        deny = self.client.post(f"/api/admin/access-requests/{request_id}/deny")
        self.assertEqual(deny.status_code, 200, deny.text)

        created = self.client.post(
            "/api/admin/invites",
            json={
                "role": "member",
                "email": "nope@example.com",
                "allowed_methods": ["local"],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token"]
        self.client.cookies.clear()
        redeem = self.client.post(
            "/api/invites/redeem/local",
            json={"token": token, "username": "denied-user", "password": "password123"},
        )
        self.assertEqual(redeem.status_code, 400, redeem.text)
        self.assertIn("denied", redeem.json()["detail"].lower())
        self.assertIsNone(self.db.get_user_by_display_name("denied-user"))

    def test_plex_new_user_blocked_without_invite(self) -> None:
        self._register_owner()
        self.client.cookies.clear()
        with mock.patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-999", "title": "Newbie", "email": "n@ex.com"},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": "fake-token"})
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn("invite", resp.json()["detail"].lower())

    def test_plex_redeem_with_invite(self) -> None:
        self._register_owner()
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "member", "allowed_methods": ["plex"]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token"]
        self.client.cookies.clear()
        with mock.patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-888", "title": "Invited", "email": "i@ex.com"},
        ):
            resp = self.client.post(
                "/api/auth/plex",
                json={"auth_token": "fake-token", "invite_token": token},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["role"], "member")
        # Replay
        with mock.patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-777", "title": "Other", "email": "o@ex.com"},
        ):
            replay = self.client.post(
                "/api/auth/plex",
                json={"auth_token": "fake-token-2", "invite_token": token},
            )
        self.assertEqual(replay.status_code, 403, replay.text)

    def test_open_auto_provision_preserves_upsert(self) -> None:
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        path = Path(self._tmpdir.name) / "settings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["features"]["open_auto_provision"] = True
        data["features"]["household_profile"] = "private"
        path.write_text(json.dumps(data), encoding="utf-8")
        self._register_owner()
        self.client.cookies.clear()
        with mock.patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-open-1", "title": "OpenUser", "email": "o@ex.com"},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": "fake-token"})
        os.environ.pop("PROJECTIONIST_ALLOW_OPEN_JOIN", None)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["role"], "member")


class AuthenticatePlexUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_owner_bootstrap_uses_role_count(self) -> None:
        settings = Settings(
            features=FeatureFlags(multi_user_enabled=True, invite_only=True),
        )
        settings.auth.plex_login_enabled = True
        # Only bootstrap-owner exists — first Plex identity becomes real owner.
        self.assertFalse(
            any(
                u["id"] != "bootstrap-owner" and u["role"] == "owner"
                for u in self.db.list_users()
            )
        )
        with mock.patch("projectionist.web.auth._settings", return_value=settings), mock.patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": "plex-owner", "title": "First", "email": None},
        ), mock.patch("projectionist.web.auth._bridge_seerr_on_login", return_value=(None, None)), mock.patch(
            "projectionist.web.avatars.find_local_avatar_file",
            return_value=None,
        ), mock.patch(
            "projectionist.web.avatars.cache_remote_avatar",
            return_value=None,
        ), mock.patch(
            "projectionist.web.avatars.resolve_avatar_url",
            return_value=None,
        ):
            user = authenticate_plex_user("tok", self.db)
        self.assertEqual(user.role, "owner")
        self.assertTrue(
            any(
                u["id"] != "bootstrap-owner" and u["role"] == "owner"
                for u in self.db.list_users()
            )
        )


if __name__ == "__main__":
    unittest.main()
