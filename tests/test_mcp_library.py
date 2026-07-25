"""Smoke tests for CuratorX MCP library tools."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.library.db import Database


class McpLibraryTests(unittest.TestCase):
    def test_library_query_tool(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp package not installed")

        from projectionist.mcp import server as mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = Database(db_path)
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Nosferatu",
                    "year": 1979,
                    "genres": ["Horror"],
                }
            )

            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_database", return_value=db):
                    raw = mcp_server.library_query(year_from=1970, year_to=1979)
            payload = json.loads(raw)
            self.assertEqual(payload["total_matched"], 1)
            self.assertEqual(payload["items"][0]["title"], "Nosferatu")

    def test_library_aggregate_tool(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp package not installed")

        from projectionist.mcp import server as mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Jaws",
                    "year": 1975,
                    "genres": ["Thriller"],
                }
            )
            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_database", return_value=db):
                    raw = mcp_server.library_aggregate(group_by="decade")
            payload = json.loads(raw)
            self.assertEqual(payload["group_by"], "decade")
            self.assertEqual(payload["buckets"][0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
