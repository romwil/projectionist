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
    select_muzak,
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
    @staticmethod
    def _service(tmp: str, calls: list):
        from projectionist.theater.weather_channel.http import FetchResult
        from projectionist.theater.weather_channel.service import WeatherService

        fixture = Path(__file__).resolve().parent / "fixtures" / "weather" / "forecast_chicago.json"

        def fake_fetch(url: str, **_kwargs):
            calls.append(url)
            return FetchResult(fixture.read_bytes())

        service = WeatherService(Path(tmp), fetch=fake_fetch, autostart=False)
        return service

    def test_wmo_labels(self):
        self.assertEqual(wmo_label(0), "Clear")
        self.assertEqual(wmo_label(95), "Thunderstorm")
        self.assertEqual(wmo_label("x"), "Mixed skies")

    def test_music_is_every_file_in_the_folder_shuffled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a-bed.mp3", "b-bed.mp3", "c-bed.ogg"):
                (root / name).write_bytes(b"x")
            tracks, note = select_muzak(str(root), allowed_roots=[root], rng=__import__("random").Random(3))
            self.assertEqual(note, "")
            self.assertEqual(len(tracks), 3)
            self.assertEqual(len({t["id"] for t in tracks}), 3)
            self.assertTrue(all(t["url"].startswith("/api/preroll/asset/") for t in tracks))
            orders = {
                tuple(t["id"] for t in select_muzak(str(root), allowed_roots=[root], rng=__import__("random").Random(seed))[0])
                for seed in range(12)
            }
            self.assertGreater(len(orders), 1)

    def test_empty_music_folder_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracks, note = select_muzak(tmp, allowed_roots=[Path(tmp)])
            self.assertEqual(tracks, [])
            self.assertIn("empty", note)
        tracks, note = select_muzak("")
        self.assertEqual(tracks, [])
        self.assertIn("no soundtrack", note)

    def test_payload_uses_the_cache_and_music_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "music"
            root.mkdir()
            (root / "weather-bed.mp3").write_bytes(b"x")
            (root / "weather-bed-2.mp3").write_bytes(b"x")
            calls: list = []
            with mock.patch("projectionist.theater.weather.resolve_preroll_root", return_value=None):
                data = weather_channel_payload(
                    service=self._service(tmp, calls),
                    environ={"PROJECTIONIST_WEATHER_PLACE": "Home"},
                    muzak_folder=str(root),
                    allowed_roots=[root],
                    rng=__import__("random").Random(1),
                )
            self.assertEqual(data["place"], "Home")
            self.assertEqual(data["location_source"], "household")
            self.assertEqual(len(data["music"]["tracks"]), 2)
            self.assertEqual(data["muzak_note"], "")
            self.assertIn("api.open-meteo.com", {e["host"] for e in data["egress"]})
            groups = {item["group"] for item in data["chyron"]}
            self.assertEqual(groups, {"NOW", "HOURLY", "5-DAY"})
            self.assertNotIn("ticker", data)
            self.assertEqual(len(calls), 1)

    def test_saved_coords_skip_geocode_and_empty_music_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls: list = []
            data = weather_channel_payload(
                service=self._service(tmp, calls),
                place_name="Chicago, Illinois, United States",
                latitude=41.88,
                longitude=-87.63,
                location_source="profile",
                muzak_folder="",
            )
            self.assertEqual(data["location_source"], "profile")
            self.assertEqual(data["latitude"], 41.88)
            self.assertIsNone(data["muzak"])
            self.assertEqual(data["music"]["tracks"], [])
            self.assertIn("no soundtrack", data["muzak_note"])
            self.assertTrue(calls)
            self.assertTrue(all("geocoding-api" not in url for url in calls))

    def test_profile_place_does_not_replace_unset_household_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = weather_channel_payload(
                service=self._service(tmp, []),
                environ={},
                place_name="Chicago",
                latitude=41.8781,
                longitude=-87.6298,
                location_source="profile",
                muzak_folder="",
            )
            self.assertEqual(data["household_place"], "your area")
            self.assertEqual(data["place"], "Chicago")
            self.assertEqual(data["location_source"], "profile")
            self.assertIn("Chicago", data["voiceover"])
            self.assertNotIn("your area", data["voiceover"])


if __name__ == "__main__":
    unittest.main()
