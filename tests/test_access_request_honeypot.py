"""Access-request honeypot and 3/IP/hour flood limit."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class AccessRequestPerimeterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-honeypot-session-secret-xx"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {
                        "multi_user_enabled": True,
                        "access_requests_enabled": True,
                    },
                    "auth": {"mode": "local", "local_login_enabled": True, "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        self.client = TestClient(app_mod.app)

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
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_fourth_request_in_an_hour_is_limited(self) -> None:
        for index in range(3):
            resp = self.client.post(
                "/api/access-requests",
                json={"display_name": f"Person {index}"},
            )
            self.assertEqual(resp.status_code, 200, resp.text)
        limited = self.client.post(
            "/api/access-requests",
            json={"display_name": "Person 3"},
        )
        self.assertEqual(limited.status_code, 429)

    def test_honeypot_returns_identical_shape_without_row_or_alert(self) -> None:
        from projectionist.web.jobs import get_job_manager

        with patch("projectionist.access_requests.notify_owners_of_access_request") as notify:
            with self.assertLogs("projectionist.web.ingress", level="INFO") as captured:
                resp = self.client.post(
                    "/api/access-requests",
                    json={
                        "display_name": "Bot",
                        "organization_url": "https://evil.example/xss<script>",
                    },
                )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("request", body)
        self.assertEqual(set(body["request"]), {"id", "status", "created_at"})
        self.assertEqual(body["request"]["status"], "pending")
        self.assertTrue(body["request"]["id"])
        rows = get_job_manager().db.list_access_requests()
        self.assertEqual(rows, [])
        notify.assert_not_called()
        joined = "\n".join(captured.output)
        self.assertIn("honeypot", joined.lower())
        self.assertNotIn("evil.example", joined)
        self.assertNotIn("<script>", joined)


if __name__ == "__main__":
    unittest.main()
