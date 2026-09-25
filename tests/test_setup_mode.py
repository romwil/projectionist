"""SETUP_MODE ratchet, handshake persist, and public-profile commit."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from projectionist.web.auth import has_real_owner
from projectionist.web.setup_mode import (
    RECOVERY_KEY_HASH_KEY,
    SETUP_SNAPSHOT_KEY,
    SETUP_STATE_KEY,
    WAN_COMMIT_OWNER_PASSWORD_DETAIL,
    is_setup_public_path,
    resolve_commit_household_domain,
    resolve_commit_invite_only,
    resolve_commit_trust_proxy,
)


class SetupModeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-setup-mode-session-secret-xx"
        os.environ["HOST"] = "0.0.0.0"
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app, client=("192.168.1.20", 43210))

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "HOST",
            "PROJECTIONIST_SETUP_STATE",
            "PROJECTIONIST_OWNER_PASSWORD",
            "PROJECTIONIST_OWNER_USERNAME",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_docker_nat_handshake_preselects_public(self) -> None:
        docker = self._client_at("172.17.0.1")
        resp = docker.get("/api/setup/handshake")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["classification"], "public_failsafe")
        self.assertEqual(body["preselect_profile"], "public")
        self.assertFalse(body["halt"])
        snap = body["snapshot"]
        blob = json.dumps(snap).lower()
        self.assertNotIn("authorization", blob)
        self.assertNotIn("x-plex-token", blob)
        from projectionist.web.jobs import get_job_manager

        stored = get_job_manager().db.get_config(SETUP_SNAPSHOT_KEY)
        self.assertIsNotNone(stored)
        self.assertNotIn("authorization", stored.lower())

    def _client_at(self, host: str) -> TestClient:
        return TestClient(self.app_mod.app, client=(host, 43210))

    def _assert_setup_uncommitted(self) -> None:
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
        self.assertFalse(has_real_owner(db))
        self.assertNotEqual(db.get_config(SETUP_STATE_KEY), "active")
        self.assertIsNone(db.get_config(RECOVERY_KEY_HASH_KEY))
        features = self.client.get("/api/features")
        self.assertEqual(features.status_code, 200, features.text)
        self.assertEqual(features.json()["setup_state"], "setup")

    def test_wan_peer_commit_is_rejected(self) -> None:
        wan = self._client_at("8.8.8.8")
        handshake = wan.get("/api/setup/handshake")
        self.assertEqual(handshake.status_code, 403, handshake.text)

        commit = wan.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
            },
        )
        self.assertEqual(commit.status_code, 403, commit.text)
        self._assert_setup_uncommitted()

    def test_wan_peer_blocks_setup_tests_health_stays_open(self) -> None:
        wan = self._client_at("8.8.8.8")
        self.assertEqual(wan.get("/api/health").status_code, 200)
        self.assertEqual(wan.get("/api/features").status_code, 200)
        plex = wan.post(
            "/api/setup/test/plex",
            json={"plex_url": "http://plex.local", "plex_token": "x"},
        )
        self.assertEqual(plex.status_code, 403, plex.text)
        tmdb = wan.post("/api/setup/test/tmdb", json={"tmdb_api_key": "x"})
        self.assertEqual(tmdb.status_code, 403, tmdb.text)

        lan = self._client_at("192.168.1.20")
        lan_plex = lan.post(
            "/api/setup/test/plex",
            json={"plex_url": "http://invalid.local", "plex_token": "bad"},
        )
        self.assertEqual(lan_plex.status_code, 200, lan_plex.text)
        self.assertFalse(lan_plex.json()["ok"])

    def test_docker_nat_setup_tests_are_not_allowlisted(self) -> None:
        docker = self._client_at("172.17.0.1")
        plex = docker.post(
            "/api/setup/test/plex",
            json={"plex_url": "http://plex.local", "plex_token": "x"},
        )
        self.assertEqual(plex.status_code, 404, plex.text)

    def test_public_failsafe_commit_requires_owner_password(self) -> None:
        docker = self._client_at("172.17.0.1")
        commit = docker.post(
            "/api/setup/commit",
            json={
                "profile": "public",
                "username": "owner",
                "password": "password123",
                "household_domain": "movies.example.com",
                "trust_proxy": True,
            },
        )
        self.assertEqual(commit.status_code, 403, commit.text)
        self.assertEqual(commit.json()["detail"], WAN_COMMIT_OWNER_PASSWORD_DETAIL)
        self._assert_setup_uncommitted()

    def test_public_failsafe_commit_allowed_when_owner_password_set(self) -> None:
        os.environ["PROJECTIONIST_OWNER_PASSWORD"] = "host-owner-password"
        docker = self._client_at("172.17.0.1")
        try:
            commit = docker.post(
                "/api/setup/commit",
                json={
                    "profile": "public",
                    "username": "owner",
                    "password": "password123",
                    "household_domain": "movies.example.com",
                    "trust_proxy": True,
                },
            )
        finally:
            os.environ.pop("PROJECTIONIST_OWNER_PASSWORD", None)
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertEqual(commit.json()["setup_state"], "active")

    def test_wan_peer_commit_public_profile_is_still_rejected(self) -> None:
        wan = self._client_at("8.8.8.8")
        commit = wan.post(
            "/api/setup/commit",
            json={
                "profile": "public",
                "username": "owner",
                "password": "password123",
                "household_domain": "movies.example.com",
                "trust_proxy": True,
            },
        )
        self.assertEqual(commit.status_code, 403, commit.text)
        self._assert_setup_uncommitted()

    def test_rfc1918_peer_can_commit(self) -> None:
        lan = self._client_at("192.168.1.20")
        handshake = lan.get("/api/setup/handshake")
        self.assertEqual(handshake.status_code, 200, handshake.text)
        self.assertFalse(handshake.json()["halt"])

        commit = lan.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertEqual(commit.json()["setup_state"], "active")

    def test_tailscale_cgnat_peer_can_commit(self) -> None:
        ts = self._client_at("100.64.1.1")
        handshake = ts.get("/api/setup/handshake")
        self.assertEqual(handshake.status_code, 200, handshake.text)
        self.assertFalse(handshake.json()["halt"])
        self.assertEqual(handshake.json()["classification"], "lan")

        commit = ts.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertEqual(commit.json()["setup_state"], "active")

    def test_commit_public_profile_locks_invite_only(self) -> None:
        handshake = self.client.get("/api/setup/handshake")
        self.assertEqual(handshake.status_code, 200, handshake.text)
        commit = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "public",
                "username": "owner",
                "password": "password123",
                "household_domain": "movies.example.com",
                "trust_proxy": True,
                "allow_access_requests": True,
                "invite_only": False,
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        body = commit.json()
        self.assertEqual(body["setup_state"], "active")
        self.assertEqual(body["profile"], "public")
        self.assertTrue(body["recovery_key"])
        self.assertTrue(body["posture"]["multi_user_enabled"])
        self.assertTrue(body["posture"]["invite_only"])
        self.assertTrue(body["posture"]["trust_proxy_headers"])
        self.assertEqual(body["posture"]["household_domain"], "movies.example.com")
        features = self.client.get("/api/features")
        self.assertEqual(features.status_code, 200, features.text)
        feat = features.json()
        self.assertEqual(feat["setup_state"], "active")
        self.assertTrue(feat["features"]["multi_user_enabled"])
        self.assertTrue(feat["features"]["invite_only"])
        self.assertTrue(feat["features"]["trust_proxy_headers"])
        self.assertNotIn("guest_tour_enabled", feat["features"])
        from projectionist.web.jobs import get_job_manager

        self.assertEqual(get_job_manager().db.get_config(SETUP_STATE_KEY), "active")

    def test_commit_private_omits_invite_only_defaults_off(self) -> None:
        commit = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        body = commit.json()
        self.assertEqual(body["profile"], "private")
        self.assertFalse(body["posture"]["invite_only"])
        feat = self.client.get("/api/features").json()
        self.assertFalse(feat["features"]["invite_only"])
        self.assertFalse(feat["features"]["trust_proxy_headers"])

    def test_commit_private_sticky_trust_proxy_stays_untrusted(self) -> None:
        commit = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
                "trust_proxy": True,
                "household_domain": "movies.example.com",
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        body = commit.json()
        self.assertEqual(body["profile"], "private")
        self.assertFalse(body["posture"]["trust_proxy_headers"])
        self.assertEqual(body["posture"]["household_domain"], "")
        feat = self.client.get("/api/features").json()
        self.assertFalse(feat["features"]["trust_proxy_headers"])
        self.assertEqual(feat["household_domain"], "")

    def test_commit_private_explicit_invite_only_on(self) -> None:
        commit = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
                "invite_only": True,
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertTrue(commit.json()["posture"]["invite_only"])
        feat = self.client.get("/api/features").json()
        self.assertTrue(feat["features"]["invite_only"])

    def test_commit_public_omits_invite_only_still_on(self) -> None:
        commit = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "public",
                "username": "owner",
                "password": "password123",
                "household_domain": "movies.example.com",
                "trust_proxy": True,
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        body = commit.json()
        self.assertTrue(body["posture"]["invite_only"])
        self.assertTrue(body["posture"]["trust_proxy_headers"])
        feat = self.client.get("/api/features").json()
        self.assertTrue(feat["features"]["invite_only"])
        self.assertTrue(feat["features"]["trust_proxy_headers"])

    def test_handshake_and_commit_404_after_active(self) -> None:
        self.client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "owner",
                "password": "password123",
                "invite_only": False,
            },
        )
        self.assertEqual(self.client.get("/api/setup/handshake").status_code, 404)
        self.assertEqual(self.client.post("/api/setup/handshake").status_code, 404)
        again = self.client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "other",
                "password": "password123",
            },
        )
        self.assertEqual(again.status_code, 404)


class SetupPublicPathTests(unittest.TestCase):
    def test_exact_allowlist_ignores_classification(self) -> None:
        self.assertTrue(is_setup_public_path("GET", "/api/health"))
        self.assertTrue(is_setup_public_path("POST", "/api/setup/commit", classification="halt_wan"))
        self.assertTrue(is_setup_public_path("POST", "/api/setup/handshake", classification="public_failsafe"))

    def test_plex_tmdb_tests_only_when_lan(self) -> None:
        self.assertTrue(is_setup_public_path("POST", "/api/setup/test/plex", classification="lan"))
        self.assertTrue(is_setup_public_path("POST", "/api/setup/test/tmdb", classification="lan"))
        self.assertFalse(is_setup_public_path("POST", "/api/setup/test/plex"))
        self.assertFalse(
            is_setup_public_path("POST", "/api/setup/test/plex", classification="public_failsafe")
        )
        self.assertFalse(is_setup_public_path("POST", "/api/setup/test/tmdb", classification="halt_wan"))


class ResolveCommitInviteOnlyTests(unittest.TestCase):
    def test_private_omitted_defaults_off(self) -> None:
        self.assertFalse(resolve_commit_invite_only("private", None))

    def test_private_explicit_true_stays_on(self) -> None:
        self.assertTrue(resolve_commit_invite_only("private", True))

    def test_private_explicit_false_stays_off(self) -> None:
        self.assertFalse(resolve_commit_invite_only("private", False))

    def test_public_always_on(self) -> None:
        self.assertTrue(resolve_commit_invite_only("public", None))
        self.assertTrue(resolve_commit_invite_only("public", False))
        self.assertTrue(resolve_commit_invite_only("public", True))


class ResolveCommitTrustProxyTests(unittest.TestCase):
    def test_private_forces_false_even_when_sticky_true(self) -> None:
        self.assertFalse(resolve_commit_trust_proxy("private", True))
        self.assertFalse(resolve_commit_trust_proxy("private", False))

    def test_public_honors_checkbox(self) -> None:
        self.assertTrue(resolve_commit_trust_proxy("public", True))
        self.assertFalse(resolve_commit_trust_proxy("public", False))


class ResolveCommitHouseholdDomainTests(unittest.TestCase):
    def test_private_drops_public_domain(self) -> None:
        self.assertEqual(resolve_commit_household_domain("private", "movies.example.com"), "")

    def test_public_keeps_trimmed_domain(self) -> None:
        self.assertEqual(
            resolve_commit_household_domain("public", " movies.example.com "),
            "movies.example.com",
        )


if __name__ == "__main__":
    unittest.main()
