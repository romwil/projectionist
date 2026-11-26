"""Just-for-me playback and Connections key persistence."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class JustForMeAndConnectionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-just-for-me-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_just_for_me_is_on_features_and_the_signed_in_user(self) -> None:
        before = self.client.get("/api/features")
        self.assertEqual(before.status_code, 200)
        self.assertFalse(before.json()["features"]["play_through_projectionist"])
        self.assertFalse(before.json()["features"]["play_through_just_for_me"])
        saved = self.client.patch("/api/auth/me", json={"play_through_just_for_me": True})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["user"]["play_through_just_for_me"])
        after = self.client.get("/api/features")
        body = after.json()
        self.assertFalse(body["features"]["play_through_projectionist"])
        self.assertTrue(body["features"]["play_through_just_for_me"])
        self.assertTrue(body["user"]["play_through_just_for_me"])

    def test_engine_opt_in_without_just_for_me_stays_on_the_library_path(self) -> None:
        opened = self.client.post(
            "/api/playback/sessions",
            json={"rating_key": "121986", "profile": "chrome", "engine_opt_in": True},
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()["plan"], "library")
        self.assertFalse(opened.json()["playable"])

    def test_successful_fanart_test_saves_and_a_failure_keeps_the_key(self) -> None:
        with patch("projectionist.web.setup.FanartClient.movie", return_value={"name": "ok"}):
            ok = self.client.post("/api/setup/test/fanart", json={"fanart_api_key": "stored-key"})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["ok"])
        settings = self.client.get("/api/settings")
        self.assertTrue(settings.json()["fanart_api_key_set"])
        certs = self.client.get("/api/setup/certifications").json()
        self.assertTrue(certs["services"]["fanart"]["certified"])

        with patch(
            "projectionist.web.setup.FanartClient.movie",
            side_effect=RuntimeError("rejected"),
        ):
            failed = self.client.post(
                "/api/setup/test/fanart", json={"fanart_api_key": "replacement-key"}
            )
        self.assertEqual(failed.status_code, 200, failed.text)
        self.assertFalse(failed.json()["ok"])
        kept = self.client.get("/api/settings").json()
        self.assertTrue(kept["fanart_api_key_set"])
        revealed = self.client.post(
            "/api/settings/secrets/reveal", json={"field": "fanart_api_key"}
        )
        self.assertEqual(revealed.status_code, 200, revealed.text)
        self.assertEqual(revealed.json().get("value") or revealed.json().get("secret"), "stored-key")

        with patch("projectionist.web.setup.FanartClient.movie", return_value={"name": "ok"}):
            blank = self.client.post("/api/setup/test/fanart", json={"fanart_api_key": ""})
        self.assertTrue(blank.json()["ok"])
        again = self.client.post(
            "/api/settings/secrets/reveal", json={"field": "fanart_api_key"}
        )
        self.assertEqual(again.json().get("value") or again.json().get("secret"), "stored-key")
        self.assertTrue(
            self.client.get("/api/setup/certifications").json()["services"]["fanart"]["certified"]
        )
