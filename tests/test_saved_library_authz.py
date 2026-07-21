"""API authorization for saved-library read/export endpoints.

Regression coverage for the fix that stops these endpoints from passing an
empty ``user_id`` to the DB: a signed-out or unscoped request must be rejected
(401) rather than matching legacy NULL-owner rows, and one member must not be
able to read another member's saved page (404).
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


class SavedLibraryAuthzTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-saved-library-authz-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
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
        clear_rate_limits()
        for key in (
            "CURATORX_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

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

    def _create_saved_page(self, name: str = "Sci-fi gaps") -> str:
        resp = self.client.post(
            "/api/saved-library",
            json={
                "name": name,
                "summary": "A short saved summary.",
                "content": {"blocks": [{"type": "text", "content": "Watch Stalker."}]},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["id"]

    def test_read_and_export_require_scoped_user_in_single_workspace(self) -> None:
        # Multi-user disabled -> _scoped_user_id is None, so there is no scoped
        # owner to match; the endpoints must reject rather than leak NULL-owner rows.
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/saved-library/any-id").status_code, 401)
        self.assertEqual(
            self.client.get("/api/saved-library/any-id/export").status_code, 401
        )

    def test_read_and_export_reject_unauthenticated_when_multi_user(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        page_id = self._create_saved_page()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(f"/api/saved-library/{page_id}").status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/saved-library/{page_id}/export").status_code, 401
        )

    def test_owner_can_read_and_export_but_member_cannot(self) -> None:
        self._enable_multi_user_via_api()
        self._login_as(1, "Owner")
        page_id = self._create_saved_page()

        owner_read = self.client.get(f"/api/saved-library/{page_id}")
        self.assertEqual(owner_read.status_code, 200, owner_read.text)
        self.assertEqual(owner_read.json()["name"], "Sci-fi gaps")
        owner_export = self.client.get(f"/api/saved-library/{page_id}/export")
        self.assertEqual(owner_export.status_code, 200, owner_export.text)

        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")
        self.assertEqual(self.client.get(f"/api/saved-library/{page_id}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/saved-library/{page_id}/export").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
