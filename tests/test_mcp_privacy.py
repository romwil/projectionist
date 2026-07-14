"""Privacy-mode MCP sanitization and HTTP key → mode mapping."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from curatorx.mcp.mode import (
    full_mode_allowed,
    resolve_http_mcp_auth,
    resolve_stdio_mcp_mode,
    set_mcp_mode,
)
from curatorx.privacy import sanitize
from curatorx.privacy.schema import derive_watch_state, public_image_urls


class PrivacySchemaTests(unittest.TestCase):
    def test_public_drops_infra_and_adds_watch_state(self) -> None:
        payload = {
            "items": [
                {
                    "title": "Jaws",
                    "year": 1975,
                    "rating_key": "plex-99",
                    "file_size": 12_000_000_000,
                    "view_count": 0,
                    "in_radarr": True,
                    "user_id": "u1",
                    "poster_url": "http://192.168.1.10:32400/library/metadata/1/thumb?X-Plex-Token=SECRET",
                    "tmdb_id": 578,
                }
            ]
        }
        cleaned = sanitize(payload, audience="privacy")
        item = cleaned["items"][0]
        self.assertEqual(item["title"], "Jaws")
        self.assertNotIn("rating_key", item)
        self.assertNotIn("file_size", item)
        self.assertNotIn("view_count", item)
        self.assertNotIn("in_radarr", item)
        self.assertNotIn("user_id", item)
        self.assertEqual(item["watch_state"], "unwatched")
        self.assertEqual(item.get("poster_url") or "", "")

    def test_tmdb_poster_rewritten_not_plex(self) -> None:
        row = {
            "poster_url": "https://image.tmdb.org/t/p/w342/abc.jpg",
            "backdrop_url": "https://image.tmdb.org/t/p/w780/bg.jpg",
        }

        class _Settings:
            mcp_tmdb_poster_size = "w500"
            mcp_tmdb_backdrop_size = "w1280"

        images = public_image_urls(row, _Settings())
        self.assertEqual(images["poster_url"], "https://image.tmdb.org/t/p/w500/abc.jpg")
        self.assertEqual(images["backdrop_url"], "https://image.tmdb.org/t/p/w1280/bg.jpg")

    def test_internal_keeps_rating_key_strips_token(self) -> None:
        payload = {
            "title": "Jaws",
            "rating_key": "99",
            "file_size": 100,
            "view_count": 2,
            "in_radarr": True,
            "poster_url": "http://plex.local/thumb?X-Plex-Token=SECRET",
        }
        cleaned = sanitize(payload, audience="mcp_full")
        self.assertEqual(cleaned["rating_key"], "99")
        self.assertEqual(cleaned["file_size"], 100)
        self.assertTrue(cleaned["in_radarr"])
        self.assertEqual(cleaned.get("poster_url") or "", "")
        dumped = json.dumps(cleaned)
        self.assertNotIn("X-Plex-Token", dumped)
        self.assertNotIn("SECRET", dumped)

    def test_derive_watch_state_episodes(self) -> None:
        self.assertEqual(
            derive_watch_state({"total_episode_count": 10, "unwatched_episode_count": 3}),
            "in_progress",
        )


class McpHttpKeyModeTests(unittest.TestCase):
    def test_privacy_key_maps_to_privacy(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_API_KEY": "priv-key",
                "CURATORX_MCP_FULL_API_KEY": "full-key",
            },
            clear=False,
        ):
            mode, detail, status = resolve_http_mcp_auth("priv-key")
            self.assertEqual(mode, "privacy")
            self.assertIsNone(detail)
            self.assertEqual(status, 200)

    def test_full_key_maps_to_full(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_API_KEY": "priv-key",
                "CURATORX_MCP_FULL_API_KEY": "full-key",
            },
            clear=False,
        ):
            mode, detail, status = resolve_http_mcp_auth("full-key")
            self.assertEqual(mode, "full")
            self.assertEqual(status, 200)

    def test_equal_keys_refuse_full(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_API_KEY": "same",
                "CURATORX_MCP_FULL_API_KEY": "same",
            },
            clear=False,
        ):
            self.assertFalse(full_mode_allowed())
            mode, detail, status = resolve_http_mcp_auth("same")
            # Privacy key still works when keys collide; full is refused.
            self.assertEqual(mode, "privacy")
            self.assertEqual(status, 200)

    def test_stdio_full_requires_distinct_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_MODE": "full",
                "CURATORX_MCP_API_KEY": "priv",
                "CURATORX_MCP_FULL_API_KEY": "",
            },
            clear=False,
        ):
            self.assertEqual(resolve_stdio_mcp_mode(), "privacy")


try:
    from curatorx.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


@skipUnless(HAS_MCP, "mcp package not installed")
class McpPrivacyToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        set_mcp_mode("privacy")

    def tearDown(self) -> None:
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_library_query_strips_rating_key(self) -> None:
        from curatorx.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        db.upsert_library_item(
            {
                "rating_key": "rk-1",
                "media_type": "movie",
                "title": "Nosferatu",
                "year": 1979,
                "genres": ["Horror"],
                "view_count": 0,
                "file_size": 999,
                "poster_url": "http://plex/thumb?X-Plex-Token=SECRET",
            }
        )
        with patch.object(mcp_server, "_database", return_value=db):
            raw = mcp_server.library_query(year_from=1970, year_to=1979)
        payload = json.loads(raw)
        item = payload["items"][0]
        self.assertEqual(item["title"], "Nosferatu")
        self.assertNotIn("rating_key", item)
        self.assertNotIn("file_size", item)
        self.assertNotIn("SECRET", raw)
        self.assertEqual(item.get("watch_state"), "unwatched")

    def test_privacy_cannot_propose_radarr(self) -> None:
        set_mcp_mode("privacy")
        payload = json.loads(mcp_server.propose_add_radarr(tmdb_id=578, title="Jaws"))
        self.assertIn("error", payload)
        self.assertIn("full MCP", payload["error"])


if __name__ == "__main__":
    unittest.main()
