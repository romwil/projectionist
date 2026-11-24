"""SEC-024: /mcp stays on the home network unless the owner allows remote MCP."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, save_settings
from projectionist.mcp.http import MCP_STAYS_HOME


class McpRemoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-mcp-remote-session-secret"
        os.environ["PROJECTIONIST_TRUSTED_PROXIES"] = "172.17.0.1"
        os.environ.pop("PROJECTIONIST_MCP_API_KEY", None)
        os.environ.pop("PROJECTIONIST_MCP_FULL_API_KEY", None)
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        save_settings(Path(self._tmpdir.name), Settings(mcp_api_key="privacy-secret-abcd"))

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_TRUSTED_PROXIES",
            "PROJECTIONIST_MCP_API_KEY",
            "PROJECTIONIST_MCP_FULL_API_KEY",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _outside(self) -> TestClient:
        return TestClient(self.app_mod.app, client=("172.17.0.1", 50000))

    def test_an_outside_request_is_refused_until_remote_mcp_is_on(self) -> None:
        headers = {
            "cf-ray": "9abc-EWR",
            "cf-connecting-ip": "203.0.113.8",
            "X-Projectionist-MCP-Key": "privacy-secret-abcd",
        }
        refused = self._outside().post("/mcp", headers=headers)
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["detail"], MCP_STAYS_HOME)
        self.assertNotIn("privacy-secret", refused.text)

        save_settings(
            Path(self._tmpdir.name),
            Settings(mcp_api_key="privacy-secret-abcd", mcp_remote_enabled=True),
        )
        allowed = self._outside().post("/mcp", headers=headers)
        self.assertNotEqual(allowed.status_code, 403, allowed.text)
        self.assertNotIn(MCP_STAYS_HOME, allowed.text)

        home = TestClient(self.app_mod.app).post("/mcp")
        self.assertEqual(home.status_code, 401, home.text)
        self.assertIn("Unauthorized", home.text)
