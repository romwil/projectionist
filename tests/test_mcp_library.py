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

    def test_sample_owned_library_and_find_collection_gaps_alias(self) -> None:
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
                    "title": "Nosferatu",
                    "year": 1979,
                    "genres": ["Horror"],
                }
            )
            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_database", return_value=db):
                    sample = json.loads(mcp_server.sample_owned_library(genres="Horror", limit=5))
                    alias = json.loads(mcp_server.find_collection_gaps(genres="Horror", limit=5))
            self.assertIn("sample_owned", sample)
            self.assertEqual(sample["sample_owned"]["total_matched"], 1)
            self.assertEqual(alias["sample_owned"]["total_matched"], 1)

    def test_discover_missing_titles_privacy_safe_gaps(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp package not installed")

        from projectionist.mcp import server as mcp_server
        from projectionist.config_store import Settings

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(tmdb_api_key="test-key")
            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_database", return_value=db):
                    with patch.object(mcp_server, "_settings", return_value=settings):
                        with patch("projectionist.agent.tools.TMDBClient") as mock_tmdb_cls:
                            mock_tmdb = mock_tmdb_cls.return_value
                            mock_tmdb.genre_list_movies.return_value = [
                                {"id": 99, "name": "Documentary"}
                            ]
                            mock_tmdb.discover_movies.return_value = [
                                {
                                    "id": 501,
                                    "title": "Missing Doc",
                                    "release_date": "2020-01-01",
                                    "vote_average": 7.5,
                                    "poster_path": "/x.jpg",
                                }
                            ]
                            mock_tmdb.poster_url.return_value = "https://image.tmdb.org/t/p/w500/x.jpg"
                            mock_tmdb.backdrop_url.return_value = ""
                            raw = mcp_server.discover_missing_titles(
                                media_type="movie",
                                genres="Documentary",
                                limit=5,
                            )
            payload = json.loads(raw)
            self.assertEqual(payload["returned"], 1)
            item = payload["items"][0]
            self.assertEqual(item["title"], "Missing Doc")
            self.assertEqual(item["year"], 2020)
            self.assertEqual(item["media_type"], "movie")
            self.assertFalse(item["in_library"])
            self.assertIn("image.tmdb.org", item.get("poster_url") or "")
            self.assertNotIn("overview", item)


if __name__ == "__main__":
    unittest.main()
