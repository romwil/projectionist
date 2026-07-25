"""Tests for Radarr connector."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from projectionist.config_store import pick_arr_root_folder
from projectionist.connectors.arr_errors import ArrTitleExistsError
from projectionist.connectors.radarr import RadarrClient, RadarrMovie


class PickArrRootFolderTests(unittest.TestCase):
    def test_exact_match_uses_registered_path(self) -> None:
        resolved = pick_arr_root_folder(
            "/media/movies",
            ["/media/movies/"],
            service="Radarr",
        )
        self.assertEqual(resolved, "/media/movies/")

    def test_single_registered_folder_auto_resolves(self) -> None:
        resolved = pick_arr_root_folder(
            "/mnt/user/data/media/movies",
            ["/movies"],
            service="Radarr",
        )
        self.assertEqual(resolved, "/movies")

    def test_multiple_registered_folders_rejects_unknown_path(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Available root folders"):
            pick_arr_root_folder(
                "/mnt/user/data/media/movies",
                ["/movies", "/media/movies"],
                service="Radarr",
            )


class RadarrClientTests(unittest.TestCase):
    def test_add_movie_builds_payload_with_root_folder(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        lookup = {
            "title": "Test Movie",
            "tmdbId": 123,
            "year": 2020,
            "path": "",
            "rootFolderPath": "",
        }
        captured: dict = {}

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            captured["url"] = url
            captured["method"] = method
            captured["body"] = body
            return {"id": 1, "title": "Test Movie"}

        with patch.object(client, "lookup_tmdb", return_value=lookup), patch.object(
            client, "root_folders", return_value=[{"path": "/media/movies"}]
        ), patch("projectionist.connectors.radarr.request_json", side_effect=fake_request_json):
            result = client.add_movie(
                123,
                root_folder="/media/movies",
                quality_profile_id=4,
                monitored=True,
                search_for_movie=False,
            )

        self.assertEqual(result["id"], 1)
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["url"], "http://radarr/api/v3/movie")
        body = captured["body"]
        self.assertEqual(body["rootFolderPath"], "/media/movies")
        self.assertEqual(body["qualityProfileId"], 4)
        self.assertEqual(body["tmdbId"], 123)
        self.assertTrue(body["monitored"])
        self.assertEqual(body["addOptions"], {"searchForMovie": False})
        self.assertNotIn("path", body)

    def test_add_movie_auto_resolves_single_registered_root_folder(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        lookup = {"title": "Test Movie", "tmdbId": 123}
        captured: dict = {}

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            captured["body"] = body
            return {"id": 1}

        with patch.object(client, "lookup_tmdb", return_value=lookup), patch.object(
            client, "root_folders", return_value=[{"path": "/movies"}]
        ), patch("projectionist.connectors.radarr.request_json", side_effect=fake_request_json):
            client.add_movie(
                123,
                root_folder="/mnt/user/data/media/movies",
                quality_profile_id=1,
            )

        self.assertEqual(captured["body"]["rootFolderPath"], "/movies")

    def test_add_movie_rejects_unregistered_root_folder(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        with patch.object(client, "movie_by_tmdb_id", return_value=None), patch.object(
            client, "lookup_tmdb", return_value={"tmdbId": 1}
        ), patch.object(
            client,
            "root_folders",
            return_value=[{"path": "/movies"}, {"path": "/media/movies"}],
        ):
            with self.assertRaisesRegex(RuntimeError, "Available root folders"):
                client.add_movie(
                    1,
                    root_folder="/mnt/user/data/media/movies",
                    quality_profile_id=1,
                )

    def test_add_movie_rejects_empty_root_folder(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        with patch.object(client, "lookup_tmdb", return_value={"tmdbId": 1}):
            with self.assertRaisesRegex(RuntimeError, "root folder path is not configured"):
                client.add_movie(1, root_folder="", quality_profile_id=1)

    def test_add_movie_preserves_existing_path(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        lookup = {
            "title": "Test Movie",
            "tmdbId": 123,
            "path": "/media/movies/Test Movie (2020)",
        }
        captured: dict = {}

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            captured["body"] = body
            return {"id": 1}

        with patch.object(client, "lookup_tmdb", return_value=lookup), patch.object(
            client, "root_folders", return_value=[{"path": "/media/movies"}]
        ), patch("projectionist.connectors.radarr.request_json", side_effect=fake_request_json):
            client.add_movie(123, root_folder="/media/movies", quality_profile_id=1)

        self.assertEqual(captured["body"]["path"], "/media/movies/Test Movie (2020)")

    def test_movie_by_tmdb_id_returns_match(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        payload = [
            {"id": 9, "title": "Existing Movie", "tmdbId": 35669, "monitored": True},
            {"id": 10, "title": "Other", "tmdbId": 1, "monitored": True},
        ]

        with patch("projectionist.connectors.radarr.request_json", return_value=payload):
            found = client.movie_by_tmdb_id(35669)

        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, 9)
        self.assertEqual(found.title, "Existing Movie")
        self.assertEqual(found.tmdb_id, 35669)

    def test_add_movie_raises_when_already_in_radarr(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        existing = RadarrMovie(
            id=9,
            title="Existing Movie",
            year=1990,
            tmdb_id=35669,
            monitored=True,
            has_file=False,
        )

        with patch.object(client, "movie_by_tmdb_id", return_value=existing):
            with self.assertRaises(ArrTitleExistsError) as ctx:
                client.add_movie(35669, root_folder="/media/movies", quality_profile_id=1)

        self.assertEqual(ctx.exception.service, "Radarr")
        self.assertEqual(ctx.exception.arr_id, 9)
        self.assertIn("Existing Movie", str(ctx.exception))

    def test_add_movie_catches_movie_exists_validator(self) -> None:
        client = RadarrClient("http://radarr", "secret")
        lookup = {"title": "Existing Movie", "tmdbId": 35669}
        error_body = json.dumps(
            [
                {
                    "propertyName": "TmdbId",
                    "errorMessage": "This movie has already been added",
                    "attemptedValue": 35669,
                    "errorCode": "MovieExistsValidator",
                }
            ]
        )
        existing = RadarrMovie(
            id=9,
            title="Existing Movie",
            year=1990,
            tmdb_id=35669,
            monitored=True,
            has_file=False,
        )

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            if method == "POST":
                raise RuntimeError(f"HTTP 400 from http://radarr/api/v3/movie: {error_body}")
            return {}

        with patch.object(client, "movie_by_tmdb_id", side_effect=[None, existing]), patch.object(
            client, "lookup_tmdb", return_value=lookup
        ), patch.object(client, "root_folders", return_value=[{"path": "/media/movies"}]), patch(
            "projectionist.connectors.radarr.request_json", side_effect=fake_request_json
        ):
            with self.assertRaises(ArrTitleExistsError) as ctx:
                client.add_movie(35669, root_folder="/media/movies", quality_profile_id=1)

        self.assertEqual(ctx.exception.arr_id, 9)


if __name__ == "__main__":
    unittest.main()
