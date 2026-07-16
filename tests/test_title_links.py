"""Tests for trailer extraction and Plex watch deep links."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from curatorx.connectors.plex import plex_watch_url
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.library.titles import get_title_detail


class PlexWatchUrlTests(unittest.TestCase):
    def test_builds_app_plex_deep_link(self) -> None:
        url = plex_watch_url("machine-1", "12345")
        self.assertIn("https://app.plex.tv/desktop/#!/server/machine-1/details", url)
        self.assertIn("key=%2Flibrary%2Fmetadata%2F12345", url)

    def test_requires_both_parts(self) -> None:
        self.assertEqual(plex_watch_url("", "123"), "")
        self.assertEqual(plex_watch_url("machine", ""), "")


class YoutubeTrailerKeyTests(unittest.TestCase):
    def test_prefers_official_english_trailer(self) -> None:
        payload = {
            "videos": {
                "results": [
                    {"site": "YouTube", "type": "Teaser", "key": "teaser1", "official": True, "iso_639_1": "en"},
                    {"site": "YouTube", "type": "Trailer", "key": "trail1", "official": False, "iso_639_1": "fr"},
                    {"site": "YouTube", "type": "Trailer", "key": "trail2", "official": True, "iso_639_1": "en"},
                    {"site": "Vimeo", "type": "Trailer", "key": "vimeo1", "official": True, "iso_639_1": "en"},
                ]
            }
        }
        self.assertEqual(TMDBClient.youtube_trailer_key(payload), "trail2")

    def test_empty_when_no_youtube(self) -> None:
        self.assertEqual(TMDBClient.youtube_trailer_key({"videos": {"results": []}}), "")
        self.assertEqual(TMDBClient.youtube_trailer_key({}), "")


class TitleDetailTrailerTests(unittest.TestCase):
    @patch("curatorx.library.titles.suggest_purge_candidates", return_value=[])
    @patch("curatorx.library.titles.cached_machine_identifier", return_value="machine-xyz")
    @patch("curatorx.library.titles.TMDBClient")
    def test_detail_includes_trailer_and_plex_url(self, mock_tmdb_cls, _mock_machine, _mock_purge) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.return_value = {
            "title": "The Matrix",
            "overview": "Whoa",
            "vote_average": 8.7,
            "poster_path": "/p.jpg",
            "backdrop_path": "/b.jpg",
            "runtime": 136,
            "credits": {"cast": [], "crew": []},
            "keywords": {"keywords": []},
            "videos": {
                "results": [
                    {"site": "YouTube", "type": "Trailer", "key": "m8e-LF8Z4Cw", "official": True, "iso_639_1": "en"}
                ]
            },
        }
        mock_tmdb.poster_url.return_value = "https://img/p.jpg"
        mock_tmdb.backdrop_url.return_value = "https://img/b.jpg"
        mock_tmdb_cls.youtube_trailer_key.return_value = "m8e-LF8Z4Cw"

        settings = MagicMock()
        settings.tmdb_api_key = "tmdb"
        settings.fanart_api_key = ""
        settings.plex_url = "http://plex.local"
        settings.plex_token = "token"

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "The Matrix",
                    "year": 1999,
                    "tmdb_id": 603,
                    "summary": "Whoa",
                }
            )

            detail = get_title_detail(db, settings, media_type="movie", tmdb_id=603)
            self.assertEqual(detail.trailer_youtube_key, "m8e-LF8Z4Cw")
            self.assertTrue(detail.in_library)
            self.assertEqual(detail.rating_key, "rk-1")
            self.assertIn("machine-xyz", detail.plex_watch_url)
            self.assertIn("rk-1", detail.plex_watch_url)


if __name__ == "__main__":
    unittest.main()
