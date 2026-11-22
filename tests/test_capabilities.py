"""NAT-001: capability manifest and api_contract on GET /api/features."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.capabilities import (
    API_CONTRACT,
    CACHED_ART_ENABLED,
    client_capabilities,
)
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from tests.owner_claim_helpers import grant_owner_claim

SHIPPED = {
    "device_pairing": 1,
    "throw": 1,
    "playback_engine": 1,
    "native_sign_in": 1,
    "cached_art": 1 if CACHED_ART_ENABLED else 0,
    "household_addresses": 1,
    "rooms": 1,
}
ACCEPTED_NOT_SHIPPED = {
    "caption_tracks": 0,
    "shared_sessions": 0,
    "timeline": 0,
    "tracks": 0,
    "push": 0,
    "approvals": 0,
}


class CapabilityMapTests(unittest.TestCase):
    def test_map_matches_the_decided_keys(self) -> None:
        caps = client_capabilities()
        self.assertEqual(caps, {**SHIPPED, **ACCEPTED_NOT_SHIPPED})
        self.assertEqual(API_CONTRACT, 3)
        self.assertTrue(CACHED_ART_ENABLED)
        self.assertEqual(caps["cached_art"], 1)

    def test_cached_art_capability_tracks_the_feature_flag(self) -> None:
        self.assertEqual(client_capabilities()["cached_art"], 1 if CACHED_ART_ENABLED else 0)


class FeaturesContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-capabilities-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        grant_owner_claim(self.client)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        self._tmpdir.cleanup()

    def test_signed_in_payload_keeps_cached_art_and_adds_the_manifest(self) -> None:
        body = self.client.get("/api/features").json()
        self.assertEqual(body["api_contract"], API_CONTRACT)
        self.assertEqual(body["capabilities"], client_capabilities())
        self.assertTrue(body["features"]["cached_art"])
        self.assertEqual(
            body["capabilities"]["cached_art"],
            1 if body["features"]["cached_art"] else 0,
        )

    def test_public_payload_gains_the_manifest_and_keeps_the_strip(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        body = self.client.get("/api/features").json()
        self.assertFalse(body["authenticated"])
        self.assertEqual(body["api_contract"], API_CONTRACT)
        self.assertEqual(body["capabilities"], client_capabilities())
        self.assertEqual(
            set(body["features"].keys()),
            {"multi_user_enabled", "access_requests_enabled"},
        )
        self.assertNotIn("cached_art", body["features"])
        self.assertEqual(body["capabilities"]["cached_art"], 1)
        for key in ("household_domain", "seerr", "auth", "notifications", "youth", "addresses"):
            self.assertNotIn(key, body)
        self.assertEqual(body["capabilities"]["household_addresses"], 1)
