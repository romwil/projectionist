"""LP-02: read-only MCP wrap of the native Live lineup."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from projectionist.live_channels.native_schedule import save_schedule

try:
    from projectionist.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False
    mcp_server = None  # type: ignore[assignment]


def _settings(data_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        data_dir=str(data_dir),
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(url="", station_meta={}),
        mcp_tmdb_poster_size="w500",
        mcp_tmdb_backdrop_size="w1280",
    )


def _lineup(*, now: float) -> dict:
    start_ms = int(now * 1000) - 5_000
    return {
        "version": 1,
        "imported_from": "test",
        "channels": {
            "ch-101": {
                "id": "ch-101",
                "name": "Mystery",
                "number": 101,
                "guide_flex_title": "Mystery · Up next",
                "icon_url": "/mnt/user/appdata/icons/mystery.png",
                "start_time_ms": start_ms,
                "library_repeat_note": (
                    "This station has one playable title in the library — it will repeat."
                ),
                "items": [
                    {
                        "type": "content",
                        "duration_ms": 120_000,
                        "title": "The Crime Scene",
                        "show_title": "Mystery",
                        "media_type": "episode",
                        "plex_rating_key": "163544",
                    },
                    {"type": "flex", "duration_ms": 15 * 60 * 1000},
                    {
                        "type": "content",
                        "duration_ms": 90_000,
                        "title": "Next Case",
                        "show_title": "Mystery",
                        "media_type": "episode",
                        "plex_rating_key": "163545",
                    },
                ],
            }
        },
    }


@skipUnless(HAS_MCP, "mcp package not installed")
class McpLiveGuideTests(unittest.TestCase):
    def test_now_next_flex_and_pool_notice(self) -> None:
        now = 1_700_000_000.0
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_schedule(_lineup(now=now), data_dir=data_dir)
            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_settings", return_value=_settings(data_dir)):
                    with patch(
                        "projectionist.live_channels.native_schedule.time.time",
                        return_value=now,
                    ):
                        payload = json.loads(mcp_server.live_guide(channel="101"))
            dumped = json.dumps(payload)
            self.assertNotIn("lineup_missing", payload)
            self.assertEqual(payload["count"], 1)
            row = payload["channels"][0]
            self.assertEqual(row["number"], 101)
            self.assertEqual(row["name"], "Mystery")
            self.assertEqual(row["now"]["kind"], "programme")
            self.assertEqual(row["now"]["title"], "Mystery")
            self.assertFalse(row["now"]["is_flex"])
            self.assertEqual(row["next"]["kind"], "flex")
            self.assertEqual(row["next"]["title"], "Between programs")
            self.assertTrue(row["next"]["is_flex"])
            self.assertIn("one playable title", row["pool_notice"])
            self.assertNotIn("163544", dumped)
            self.assertNotIn("/mnt/", dumped)
            self.assertNotIn("X-Plex-Token", dumped)
            self.assertNotIn("plex_rating_key", dumped)

    def test_missing_file_is_lineup_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            with patch.dict("os.environ", {"DATA_DIR": tmp}):
                with patch.object(mcp_server, "_settings", return_value=_settings(data_dir)):
                    payload = json.loads(mcp_server.live_guide())
        self.assertEqual(payload, {"error": "lineup_missing"})
        self.assertNotIn("channels", payload)


if __name__ == "__main__":
    unittest.main()
