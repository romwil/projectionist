"""SEC-023: a cookie write from another site is refused. A bearer is exempt."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from projectionist.web.origin_check import ORIGIN_REJECTED
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache, create_session_token


class CookieOriginTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-cookie-origin-session-secret"
        clear_session_secret_cache()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("owner-1"))

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SETUP_STATE",
            "PROJECTIONIST_SESSION_SECRET",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_another_site_cannot_spend_the_cookie(self) -> None:
        foreign = self.client.post(
            "/api/settings",
            json={"llm_provider": "ollama"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(foreign.status_code, 403, foreign.text)
        self.assertEqual(foreign.json()["detail"], ORIGIN_REJECTED)

        home = self.client.post(
            "/api/not-a-route",
            headers={"Origin": "http://10.0.0.8:8788"},
        )
        self.assertNotEqual(home.status_code, 403, home.text)

        bearer = self.client.post(
            "/api/not-a-route",
            headers={"Origin": "https://evil.example", "Authorization": "Bearer device-token"},
        )
        self.assertNotEqual(bearer.json().get("detail"), ORIGIN_REJECTED)

        self.client.cookies.clear()
        unsigned = self.client.post(
            "/api/not-a-route",
            headers={"Origin": "https://evil.example"},
        )
        self.assertNotEqual(unsigned.json().get("detail"), ORIGIN_REJECTED)
