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


class UsContentRatingTests(unittest.TestCase):
    def test_movie_prefers_us_theatrical_certification(self) -> None:
        payload = {
            "release_dates": {
                "results": [
                    {
                        "iso_3166_1": "GB",
                        "release_dates": [{"certification": "15", "type": 3}],
                    },
                    {
                        "iso_3166_1": "US",
                        "release_dates": [
                            {"certification": "PG", "type": 1},
                            {"certification": "PG-13", "type": 3},
                        ],
                    },
                ]
            }
        }
        self.assertEqual(TMDBClient.us_content_rating(payload), "PG-13")

    def test_tv_uses_us_content_ratings(self) -> None:
        payload = {
            "content_ratings": {
                "results": [
                    {"iso_3166_1": "CA", "rating": "14+"},
                    {"iso_3166_1": "US", "rating": "TV-14"},
                ]
            }
        }
        self.assertEqual(TMDBClient.us_content_rating(payload), "TV-14")

    def test_empty_when_missing(self) -> None:
        self.assertEqual(TMDBClient.us_content_rating({}), "")
        self.assertEqual(TMDBClient.us_content_rating({"release_dates": {"results": []}}), "")


class TitleDetailTrailerTests(unittest.TestCase):
    @patch("curatorx.library.titles.cached_machine_identifier", return_value="machine-xyz")
    @patch("curatorx.library.titles.TMDBClient")
    def test_detail_includes_trailer_and_plex_url(self, mock_tmdb_cls, _mock_machine) -> None:
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
        mock_tmdb_cls.us_content_rating.return_value = "R"

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
            self.assertEqual(detail.content_rating, "R")
            self.assertTrue(detail.in_library)
            self.assertEqual(detail.rating_key, "rk-1")
            self.assertIn("machine-xyz", detail.plex_watch_url)
            self.assertIn("rk-1", detail.plex_watch_url)

    @patch("curatorx.library.titles.cached_machine_identifier", return_value="")
    @patch("curatorx.library.titles.TMDBClient")
    def test_detail_keeps_plex_content_rating_without_enrichment(
        self, mock_tmdb_cls, _mock_machine
    ) -> None:
        settings = MagicMock()
        settings.tmdb_api_key = ""
        settings.fanart_api_key = ""
        settings.plex_url = ""
        settings.plex_token = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-pg13",
                    "media_type": "movie",
                    "title": "Jurassic Park",
                    "year": 1993,
                    "tmdb_id": 329,
                    "summary": "Dinosaurs",
                    "content_rating": "PG-13",
                    "vote_average": 7.9,
                    "poster_url": "https://img/p.jpg",
                    "backdrop_url": "https://img/b.jpg",
                    "runtime_minutes": 127,
                    "release_date": "1993-06-11",
                    "keywords": ["dinosaur"],
                    "cast": ["Sam Neill"],
                    "directors": ["Steven Spielberg"],
                }
            )

            detail = get_title_detail(
                db, settings, media_type="movie", tmdb_id=329, enrich=False
            )
            self.assertEqual(detail.content_rating, "PG-13")
            self.assertAlmostEqual(float(detail.rating or 0), 7.9)
            mock_tmdb_cls.assert_not_called()


class TitleDetailHotPathTests(unittest.TestCase):
    @patch("curatorx.preferences.purge._build_candidates")
    @patch("curatorx.library.titles.cached_machine_identifier", return_value="machine-xyz")
    @patch("curatorx.library.titles.TMDBClient")
    def test_enrich_false_skips_external_calls(
        self, mock_tmdb_cls, mock_machine, mock_purge_build
    ) -> None:
        settings = MagicMock()
        settings.tmdb_api_key = "tmdb"
        settings.fanart_api_key = "fanart"
        settings.plex_url = "http://plex.local"
        settings.plex_token = "token"

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-fast",
                    "media_type": "movie",
                    "title": "Fast Local",
                    "year": 2020,
                    "tmdb_id": 42,
                    "summary": "Local overview",
                    "poster_url": "https://img/local.jpg",
                }
            )

            detail = get_title_detail(
                db, settings, media_type="movie", tmdb_id=42, enrich=False
            )

        self.assertEqual(detail.title, "Fast Local")
        self.assertEqual(detail.poster_url, "https://img/local.jpg")
        self.assertEqual(detail.purge_reason, "")
        mock_tmdb_cls.assert_not_called()
        mock_purge_build.assert_not_called()
        mock_machine.assert_called_once()

    @patch("curatorx.preferences.purge._build_candidates")
    @patch("curatorx.library.titles.FanartClient")
    @patch("curatorx.library.titles.cached_machine_identifier", return_value="")
    @patch("curatorx.library.titles.TMDBClient")
    def test_enrich_true_never_calls_purge_scoring(
        self, mock_tmdb_cls, _mock_machine, _mock_fanart, mock_purge_build
    ) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.return_value = {
            "title": "Enriched",
            "overview": "From TMDB",
            "vote_average": 7.1,
            "poster_path": "/p.jpg",
            "backdrop_path": "/b.jpg",
            "runtime": 100,
            "credits": {"cast": [], "crew": []},
            "keywords": {"keywords": []},
            "videos": {"results": []},
        }
        mock_tmdb.poster_url.return_value = "https://img/p.jpg"
        mock_tmdb.backdrop_url.return_value = "https://img/b.jpg"
        mock_tmdb_cls.youtube_trailer_key.return_value = ""

        settings = MagicMock()
        settings.tmdb_api_key = "tmdb"
        settings.fanart_api_key = ""
        settings.plex_url = ""
        settings.plex_token = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            detail = get_title_detail(
                db, settings, media_type="movie", tmdb_id=99, enrich=True
            )

        self.assertEqual(detail.title, "Enriched")
        mock_purge_build.assert_not_called()
        mock_tmdb_cls.assert_called_once()
        self.assertEqual(mock_tmdb_cls.call_args.kwargs.get("timeout"), 5)

    def test_library_item_by_rating_key_uses_index_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-lookup",
                    "media_type": "movie",
                    "title": "Lookup",
                    "year": 2011,
                    "tmdb_id": 11,
                }
            )
            row = db.library_item_by_rating_key("rk-lookup")
            self.assertIsNotNone(row)
            self.assertEqual(row["title"], "Lookup")
            self.assertIsNone(db.library_item_by_rating_key(""))


if __name__ == "__main__":
    unittest.main()
