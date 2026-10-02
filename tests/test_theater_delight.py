"""Tests for host preroll discovery + Weather Channel payload."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from projectionist.theater.preroll import (
    asset_id_for_path,
    choose_preroll_video,
    list_preroll_audio,
    list_preroll_videos,
    pick_preroll,
    resolve_asset,
)
from projectionist.theater.weather import (
    build_ticker_lines,
    build_voiceover_script,
    weather_channel_payload,
    wmo_label,
)


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

    def test_movie_preroll_is_random_not_pinned_to_first(self):
        items = [
            {"id": "aaa", "title": "Trailer A", "content_type": "video/mp4"},
            {"id": "bbb", "title": "Trailer B", "content_type": "video/mp4"},
            {"id": "ccc", "title": "Trailer C", "content_type": "video/mp4"},
        ]
        picks = {
            choose_preroll_video(items, rng=__import__("random").Random(seed))["id"]
            for seed in range(24)
        }
        self.assertGreater(len(picks), 1)
        self.assertNotEqual(picks, {"aaa"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("alpha.mp4", "bravo.mp4", "charlie.mp4"):
                (root / name).write_bytes(b"x")
            movie_picks = {
                pick_preroll(context="movie", root=root, rng=__import__("random").Random(seed))["id"]
                for seed in range(24)
            }
            self.assertGreater(len(movie_picks), 1)

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
        lines = build_ticker_lines(
            payload["current"],
            {
                "time": ["2026-10-02"],
                "precipitation_probability_max": [30],
                "temperature_2m_max": [80],
                "temperature_2m_min": [60],
            },
        )
        joined = " ".join(lines)
        self.assertIn("Humidity 40%", joined)
        self.assertIn("rain chance 30%", joined)
        self.assertNotIn("72", joined)
        self.assertNotIn("Hi ", joined)

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
                    muzak_folder=str(root),
                    allowed_roots=[root],
                    rng=__import__("random").Random(1),
                )
            self.assertEqual(data["place"], "Home")
            self.assertEqual(data["location_source"], "household")
            self.assertTrue(data["muzak"])
            self.assertEqual(data["muzak_note"], "")
            self.assertIn("open-meteo", data["egress"]["host"])
            self.assertTrue(data["ticker"])
            joined = " ".join(data["ticker"])
            self.assertIn("Humidity", joined)
            self.assertNotIn("NOW", joined)
            self.assertNotIn("55", joined)
            self.assertNotIn("Hi ", joined)

    def test_saved_coords_skip_geocode_and_empty_music_is_honest(self):
        calls = []

        def fake_fetch(url: str):
            calls.append(url)
            return {
                "current": {"temperature_2m": 70, "weather_code": 0, "wind_speed_10m": 3},
                "daily": {"time": [], "temperature_2m_max": [], "temperature_2m_min": [], "weather_code": []},
            }

        data = weather_channel_payload(
            place_name="Chicago, Illinois, United States",
            latitude=41.88,
            longitude=-87.63,
            location_source="profile",
            fetch_json=fake_fetch,
            muzak_folder="",
        )
        self.assertEqual(data["location_source"], "profile")
        self.assertEqual(data["latitude"], 41.88)
        self.assertIsNone(data["muzak"])
        self.assertIn("No music folder", data["muzak_note"])
        self.assertTrue(calls)
        self.assertTrue(all("geocoding-api" not in url for url in calls))

    def test_profile_place_does_not_replace_unset_household_default(self):
        def fake_fetch(_url: str):
            return {
                "current": {"temperature_2m": 70, "weather_code": 0},
                "daily": {
                    "time": [],
                    "temperature_2m_max": [],
                    "temperature_2m_min": [],
                    "weather_code": [],
                },
            }

        data = weather_channel_payload(
            environ={},
            place_name="Chicago",
            latitude=41.8781,
            longitude=-87.6298,
            location_source="profile",
            fetch_json=fake_fetch,
            muzak_folder="",
        )
        self.assertEqual(data["household_place"], "your area")
        self.assertEqual(data["place"], "Chicago")
        self.assertEqual(data["location_source"], "profile")
        self.assertIn("Chicago", data["voiceover"])
        self.assertNotIn("your area", data["voiceover"])


if __name__ == "__main__":
    unittest.main()
