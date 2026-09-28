"""Rematch studio: Plex GUID vs Radarr TMDB vs folder (Presence / Savages)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from projectionist.connectors.radarr import RadarrMovie
from projectionist.library.db import Database
from projectionist.library.rematch import (
    KIND_NEEDS_PLEX_ID,
    KIND_PATH_CONFLICT,
    KIND_TITLE_COLLISION,
    collect_repair_misses,
    humanize_operator_error,
    looks_like_json_dump,
    repair_actions_for,
    retry_register_title,
    scan_identity_mismatches,
    set_skipped,
)
from projectionist.notifications.good_news import format_good_news


class _CatalogRadarr:
    def __init__(self, movies: Optional[List[RadarrMovie]] = None) -> None:
        self._movies = list(movies or [])
        self.added: List[int] = []

    def movies(self) -> List[RadarrMovie]:
        return list(self._movies)

    def add_movie(self, tmdb_id: int, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        self.added.append(int(tmdb_id))
        return {"id": 99, "tmdbId": int(tmdb_id)}


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        radarr_url="http://radarr.test",
        radarr_api_key="secret",
        radarr_root_folder="/movies",
        movies_root="/movies",
        radarr_quality_profile_id=1,
    )


def _movie(
    *,
    rating_key: str,
    title: str,
    year: int,
    tmdb_id: Optional[int],
) -> Dict[str, Any]:
    return {
        "rating_key": rating_key,
        "media_type": "movie",
        "title": title,
        "year": year,
        "tmdb_id": tmdb_id,
        "in_radarr": 0,
    }


class RematchStudioTests(unittest.TestCase):
    def test_presence_vs_savages_is_path_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [
                    _movie(
                        rating_key="rk-presence",
                        title="Presence",
                        year=2025,
                        tmdb_id=1388150,
                    )
                ]
            )
            catalog = [
                RadarrMovie(
                    id=9,
                    title="Savages",
                    year=2012,
                    tmdb_id=111,
                    monitored=True,
                    has_file=True,
                    folder_path="/movies/Presence (2025)",
                )
            ]
            result = scan_identity_mismatches(db, _settings(), catalog=catalog)
            self.assertEqual(result["total"], 1)
            row = result["items"][0]
            self.assertEqual(row["kind"], KIND_PATH_CONFLICT)
            self.assertFalse(row["same_title"])
            self.assertIn("Path conflict", row["message"])
            self.assertNotIn("formattedMessagePlaceholderValues", row["message"])
            self.assertEqual(row["plex"]["tmdb_id"], 1388150)
            self.assertEqual(row["radarr"]["tmdb_id"], 111)
            self.assertIn("retry", row["actions"])
            self.assertIn("rematch", row["actions"])

    def test_same_title_path_conflict_is_honest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-p", title="Presence", year=2025, tmdb_id=1388150)]
            )
            catalog = [
                RadarrMovie(
                    id=9,
                    title="Presence",
                    year=2025,
                    tmdb_id=111,
                    monitored=True,
                    has_file=True,
                    folder_path="/movies/Presence (2025)",
                )
            ]
            row = scan_identity_mismatches(db, _settings(), catalog=catalog)["items"][0]
            self.assertEqual(row["kind"], KIND_PATH_CONFLICT)
            self.assertTrue(row["same_title"])
            self.assertIn("tmdb 1388150", row["message"])
            self.assertIn("tmdb 111", row["message"])

    def test_same_title_different_folder_is_title_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-hunt", title="The Hunt", year=2020, tmdb_id=514847)]
            )
            catalog = [
                RadarrMovie(
                    id=3,
                    title="The Hunt",
                    year=2020,
                    tmdb_id=99,
                    monitored=True,
                    has_file=True,
                    folder_path="/movies/The Hunt (2012)",
                )
            ]
            row = scan_identity_mismatches(db, _settings(), catalog=catalog)["items"][0]
            self.assertEqual(row["kind"], KIND_TITLE_COLLISION)
            self.assertTrue(row["same_title"])
            self.assertIn("Same title", row["message"])
            self.assertIn("FileBot", row["message"])

    def test_missing_plex_tmdb_needs_rematch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-x", title="Unknown Reel", year=1999, tmdb_id=None)]
            )
            row = scan_identity_mismatches(db, _settings(), catalog=[])["items"][0]
            self.assertEqual(row["kind"], KIND_NEEDS_PLEX_ID)
            self.assertIn("no TMDB id", row["message"])
            self.assertNotIn("retry", row["actions"])
            self.assertIn("Plex Match", row["message"])

    def test_basename_match_when_root_prefix_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-p", title="Presence", year=2025, tmdb_id=1388150)]
            )
            catalog = [
                RadarrMovie(
                    id=9,
                    title="Savages",
                    year=2012,
                    tmdb_id=111,
                    monitored=True,
                    has_file=True,
                    folder_path="/data/media/Presence (2025)",
                )
            ]
            settings = SimpleNamespace(
                radarr_url="http://radarr.test",
                radarr_api_key="secret",
                radarr_root_folder="/movies",
                movies_root="/movies",
                radarr_quality_profile_id=1,
            )
            row = scan_identity_mismatches(db, settings, catalog=catalog)["items"][0]
            self.assertEqual(row["kind"], KIND_PATH_CONFLICT)
            self.assertEqual(row["radarr"]["tmdb_id"], 111)

    def test_same_tmdb_is_not_a_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-ok", title="Moon", year=2009, tmdb_id=17431)]
            )
            catalog = [
                RadarrMovie(
                    id=1,
                    title="Moon",
                    year=2009,
                    tmdb_id=17431,
                    monitored=True,
                    has_file=True,
                    folder_path="/movies/Moon (2009)",
                )
            ]
            result = scan_identity_mismatches(db, _settings(), catalog=catalog)
            self.assertEqual(result["items"], [])

    def test_skip_hides_row_until_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-x", title="Unknown Reel", year=1999, tmdb_id=None)]
            )
            item_id = int(db.library_item_by_rating_key("rk-x")["id"])
            set_skipped(db, item_id, skipped=True)
            hidden = scan_identity_mismatches(db, _settings(), catalog=[])
            self.assertEqual(hidden["total"], 0)
            shown = scan_identity_mismatches(db, _settings(), catalog=[], include_skipped=True)
            self.assertEqual(shown["total"], 1)
            self.assertTrue(shown["items"][0]["skipped"])

    def test_retry_registers_when_folder_is_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-moon", title="Moon", year=2009, tmdb_id=17431)]
            )
            item_id = int(db.library_item_by_tmdb(17431, "movie")["id"])
            client = _CatalogRadarr([])
            result = retry_register_title(db, _settings(), item_id, client=client)
            self.assertTrue(result["ok"])
            self.assertEqual(result["outcome"], "registered")
            self.assertEqual(client.added, [17431])
            self.assertEqual(int(db.library_item_by_tmdb(17431, "movie")["in_radarr"] or 0), 1)

    def test_retry_path_conflict_does_not_mark_in_radarr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [_movie(rating_key="rk-p", title="Presence", year=2025, tmdb_id=1388150)]
            )
            item_id = int(db.library_item_by_tmdb(1388150, "movie")["id"])
            client = _CatalogRadarr(
                [
                    RadarrMovie(
                        id=9,
                        title="Savages",
                        year=2012,
                        tmdb_id=111,
                        monitored=True,
                        has_file=True,
                        folder_path="/movies/Presence (2025)",
                    )
                ]
            )
            result = retry_register_title(db, _settings(), item_id, client=client)
            self.assertFalse(result["ok"])
            self.assertEqual(result["outcome"], KIND_PATH_CONFLICT)
            self.assertEqual(client.added, [])
            self.assertEqual(int(db.library_item_by_tmdb(1388150, "movie")["in_radarr"] or 0), 0)
            self.assertNotIn("{", result["message"])

    def test_humanize_strips_radarr_json_dump(self) -> None:
        raw = (
            "HTTP 400 from http://10.10.1.210/api/v3/movie: "
            + json.dumps(
                [
                    {
                        "errorCode": "MoviePathValidator",
                        "errorMessage": "Path '/movies/Presence (2025)' is already configured for an existing movie",
                        "formattedMessagePlaceholderValues": {"path": "/movies/Presence (2025)"},
                    }
                ]
            )
        )
        self.assertTrue(looks_like_json_dump(raw))
        cleaned = humanize_operator_error(raw)
        self.assertNotIn("formattedMessagePlaceholderValues", cleaned)
        self.assertNotIn('"errorCode"', cleaned)

    def test_repair_actions_include_investigate_for_shows(self) -> None:
        self.assertEqual(
            repair_actions_for(kind="failed", media_type="show"),
            ["retry", "investigate", "skip"],
        )
        misses = collect_repair_misses(
            register_items=[
                {
                    "id": 4,
                    "title": "Presence (2025)",
                    "status": "failed",
                    "outcome": "path_conflict",
                    "error": raw_path_dump(),
                    "tmdb_id": 1388150,
                }
            ],
            sonarr_status={"execution": {"failed": 1, "last_error": raw_path_dump()}},
        )
        self.assertEqual(len(misses), 2)
        self.assertNotIn("formattedMessagePlaceholderValues", misses[0]["message"])
        self.assertIn("investigate", misses[1]["actions"])


def raw_path_dump() -> str:
    return (
        'HTTP 400 from http://radarr/api/v3/movie: [{"errorCode":"MoviePathValidator",'
        '"formattedMessagePlaceholderValues":{"path":"/movies/Presence (2025)"}}]'
    )


class GoodNewsCopyTests(unittest.TestCase):
    def test_gap_arrival_is_persona_not_download_complete(self) -> None:
        headline, body = format_good_news(
            title="Gap Movie",
            year=2001,
            source="gap",
            curator_name="Ada",
            preset_id="classic-curator",
        )
        blob = f"{headline} {body}".lower()
        self.assertIn("ada", headline.lower())
        self.assertIn("gap movie", headline.lower())
        self.assertNotIn("download complete", blob)
        self.assertNotIn("now in your library", headline.lower())

    def test_watchlist_arrival_is_good_news(self) -> None:
        headline, body = format_good_news(
            title="Arrival",
            year=2016,
            source="watchlist",
            curator_name="Ada",
        )
        self.assertIn("good news", headline.lower())
        self.assertIn("arrival", headline.lower())
        self.assertNotIn("download complete", body.lower())


if __name__ == "__main__":
    unittest.main()
