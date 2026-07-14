"""Full-mode MCP tools, auth mapping, and schema allowances."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from curatorx.mcp.mode import resolve_http_mcp_auth, set_mcp_mode
from curatorx.privacy import sanitize


class FullModeAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self._tmpdir.name

    def tearDown(self) -> None:
        if self._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev_data_dir
        self._tmpdir.cleanup()

    def test_wrong_key_does_not_escalate(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_API_KEY": "priv-key",
                "CURATORX_MCP_FULL_API_KEY": "full-key",
            },
            clear=False,
        ):
            mode, _, status = resolve_http_mcp_auth("priv-key")
            self.assertEqual(mode, "privacy")
            self.assertEqual(status, 200)
            mode2, detail, status2 = resolve_http_mcp_auth("not-a-key")
            self.assertIsNone(mode2)
            self.assertEqual(status2, 401)
            self.assertIn("Invalid", detail or "")


class FullSchemaTests(unittest.TestCase):
    def test_full_allows_rating_key_never_token(self) -> None:
        cleaned = sanitize(
            {
                "rating_key": "42",
                "view_count": 3,
                "in_sonarr": True,
                "file_size": 50,
                "poster_url": "https://image.tmdb.org/t/p/w342/x.jpg",
                "backdrop_url": "http://lan/plex?X-Plex-Token=sekrit",
            },
            audience="mcp_full",
            settings=type(
                "S",
                (),
                {"mcp_tmdb_poster_size": "w500", "mcp_tmdb_backdrop_size": "w1280"},
            )(),
        )
        self.assertEqual(cleaned["rating_key"], "42")
        self.assertEqual(cleaned["view_count"], 3)
        self.assertTrue(cleaned["in_sonarr"])
        self.assertEqual(cleaned["poster_url"], "https://image.tmdb.org/t/p/w500/x.jpg")
        self.assertEqual(cleaned.get("backdrop_url") or "", "")
        self.assertNotIn("sekrit", json.dumps(cleaned))


try:
    from curatorx.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


@skipUnless(HAS_MCP, "mcp package not installed")
class McpFullModeToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")

    def tearDown(self) -> None:
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_library_query_keeps_rating_key(self) -> None:
        from curatorx.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        db.upsert_library_item(
            {
                "rating_key": "rk-full",
                "media_type": "movie",
                "title": "Alien",
                "year": 1979,
                "file_size": 1234,
                "view_count": 1,
                "poster_url": "http://plex/thumb?X-Plex-Token=SECRET",
            }
        )
        with patch.object(mcp_server, "_database", return_value=db):
            raw = mcp_server.library_query(year_from=1970, year_to=1979)
        payload = json.loads(raw)
        item = payload["items"][0]
        self.assertEqual(item["rating_key"], "rk-full")
        self.assertEqual(item["file_size"], 1234)
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("X-Plex-Token", raw)

    def test_propose_add_radarr_returns_pending_token(self) -> None:
        mock_settings = MagicMock()
        mock_settings.radarr_url = "http://radarr"
        mock_settings.radarr_api_key = "key"
        mock_settings.radarr_root_folder = "/movies"
        mock_settings.movies_root = "/movies"
        mock_settings.radarr_quality_profile_id = 1

        db = MagicMock()
        db.save_pending_action = MagicMock()

        with (
            patch.object(mcp_server, "_database", return_value=db),
            patch.object(mcp_server, "_settings", return_value=mock_settings),
            patch("curatorx.config_store.radarr_add_configuration_error", return_value=None),
            patch("curatorx.config_store.validate_arr_root_folder", return_value=None),
            patch("curatorx.config_store.resolve_radarr_root_folder", return_value="/movies"),
            patch("curatorx.connectors.radarr.RadarrClient") as client_cls,
            patch("curatorx.agent.tools.check_radarr_already_exists", return_value=None),
        ):
            client_cls.return_value.root_folders.return_value = [{"path": "/movies"}]
            raw = mcp_server.propose_add_radarr(tmdb_id=578, title="Jaws")
        payload = json.loads(raw)
        self.assertIn("pending_token", payload)
        self.assertTrue(payload["pending_token"])
        db.save_pending_action.assert_called_once()

    def test_privacy_key_holder_blocked_from_propose(self) -> None:
        set_mcp_mode("privacy")
        payload = json.loads(mcp_server.propose_remove_arr(media_type="movie", title="X"))
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
