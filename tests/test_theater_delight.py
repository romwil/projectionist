"""Tests for host preroll discovery + Weather Channel payload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from projectionist.theater.preroll import (
    asset_id_for_path,
    list_preroll_audio,
    list_preroll_videos,
    pick_preroll,
    resolve_asset,
)
from projectionist.theater.weather import build_voiceover_script, weather_channel_payload, wmo_label


class PrerollTests(unittest.TestCase):
    def test_lists_and_picks_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bumper-a.mp4").write_bytes(b"fake")
            (root / "bumper-b.webm").write_bytes(b"fake")
            (root / "bed.mp3").write_bytes(b"fake")
            videos = list_preroll_videos(root)
            self.assertEqual(len(videos), 2)
            audio = list_preroll_audio(root)
            self.assertEqual(len(audio), 1)
            first = pick_preroll(root=root, rng=__import__("random").Random(1))
            second = pick_preroll(root=root, rng=__import__("random").Random(2))
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertTrue(str(first["url"]).startswith("/api/preroll/asset/"))
            resolved = resolve_asset(first["id"], root=root)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["id"], first["id"])

    def test_asset_id_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "x.mp4"
            path.write_bytes(b"x")
            a = asset_id_for_path(path, root=root)
            b = asset_id_for_path(path, root=root)
            self.assertEqual(a, b)
            self.assertEqual(len(a), 24)


class WeatherTests(unittest.TestCase):
    def test_wmo_and_script(self):
        self.assertEqual(wmo_label(0), "Clear")
        payload = {
            "current": {
                "temperature_2m": 72.4,
                "relative_humidity_2m": 40,
                "weather_code": 1,
                "wind_speed_10m": 8,
            },
            "daily": {
                "time": ["2026-10-02"],
                "temperature_2m_max": [80],
                "temperature_2m_min": [60],
                "weather_code": [2],
            },
        }
        script = build_voiceover_script(payload, place_name="Chicago")
        self.assertIn("Chicago", script)
        self.assertIn("72", script)

    def test_payload_uses_fetch_and_muzak(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "weather-bed.mp3").write_bytes(b"x")
            (root / "intro.mp4").write_bytes(b"x")

            def fake_fetch(_url: str):
                return {
                    "current": {
                        "temperature_2m": 55,
                        "relative_humidity_2m": 50,
                        "weather_code": 3,
                        "wind_speed_10m": 5,
                    },
                    "daily": {
                        "time": ["2026-10-02"],
                        "temperature_2m_max": [60],
                        "temperature_2m_min": [50],
                        "weather_code": [3],
                    },
                }

            with mock.patch(
                "projectionist.theater.weather.resolve_preroll_root",
                return_value=root,
            ):
                data = weather_channel_payload(
                    environ={"PROJECTIONIST_WEATHER_PLACE": "Home"},
                    fetch_json=fake_fetch,
                )
            self.assertEqual(data["place"], "Home")
            self.assertTrue(data["muzak"])
            self.assertIn("open-meteo", data["egress"]["host"])
            self.assertTrue(data["ticker"])


if __name__ == "__main__":
    unittest.main()
