"""P0 value-based tests for high-risk tool methods.

Tests seed known data and verify exact output values (not just shapes)
to catch SQL logic bugs, threshold errors, and NULL handling issues.
"""

import json
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conftest import (
    BOUNDARY_RUNTIME_120,
    NULL_RATING,
    NULL_RUNTIME,
    NULL_YEAR,
    SHOW_ITEM,
    STALE_WATCHED,
    UNWATCHED_HIGH_RATED,
    UNWATCHED_LOW_RATED,
    WATCHED_HIGH_RATED,
    execute_tool,
    make_tool_registry,
    seed_library,
)
from curatorx.agent.tools import ToolRegistry
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database


# ===========================================================================
# search_library — FTS query construction, ranking, genre filter interaction
# ===========================================================================


class TestSearchLibrary(unittest.IsolatedAsyncioTestCase):
    """Test search_library tool: FTS matching, ranking, genre filtering."""

    def _make_db_with_fts(self, tmp_path: Path, items: list[dict]) -> Database:
        db = Database(tmp_path / "test.db")
        inserted = seed_library(db, items)
        for item_dict in inserted:
            row = db.library_item_by_title(item_dict["title"])
            if row:
                db.upsert_library_fts_row(
                    item_id=int(row["id"]),
                    title=item_dict["title"],
                    summary=item_dict.get("summary", ""),
                    cast_text=" ".join(item_dict.get("cast", [])),
                    directors_text=" ".join(item_dict.get("directors", [])),
                    keywords_text=" ".join(item_dict.get("keywords", [])),
                )
        return db

    @patch("curatorx.library.query.embed_text")
    async def test_fts_query_finds_exact_title_match(self, mock_embed):
        """FTS query matching title keywords returns the correct item."""
        mock_embed.side_effect = Exception("Should not use embeddings for FTS")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {"rating_key": "m1", "media_type": "movie", "title": "The Matrix", "year": 1999, "genres": ["Sci-Fi", "Action"]},
                {"rating_key": "m2", "media_type": "movie", "title": "The Godfather", "year": 1972, "genres": ["Crime", "Drama"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Matrix Reloaded", "year": 2003, "genres": ["Sci-Fi", "Action"]},
            ]
            db = self._make_db_with_fts(Path(tmp), items)
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"fts_query": "Matrix"})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"The Matrix", "Matrix Reloaded"})

    @patch("curatorx.library.query.embed_text")
    async def test_fts_with_media_type_filter(self, mock_embed):
        """FTS query combined with media_type filter narrows results."""
        mock_embed.side_effect = Exception("Should not use embeddings for FTS")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {"rating_key": "m1", "media_type": "movie", "title": "Dark Knight", "year": 2008, "genres": ["Action"]},
                {"rating_key": "s1", "media_type": "show", "title": "Dark", "year": 2017, "genres": ["Sci-Fi"]},
            ]
            db = self._make_db_with_fts(Path(tmp), items)
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"fts_query": "Dark", "media_type": "movie"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Dark Knight")

    @patch("curatorx.library.query.embed_text")
    async def test_fts_no_matches_returns_empty(self, mock_embed):
        """FTS query with no matching terms returns empty result."""
        mock_embed.side_effect = Exception("Should not use embeddings for FTS")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {"rating_key": "m1", "media_type": "movie", "title": "Inception", "year": 2010, "genres": ["Sci-Fi"]},
            ]
            db = self._make_db_with_fts(Path(tmp), items)
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"fts_query": "nonexistent_term_xyz"})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    @patch("curatorx.library.query.embed_text")
    async def test_fts_with_genre_filter_composition(self, mock_embed):
        """FTS combined with genre filter returns intersection."""
        mock_embed.side_effect = Exception("Should not use embeddings for FTS")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {"rating_key": "m1", "media_type": "movie", "title": "Space Wars", "year": 2020, "genres": ["Sci-Fi", "Action"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Space Romance", "year": 2021, "genres": ["Romance", "Sci-Fi"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Space Horror", "year": 2019, "genres": ["Horror"]},
            ]
            db = self._make_db_with_fts(Path(tmp), items)
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"fts_query": "Space", "genres": "Action"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Space Wars")

    @patch("curatorx.library.query.embed_text")
    async def test_fts_search_in_summary(self, mock_embed):
        """FTS searches summary field as well as title."""
        mock_embed.side_effect = Exception("Should not use embeddings for FTS")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            items = [
                {"rating_key": "m1", "media_type": "movie", "title": "Generic Title", "year": 2020, "genres": ["Drama"], "summary": "A story about redemption in prison"},
                {"rating_key": "m2", "media_type": "movie", "title": "Another Film", "year": 2021, "genres": ["Comedy"], "summary": "A funny comedy about cats"},
            ]
            db = self._make_db_with_fts(Path(tmp), items)
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"fts_query": "redemption"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Generic Title")


# ===========================================================================
# query_library — dynamic WHERE clause assembly and facet filtering
# ===========================================================================


class TestQueryLibrary(unittest.IsolatedAsyncioTestCase):
    """Test query_library: WHERE clause construction, filters, pagination."""

    async def test_media_type_filter(self):
        """Filtering by media_type returns only matching type."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Movie A", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Movie B", "year": 2021, "genres": ["Action"]},
                {"rating_key": "s1", "media_type": "show", "title": "Show A", "year": 2022, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 2)
            types = {item["media_type"] for item in result["items"]}
            self.assertEqual(types, {"movie"})

    async def test_year_range_filter(self):
        """Year range filter is inclusive on both ends."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Old Film", "year": 1990, "genres": ["Drama"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Mid Film", "year": 2000, "genres": ["Drama"]},
                {"rating_key": "m3", "media_type": "movie", "title": "New Film", "year": 2010, "genres": ["Drama"]},
                {"rating_key": "m4", "media_type": "movie", "title": "Newest Film", "year": 2020, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"year_from": 2000, "year_to": 2010})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"Mid Film", "New Film"})

    async def test_unwatched_only_filter(self):
        """unwatched_only=True excludes items with view_count > 0."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Watched", "year": 2020, "genres": ["Drama"], "view_count": 3},
                {"rating_key": "m2", "media_type": "movie", "title": "Unwatched", "year": 2020, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "m3", "media_type": "movie", "title": "Also Unwatched", "year": 2020, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"unwatched_only": True})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"Unwatched", "Also Unwatched"})

    async def test_genre_filter_uses_like(self):
        """Genre filter uses LIKE matching on the genres JSON column."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Action Film", "year": 2020, "genres": ["Action", "Thriller"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Drama Film", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Action Drama", "year": 2020, "genres": ["Action", "Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"genres": "Action"})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"Action Film", "Action Drama"})

    async def test_multiple_genre_filter_uses_or(self):
        """Multiple genres are OR'd — any match qualifies."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Action Film", "year": 2020, "genres": ["Action"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Horror Film", "year": 2020, "genres": ["Horror"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Drama Film", "year": 2020, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"genres": "Action, Horror"})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"Action Film", "Horror Film"})

    async def test_vote_min_filter(self):
        """vote_min filter uses >= comparison."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "High", "year": 2020, "genres": ["Drama"], "vote_average": 8.0},
                {"rating_key": "m2", "media_type": "movie", "title": "Boundary", "year": 2020, "genres": ["Drama"], "vote_average": 7.0},
                {"rating_key": "m3", "media_type": "movie", "title": "Low", "year": 2020, "genres": ["Drama"], "vote_average": 6.9},
                {"rating_key": "m4", "media_type": "movie", "title": "No Rating", "year": 2020, "genres": ["Drama"], "vote_average": None},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"vote_min": 7.0})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"High", "Boundary"})

    async def test_runtime_range_filter(self):
        """Runtime range filter is inclusive on both ends."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Short", "year": 2020, "genres": ["Drama"], "runtime_minutes": 80},
                {"rating_key": "m2", "media_type": "movie", "title": "At Min", "year": 2020, "genres": ["Drama"], "runtime_minutes": 90},
                {"rating_key": "m3", "media_type": "movie", "title": "Mid", "year": 2020, "genres": ["Drama"], "runtime_minutes": 100},
                {"rating_key": "m4", "media_type": "movie", "title": "At Max", "year": 2020, "genres": ["Drama"], "runtime_minutes": 120},
                {"rating_key": "m5", "media_type": "movie", "title": "Long", "year": 2020, "genres": ["Drama"], "runtime_minutes": 150},
                {"rating_key": "m6", "media_type": "movie", "title": "No Runtime", "year": 2020, "genres": ["Drama"], "runtime_minutes": None},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"runtime_min": 90, "runtime_max": 120})

            self.assertEqual(result["total_matched"], 3)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"At Min", "Mid", "At Max"})

    async def test_combined_filters(self):
        """Multiple filters compose with AND logic."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Perfect Match", "year": 2020, "genres": ["Action"], "vote_average": 8.0, "view_count": 0},
                {"rating_key": "m2", "media_type": "movie", "title": "Wrong Genre", "year": 2020, "genres": ["Drama"], "vote_average": 8.5, "view_count": 0},
                {"rating_key": "m3", "media_type": "movie", "title": "Already Watched", "year": 2020, "genres": ["Action"], "vote_average": 9.0, "view_count": 2},
                {"rating_key": "m4", "media_type": "movie", "title": "Low Rated", "year": 2020, "genres": ["Action"], "vote_average": 5.0, "view_count": 0},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {
                "genres": "Action",
                "vote_min": 7.0,
                "unwatched_only": True,
            })

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Perfect Match")

    async def test_pagination_offset_limit(self):
        """Pagination via offset/limit returns correct page."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": f"m{i}", "media_type": "movie", "title": f"Film {i:02d}", "year": 2020, "genres": ["Drama"]}
                for i in range(10)
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"limit": 3, "offset": 3, "sort": "title"})

            self.assertEqual(result["total_matched"], 10)
            self.assertEqual(result["returned"], 3)
            self.assertEqual(result["offset"], 3)
            self.assertTrue(result["has_more"])

    async def test_null_year_items_included_without_year_filter(self):
        """Items with NULL year are included when no year filter is active."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Has Year", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "m2", "media_type": "movie", "title": "No Year", "year": None, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 2)

    async def test_null_year_excluded_by_year_filter(self):
        """Items with NULL year are excluded when year_from is set."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Has Year", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "m2", "media_type": "movie", "title": "No Year", "year": None, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"year_from": 2000})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Has Year")

    async def test_empty_library_returns_zero(self):
        """Empty library returns total_matched=0."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"genres": "Action"})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])


# ===========================================================================
# recommend_hidden_gems — rating thresholds, exclusion of owned, NULL handling
# ===========================================================================


class TestRecommendHiddenGems(unittest.IsolatedAsyncioTestCase):
    """Test recommend_hidden_gems: rating filter, owned exclusion, queue exclusion."""

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_excludes_owned_titles(self, mock_tmdb_cls):
        """Items already in library are excluded from recommendations."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 100, "title": "Owned Film", "vote_average": 8.5, "release_date": "2020-01-01"},
            {"id": 200, "title": "Not Owned Film", "vote_average": 8.0, "release_date": "2021-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "owned", "media_type": "movie", "title": "Owned Film", "tmdb_id": 100, "year": 2020, "genres": ["Drama"]},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Not Owned Film")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_filters_below_7_rating(self, mock_tmdb_cls):
        """Items with vote_average < 7.0 are excluded."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 1, "title": "High Rated", "vote_average": 8.5, "release_date": "2020-01-01"},
            {"id": 2, "title": "Exactly 7", "vote_average": 7.0, "release_date": "2021-01-01"},
            {"id": 3, "title": "Below 7", "vote_average": 6.9, "release_date": "2022-01-01"},
            {"id": 4, "title": "Zero Rating", "vote_average": 0, "release_date": "2023-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"High Rated", "Exactly 7"})

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_excludes_items_in_radarr_queue(self, mock_tmdb_cls):
        """Items already queued in Radarr are excluded."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 300, "title": "Queued Film", "vote_average": 8.0, "release_date": "2020-01-01"},
            {"id": 301, "title": "Not Queued Film", "vote_average": 7.5, "release_date": "2021-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=300, title="Queued Film")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Not Queued Film")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_no_tmdb_key_returns_error(self, mock_tmdb_cls):
        """Missing TMDB key returns error."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db, tmdb_api_key="")
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertIn("error", result)
            self.assertIn("TMDB", result["error"])

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_null_vote_average_treated_as_zero(self, mock_tmdb_cls):
        """Items with null/missing vote_average are treated as 0 (excluded)."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 1, "title": "No Rating", "vote_average": None, "release_date": "2020-01-01"},
            {"id": 2, "title": "Good Rating", "vote_average": 7.5, "release_date": "2020-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Good Rating")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_empty_tmdb_results(self, mock_tmdb_cls):
        """Empty TMDB results return empty items list."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = []
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_max_10_results(self, mock_tmdb_cls):
        """At most 10 recommendations are returned."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": i, "title": f"Film {i}", "vote_average": 8.0, "release_date": "2020-01-01"}
            for i in range(1, 20)
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "recommend_hidden_gems", {"media_type": "movie"})

            self.assertEqual(result["total_matched"], 10)
            self.assertEqual(result["returned"], 10)


# ===========================================================================
# suggest_purge_candidates — multi-criteria scoring
# ===========================================================================


class TestSuggestPurgeCandidates(unittest.IsolatedAsyncioTestCase):
    """Test purge candidates: file size, staleness, view count, taste matching."""

    async def test_excludes_small_files(self):
        """Files below 500MB are excluded from purge candidates."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "small", "media_type": "movie", "title": "Small File", "year": 2020, "genres": ["Drama"], "file_size": 400_000_000, "view_count": 0},
                {"rating_key": "big", "media_type": "movie", "title": "Big File", "year": 2020, "genres": ["Drama"], "file_size": 600_000_000, "view_count": 0},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            titles = {item["title"] for item in result["items"]}
            self.assertNotIn("Small File", titles)
            self.assertIn("Big File", titles)

    async def test_excludes_highly_watched(self):
        """Items with view_count > 2 are excluded."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "popular", "media_type": "movie", "title": "Popular Film", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 3},
                {"rating_key": "unpopular", "media_type": "movie", "title": "Unpopular Film", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 1},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            titles = {item["title"] for item in result["items"]}
            self.assertNotIn("Popular Film", titles)
            self.assertIn("Unpopular Film", titles)

    async def test_view_count_boundary_at_2(self):
        """Items with exactly view_count=2 are included; view_count=3 excluded."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "at_2", "media_type": "movie", "title": "Watched Twice", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 2},
                {"rating_key": "at_3", "media_type": "movie", "title": "Watched Thrice", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 3},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Watched Twice", titles)
            self.assertNotIn("Watched Thrice", titles)

    async def test_stale_items_score_higher(self):
        """Stale items (never watched or last viewed long ago) rank higher."""
        import tempfile
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "stale", "media_type": "movie", "title": "Very Stale", "year": 2005, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 1, "last_viewed_at": now - (5 * 365 * 86400)},
                {"rating_key": "fresh", "media_type": "movie", "title": "Recently Viewed", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 1, "last_viewed_at": now - 86400},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(result["items"][0]["title"], "Very Stale")

    async def test_never_watched_scores_as_5_years_stale(self):
        """Items with view_count=0 and no last_viewed_at get 5.0 stale_years."""
        import tempfile
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "never", "media_type": "movie", "title": "Never Watched", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 0, "last_viewed_at": None},
                {"rating_key": "recent", "media_type": "movie", "title": "Recently Viewed", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 1, "last_viewed_at": now - (2 * 365 * 86400)},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            self.assertEqual(result["items"][0]["title"], "Never Watched")

    async def test_empty_library_returns_no_candidates(self):
        """Empty library returns zero candidates."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    async def test_larger_files_score_higher(self):
        """Larger files rank higher in purge scoring (all else being equal)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "huge", "media_type": "movie", "title": "Huge File", "year": 2020, "genres": ["Drama"], "file_size": 10_000_000_000, "view_count": 0},
                {"rating_key": "medium", "media_type": "movie", "title": "Medium File", "year": 2020, "genres": ["Drama"], "file_size": 1_000_000_000, "view_count": 0},
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 10})

            self.assertEqual(result["items"][0]["title"], "Huge File")

    async def test_limit_parameter_respected(self):
        """limit parameter caps the number of returned candidates."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": f"m{i}", "media_type": "movie", "title": f"Film {i}", "year": 2020, "genres": ["Drama"], "file_size": 2_000_000_000, "view_count": 0}
                for i in range(10)
            ])
            registry = make_tool_registry(db, tautulli_url="", tautulli_api_key="")
            result = await execute_tool(registry, "suggest_purge_candidates", {"limit": 3})

            self.assertEqual(result["returned"], 3)


# ===========================================================================
# what_to_watch_tonight — preference weighting, unwatched filter, runtime caps
# ===========================================================================


class TestWhatToWatchTonight(unittest.IsolatedAsyncioTestCase):
    """Test what_to_watch_tonight: scoring logic without mood (direct DB path)."""

    async def test_excludes_view_count_above_2(self):
        """Items with view_count > 2 are excluded."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "v0", "media_type": "movie", "title": "Never Watched", "year": 2020, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "v1", "media_type": "movie", "title": "Once", "year": 2020, "genres": ["Action"], "view_count": 1},
                {"rating_key": "v2", "media_type": "movie", "title": "Twice", "year": 2020, "genres": ["Thriller"], "view_count": 2},
                {"rating_key": "v3", "media_type": "movie", "title": "Three Times", "year": 2020, "genres": ["Comedy"], "view_count": 3},
                {"rating_key": "v5", "media_type": "movie", "title": "Five Times", "year": 2020, "genres": ["Horror"], "view_count": 5},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 10})

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Never Watched", titles)
            self.assertIn("Once", titles)
            self.assertIn("Twice", titles)
            self.assertNotIn("Three Times", titles)
            self.assertNotIn("Five Times", titles)

    async def test_unwatched_items_ranked_higher(self):
        """Items with lower view_count score higher (unwatched > watched once > twice)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "v0", "media_type": "movie", "title": "Unwatched", "year": 2020, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "v1", "media_type": "movie", "title": "Watched Once", "year": 2020, "genres": ["Action"], "view_count": 1},
                {"rating_key": "v2", "media_type": "movie", "title": "Watched Twice", "year": 2020, "genres": ["Thriller"], "view_count": 2},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 10})

            titles = [item["title"] for item in result["items"]]
            self.assertEqual(titles[0], "Unwatched")

    async def test_media_type_filter(self):
        """media_type filter restricts to only that type."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Movie A", "year": 2020, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "s1", "media_type": "show", "title": "Show A", "year": 2020, "genres": ["Drama"], "view_count": 0},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"media_type": "movie", "limit": 10})

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Movie A", titles)
            self.assertNotIn("Show A", titles)

    async def test_last_viewed_at_penalty(self):
        """Items with last_viewed_at get a -2 penalty compared to those without."""
        import tempfile
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "no_lv", "media_type": "movie", "title": "No Last Viewed", "year": 2020, "genres": ["Drama"], "view_count": 1, "last_viewed_at": None},
                {"rating_key": "has_lv", "media_type": "movie", "title": "Has Last Viewed", "year": 2020, "genres": ["Drama"], "view_count": 1, "last_viewed_at": now - 100},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 10})

            titles = [item["title"] for item in result["items"]]
            self.assertEqual(titles[0], "No Last Viewed")

    async def test_limit_parameter(self):
        """limit parameter caps results."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": f"m{i}", "media_type": "movie", "title": f"Film {i}", "year": 2020, "genres": ["Drama"], "view_count": 0}
                for i in range(20)
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 5})

            self.assertEqual(result["returned"], 5)

    async def test_empty_library(self):
        """Empty library returns zero items."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 5})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    async def test_all_items_over_threshold(self):
        """Library where all items have view_count > 2 returns empty."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Watched A", "year": 2020, "genres": ["Drama"], "view_count": 5},
                {"rating_key": "m2", "media_type": "movie", "title": "Watched B", "year": 2020, "genres": ["Action"], "view_count": 10},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"limit": 10})

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    @patch("curatorx.agent.tools.search_library")
    async def test_mood_path_calls_search_library(self, mock_search):
        """When mood is provided, search_library is used instead of direct DB query."""
        from curatorx.models.schemas import TitleCard

        mock_card = TitleCard(
            media_type="movie",
            title="Mood Match",
            year=2020,
            tmdb_id=123,
            rating_key="mood1",
            poster_url="",
            backdrop_url="",
            overview="",
            genres=["Drama"],
            in_library=True,
        )
        mock_search.return_value = [mock_card]

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "what_to_watch_tonight", {"mood": "dark thriller", "limit": 5})

            mock_search.assert_called_once()
            call_args = mock_search.call_args
            self.assertEqual(call_args[0][2], "dark thriller")
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Mood Match")


# ===========================================================================
# Integration: query_library sort and stale_days
# ===========================================================================


class TestQueryLibraryAdvanced(unittest.IsolatedAsyncioTestCase):
    """Advanced query_library tests: sorting, stale_days, file_size filters."""

    async def test_sort_by_vote_average(self):
        """Sorting by vote_average returns highest first."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Low", "year": 2020, "genres": ["Drama"], "vote_average": 5.0},
                {"rating_key": "m2", "media_type": "movie", "title": "High", "year": 2020, "genres": ["Drama"], "vote_average": 9.0},
                {"rating_key": "m3", "media_type": "movie", "title": "Mid", "year": 2020, "genres": ["Drama"], "vote_average": 7.0},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"sort": "vote_average"})

            titles = [item["title"] for item in result["items"]]
            self.assertEqual(titles, ["High", "Mid", "Low"])

    async def test_stale_days_filter(self):
        """stale_days filters items not viewed within N days (or never viewed)."""
        import tempfile
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "stale", "media_type": "movie", "title": "Stale", "year": 2020, "genres": ["Drama"], "last_viewed_at": now - (400 * 86400)},
                {"rating_key": "fresh", "media_type": "movie", "title": "Fresh", "year": 2020, "genres": ["Drama"], "last_viewed_at": now - (10 * 86400)},
                {"rating_key": "never", "media_type": "movie", "title": "Never", "year": 2020, "genres": ["Drama"], "last_viewed_at": None},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"stale_days": 365})

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Stale", titles)
            self.assertIn("Never", titles)
            self.assertNotIn("Fresh", titles)

    async def test_query_text_filter_title_and_summary(self):
        """query filter uses LIKE on title and summary."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "The Matrix", "year": 1999, "genres": ["Sci-Fi"], "summary": "A computer hacker..."},
                {"rating_key": "m2", "media_type": "movie", "title": "Hackers", "year": 1995, "genres": ["Thriller"], "summary": "A group of hackers conspire..."},
                {"rating_key": "m3", "media_type": "movie", "title": "Unrelated", "year": 2020, "genres": ["Drama"], "summary": "A love story."},
            ])
            registry = make_tool_registry(db)
            result = await execute_tool(registry, "query_library", {"query": "hacker"})

            self.assertEqual(result["total_matched"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertEqual(titles, {"The Matrix", "Hackers"})


if __name__ == "__main__":
    unittest.main()
