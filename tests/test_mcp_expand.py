"""Smoke tests for expanded MCP tools (skip when mcp extra missing)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless

try:
    from curatorx.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


@skipUnless(HAS_MCP, "mcp package not installed")
class McpExpandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        self._tmpdir.cleanup()

    def test_what_to_watch_and_purge_tools(self) -> None:
        path = Path(self._tmpdir.name) / "curatorx.db"
        # Ensure DB exists via Database ctor used by mcp helpers
        from curatorx.library.db import Database

        Database(path).ensure_seed_data()
        out = json.loads(mcp_server.what_to_watch_tonight(limit=5))
        self.assertIn("items", out)
        purge = json.loads(mcp_server.suggest_purge_candidates_tool(limit=3))
        self.assertIn("items", purge)


if __name__ == "__main__":
    unittest.main()
