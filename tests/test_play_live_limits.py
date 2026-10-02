"""Random preroll helpers, weather place search, profile location, muzak roots."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.theater.media_browser import (
    allowed_media_roots,
    browse_media,
    confine_muzak_folder,
    is_shared_in_mount,
    parse_mountinfo,
    resolve_within_roots,
)
from projectionist.theater.weather_geo import geocode_query, parse_geocode_results


class GeocodeParseTests(unittest.TestCase):
    def test_parses_candidates_and_skips_junk(self):
        payload = {
            "results": [
                {
                    "name": "Chicago",
                    "admin1": "Illinois",
                    "country": "United States",
                    "latitude": 41.85,
                    "longitude": -87.65,
                },
                {"name": "Broken"},
                "nope",
                {"name": "Nope", "latitude": 999, "longitude": 0},
            ]
        }
        rows = parse_geocode_results(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "Chicago, Illinois, United States")
        self.assertEqual(rows[0]["latitude"], 41.85)
        self.assertEqual(parse_geocode_results({}), [])
        self.assertEqual(parse_geocode_results(None), [])

    def test_query_uses_fetch_and_parser(self):
        def fake_fetch(url: str):
            self.assertIn("geocoding-api.open-meteo.com", url)
            self.assertIn("Chicago", url)
            return {
                "results": [
                    {
                        "name": "Chicago",
                        "admin1": "Illinois",
                        "country": "United States",
                        "latitude": 41.8,
                        "longitude": -87.6,
                    }
                ]
            }

        rows = geocode_query("Chicago, IL", fetch_json=fake_fetch)
        self.assertEqual(rows[0]["label"], "Chicago, Illinois, United States")
        self.assertEqual(geocode_query("x", fetch_json=fake_fetch), [])


class ProfileWeatherLocationTests(unittest.TestCase):
    def test_location_persists_and_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "proj.db")
            try:
                user = db.create_local_user(
                    user_id="member-weather",
                    display_name="Sam",
                    password_hash="not-used",
                )
                saved = db.update_user_profile(
                    user["id"],
                    weather_location=("Chicago, Illinois, United States", 41.88, -87.63),
                )
                self.assertEqual(saved["weather_place"], "Chicago, Illinois, United States")
                self.assertAlmostEqual(saved["weather_lat"], 41.88)
                self.assertAlmostEqual(saved["weather_lon"], -87.63)
                again = db.get_user(user["id"])
                self.assertEqual(again["weather_place"], "Chicago, Illinois, United States")
                cleared = db.update_user_profile(user["id"], weather_location=None)
                self.assertIsNone(cleared["weather_place"])
                self.assertIsNone(cleared["weather_lat"])
                self.assertIsNone(cleared["weather_lon"])
            finally:
                db.close()


class MuzakRootTests(unittest.TestCase):
    def test_mountinfo_marks_shared_in_and_skips_root_fs(self):
        text = "\n".join(
            [
                "36 35 98:0 /mnt/user/data/media/preroll /preroll rw,relatime - ext4 /dev/md1 rw",
                "37 35 98:0 /mnt/user/data/media/tv /tv rw,relatime - ext4 /dev/md1 rw",
                "1 0 0:1 / / rw - overlay overlay rw",
                "9 1 0:1 / /etc rw - ext4 /dev/md1 rw",
            ]
        )
        mounts = parse_mountinfo(text)
        by_point = {item["mountpoint"]: item for item in mounts}
        self.assertTrue(is_shared_in_mount(by_point["/preroll"]))
        self.assertTrue(is_shared_in_mount(by_point["/tv"]))
        self.assertFalse(is_shared_in_mount(by_point["/"]))
        self.assertFalse(is_shared_in_mount(by_point["/etc"]))

    def test_path_stays_inside_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "movies"
            secret = Path(tmp) / "secret"
            beds = media / "beds"
            media.mkdir()
            secret.mkdir()
            beds.mkdir()
            (beds / "soft.mp3").write_bytes(b"x")
            roots = [media]
            self.assertEqual(resolve_within_roots(str(beds), roots), beds.resolve())
            self.assertIsNone(resolve_within_roots(str(secret), roots))
            self.assertIsNone(resolve_within_roots(str(beds / ".." / ".." / "secret"), roots))
            self.assertIsNone(resolve_within_roots(str(media) + "/beds/../../secret", roots))
            link = media / "escape"
            link.symlink_to(secret, target_is_directory=True)
            self.assertIsNone(resolve_within_roots(str(link), roots))
            self.assertIsNone(confine_muzak_folder(str(secret), settings=_Settings(str(media))))
            confined = confine_muzak_folder(
                str(beds),
                settings=_Settings(str(media)),
                mountinfo_text="",
                environ={"PROJECTIONIST_PREROLL_MEDIA": ""},
            )
            self.assertEqual(confined, beds.resolve())

    def test_browser_highlights_bind_mount_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "movies"
            (media / "beds").mkdir(parents=True)
            resolved = str(media.resolve())
            mountinfo = (
                f"36 35 98:0 /host/movies {resolved} rw,relatime - ext4 /dev/sda1 rw\n"
                "1 0 0:1 / / rw - overlay overlay rw\n"
            )
            settings = _Settings(resolved)
            roots = allowed_media_roots(
                settings=settings,
                environ={"PROJECTIONIST_PREROLL_MEDIA": str(Path(tmp) / "missing-preroll")},
                mountinfo_text=mountinfo,
            )
            self.assertIn(media.resolve(), roots)
            listing = browse_media(
                "",
                settings=settings,
                environ={"PROJECTIONIST_PREROLL_MEDIA": str(Path(tmp) / "missing-preroll")},
                mountinfo_text=mountinfo,
            )
            match = next(entry for entry in listing["entries"] if entry["path"] == resolved)
            self.assertTrue(match["bind_mount"])
            with self.assertRaises(ValueError):
                browse_media("/etc", settings=settings, mountinfo_text=mountinfo, environ={})


class _Settings:
    def __init__(self, movies_root: str) -> None:
        self.movies_root = movies_root
        self.tv_root = ""


if __name__ == "__main__":
    unittest.main()
