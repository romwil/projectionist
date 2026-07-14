"""Tests for optional multi-user Plex auth."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.session_tokens import clear_session_secret_cache


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-auth-session-secret-value"
        clear_session_secret_cache()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self, *, seerr: bool = False) -> None:
        """Enable multi-user by writing settings to disk (owner PUT also works)."""
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True, "seerr_enabled": seerr},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
        }
        if seerr:
            payload["seerr"] = {"url": "http://seerr.test", "api_key": "secret"}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing.update(payload)
            if "features" in existing and "features" in payload:
                existing["features"] = {**existing.get("features", {}), **payload["features"]}
            payload = existing
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_bootstrap_owner_when_multi_user_disabled(self) -> None:
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["role"], "owner")
        self.assertEqual(body["user"]["id"], "bootstrap-owner")

    def test_auth_me_requires_session_when_multi_user_enabled(self) -> None:
        self._enable_multi_user()
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_features_unauthenticated_when_multi_user_enabled(self) -> None:
        self._enable_multi_user()
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["features"]["multi_user_enabled"])
        self.assertFalse(body["authenticated"])
        self.assertIsNone(body["user"])

    def test_plex_login_creates_owner_and_session(self) -> None:
        self._enable_multi_user()
        profile = {
            "id": 12345,
            "title": "Household Owner",
            "email": "owner@example.com",
            "thumb": "https://plex.test/avatar.jpg",
        }
        with patch("curatorx.web.auth.fetch_plex_account", return_value=profile):
            resp = self.client.post("/api/auth/plex", json={"auth_token": "plex-token-1"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["role"], "owner")
        self.assertEqual(body["user"]["plex_user_id"], "12345")
        self.assertIn("curatorx_session", resp.cookies)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["display_name"], "Household Owner")

    def test_plex_pin_login_flow(self) -> None:
        self._enable_multi_user()
        pin_create = {
            "id": 77,
            "code": "ABCD",
            "client_id": "client-xyz",
            "auth_url": "https://app.plex.tv/auth/#!?clientID=client-xyz&code=ABCD",
            "expires_in": 1800,
            "expires_at": "2099-01-01T00:00:00Z",
        }
        profile = {"id": 4242, "title": "PIN User", "email": "pin@example.com"}
        with patch("curatorx.web.auth.create_plex_pin", return_value=pin_create), patch(
            "curatorx.web.auth.get_or_create_client_id",
            return_value="client-xyz",
        ):
            start = self.client.post("/api/auth/plex/pin")
        self.assertEqual(start.status_code, 200)
        start_body = start.json()
        self.assertEqual(start_body["id"], 77)
        self.assertEqual(start_body["code"], "ABCD")
        self.assertIn("app.plex.tv/auth", start_body["auth_url"])

        with patch("curatorx.web.auth.fetch_plex_pin", return_value={"authToken": None}), patch(
            "curatorx.web.auth.get_or_create_client_id",
            return_value="client-xyz",
        ):
            pending = self.client.get("/api/auth/plex/pin/77")
        self.assertEqual(pending.status_code, 200)
        self.assertTrue(pending.json()["pending"])
        self.assertFalse(pending.json()["authenticated"])

        with patch(
            "curatorx.web.auth.fetch_plex_pin",
            return_value={"authToken": "pin-auth-token"},
        ), patch(
            "curatorx.web.auth.get_or_create_client_id",
            return_value="client-xyz",
        ), patch("curatorx.web.auth.fetch_plex_account", return_value=profile):
            done = self.client.get("/api/auth/plex/pin/77")
        self.assertEqual(done.status_code, 200)
        body = done.json()
        self.assertTrue(body["authenticated"])
        self.assertFalse(body["pending"])
        self.assertEqual(body["user"]["plex_user_id"], "4242")
        self.assertIn("curatorx_session", done.cookies)

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["display_name"], "PIN User")

    def test_plex_pin_start_requires_multi_user(self) -> None:
        resp = self.client.post("/api/auth/plex/pin")
        self.assertEqual(resp.status_code, 400)

    def test_plex_login_second_user_is_member(self) -> None:
        self._enable_multi_user()
        owner_profile = {"id": 1, "title": "Owner", "email": "owner@example.com"}
        member_profile = {"id": 2, "title": "Member", "email": "member@example.com"}
        with patch("curatorx.web.auth.fetch_plex_account", return_value=owner_profile):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        self.client.post("/api/auth/logout")

        with patch("curatorx.web.auth.fetch_plex_account", return_value=member_profile):
            resp = self.client.post("/api/auth/plex", json={"auth_token": "member-token"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"]["role"], "member")

    def test_plex_login_bridges_seerr_when_enabled(self) -> None:
        self._enable_multi_user(seerr=True)
        profile = {"id": 99, "title": "Seerr User", "email": "seerr@example.com"}
        seerr_payload = {"id": 7, "permissions": 2}
        with patch("curatorx.web.auth.fetch_plex_account", return_value=profile), patch(
            "curatorx.web.auth.SeerrClient.link_plex_user",
            return_value=seerr_payload,
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": "plex-token"})
        self.assertEqual(resp.status_code, 200)
        user = resp.json()["user"]
        self.assertEqual(user["seerr_user_id"], 7)

        import curatorx.web.jobs as jobs

        row = jobs.get_job_manager().db.get_user(user["id"])
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(int(row["seerr_user_id"]), 7)
        self.assertEqual(int(row["seerr_permissions"]), 2)

    def test_logout_clears_session(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 5, "title": "Logout User"},
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "token"})
        self.assertEqual(login.status_code, 200)

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertTrue(logout.json()["logged_out"])

        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 401)

    def test_owner_can_list_and_update_users(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})

        listed = self.client.get("/api/users")
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["items"]
        self.assertTrue(any(item["role"] == "owner" for item in items))

        member_id = "plex-20"
        import curatorx.web.jobs as jobs

        jobs.get_job_manager().db.upsert_plex_user(
            user_id=member_id,
            display_name="Member",
            email="member@example.com",
            plex_user_id="20",
            role="member",
        )
        updated = self.client.patch(f"/api/users/{member_id}", json={"role": "guest"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["user"]["role"], "guest")

    def test_member_requests_filtered_by_seerr_user(self) -> None:
        self._enable_multi_user(seerr=True)
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 30, "title": "Owner"},
        ), patch(
            "curatorx.web.auth.SeerrClient.link_plex_user",
            return_value={"id": 99, "permissions": 0},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        self.client.post("/api/auth/logout")

        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 31, "title": "Member"},
        ), patch(
            "curatorx.web.auth.SeerrClient.link_plex_user",
            return_value={"id": 55, "permissions": 0},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "member-token"})

        payload = {"results": [], "pageInfo": {"results": 0, "pages": 0, "page": 1, "pageSize": 20}}
        with patch("curatorx.web.app.SeerrClient.list_requests", return_value=payload) as mock_list:
            resp = self.client.get("/api/requests")
        self.assertEqual(resp.status_code, 200)
        mock_list.assert_called_once_with(take=20, skip=0, filter=None, requested_by=55)
