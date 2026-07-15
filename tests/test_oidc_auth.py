"""Tests for OIDC authentication (Item 28).

Covers authorize redirect URL construction, callback token exchange
(mocked), user creation, session creation, and CSRF state validation.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from curatorx.web.auth import clear_oidc_states, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


def _mock_discovery():
    """Return a plausible OIDC discovery response."""
    return {
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "userinfo_endpoint": "https://idp.example.com/userinfo",
    }


def _mock_token_response():
    return MagicMock(
        status_code=200,
        json=lambda: {"access_token": "test-access-token", "token_type": "Bearer"},
        raise_for_status=lambda: None,
    )


def _mock_userinfo_response(sub="oidc-user-42", name="Jane Doe", email="jane@example.com"):
    return MagicMock(
        status_code=200,
        json=lambda: {"sub": sub, "name": name, "email": email},
        raise_for_status=lambda: None,
    )


class OIDCAuthTests(unittest.TestCase):
    """Integration tests for GET /api/auth/oidc/authorize and /api/auth/oidc/callback."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-oidc-auth-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        clear_oidc_states()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        clear_oidc_states()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _enable_oidc(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True},
            "auth": {
                "mode": "oidc",
                "plex_login_enabled": False,
                "oidc_enabled": True,
                "oidc_issuer_url": "https://idp.example.com",
                "oidc_client_id": "curatorx-test",
                "oidc_client_secret": "super-secret",
                "oidc_redirect_uri": "http://localhost:8000/api/auth/oidc/callback",
                "oidc_provider_name": "TestIDP",
            },
            "llm_provider": "ollama",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    # -- Authorize --

    def test_authorize_fails_when_oidc_disabled(self) -> None:
        resp = self.client.get("/api/auth/oidc/authorize")
        self.assertEqual(resp.status_code, 400)

    @patch("curatorx.web.auth.httpx")
    def test_authorize_returns_redirect_url(self, mock_httpx) -> None:
        self._enable_oidc()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_discovery()
        mock_httpx.get.return_value = mock_resp

        resp = self.client.get("/api/auth/oidc/authorize")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("authorize_url", body)
        self.assertIn("state", body)
        self.assertIn("https://idp.example.com/authorize", body["authorize_url"])
        self.assertIn("client_id=curatorx-test", body["authorize_url"])
        self.assertIn(f"state={body['state']}", body["authorize_url"])

    # -- Callback --

    def test_callback_rejects_invalid_state(self) -> None:
        self._enable_oidc()
        resp = self.client.get("/api/auth/oidc/callback?code=testcode&state=bogus")
        self.assertEqual(resp.status_code, 401)

    @patch("curatorx.web.auth.httpx")
    def test_callback_creates_user_and_sets_cookie(self, mock_httpx) -> None:
        self._enable_oidc()

        # 1. Start authorize to populate the state store
        mock_disc_resp = MagicMock()
        mock_disc_resp.json.return_value = _mock_discovery()
        mock_httpx.get.return_value = mock_disc_resp

        auth_resp = self.client.get("/api/auth/oidc/authorize")
        state = auth_resp.json()["state"]

        # 2. Mock token exchange and userinfo calls
        mock_httpx.post.return_value = _mock_token_response()
        mock_httpx.get.return_value = _mock_userinfo_response()

        # 3. Callback
        cb_resp = self.client.get(f"/api/auth/oidc/callback?code=testcode&state={state}")
        self.assertEqual(cb_resp.status_code, 200, cb_resp.text)
        body = cb_resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["display_name"], "Jane Doe")
        self.assertIn(SESSION_COOKIE_NAME, cb_resp.cookies)

    @patch("curatorx.web.auth.httpx")
    def test_callback_state_consumed_once(self, mock_httpx) -> None:
        """CSRF protection: state tokens are single-use."""
        self._enable_oidc()
        mock_disc_resp = MagicMock()
        mock_disc_resp.json.return_value = _mock_discovery()
        mock_httpx.get.return_value = mock_disc_resp

        auth_resp = self.client.get("/api/auth/oidc/authorize")
        state = auth_resp.json()["state"]

        mock_httpx.post.return_value = _mock_token_response()
        mock_httpx.get.return_value = _mock_userinfo_response()

        self.client.get(f"/api/auth/oidc/callback?code=testcode&state={state}")
        # Second use should fail
        second = self.client.get(f"/api/auth/oidc/callback?code=testcode&state={state}")
        self.assertEqual(second.status_code, 401)

    @patch("curatorx.web.auth.httpx")
    def test_oidc_user_auto_created_as_member(self, mock_httpx) -> None:
        """First OIDC login auto-creates users with member role."""
        self._enable_oidc()
        # Create an existing owner first so the OIDC user isn't the first
        from curatorx.web.jobs import get_job_manager

        db = get_job_manager().db
        db.ensure_bootstrap_owner()

        mock_disc_resp = MagicMock()
        mock_disc_resp.json.return_value = _mock_discovery()
        mock_httpx.get.return_value = mock_disc_resp
        auth_resp = self.client.get("/api/auth/oidc/authorize")
        state = auth_resp.json()["state"]

        mock_httpx.post.return_value = _mock_token_response()
        mock_httpx.get.return_value = _mock_userinfo_response(sub="new-sub-123")

        cb_resp = self.client.get(f"/api/auth/oidc/callback?code=c&state={state}")
        self.assertEqual(cb_resp.status_code, 200)
        self.assertEqual(cb_resp.json()["user"]["role"], "member")

    # -- Features --

    def test_features_includes_oidc_provider_name(self) -> None:
        self._enable_oidc()
        resp = self.client.get("/api/features")
        body = resp.json()
        self.assertIn("oidc", body.get("auth_methods", []))
        self.assertEqual(body["auth"]["oidc_provider_name"], "TestIDP")


if __name__ == "__main__":
    unittest.main()
