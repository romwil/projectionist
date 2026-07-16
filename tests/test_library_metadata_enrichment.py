"""Value-based tests for Wave 1 metadata enrichment + structured credits."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from curatorx.config_store import Settings
from curatorx.connectors.plex import PlexLibraryItem
from curatorx.library.db import Database
from curatorx.library.sync import (
    _apply_tmdb_enrichment,
    _row_from_plex_item,
    _structured_credits_from_tmdb,
)
from curatorx.scheduler.tasks import metadata_enrichment


MOVIE_TMDB_DETAILS = {
    "release_date": "1982-06-25",
    "status": "Released",
    "vote_average": 8.1,
    "original_language": "en",
    "runtime": 117,
    "belongs_to_collection": {"id": 10, "name": "Blade Runner Collection"},
    "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}],
    "production_companies": [
        {"id": 1, "name": "Warner Bros. Pictures"},
        {"id": 2, "name": "The Ladd Company"},
    ],
    "keywords": {"keywords": [{"name": "dystopia"}]},
    "credits": {
        "cast": [
            {
                "id": 3,
                "name": "Harrison Ford",
                "character": "Deckard",
                "order": 0,
                "profile_path": "/ford.jpg",
            },
            {
                "id": 4,
                "name": "Rutger Hauer",
                "character": "Batty",
                "order": 1,
                "profile_path": None,
            },
        ],
        "crew": [
            {
                "id": 5,
                "name": "Ridley Scott",
                "job": "Director",
                "department": "Directing",
                "profile_path": "/scott.jpg",
            }
        ],
    },
}

SHOW_TMDB_DETAILS = {
    "first_air_date": "2011-04-17",
    "last_air_date": "2019-05-19",
    "status": "Ended",
    "original_language": "en",
    "episode_run_time": [60],
    "networks": [{"id": 49, "name": "HBO"}],
    "production_companies": [{"id": 3268, "name": "HBO"}],
    "keywords": {"results": []},
    "credits": {
        "cast": [
            {
                "id": 100,
                "name": "Peter Dinklage",
                "character": "Tyrion",
                "order": 0,
            }
        ],
        "crew": [
            {
                "id": 101,
                "name": "David Benioff",
                "job": "Creator",
                "department": "Writing",
            }
        ],
    },
}


class MetadataMigrationTests(unittest.TestCase):
    def test_new_columns_and_indexes_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(library_items)")}
                self.assertTrue(
                    {
                        "release_date",
                        "first_air_date",
                        "last_air_date",
                        "tmdb_collection_id",
                        "collection_name",
                        "status",
                        "networks",
                        "production_companies",
                    }.issubset(cols)
                )
                indexes = {
                    str(r["name"])
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
                }
                self.assertIn("idx_library_release_date", indexes)
                self.assertIn("idx_library_first_air_date", indexes)

    def test_people_and_credits_tables_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                tables = {
                    str(r["name"])
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            self.assertIn("people", tables)
            self.assertIn("credits", tables)


class MetadataUpsertTests(unittest.TestCase):
    def test_upsert_persists_dates_and_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-br",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "tmdb_id": 78,
                    "release_date": "1982-06-25",
                    "tmdb_collection_id": 10,
                    "collection_name": "Blade Runner Collection",
                    "status": "Released",
                    "production_companies": ["Warner Bros. Pictures"],
                    "networks": [],
                }
            )
            self.assertGreater(item_id, 0)
            row = db.library_item_by_id(item_id)
            assert row is not None
            self.assertEqual(row["release_date"], "1982-06-25")
            self.assertEqual(int(row["tmdb_collection_id"]), 10)
            self.assertEqual(row["collection_name"], "Blade Runner Collection")
            self.assertEqual(row["status"], "Released")
            self.assertEqual(
                json.loads(row["production_companies"]),
                ["Warner Bros. Pictures"],
            )

    def test_upsert_does_not_clobber_existing_dates_with_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "Film",
                    "year": 2000,
                    "release_date": "2000-01-15",
                    "status": "Released",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "Film",
                    "year": 2000,
                    # omit dates — COALESCE should keep prior values
                }
            )
            row = db.library_item_by_rating_key("rk-1") if hasattr(db, "library_item_by_rating_key") else None
            if row is None:
                with db.connect() as conn:
                    row = conn.execute(
                        "SELECT * FROM library_items WHERE rating_key = ?",
                        ("rk-1",),
                    ).fetchone()
            assert row is not None
            self.assertEqual(row["release_date"], "2000-01-15")
            self.assertEqual(row["status"], "Released")


class PeopleCreditsTests(unittest.TestCase):
    def test_people_credits_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-br",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "tmdb_id": 78,
                    "cast": ["Harrison Ford"],
                    "directors": ["Ridley Scott"],
                    "structured_credits": [
                        {
                            "tmdb_person_id": 3,
                            "name": "Harrison Ford",
                            "profile_url": "https://image.tmdb.org/t/p/w185/ford.jpg",
                            "department": "Acting",
                            "job": "Actor",
                            "character": "Deckard",
                            "billing_order": 0,
                        },
                        {
                            "tmdb_person_id": 5,
                            "name": "Ridley Scott",
                            "profile_url": "",
                            "department": "Directing",
                            "job": "Director",
                            "character": "",
                            "billing_order": 0,
                        },
                    ],
                }
            )
            credits = db.list_credits_for_item(item_id)
            self.assertEqual(len(credits), 2)
            names = {str(c["name"]) for c in credits}
            self.assertEqual(names, {"Harrison Ford", "Ridley Scott"})
            ford = next(c for c in credits if c["name"] == "Harrison Ford")
            self.assertEqual(ford["character"], "Deckard")
            self.assertEqual(int(ford["tmdb_person_id"]), 3)

            titles = db.list_library_titles_for_person(tmdb_person_id=5)
            self.assertEqual(len(titles), 1)
            self.assertEqual(titles[0]["title"], "Blade Runner")
            self.assertEqual(titles[0]["job"], "Director")

            # Dual-write: JSON cast/directors still present for older callers.
            row = db.library_item_by_id(item_id)
            assert row is not None
            self.assertEqual(json.loads(row["cast"]), ["Harrison Ford"])
            self.assertEqual(json.loads(row["directors"]), ["Ridley Scott"])

    def test_upsert_credits_replaces_prior_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-a",
                    "media_type": "movie",
                    "title": "A",
                    "year": 1990,
                }
            )
            db.upsert_credits_for_item(
                item_id,
                [
                    {
                        "tmdb_person_id": 1,
                        "name": "Alice",
                        "department": "Acting",
                        "job": "Actor",
                        "character": "Hero",
                        "billing_order": 0,
                    }
                ],
            )
            db.upsert_credits_for_item(
                item_id,
                [
                    {
                        "tmdb_person_id": 2,
                        "name": "Bob",
                        "department": "Directing",
                        "job": "Director",
                        "character": "",
                        "billing_order": 0,
                    }
                ],
            )
            credits = db.list_credits_for_item(item_id)
            self.assertEqual(len(credits), 1)
            self.assertEqual(credits[0]["name"], "Bob")


class ApplyTmdbEnrichmentTests(unittest.TestCase):
    def test_movie_dates_collection_and_structured_credits(self) -> None:
        row: dict = {}
        tmdb = MagicMock()
        tmdb.poster_url.side_effect = lambda path, size="w500": f"https://img/{size}{path}"
        _apply_tmdb_enrichment(row, MOVIE_TMDB_DETAILS, media_type="movie", tmdb_client=tmdb)
        self.assertEqual(row["release_date"], "1982-06-25")
        self.assertEqual(row["tmdb_collection_id"], 10)
        self.assertEqual(row["collection_name"], "Blade Runner Collection")
        self.assertEqual(row["status"], "Released")
        self.assertEqual(row["production_companies"], ["Warner Bros. Pictures", "The Ladd Company"])
        self.assertEqual(row["cast"], ["Harrison Ford", "Rutger Hauer"])
        self.assertEqual(row["directors"], ["Ridley Scott"])
        structured = row["structured_credits"]
        self.assertEqual(len(structured), 3)
        self.assertEqual(structured[0]["tmdb_person_id"], 3)
        self.assertEqual(structured[0]["character"], "Deckard")

    def test_show_air_dates_and_networks(self) -> None:
        row: dict = {}
        _apply_tmdb_enrichment(row, SHOW_TMDB_DETAILS, media_type="show")
        self.assertEqual(row["first_air_date"], "2011-04-17")
        self.assertEqual(row["last_air_date"], "2019-05-19")
        self.assertEqual(row["networks"], ["HBO"])
        self.assertEqual(row["status"], "Ended")

    def test_row_from_plex_item_carries_enrichment(self) -> None:
        item = PlexLibraryItem(
            rating_key="78",
            media_type="movie",
            title="Blade Runner",
            year=1982,
            tmdb_id="78",
        )
        plex = MagicMock()
        plex.thumb_url.side_effect = lambda path: path or ""
        tmdb = MagicMock()
        tmdb.movie_details.return_value = MOVIE_TMDB_DETAILS
        tmdb.poster_url.side_effect = lambda path, size="w500": f"https://img/{size}{path}"
        tmdb.backdrop_url.return_value = ""
        row = _row_from_plex_item(
            item, plex=plex, tmdb=tmdb, fanart=None, in_radarr=False, in_sonarr=False
        )
        self.assertEqual(row["release_date"], "1982-06-25")
        self.assertEqual(row["tmdb_collection_id"], 10)
        self.assertIn("structured_credits", row)
        self.assertGreaterEqual(len(row["structured_credits"]), 2)

    def test_structured_credits_helper_limits(self) -> None:
        details = {
            "credits": {
                "cast": [
                    {"id": i, "name": f"Actor {i}", "character": "X", "order": i}
                    for i in range(50)
                ],
                "crew": [],
            }
        }
        out = _structured_credits_from_tmdb(details, cast_limit=5)
        self.assertEqual(len(out), 5)


class MetadataTrickleTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_trickle_backfills_missing_release_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-old",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "tmdb_id": 78,
                    "cast": ["Harrison Ford"],
                    "directors": ["Ridley Scott"],
                    "genres": ["Sci-Fi"],
                }
            )
            row = db.library_item_by_id(item_id)
            assert row is not None
            self.assertTrue(row["release_date"] is None or row["release_date"] == "")

            settings = Settings(tmdb_api_key="test-key")
            fake_tmdb = MagicMock()
            fake_tmdb.movie_details.return_value = MOVIE_TMDB_DETAILS
            fake_tmdb.poster_url.side_effect = lambda path, size="w500": f"https://img/{size}{path}"

            with patch(
                "curatorx.scheduler.tasks.metadata_enrichment.TMDBClient",
                return_value=fake_tmdb,
            ), patch(
                "curatorx.scheduler.tasks.metadata_enrichment.asyncio.sleep",
                new=AsyncMock(),
            ):
                result = await metadata_enrichment.run(db, settings, should_stop=lambda: False)

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 1)
            updated = db.library_item_by_id(item_id)
            assert updated is not None
            self.assertEqual(updated["release_date"], "1982-06-25")
            self.assertEqual(int(updated["tmdb_collection_id"]), 10)
            # Existing JSON fields preserved.
            self.assertEqual(json.loads(updated["cast"]), ["Harrison Ford"])
            self.assertEqual(json.loads(updated["genres"]), ["Sci-Fi"])
            credits = db.list_credits_for_item(item_id)
            self.assertGreaterEqual(len(credits), 2)

    async def test_trickle_skips_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            result = await metadata_enrichment.run(
                db, Settings(tmdb_api_key=""), should_stop=lambda: False
            )
            self.assertEqual(result["status"], "skipped")

    def test_task_registered(self) -> None:
        from curatorx.scheduler.engine import IdleScheduler
        from curatorx.scheduler.tasks import register_all

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            register_all(scheduler)
            names = [s["name"] for s in scheduler.get_task_states()]
            self.assertIn("metadata_enrichment", names)


if __name__ == "__main__":
    unittest.main()
