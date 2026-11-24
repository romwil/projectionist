"""SEC-024: MCP stays on the home network unless the owner allows it."""

from __future__ import annotations

import importlib
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.mcp.http import MCP_STAYS_HOME


class McpStaysHomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-mcp-remote-session-secret"
        os.environ["PROJECTIONIST_MCP_API_KEY"] = "home-mcp-key"
        os.environ.pop("PROJECTIONIST_MCP_FULL_API_KEY", None)
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app, follow_redirects=False)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_MCP_API_KEY",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_an_outside_request_is_refused_until_the_owner_allows_it(self) -> None:
        headers = {"X-Projectionist-MCP-Key": "home-mcp-key"}
        with patch("projectionist.web.ingress.request_is_external", return_value=True):
            refused = self.client.post("/mcp", headers=headers)
        self.assertEqual(refused.status_code, 403, refused.text)
        self.assertEqual(refused.json()["detail"], MCP_STAYS_HOME)

        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(json.dumps({"mcp_remote_enabled": True}), encoding="utf-8")
        with patch("projectionist.web.ingress.request_is_external", return_value=True):
            allowed = self.client.post("/mcp", headers=headers)
        self.assertNotEqual(allowed.status_code, 403, allowed.text)

        home = self.client.post("/mcp/", headers=headers)
        self.assertNotEqual(home.status_code, 403, home.text)
        self.assertNotIn(MCP_STAYS_HOME, home.text)

    def test_a_failed_mcp_key_is_logged_without_the_key(self) -> None:
        with self.assertLogs("projectionist.mcp.http", level=logging.WARNING) as captured:
            response = self.client.post(
                "/mcp",
                headers={"X-Projectionist-MCP-Key": "not-the-key"},
            )
        self.assertEqual(response.status_code, 401, response.text)
        blob = "\n".join(captured.output)
        self.assertIn("MCP auth failed", blob)
        self.assertNotIn("not-the-key", blob)
        self.assertNotIn("home-mcp-key", blob)
