"""API authorization when multi-user auth is enabled."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.session_tokens import (
    DEV_SESSION_SECRET,
    clear_session_secret_cache,
    ensure_session_secret,
)


class ApiAuthzTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-api-authz-session-secret-value"
        clear_session_secret_cache()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        for key in (
            "CURATORX_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _write_multi_user_settings(self, *, seerr: bool = False) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True, "seerr_enabled": seerr},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
        }
        if seerr:
            payload["seerr"] = {"url": "http://seerr.test", "api_key": "secret"}
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _enable_multi_user_via_api(self) -> None:
        resp = self.client.put(
            "/api/settings",
            json={
                "features": {"multi_user_enabled": True, "seerr_enabled": False},
                "auth": {"mode": "plex", "plex_login_enabled": True},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def _login_as(self, plex_id: int, title: str) -> None:
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": plex_id, "title": title, "email": f"{title}@example.com"},
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"token-{plex_id}"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_unauthenticated_mutating_routes_require_session(self) -> None:
        self._enable_multi_user_via_api()
        self.client.cookies.clear()

        settings = self.client.put("/api/settings", json={"features": {"multi_user_enabled": True}})
        self.assertEqual(settings.status_code, 401)

        chat = self.client.post("/api/chat", json={"message": "hi", "session_id": "s1"})
        self.assertEqual(chat.status_code, 401)

        confirm = self.client.post(
            "/api/actions/confirm",
            json={"token": "not-a-real-token", "confirmed": True},
        )
        self.assertEqual(confirm.status_code, 401)

    def test_member_cannot_put_settings_owner_can(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")

        denied = self.client.put(
            "/api/settings",
            json={"features": {"multi_user_enabled": True}},
        )
        self.assertEqual(denied.status_code, 403)

        self.client.post("/api/auth/logout")
        self._login_as(1, "Owner")
        allowed = self.client.put(
            "/api/settings",
            json={"features": {"multi_user_enabled": True}},
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertTrue(allowed.json()["features"]["multi_user_enabled"])

    def test_public_allowlist_stays_open(self) -> None:
        self._write_multi_user_settings()
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        features = self.client.get("/api/features")
        self.assertEqual(features.status_code, 200)
        self.assertTrue(features.json()["features"]["multi_user_enabled"])
        self.assertFalse(features.json()["authenticated"])

    def test_library_csv_export_requires_auth_and_uses_requested_columns(self) -> None:
        self._enable_multi_user_via_api()
        from curatorx.web.jobs import get_job_manager

        get_job_manager().db.upsert_library_item(
            {"rating_key": "csv-1", "media_type": "movie", "title": "CSV Title", "year": 2024}
        )
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/library/export.csv").status_code, 401)
        self._login_as(1, "Owner")
        response = self.client.get("/api/library/export.csv?columns=title,year")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.text.splitlines()[0], "title,year")
        self.assertIn("CSV Title,2024", response.text)
        self.assertIn("curatorx-library-", response.headers["content-disposition"])

    def test_member_can_report_but_cannot_repair_media_issue(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")
        created = self.client.post(
            "/api/media-issues",
            json={"media_type": "movie", "title": "Broken Movie", "tmdb_id": 1, "code": "bad_video"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        issue_id = created.json()["id"]
        self.assertEqual(self.client.get("/api/media-issues").status_code, 403)
        self.assertEqual(self.client.post(f"/api/media-issues/{issue_id}/repair").status_code, 403)
        self.client.post("/api/auth/logout")
        self._login_as(1, "Owner")
        repaired = self.client.post(f"/api/media-issues/{issue_id}/repair")
        self.assertEqual(repaired.status_code, 200, repaired.text)
        self.assertEqual(repaired.json()["repair_action"], "skipped")

    def test_refuse_multi_user_when_dev_session_secret(self) -> None:
        os.environ["CURATORX_SESSION_SECRET"] = DEV_SESSION_SECRET
        clear_session_secret_cache()
        resp = self.client.put(
            "/api/settings",
            json={
                "features": {"multi_user_enabled": True},
                "auth": {"mode": "plex", "plex_login_enabled": True},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("session secret", resp.json()["detail"].lower())

    def test_session_secret_auto_persisted(self) -> None:
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        clear_session_secret_cache()
        secret = ensure_session_secret(Path(self._tmpdir.name))
        path = Path(self._tmpdir.name) / "session_secret"
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8").strip(), secret)
        self.assertNotEqual(secret, DEV_SESSION_SECRET)

    def test_system_config_requires_auth_when_multi_user(self) -> None:
        self._enable_multi_user_via_api()
        self.client.cookies.clear()
        resp = self.client.get("/api/system-config")
        self.assertEqual(resp.status_code, 401)

    def test_system_config_accessible_to_owner(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        resp = self.client.get("/api/system-config")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), dict)

    def test_system_config_blocked_for_member(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")
        resp = self.client.get("/api/system-config")
        self.assertEqual(resp.status_code, 403)

    def test_system_config_blocked_for_guest(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        from curatorx.web.jobs import get_job_manager

        get_job_manager().db.update_user_role(
            self._get_user_id(3, "Guest"), "guest"
        )
        self.client.post("/api/auth/logout")
        self._login_as(3, "Guest")
        resp = self.client.get("/api/system-config")
        self.assertEqual(resp.status_code, 403)

    def _get_user_id(self, plex_id: int, title: str) -> str:
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={
                "id": plex_id,
                "title": title,
                "email": f"{title}@example.com",
            },
        ):
            resp = self.client.post(
                "/api/auth/plex",
                json={"auth_token": f"token-{plex_id}"},
            )
        return resp.json()["user"]["id"]

    def test_secure_cookie_with_forwarded_proto(self) -> None:
        self._enable_multi_user_via_api()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 9, "title": "Secure User"},
        ):
            resp = self.client.post(
                "/api/auth/plex",
                json={"auth_token": "secure-token"},
                headers={"X-Forwarded-Proto": "https"},
            )
        self.assertEqual(resp.status_code, 200)
        set_cookie = resp.headers.get("set-cookie", "")
        self.assertIn("curatorx_session=", set_cookie)
        self.assertIn("Secure", set_cookie)


if __name__ == "__main__":
    unittest.main()
