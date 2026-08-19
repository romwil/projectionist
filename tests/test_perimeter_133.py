"""HTTP perimeter: MCP slash-auth, public body clamp, webhook leak."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class McpHttpPerimeterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["CURATORX_SESSION_SECRET"] = "test-mcp-perimeter-session-secret"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app, follow_redirects=False)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        os.environ.pop("DATA_DIR", None)
        self._tmpdir.cleanup()

    def test_unauthenticated_mcp_is_401_without_slash_redirect(self) -> None:
        for path in ("/mcp", "/mcp/"):
            response = self.client.post(path)
            self.assertEqual(response.status_code, 401, response.text)
            self.assertNotIn("location", {key.lower() for key in response.headers})
            body = response.text
            self.assertNotIn("PROJECTIONIST_", body)
            self.assertNotIn("CURATORX_", body)
            self.assertIn("Unauthorized", body)

    def test_oversized_access_request_is_413(self) -> None:
        blob = b'{"display_name":"' + b"x" * 70_000 + b'","message":"hi"}'
        response = self.client.post(
            "/api/access-requests",
            content=blob,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("too large", response.text.lower())


if __name__ == "__main__":
    unittest.main()
