"""Credit enrichment and person browse API coverage."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from curatorx.library.db import Database
from curatorx.library.titles import get_title_detail


class TitleDetailCreditsTests(unittest.TestCase):
    @patch("curatorx.library.titles.cached_machine_identifier", return_value="")
    @patch("curatorx.library.titles.TMDBClient")
    def test_prefers_db_credits_when_in_library(self, mock_tmdb_cls, _machine) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.return_value = {
            "title": "Blade Runner",
            "overview": "Neo-noir",
            "vote_average": 8.1,
            "credits": {
                "cast": [{"id": 99, "name": "TMDB Only", "character": "X", "order": 0}],
                "crew": [{"id": 5, "name": "Ridley Scott", "job": "Director"}],
            },
            "keywords": {"keywords": [{"name": "cyberpunk"}]},
            "videos": {"results": []},
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""
        mock_tmdb.profile_url.return_value = ""
        mock_tmdb_cls.youtube_trailer_key.return_value = ""

        settings = MagicMock()
        settings.tmdb_api_key = "tmdb"
        settings.fanart_api_key = ""
        settings.plex_url = ""
        settings.plex_token = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-78",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "tmdb_id": 78,
                    "cast": ["Harrison Ford"],
                    "directors": ["Ridley Scott"],
                    "keywords": ["dystopia"],
                    "structured_credits": [
                        {
                            "tmdb_person_id": 3,
                            "name": "Harrison Ford",
                            "department": "Acting",
                            "job": "Actor",
                            "character": "Deckard",
                            "billing_order": 0,
                        },
                        {
                            "tmdb_person_id": 5,
                            "name": "Ridley Scott",
                            "department": "Directing",
                            "job": "Director",
                            "character": "",
                            "billing_order": 0,
                        },
                    ],
                }
            )
            detail = get_title_detail(db, settings, media_type="movie", tmdb_id=78)
            self.assertEqual(len(detail.credits), 2)
            names = {c.name for c in detail.credits}
            self.assertEqual(names, {"Harrison Ford", "Ridley Scott"})
            ford = next(c for c in detail.credits if c.name == "Harrison Ford")
            self.assertEqual(ford.tmdb_person_id, 3)
            self.assertEqual(ford.character, "Deckard")
            self.assertEqual(detail.cast, ["Harrison Ford"])
            self.assertEqual(detail.directors, ["Ridley Scott"])
            self.assertEqual(detail.keywords, ["dystopia"])

    @patch("curatorx.library.titles.cached_machine_identifier", return_value="")
    @patch("curatorx.library.titles.TMDBClient")
    def test_tv_fills_cast_keywords_and_credits(self, mock_tmdb_cls, _machine) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.tv_details.return_value = {
            "name": "The Wire",
            "overview": "Baltimore",
            "vote_average": 9.0,
            "external_ids": {"tvdb_id": 79126},
            "credits": {
                "cast": [
                    {"id": 17419, "name": "Dominic West", "character": "McNulty", "order": 0},
                ],
                "crew": [],
            },
            "keywords": {"results": [{"name": "corruption"}, {"name": "police"}]},
            "videos": {"results": []},
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""
        mock_tmdb.profile_url.side_effect = lambda path, size="w185": f"https://img{path}" if path else ""
        mock_tmdb_cls.youtube_trailer_key.return_value = ""

        settings = MagicMock()
        settings.tmdb_api_key = "tmdb"
        settings.fanart_api_key = ""
        settings.plex_url = ""
        settings.plex_token = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            detail = get_title_detail(db, settings, media_type="show", tmdb_id=1438)
            self.assertEqual(detail.cast, ["Dominic West"])
            self.assertEqual(detail.keywords, ["corruption", "police"])
            self.assertEqual(len(detail.credits), 1)
            self.assertEqual(detail.credits[0].tmdb_person_id, 17419)
            self.assertEqual(detail.credits[0].character, "McNulty")
            self.assertEqual(detail.tvdb_id, 79126)


class PersonApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    @patch("curatorx.web.app.TMDBClient")
    def test_person_api_merges_tmdb_and_library(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.person_details.return_value = {
            "id": 287,
            "name": "Brad Pitt",
            "biography": "Actor and producer.",
            "birthday": "1963-12-18",
            "deathday": None,
            "place_of_birth": "Oklahoma",
            "profile_path": "/pitt.jpg",
            "known_for_department": "Acting",
        }
        mock_tmdb.profile_url.return_value = "https://image.tmdb.org/t/p/w342/pitt.jpg"

        with patch.object(self.app_mod, "_settings") as mock_settings:
            settings = MagicMock()
            settings.tmdb_api_key = "tmdb"
            settings.features.multi_user_enabled = False
            mock_settings.return_value = settings

            item_id = self.db.upsert_library_item(
                {
                    "rating_key": "rk-550",
                    "media_type": "movie",
                    "title": "Fight Club",
                    "year": 1999,
                    "tmdb_id": 550,
                    "structured_credits": [
                        {
                            "tmdb_person_id": 287,
                            "name": "Brad Pitt",
                            "department": "Acting",
                            "job": "Actor",
                            "character": "Tyler Durden",
                            "billing_order": 1,
                        }
                    ],
                }
            )
            self.assertTrue(item_id)

            response = self.client.get("/api/person/287")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["name"], "Brad Pitt")
            self.assertEqual(payload["tmdb_person_id"], 287)
            self.assertIn("Actor and producer", payload["biography"])
            self.assertEqual(payload["returned"], 1)
            self.assertEqual(payload["titles"][0]["title"], "Fight Club")
            self.assertEqual(payload["titles"][0]["character"], "Tyler Durden")

    def test_person_api_404_when_unknown(self) -> None:
        with patch.object(self.app_mod, "_settings") as mock_settings:
            settings = MagicMock()
            settings.tmdb_api_key = ""
            settings.features.multi_user_enabled = False
            mock_settings.return_value = settings
            response = self.client.get("/api/person/999001")
            self.assertEqual(response.status_code, 404)

    def test_person_resolve_by_name(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-78",
                "media_type": "movie",
                "title": "Blade Runner",
                "year": 1982,
                "tmdb_id": 78,
                "structured_credits": [
                    {
                        "tmdb_person_id": 5,
                        "name": "Ridley Scott",
                        "department": "Directing",
                        "job": "Director",
                        "character": "",
                        "billing_order": 0,
                    }
                ],
            }
        )
        response = self.client.get("/api/person/resolve", params={"name": "ridley scott"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tmdb_person_id"], 5)
        self.assertFalse(payload["library_only"])

    def test_spa_shells_for_person_and_tag(self) -> None:
        person = self.client.get("/person/287")
        tag = self.client.get("/tag/cyberpunk")
        self.assertEqual(person.status_code, 200)
        self.assertEqual(tag.status_code, 200)


if __name__ == "__main__":
    unittest.main()
