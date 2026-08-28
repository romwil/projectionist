"""Tests for mark-bad-media replace flow (no acquisition exclusion)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.connectors.radarr import RadarrMovie
from projectionist.connectors.sonarr import SonarrSeries
from projectionist.library.bad_media import BadMediaError, mark_bad_media
from projectionist.library.db import Database
from projectionist.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache, create_session_token


class MarkBadMediaLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "bad-media.db")
        self.settings = Settings(
            radarr_url="http://radarr",
            radarr_api_key="secret",
            sonarr_url="http://sonarr",
            sonarr_api_key="secret",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _seed_movie(self, *, tmdb_id: int = 123) -> str:
        self.db.upsert_library_items(
            [
                {
                    "rating_key": "rk-bad-movie",
                    "media_type": "movie",
                    "title": "Bad Movie",
                    "year": 2020,
                    "tmdb_id": tmdb_id,
                }
            ]
        )
        return "rk-bad-movie"

    def _seed_show(self, *, tvdb_id: int = 456) -> str:
        self.db.upsert_library_items(
            [
                {
                    "rating_key": "rk-bad-show",
                    "media_type": "show",
                    "title": "Bad Show",
                    "year": 2021,
                    "tvdb_id": tvdb_id,
                }
            ]
        )
        return "rk-bad-show"

    @patch("projectionist.library.bad_media.RadarrClient")
    def test_movie_deletes_file_searches_no_exclusion(self, radarr_cls: MagicMock) -> None:
        self._seed_movie()
        radarr = MagicMock()
        radarr.movie_by_tmdb_id.return_value = RadarrMovie(
            id=9,
            title="Bad Movie",
            year=2020,
            tmdb_id=123,
            monitored=True,
            has_file=True,
            movie_file_id=88,
        )
        radarr.search_movie.return_value = {"name": "MoviesSearch"}
        radarr_cls.return_value = radarr

        result = mark_bad_media(
            self.db,
            self.settings,
            rating_key="rk-bad-movie",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["add_exclusion"])
        self.assertEqual(result["files_removed"], 1)
        radarr.mark_movie_file_failed.assert_called_once_with(88)
        radarr.search_movie.assert_called_once_with(9)
        self.assertFalse(self.db.is_acquisition_excluded(media_type="movie", tmdb_id=123))

    @patch("projectionist.library.bad_media.SonarrClient")
    def test_show_episode_deletes_file_and_episode_search(self, sonarr_cls: MagicMock) -> None:
        rating_key = self._seed_show()
        show_row = self.db.library_item_by_rating_key(rating_key)
        assert show_row is not None
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_episodes (
                    show_item_id, rating_key, season_number, episode_number, title
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (int(show_row["id"]), "ep-rk-1", 1, 3, "Pilot"),
            )
            conn.commit()

        sonarr = MagicMock()
        sonarr.series_by_tvdb_id.return_value = SonarrSeries(
            id=5,
            title="Bad Show",
            year=2021,
            tvdb_id=456,
            tmdb_id=None,
            monitored=True,
        )
        sonarr.episodes.return_value = [
            {
                "id": 101,
                "seasonNumber": 1,
                "episodeNumber": 3,
                "episodeFileId": 77,
                "hasFile": True,
            }
        ]
        sonarr.episode_files.return_value = []
        sonarr.search_episodes.return_value = {"name": "EpisodeSearch"}
        sonarr_cls.return_value = sonarr

        result = mark_bad_media(
            self.db,
            self.settings,
            rating_key=rating_key,
            episode_rating_key="ep-rk-1",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["add_exclusion"])
        self.assertEqual(result["files_removed"], 1)
        sonarr.delete_episode_files.assert_called_once_with([77])
        sonarr.search_episodes.assert_called_once_with([101])
        self.assertFalse(self.db.is_acquisition_excluded(media_type="show", tvdb_id=456))

    @patch("projectionist.library.bad_media.RadarrClient")
    def test_movie_not_in_radarr_raises(self, radarr_cls: MagicMock) -> None:
        self._seed_movie()
        radarr_cls.return_value.movie_by_tmdb_id.return_value = None
        with self.assertRaises(BadMediaError):
            mark_bad_media(self.db, self.settings, rating_key="rk-bad-movie")


class MarkBadMediaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-bad-media-session"
        os.environ["RADARR_URL"] = "http://radarr"
        os.environ["RADARR_API_KEY"] = "secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import importlib
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = app_mod._db()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        self._tmpdir.cleanup()

    def _owner_cookie(self) -> dict[str, str]:
        token = create_session_token({"id": "owner-1", "role": "owner", "username": "owner"})
        return {SESSION_COOKIE_NAME: token}

    @patch("projectionist.library.bad_media.mark_bad_media")
    def test_api_requires_confirm(self, mark_mock: MagicMock) -> None:
        resp = self.client.post(
            "/api/library/items/mark-bad-media",
            json={"rating_key": "rk-1", "confirm": False},
            cookies=self._owner_cookie(),
        )
        self.assertEqual(resp.status_code, 400)
        mark_mock.assert_not_called()

    @patch("projectionist.library.bad_media.RadarrClient")
    def test_api_owner_mark_bad_movie(self, radarr_cls: MagicMock) -> None:
        self.db.upsert_library_items(
            [
                {
                    "rating_key": "rk-api-movie",
                    "media_type": "movie",
                    "title": "Glitch",
                    "tmdb_id": 999,
                }
            ]
        )
        radarr = MagicMock()
        radarr.movie_by_tmdb_id.return_value = RadarrMovie(
            id=1,
            title="Glitch",
            year=None,
            tmdb_id=999,
            monitored=True,
            has_file=True,
            movie_file_id=2,
        )
        radarr.search_movie.return_value = {"name": "MoviesSearch"}
        radarr_cls.return_value = radarr

        resp = self.client.post(
            "/api/library/items/mark-bad-media",
            json={"rating_key": "rk-api-movie", "confirm": True},
            cookies=self._owner_cookie(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["add_exclusion"])


class MarkBadMediaAgentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_mark_bad_media_tool(self) -> None:
        from projectionist.agent.tools import ToolRegistry
        from projectionist.library.db import DEFAULT_LENS_ID, Database

        tmpdir = tempfile.TemporaryDirectory()
        db = Database(Path(tmpdir.name) / "agent-bad-media.db")
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-agent",
                    "media_type": "movie",
                    "title": "Agent Movie",
                    "tmdb_id": 555,
                }
            ]
        )
        settings = Settings(radarr_url="http://radarr", radarr_api_key="secret")
        registry = ToolRegistry(db, settings, DEFAULT_LENS_ID)
        movie = RadarrMovie(
            id=3,
            title="Agent Movie",
            year=2022,
            tmdb_id=555,
            monitored=True,
            has_file=True,
            movie_file_id=4,
        )
        with patch("projectionist.library.bad_media.RadarrClient") as radarr_cls:
            radarr = MagicMock()
            radarr.movie_by_tmdb_id.return_value = movie
            radarr.search_movie.return_value = {"name": "MoviesSearch"}
            radarr_cls.return_value = radarr
            raw = await registry.execute(
                "mark_bad_media",
                {"rating_key": "rk-agent", "media_type": "movie", "tmdb_id": 555},
            )
        payload = json.loads(raw)
        self.assertTrue(payload.get("ok"))
        self.assertFalse(payload.get("add_exclusion"))
        tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()
