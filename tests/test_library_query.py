"""Tests for library query layer."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.library.facets import library_facet_catalog
from curatorx.library.query import (
    LibraryFilters,
    aggregate_library,
    compute_library_overview,
    filters_from_mapping,
    library_overview,
    query_library,
    refresh_library_overview_cache,
    _parse_timestamp,
)


class LibraryQueryTests(unittest.TestCase):
    def _seed_decades(self, db: Database) -> None:
        samples = [
            ("m1", "movie", "Alien", 1979, ["Horror", "Sci-Fi"]),
            ("m2", "movie", "Star Wars", 1977, ["Sci-Fi"]),
            ("m3", "movie", "The Thing", 1982, ["Horror"]),
            ("s1", "show", "Twilight Zone", 1959, ["Drama"]),
        ]
        for rating_key, media_type, title, year, genres in samples:
            db.upsert_library_item(
                {
                    "rating_key": rating_key,
                    "media_type": media_type,
                    "title": title,
                    "year": year,
                    "genres": genres,
                    "view_count": 0,
                }
            )

    def test_query_library_year_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            result = query_library(
                db,
                LibraryFilters(year_from=1970, year_to=1979, media_type="movie"),
            )
            self.assertEqual(result["total_matched"], 2)
            self.assertEqual(result["returned"], 2)
            self.assertFalse(result["has_more"])
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"Alien", "Star Wars"})

    def test_query_library_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            page1 = query_library(db, LibraryFilters(limit=2, offset=0, sort="title"))
            page2 = query_library(db, LibraryFilters(limit=2, offset=2, sort="title"))
            self.assertEqual(page1["total_matched"], 4)
            self.assertTrue(page1["has_more"])
            self.assertEqual(page1["returned"], 2)
            self.assertEqual(page2["returned"], 2)
            self.assertFalse(page2["has_more"])

    def test_aggregate_by_decade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            result = aggregate_library(db, "decade")
            buckets = {b["decade"]: b["count"] for b in result["buckets"]}
            self.assertEqual(buckets["1970s"], 2)
            self.assertEqual(buckets["1980s"], 1)

    def test_aggregate_by_genre_with_year_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            result = aggregate_library(
                db,
                "genre",
                LibraryFilters(year_from=1970, year_to=1979),
            )
            buckets = {b["genre"]: b["count"] for b in result["buckets"]}
            self.assertEqual(buckets["Sci-Fi"], 2)
            self.assertEqual(buckets["Horror"], 1)

    def test_library_overview_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            refresh_library_overview_cache(db)
            cached = library_overview(db, use_cache=True)
            self.assertEqual(cached["total"], 4)
            self.assertEqual(cached["movies"], 3)

    def test_filters_from_mapping(self) -> None:
        filters = filters_from_mapping(
            {
                "genres": "Horror, Sci-Fi",
                "year_from": 1970,
                "limit": 100,
            }
        )
        self.assertEqual(filters.genres, ["Horror", "Sci-Fi"])
        self.assertEqual(filters.year_from, 1970)
        self.assertEqual(filters.normalized_limit(), 100)

    def test_query_sort_direction_overrides_legacy_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item({"rating_key": "old", "media_type": "movie", "title": "Old", "year": 1970})
            db.upsert_library_item({"rating_key": "new", "media_type": "movie", "title": "New", "year": 2020})
            legacy = query_library(db, LibraryFilters(sort="year"))
            ascending = query_library(db, LibraryFilters(sort="year", sort_dir="asc"))
            self.assertEqual(legacy["items"][0]["title"], "New")
            self.assertEqual(ascending["items"][0]["title"], "Old")

    def test_compute_overview_decades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_decades(db)
            overview = compute_library_overview(db)
            self.assertEqual(overview["total"], 4)
            decades = {d["decade"]: d["count"] for d in overview["decades"]}
            self.assertIn("1970s", decades)

    def test_compute_overview_by_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "m1",
                    "media_type": "movie",
                    "title": "Alien",
                    "year": 1979,
                    "genres": ["Horror", "Sci-Fi"],
                    "runtime_minutes": 117,
                    "view_count": 0,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "m2",
                    "media_type": "movie",
                    "title": "Star Wars",
                    "year": 1977,
                    "genres": ["Sci-Fi"],
                    "runtime_minutes": 121,
                    "view_count": 1,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "s1",
                    "media_type": "show",
                    "title": "Twilight Zone",
                    "year": 1959,
                    "genres": ["Drama"],
                    "runtime_minutes": 30,
                    "view_count": 0,
                }
            )
            overview = compute_library_overview(db)
            self.assertEqual(overview["movies"], 2)
            self.assertEqual(overview["shows"], 1)
            self.assertEqual(overview["total_runtime_minutes"], 268)
            self.assertEqual(overview["avg_runtime_minutes"], round(268 / 3, 1))
            movie = overview["by_media_type"]["movie"]
            show = overview["by_media_type"]["show"]
            self.assertEqual(movie["count"], 2)
            self.assertEqual(movie["total_runtime_minutes"], 238)
            self.assertEqual(movie["top_genre"]["genre"], "Sci-Fi")
            self.assertEqual(movie["top_genre"]["count"], 2)
            self.assertEqual(show["count"], 1)
            self.assertEqual(show["total_runtime_minutes"], 30)
            self.assertEqual(show["top_genre"]["genre"], "Drama")
            self.assertEqual(show["top_genre"]["count"], 1)

    def test_query_runtime_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "short",
                    "media_type": "movie",
                    "title": "Short Film",
                    "year": 2020,
                    "runtime_minutes": 80,
                    "genres": ["Drama"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "long",
                    "media_type": "movie",
                    "title": "Long Film",
                    "year": 2020,
                    "runtime_minutes": 180,
                    "genres": ["Drama"],
                }
            )
            result = query_library(db, LibraryFilters(runtime_max=90))
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Short Film")

    def test_aggregate_director(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Test",
                    "directors": ["Nolan"],
                }
            )
            from curatorx.library.facets import rebuild_library_facets

            rebuild_library_facets(db)
            result = aggregate_library(db, "director")
            self.assertEqual(result["group_by"], "director")
            self.assertEqual(result["buckets"][0]["value"], "Nolan")

    def test_aggregate_country_without_facets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "us",
                    "media_type": "movie",
                    "title": "US Film",
                    "countries": ["United States of America"],
                    "original_language": "en",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fr",
                    "media_type": "movie",
                    "title": "French Film",
                    "countries": ["France"],
                    "original_language": "fr",
                }
            )
            result = aggregate_library(db, "country")
            buckets = {b["value"]: b["count"] for b in result["buckets"]}
            self.assertEqual(result["group_by"], "country")
            self.assertEqual(buckets["United States of America"], 1)
            self.assertEqual(buckets["France"], 1)

    def test_aggregate_language_without_facets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "en",
                    "media_type": "movie",
                    "title": "English Film",
                    "original_language": "en",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fr",
                    "media_type": "movie",
                    "title": "French Film",
                    "original_language": "fr",
                }
            )
            result = aggregate_library(db, "language")
            buckets = {b["value"]: b["count"] for b in result["buckets"]}
            self.assertEqual(result["group_by"], "language")
            self.assertEqual(buckets["en"], 1)
            self.assertEqual(buckets["fr"], 1)

    def test_aggregate_country_and_language_from_json_columns(self) -> None:
        """Integration: stored JSON text columns aggregate without facet index."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "multi",
                    "media_type": "movie",
                    "title": "Multi Country",
                    "countries": ["United States", "France"],
                    "original_language": "en",
                }
            )
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT countries, original_language FROM library_items WHERE rating_key = ?",
                    ("multi",),
                ).fetchone()
            self.assertEqual(row["countries"], '["United States", "France"]')
            self.assertEqual(row["original_language"], "en")

            country_result = aggregate_library(db, "country")
            language_result = aggregate_library(db, "language")
            country_buckets = {b["value"]: b["count"] for b in country_result["buckets"]}
            language_buckets = {b["value"]: b["count"] for b in language_result["buckets"]}

            self.assertGreater(country_result["total_matched"], 0)
            self.assertEqual(country_buckets["United States"], 1)
            self.assertEqual(country_buckets["France"], 1)
            self.assertGreater(language_result["total_matched"], 0)
            self.assertEqual(language_buckets["en"], 1)

            country_catalog = library_facet_catalog(db, "country", limit=10)
            language_catalog = library_facet_catalog(db, "language", limit=10)
            self.assertGreater(country_catalog["returned"], 0)
            self.assertGreater(language_catalog["returned"], 0)

    def test_query_country_filter_uses_item_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "jp",
                    "media_type": "movie",
                    "title": "Tokyo Story",
                    "countries": ["Japan"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "us",
                    "media_type": "movie",
                    "title": "Jaws",
                    "countries": ["United States of America"],
                }
            )
            result = query_library(db, LibraryFilters(countries=["Japan"], media_type="movie"))
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Tokyo Story")

    def test_upsert_preserves_country_language_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "keep",
                    "media_type": "movie",
                    "title": "Preserved",
                    "countries": ["Japan"],
                    "original_language": "ja",
                    "vote_average": 8.2,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "keep",
                    "media_type": "movie",
                    "title": "Preserved",
                    "view_count": 3,
                }
            )
            row = db.library_item_by_title("Preserved", media_type="movie")
            assert row is not None
            self.assertEqual(json.loads(row["countries"]), ["Japan"])
            self.assertEqual(row["original_language"], "ja")
            self.assertEqual(float(row["vote_average"]), 8.2)
            self.assertEqual(int(row["view_count"]), 3)

    def test_parse_timestamp_iso_and_unix(self) -> None:
        self.assertEqual(_parse_timestamp("1704067200"), 1704067200)
        parsed = _parse_timestamp("2024-01-15")
        assert parsed is not None
        end = _parse_timestamp("2024-01-15", end_of_day=True)
        assert end is not None
        self.assertGreater(end, parsed)

    def test_filters_from_mapping_recently_added_days(self) -> None:
        import time

        filters = filters_from_mapping({"recently_added_days": 7})
        assert filters.added_from is not None
        self.assertGreater(filters.added_from, int(time.time()) - 8 * 86400)

    def test_query_added_at_filter_and_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "old",
                    "media_type": "movie",
                    "title": "Old Movie",
                    "added_at": 1_700_000_000,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "new",
                    "media_type": "movie",
                    "title": "New Movie",
                    "added_at": 1_750_000_000,
                }
            )
            result = query_library(
                db,
                LibraryFilters(added_from=1_740_000_000, sort="added_at"),
            )
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "New Movie")
            self.assertEqual(result["items"][0]["added_at"], 1_750_000_000)

            sorted_result = query_library(db, LibraryFilters(sort="added_at", limit=10))
            titles = [item["title"] for item in sorted_result["items"]]
            self.assertEqual(titles[0], "New Movie")

    def test_query_recently_added_unwatched_combo(self) -> None:
        import time

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            db.upsert_library_item(
                {
                    "rating_key": "fresh",
                    "media_type": "movie",
                    "title": "Fresh Unwatched",
                    "added_at": now - 86400,
                    "view_count": 0,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fresh-watched",
                    "media_type": "movie",
                    "title": "Fresh Watched",
                    "added_at": now - 86400,
                    "view_count": 2,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "stale",
                    "media_type": "movie",
                    "title": "Stale Unwatched",
                    "added_at": now - 40 * 86400,
                    "view_count": 0,
                }
            )
            result = query_library(
                db,
                LibraryFilters(recently_added_days=7, unwatched_only=True),
            )
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Fresh Unwatched")

    def test_query_unwatched_excludes_in_progress_movies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "unwatched",
                    "media_type": "movie",
                    "title": "Unwatched",
                    "view_count": 0,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "in-progress",
                    "media_type": "movie",
                    "title": "In Progress",
                    "view_count": 0,
                    "view_offset_ms": 12_000,
                }
            )
            result = query_library(db, LibraryFilters(unwatched_only=True))
            self.assertEqual([item["title"] for item in result["items"]], ["Unwatched"])

    def test_query_missing_from_radarr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "arr",
                    "media_type": "movie",
                    "title": "In Radarr",
                    "in_radarr": True,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "no-arr",
                    "media_type": "movie",
                    "title": "Missing Radarr",
                    "in_radarr": False,
                }
            )
            result = query_library(db, LibraryFilters(media_type="movie", in_radarr=False))
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Missing Radarr")

    def test_query_file_size_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "small",
                    "media_type": "movie",
                    "title": "Small",
                    "file_size": 1_000_000_000,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "large",
                    "media_type": "movie",
                    "title": "Large",
                    "file_size": 20_000_000_000,
                }
            )
            result = query_library(db, LibraryFilters(sort="file_size", limit=5))
            self.assertEqual(result["items"][0]["title"], "Large")

    def test_query_collection_name_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "a1",
                    "media_type": "movie",
                    "title": "Alien",
                    "collection_name": "Alien Collection",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "a2",
                    "media_type": "movie",
                    "title": "Other",
                    "collection_name": "Something Else",
                }
            )
            result = query_library(
                db,
                LibraryFilters(collection_name="Alien Collection"),
            )
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Alien")
            self.assertEqual(result["items"][0]["collection_name"], "Alien Collection")

    def test_query_keywords_and_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            from curatorx.library.facets import rebuild_library_facets

            db.upsert_library_item(
                {
                    "rating_key": "both",
                    "media_type": "movie",
                    "title": "Both Tags",
                    "keywords": ["heist", "noir"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "one",
                    "media_type": "movie",
                    "title": "One Tag",
                    "keywords": ["heist"],
                }
            )
            rebuild_library_facets(db)
            both = query_library(db, LibraryFilters(keywords=["heist", "noir"]))
            titles = {item["title"] for item in both["items"]}
            self.assertEqual(titles, {"Both Tags"})

    def test_legacy_db_migrates_added_at_column_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE library_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rating_key TEXT UNIQUE,
                    media_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    year INTEGER,
                    summary TEXT DEFAULT '',
                    genres TEXT DEFAULT '[]',
                    cast TEXT DEFAULT '[]',
                    directors TEXT DEFAULT '[]',
                    keywords TEXT DEFAULT '[]',
                    tmdb_id INTEGER,
                    tvdb_id INTEGER,
                    imdb_id TEXT,
                    poster_url TEXT DEFAULT '',
                    backdrop_url TEXT DEFAULT '',
                    view_count INTEGER DEFAULT 0,
                    last_viewed_at INTEGER,
                    file_size INTEGER DEFAULT 0,
                    in_radarr INTEGER DEFAULT 0,
                    in_sonarr INTEGER DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                INSERT INTO library_items (
                    rating_key, media_type, title, updated_at
                ) VALUES ('legacy-1', 'movie', 'Legacy Title', 1.0);
                """
            )
            conn.close()

            db = Database(db_path)

            with db.connect() as migrated:
                columns = {
                    row["name"]
                    for row in migrated.execute("PRAGMA table_info(library_items)").fetchall()
                }
                indexes = {
                    row["name"]
                    for row in migrated.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    ).fetchall()
                }

            self.assertIn("added_at", columns)
            self.assertIn("idx_library_added_at", indexes)


if __name__ == "__main__":
    unittest.main()
