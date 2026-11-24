"""NAT-002: every web sign-in path can end in a device credential."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from projectionist.devices.pairing import CREDENTIAL_PREFIX
from projectionist.web.auth import clear_oidc_states, clear_pin_bindings
from projectionist.web.capabilities import client_capabilities
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache
from tests.owner_claim_helpers import grant_owner_claim

CLIENT = {"kind": "iphone", "label": "Kitchen phone"}
PIN_HEADER = "x-projectionist-pin-nonce"


def _pkce(verifier: str = "a" * 43) -> tuple[str, str]:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class NativeSignInTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-native-sign-in-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
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
        grant_owner_claim(self.client)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        clear_oidc_states()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
            "PROJECTIONIST_ALLOW_OPEN_JOIN",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _write_settings(self, **auth: object) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {
                "multi_user_enabled": True,
                "invite_only": True,
                "open_auto_provision": True,
                "access_requests_enabled": True,
            },
            "auth": {
                "mode": "local",
                "plex_login_enabled": False,
                "local_login_enabled": True,
                "oidc_enabled": False,
                **auth,
            },
            "llm_provider": "ollama",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _seed_owner(self) -> None:
        from projectionist.web.auth import _hash_password
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.create_local_user(
            user_id="local-owner",
            display_name="Owner",
            password_hash=_hash_password("correct-horse"),
            role="owner",
        )

    def _assert_device_credential(self, body: dict, *, kind: str = "iphone") -> str:
        credential = str(body.get("credential") or "")
        self.assertTrue(credential.startswith(CREDENTIAL_PREFIX), body)
        self.assertEqual(body.get("kind"), kind)
        self.assertTrue(body.get("device_id"))
        self.assertNotIn(credential, json.dumps({k: v for k, v in body.items() if k != "credential"}))
        return credential

    def _device_me(self, credential: str) -> dict:
        bare = TestClient(self.client.app)
        resp = bare.get("/api/auth/me", headers={"Authorization": f"Bearer {credential}"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["user"]

    def test_public_method_list_and_capability_stay_honest(self) -> None:
        self._write_settings()
        resp = TestClient(self.client.app).get("/api/features")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["sign_in"]["methods"], ["local"])
        self.assertTrue(body["sign_in"]["access_requests_open"])
        self.assertEqual(body["capabilities"]["native_sign_in"], client_capabilities()["native_sign_in"])
        self.assertEqual(body["capabilities"]["native_sign_in"], 1)

    def test_local_login_returns_a_credential_and_skips_the_cookie(self) -> None:
        self._write_settings()
        self._seed_owner()
        payload = {"username": "Owner", "password": "correct-horse", "client": CLIENT}
        resp = self.client.post("/api/auth/local/login", json=payload)
        from tests.totp_login import finish_sign_in_code

        resp = finish_sign_in_code(
            self.client, resp, "Owner", "correct-horse", payload=payload
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertNotIn(SESSION_COOKIE_NAME, resp.cookies)
        self.assertIn("no-store", resp.headers.get("cache-control", ""))
        credential = self._assert_device_credential(body)
        self.assertEqual(self._device_me(credential)["display_name"], "Owner")
        listed = TestClient(self.client.app).get(
            "/api/devices", headers={"Authorization": f"Bearer {credential}"}
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        devices = listed.json()["devices"]
        self.assertEqual(devices[0]["kind"], "iphone")
        self.assertEqual(devices[0]["label"], "Kitchen phone")
        self.assertNotIn("credential", devices[0])

        browser = self.client.post(
            "/api/auth/local/login",
            json={"username": "Owner", "password": "correct-horse"},
        )
        from tests.totp_login import finish_sign_in_code

        browser = finish_sign_in_code(self.client, browser, "Owner", "correct-horse")
        self.assertEqual(browser.status_code, 200, browser.text)
        self.assertNotIn("credential", browser.json())
        self.assertIn(SESSION_COOKIE_NAME, browser.cookies)

    def test_bad_client_kind_is_rejected_before_a_session(self) -> None:
        self._write_settings()
        self._seed_owner()
        resp = self.client.post(
            "/api/auth/local/login",
            json={
                "username": "Owner",
                "password": "correct-horse",
                "client": {"kind": "android", "label": "Phone"},
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertNotIn(SESSION_COOKIE_NAME, resp.cookies)
        self.assertNotIn("credential", resp.json())
        self.assertNotIn("secret", resp.json())

    def test_owner_register_can_hand_the_new_account_a_device(self) -> None:
        self._write_settings()
        self._seed_owner()
        owner = self.client.post(
            "/api/auth/local/login",
            json={"username": "Owner", "password": "correct-horse"},
        )
        from tests.totp_login import finish_sign_in_code

        owner = finish_sign_in_code(self.client, owner, "Owner", "correct-horse")
        self.assertEqual(owner.status_code, 200, owner.text)
        created = self.client.post(
            "/api/auth/local/register",
            json={"username": "Alex", "password": "correct-horse", "client": CLIENT},
        )
        self.assertEqual(created.status_code, 200, created.text)
        credential = self._assert_device_credential(created.json())
        self.assertEqual(self._device_me(credential)["display_name"], "Alex")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.json()["user"]["display_name"], "Owner")

    def test_plex_pin_nonce_is_client_held(self) -> None:
        self._write_settings(plex_login_enabled=True, mode="plex")
        self._seed_owner()
        pin_create = {
            "id": 77,
            "code": "ABCD",
            "auth_url": "https://app.plex.tv/auth/#!?clientID=client-xyz&code=ABCD",
            "expires_in": 1800,
        }
        profile = {"id": 4242, "title": "PIN User", "email": "pin@example.com"}
        with patch("projectionist.web.auth.create_plex_pin", return_value=pin_create), patch(
            "projectionist.web.auth.get_or_create_client_id", return_value="client-xyz"
        ):
            start = self.client.post("/api/auth/plex/pin", json={"client": CLIENT})
        self.assertEqual(start.status_code, 200, start.text)
        nonce = start.json().get("pin_nonce")
        self.assertTrue(nonce)
        self.assertNotIn("plex_pin_nonce", start.cookies)
        self.assertNotIn(str(nonce), start.json()["auth_url"])

        bare = TestClient(self.client.app)
        with patch("projectionist.web.auth.fetch_plex_pin", return_value={"authToken": "pin-token"}):
            missing = bare.get("/api/auth/plex/pin/77")
        self.assertEqual(missing.status_code, 401)

        with patch("projectionist.web.auth.fetch_plex_pin", return_value={"authToken": None}), patch(
            "projectionist.web.auth.get_or_create_client_id", return_value="client-xyz"
        ):
            pending = bare.get("/api/auth/plex/pin/77", headers={PIN_HEADER: nonce})
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertTrue(pending.json()["pending"])

        with patch(
            "projectionist.web.auth.fetch_plex_pin", return_value={"authToken": "pin-token"}
        ), patch(
            "projectionist.web.auth.get_or_create_client_id", return_value="client-xyz"
        ), patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            done = bare.get("/api/auth/plex/pin/77", headers={PIN_HEADER: nonce})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertNotIn(SESSION_COOKIE_NAME, done.cookies)
        credential = self._assert_device_credential(done.json())
        self.assertEqual(self._device_me(credential)["display_name"], "PIN User")
        self.assertNotIn("pin-token", done.text)

        with patch(
            "projectionist.web.auth.fetch_plex_pin", return_value={"authToken": "pin-token"}
        ):
            replay = bare.get("/api/auth/plex/pin/77", headers={PIN_HEADER: nonce})
        self.assertIn(replay.status_code, (401, 409))

    def test_plex_token_login_returns_a_credential(self) -> None:
        self._write_settings(plex_login_enabled=True, mode="plex")
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 9, "title": "Plex Owner"},
        ):
            resp = self.client.post(
                "/api/auth/plex",
                json={"auth_token": "plex-token", "client": CLIENT},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn(SESSION_COOKIE_NAME, resp.cookies)
        credential = self._assert_device_credential(resp.json())
        self.assertEqual(self._device_me(credential)["role"], "owner")
        self.assertNotIn("plex-token", resp.text)

    def test_oidc_uses_pkce_and_a_single_use_code(self) -> None:
        self._write_settings(
            mode="oidc",
            plex_login_enabled=False,
            local_login_enabled=True,
            oidc_enabled=True,
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="projectionist-test",
            oidc_client_secret="super-secret",
            oidc_redirect_uri="http://localhost:8788/api/auth/oidc/callback",
        )
        self._seed_owner()
        verifier, challenge = _pkce()
        discovery = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
        }
        with patch("projectionist.web.auth.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: discovery)
            started = self.client.post(
                "/api/auth/oidc/authorize",
                json={
                    "client": CLIENT,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
        self.assertEqual(started.status_code, 200, started.text)
        authorize_url = started.json()["authorize_url"]
        parsed = urlparse(authorize_url)
        params = parse_qs(parsed.query)
        self.assertEqual(params["code_challenge"], [challenge])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(
            params["redirect_uri"],
            ["http://localhost:8788/api/auth/oidc/callback"],
        )
        self.assertNotIn("projectionist://", authorize_url)
        state = started.json()["state"]

        token = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "idp-access"},
            raise_for_status=lambda: None,
        )
        userinfo = MagicMock(
            status_code=200,
            json=lambda: {"sub": "native-1", "name": "Native Member"},
            raise_for_status=lambda: None,
        )
        with patch("projectionist.web.auth.httpx.post", return_value=token) as mock_post, patch(
            "projectionist.web.auth.httpx.get", return_value=userinfo
        ):
            callback = self.client.get(
                "/api/auth/oidc/callback",
                params={"code": "idp-code", "state": state},
                follow_redirects=False,
            )
            self.assertEqual(callback.status_code, 302, callback.text)
            location = callback.headers["location"]
            self.assertTrue(location.startswith("projectionist://auth/callback?"))
            self.assertNotIn("credential", location)
            self.assertNotIn("idp-code", location)
            self.assertNotIn(SESSION_COOKIE_NAME, callback.cookies)
            handed = parse_qs(urlparse(location).query)
            code = handed["code"][0]

            bare = TestClient(self.client.app)
            exchanged = bare.post(
                "/api/auth/oidc/exchange",
                json={"code": code, "code_verifier": verifier, "client": CLIENT},
            )
            self.assertEqual(exchanged.status_code, 200, exchanged.text)
            self.assertNotIn(SESSION_COOKIE_NAME, exchanged.cookies)
            credential = self._assert_device_credential(exchanged.json())
            self.assertEqual(self._device_me(credential)["display_name"], "Native Member")
            sent = mock_post.call_args.kwargs["data"]
            self.assertEqual(sent["code_verifier"], verifier)
            self.assertNotIn("super-secret", exchanged.text)

            replay = bare.post(
                "/api/auth/oidc/exchange",
                json={"code": code, "code_verifier": verifier, "client": CLIENT},
            )
            self.assertEqual(replay.status_code, 401, replay.text)

    def test_invite_validate_is_public_and_redeem_returns_a_credential(self) -> None:
        self._write_settings()
        self._seed_owner()
        owner = self.client.post(
            "/api/auth/local/login",
            json={"username": "Owner", "password": "correct-horse"},
        )
        from tests.totp_login import finish_sign_in_code

        owner = finish_sign_in_code(self.client, owner, "Owner", "correct-horse")
        self.assertEqual(owner.status_code, 200, owner.text)
        created = self.client.post(
            "/api/admin/invites",
            json={"role": "member", "allowed_methods": ["local"]},
        )
        self.assertEqual(created.status_code, 200, created.text)
        token = created.json()["token"]
        bare = TestClient(self.client.app)
        valid = bare.get("/api/invites/validate", params={"token": token})
        self.assertEqual(valid.status_code, 200, valid.text)
        invite = valid.json()["invite"]
        self.assertEqual(invite["inviter_display_name"], "Owner")
        self.assertEqual(invite["role"], "member")
        self.assertIn("expires_at", invite)
        self.assertNotIn("email", invite)
        self.assertEqual(set(invite), {
            "inviter_display_name",
            "role",
            "expires_at",
            "is_youth",
            "allowed_methods",
        })

        redeemed = bare.post(
            "/api/invites/redeem/local",
            json={
                "token": token,
                "username": "Alex",
                "password": "correct-horse",
                "client": {"kind": "ipad", "label": "Sofa"},
            },
        )
        self.assertEqual(redeemed.status_code, 200, redeemed.text)
        self.assertNotIn(SESSION_COOKIE_NAME, redeemed.cookies)
        credential = self._assert_device_credential(redeemed.json(), kind="ipad")
        self.assertEqual(self._device_me(credential)["display_name"], "Alex")

    def test_access_request_needs_no_cookie(self) -> None:
        self._write_settings()
        bare = TestClient(self.client.app)
        resp = bare.post(
            "/api/access-requests",
            json={"display_name": "Neighbor", "message": "May I join?"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["request"]["status"], "pending")
        self.assertNotIn(SESSION_COOKIE_NAME, resp.cookies)
        self.assertNotIn("credential", resp.json())
