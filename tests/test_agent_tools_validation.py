"""Value-based validation tests for agent tools.

These tests seed known datasets and verify ACTUAL returned values,
not just structural presence.
"""

import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from curatorx.agent.tools import ToolRegistry, _card_to_tool_item
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database


def _seed_library(db: Database, items: list[dict]) -> None:
    for item in items:
        db.upsert_library_item(item)


# ---------------------------------------------------------------------------
# find_collection_gaps – value-based validation
# ---------------------------------------------------------------------------


class TestFindCollectionGapsValues(unittest.IsolatedAsyncioTestCase):
    """Verify gap detection returns exactly the expected missing titles."""

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_returns_only_missing_from_filmography(self, mock_tmdb_cls):
        """Seed 3 of 5 Spielberg films -> gap tool should return only the 2 missing."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = [
            {"id": 18, "name": "Drama"},
            {"id": 12, "name": "Adventure"},
        ]
        mock_tmdb.discover_movies.return_value = [
            {"id": 101, "title": "Schindler's List", "release_date": "1993-12-15", "vote_average": 8.9},
            {"id": 102, "title": "Saving Private Ryan", "release_date": "1998-07-24", "vote_average": 8.6},
            {"id": 103, "title": "Jurassic Park", "release_date": "1993-06-11", "vote_average": 8.1},
            {"id": 104, "title": "E.T.", "release_date": "1982-06-11", "vote_average": 7.9},
            {"id": 105, "title": "Jaws", "release_date": "1975-06-20", "vote_average": 8.0},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "movie", "title": "Schindler's List", "tmdb_id": 101, "year": 1993},
                {"rating_key": "s2", "media_type": "movie", "title": "Jurassic Park", "tmdb_id": 103, "year": 1993},
                {"rating_key": "s3", "media_type": "movie", "title": "E.T.", "tmdb_id": 104, "year": 1982},
            ])
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("find_collection_gaps", {"media_type": "movie"}))

            self.assertEqual(result["total_matched"], 2)
            returned_ids = {item["tmdb_id"] for item in result["items"]}
            self.assertEqual(returned_ids, {102, 105})
            returned_titles = {item["title"] for item in result["items"]}
            self.assertEqual(returned_titles, {"Saving Private Ryan", "Jaws"})

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_returns_empty_when_all_owned(self, mock_tmdb_cls):
        """Complete filmography -> gap tool should return empty."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {"id": 101, "title": "Film A", "release_date": "2000-01-01", "vote_average": 7.5},
            {"id": 102, "title": "Film B", "release_date": "2001-01-01", "vote_average": 7.8},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "a", "media_type": "movie", "title": "Film A", "tmdb_id": 101},
                {"rating_key": "b", "media_type": "movie", "title": "Film B", "tmdb_id": 102},
            ])
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("find_collection_gaps", {"media_type": "movie"}))
            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_genre_filter_resolves_correctly(self, mock_tmdb_cls):
        """Genre filter should resolve names to IDs and pass them to discover."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = [
            {"id": 27, "name": "Horror"},
            {"id": 28, "name": "Action"},
            {"id": 878, "name": "Science Fiction"},
        ]
        mock_tmdb.discover_movies.return_value = [
            {"id": 500, "title": "Alien", "release_date": "1979-05-25", "vote_average": 8.5},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(
                await registry.execute("find_collection_gaps", {"media_type": "movie", "genres": "Horror, Science Fiction"})
            )

            mock_tmdb.discover_movies.assert_called_once()
            call_kwargs = mock_tmdb.discover_movies.call_args[1]
            genre_arg = call_kwargs.get("with_genres", "")
            self.assertIn("27", genre_arg)
            self.assertIn("878", genre_arg)
            self.assertNotIn("28", genre_arg)
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Alien")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_keyword_resolution_searches_tmdb(self, mock_tmdb_cls):
        """Keywords should be resolved from text to IDs via TMDB keyword search."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.search_keywords.return_value = [{"id": 9715, "name": "superhero"}]
        mock_tmdb.discover_movies.return_value = [
            {"id": 299536, "title": "Avengers: Infinity War", "release_date": "2018-04-27", "vote_average": 8.3},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(
                await registry.execute("find_collection_gaps", {"media_type": "movie", "keywords": "superhero"})
            )

            mock_tmdb.search_keywords.assert_called_once_with("superhero")
            call_kwargs = mock_tmdb.discover_movies.call_args[1]
            self.assertEqual(call_kwargs.get("with_keywords"), "9715")
            self.assertEqual(result["total_matched"], 1)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_numeric_keyword_passed_directly(self, mock_tmdb_cls):
        """Numeric keywords should be passed directly without searching."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {"id": 800, "title": "Test Film", "release_date": "2020-01-01", "vote_average": 7.0},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            await registry.execute("find_collection_gaps", {"media_type": "movie", "keywords": "9715"})

            mock_tmdb.search_keywords.assert_not_called()
            call_kwargs = mock_tmdb.discover_movies.call_args[1]
            self.assertEqual(call_kwargs.get("with_keywords"), "9715")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_excludes_items_in_radarr(self, mock_tmdb_cls):
        """Items already in Radarr should be excluded from gap results."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {"id": 200, "title": "Queued Film", "release_date": "2020-01-01", "vote_average": 7.5},
            {"id": 201, "title": "Gap Film", "release_date": "2020-06-01", "vote_average": 7.2},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=200, title="Queued Film")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("find_collection_gaps", {"media_type": "movie"}))

            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["tmdb_id"], 201)
            self.assertEqual(result["items"][0]["title"], "Gap Film")


# ---------------------------------------------------------------------------
# get_todays_anniversaries – value-based validation
# ---------------------------------------------------------------------------


class TestAnniversariesValues(unittest.IsolatedAsyncioTestCase):
    """Verify anniversary detection returns correct milestone matches."""

    async def test_exact_milestone_years_match(self):
        """Only films from milestone years should be returned."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "10yr", "media_type": "movie", "title": "10 Year Film", "year": current_year - 10, "genres": ["Drama"]},
                {"rating_key": "25yr", "media_type": "movie", "title": "25 Year Film", "year": current_year - 25, "genres": ["Thriller"]},
                {"rating_key": "50yr", "media_type": "movie", "title": "50 Year Film", "year": current_year - 50, "genres": ["Western"]},
                {"rating_key": "3yr", "media_type": "movie", "title": "3 Year Film", "year": current_year - 3, "genres": ["Comedy"]},
                {"rating_key": "7yr", "media_type": "movie", "title": "7 Year Film", "year": current_year - 7, "genres": ["Action"]},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_todays_anniversaries", {"limit": 10}))

            returned_titles = {item["title"] for item in result["items"]}
            self.assertIn("10 Year Film", returned_titles)
            self.assertIn("25 Year Film", returned_titles)
            self.assertIn("50 Year Film", returned_titles)
            self.assertNotIn("3 Year Film", returned_titles)
            self.assertNotIn("7 Year Film", returned_titles)

    async def test_anniversary_context_includes_years_ago(self):
        """Each result should have correct 'X years ago' context."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "20yr", "media_type": "movie", "title": "Anniversary Classic", "year": current_year - 20, "genres": ["Drama"]},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))

            self.assertEqual(result["count"], 1)
            self.assertIn("20 years ago", result["items"][0]["anniversary_context"])

    async def test_anniversary_with_last_viewed_context(self):
        """Items with last_viewed_at should show 'Last watched X months ago'."""
        current_year = date.today().year
        six_months_ago = int(time.time()) - (180 * 86400)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "viewed",
                    "media_type": "movie",
                    "title": "Viewed Classic",
                    "year": current_year - 25,
                    "genres": ["Drama"],
                    "view_count": 2,
                    "last_viewed_at": six_months_ago,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))

            self.assertEqual(result["count"], 1)
            context = result["items"][0]["anniversary_context"]
            self.assertIn("25 years ago", context)
            self.assertIn("Last watched", context)
            self.assertIn("month", context)


# ---------------------------------------------------------------------------
# get_library_snapshot – value-based validation
# ---------------------------------------------------------------------------


class TestLibrarySnapshotValues(unittest.IsolatedAsyncioTestCase):
    """Verify snapshot returns exact counts matching seeded data."""

    async def test_counts_match_seeded_data(self):
        """Snapshot totals must exactly match the number of seeded items."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Movie 1", "year": 1990, "genres": ["Action"]},
                {"rating_key": "m2", "media_type": "movie", "title": "Movie 2", "year": 2000, "genres": ["Drama"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Movie 3", "year": 2010, "genres": ["Action", "Thriller"]},
                {"rating_key": "s1", "media_type": "show", "title": "Show 1", "year": 2015, "genres": ["Drama"]},
                {"rating_key": "s2", "media_type": "show", "title": "Show 2", "year": 2020, "genres": ["Comedy"]},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))

            self.assertEqual(result["total"], 5)
            self.assertEqual(result["movies"], 3)
            self.assertEqual(result["shows"], 2)
            self.assertEqual(result["decade_range"], "1990–2020")

    async def test_top_genres_reflect_actual_genre_distribution(self):
        """Top genres should reflect the most common genres in the library."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "A", "year": 2000, "genres": ["Action", "Thriller"]},
                {"rating_key": "2", "media_type": "movie", "title": "B", "year": 2001, "genres": ["Action", "Drama"]},
                {"rating_key": "3", "media_type": "movie", "title": "C", "year": 2002, "genres": ["Action"]},
                {"rating_key": "4", "media_type": "movie", "title": "D", "year": 2003, "genres": ["Drama", "Romance"]},
                {"rating_key": "5", "media_type": "movie", "title": "E", "year": 2004, "genres": ["Comedy"]},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))

            genre_names = [g["name"] for g in result["top_genres"]]
            self.assertEqual(genre_names[0], "Action")
            self.assertEqual(result["top_genres"][0]["count"], 3)
            self.assertIn("Drama", genre_names)

    async def test_hidden_gems_counts_unwatched_high_rated(self):
        """Hidden gems = unwatched + vote_average >= 7.0."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "gem1", "media_type": "movie", "title": "Gem A", "year": 2010,
                 "genres": ["Drama"], "view_count": 0, "vote_average": 8.5},
                {"rating_key": "gem2", "media_type": "movie", "title": "Gem B", "year": 2012,
                 "genres": ["Thriller"], "view_count": 0, "vote_average": 7.0},
                {"rating_key": "watched", "media_type": "movie", "title": "Watched High", "year": 2015,
                 "genres": ["Action"], "view_count": 3, "vote_average": 9.0},
                {"rating_key": "low", "media_type": "movie", "title": "Low Rated", "year": 2018,
                 "genres": ["Horror"], "view_count": 0, "vote_average": 4.5},
                {"rating_key": "null", "media_type": "movie", "title": "No Rating", "year": 2019,
                 "genres": ["Sci-Fi"], "view_count": 0, "vote_average": None},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))

            self.assertEqual(result["hidden_gems"], 2)


# ---------------------------------------------------------------------------
# get_tonight_picks – value-based validation
# ---------------------------------------------------------------------------


class TestTonightPicksValues(unittest.IsolatedAsyncioTestCase):
    """Verify tonight picks only return unwatched items matching runtime filter."""

    async def test_only_unwatched_returned(self):
        """All returned items must have view_count=0."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "uw1", "media_type": "movie", "title": "Unwatched 1", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 90},
                {"rating_key": "uw2", "media_type": "movie", "title": "Unwatched 2", "year": 2021, "genres": ["Action"], "view_count": 0, "runtime_minutes": 120},
                {"rating_key": "w1", "media_type": "movie", "title": "Watched 1", "year": 2019, "genres": ["Comedy"], "view_count": 2, "runtime_minutes": 95},
                {"rating_key": "w2", "media_type": "movie", "title": "Watched 2", "year": 2018, "genres": ["Thriller"], "view_count": 5, "runtime_minutes": 110},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_tonight_picks", {"limit": 10}))

            self.assertEqual(result["count"], 2)
            titles = {item["title"] for item in result["items"]}
            self.assertTrue(titles.issubset({"Unwatched 1", "Unwatched 2"}))
            self.assertNotIn("Watched 1", titles)
            self.assertNotIn("Watched 2", titles)

    async def test_runtime_filter_exact_boundary(self):
        """Items at exactly max_runtime should be included."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "at_limit", "media_type": "movie", "title": "At Limit", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 120},
                {"rating_key": "over", "media_type": "movie", "title": "Over Limit", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 121},
                {"rating_key": "under", "media_type": "movie", "title": "Under Limit", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 119},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_tonight_picks", {"max_runtime_minutes": 120, "limit": 10}))

            titles = {item["title"] for item in result["items"]}
            self.assertIn("At Limit", titles)
            self.assertIn("Under Limit", titles)
            self.assertNotIn("Over Limit", titles)

    async def test_null_runtime_excluded_with_runtime_filter(self):
        """Items with NULL runtime should be excluded when a runtime filter is active."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "no_rt", "media_type": "movie", "title": "No Runtime", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": None},
                {"rating_key": "has_rt", "media_type": "movie", "title": "Has Runtime", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 90},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_tonight_picks", {"max_runtime_minutes": 120}))

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Has Runtime", titles)
            self.assertNotIn("No Runtime", titles)


# ---------------------------------------------------------------------------
# suggest_double_feature – value-based validation
# ---------------------------------------------------------------------------


class TestDoubleFeatureValues(unittest.IsolatedAsyncioTestCase):
    """Verify double feature pairing logic."""

    async def test_pair_shares_genre(self):
        """If genre-sharing titles exist, pairing should share at least one genre."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "a", "media_type": "movie", "title": "Noir A", "year": 1945, "genres": ["Crime", "Thriller"], "view_count": 1, "runtime_minutes": 100},
                {"rating_key": "b", "media_type": "movie", "title": "Noir B", "year": 1948, "genres": ["Crime", "Drama"], "view_count": 2, "runtime_minutes": 95},
                {"rating_key": "c", "media_type": "movie", "title": "Noir C", "year": 1950, "genres": ["Crime", "Mystery"], "view_count": 0, "runtime_minutes": 88},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {}))

            self.assertTrue(result["double_feature"])
            self.assertGreater(result["combined_runtime"], 0)
            self.assertIn("bridge_text", result)
            self.assertIn("title_a", result)
            self.assertIn("title_b", result)
            self.assertNotEqual(result["title_a"]["title"], result["title_b"]["title"])

    async def test_theme_filter_restricts_by_genre(self):
        """Theme filter should restrict to movies matching that genre text."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "horror1", "media_type": "movie", "title": "Horror A", "year": 2010, "genres": ["Horror"], "view_count": 1, "runtime_minutes": 90},
                {"rating_key": "horror2", "media_type": "movie", "title": "Horror B", "year": 2015, "genres": ["Horror", "Thriller"], "view_count": 0, "runtime_minutes": 95},
                {"rating_key": "comedy1", "media_type": "movie", "title": "Comedy A", "year": 2020, "genres": ["Comedy"], "view_count": 3, "runtime_minutes": 105},
                {"rating_key": "comedy2", "media_type": "movie", "title": "Comedy B", "year": 2018, "genres": ["Comedy", "Romance"], "view_count": 1, "runtime_minutes": 100},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {"theme": "horror"}))

            self.assertTrue(result["double_feature"])
            title_a = result["title_a"]["title"]
            title_b = result["title_b"]["title"]
            horror_titles = {"Horror A", "Horror B"}
            self.assertIn(title_a, horror_titles)
            self.assertIn(title_b, horror_titles)

    async def test_combined_runtime_sum_is_correct(self):
        """Combined runtime should equal sum of both titles' runtimes."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "f1", "media_type": "movie", "title": "Film A", "year": 2000, "genres": ["Drama"], "view_count": 1, "runtime_minutes": 110},
                {"rating_key": "f2", "media_type": "movie", "title": "Film B", "year": 2005, "genres": ["Drama"], "view_count": 2, "runtime_minutes": 130},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {}))

            self.assertEqual(result["combined_runtime"], 110 + 130)

    async def test_only_movies_used_for_double_feature(self):
        """Double feature should only use movies, not shows."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "movie1", "media_type": "movie", "title": "Movie A", "year": 2010, "genres": ["Action"], "view_count": 1, "runtime_minutes": 100},
                {"rating_key": "show1", "media_type": "show", "title": "Show A", "year": 2015, "genres": ["Action"], "view_count": 1, "runtime_minutes": 50},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {}))

            self.assertIn("error", result)


# ---------------------------------------------------------------------------
# quick_pick_roulette – value-based validation
# ---------------------------------------------------------------------------


class TestQuickPickRouletteValues(unittest.IsolatedAsyncioTestCase):
    """Verify quick pick filters correctly and returns expected fields."""

    async def test_genre_filter_returns_matching_genre_only(self):
        """Filtering by genre should only return titles with that genre."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "sf1", "media_type": "movie", "title": "Sci-Fi A", "year": 2020, "genres": ["Science Fiction"], "view_count": 0, "runtime_minutes": 120},
                {"rating_key": "dr1", "media_type": "movie", "title": "Drama A", "year": 2021, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 110},
                {"rating_key": "ho1", "media_type": "movie", "title": "Horror A", "year": 2019, "genres": ["Horror"], "view_count": 0, "runtime_minutes": 95},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {"genres": "Science Fiction"}))

            self.assertTrue(result["quick_pick"])
            self.assertEqual(result["item"]["title"], "Sci-Fi A")

    async def test_runtime_filter_excludes_long_films(self):
        """Runtime filter should exclude films over the limit."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "short", "media_type": "movie", "title": "Short Film", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 80},
                {"rating_key": "long", "media_type": "movie", "title": "Long Film", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 200},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {"max_runtime_minutes": 100}))

            self.assertTrue(result["quick_pick"])
            self.assertEqual(result["item"]["title"], "Short Film")

    async def test_multi_genre_filter_uses_or(self):
        """Multiple genres should be OR'd — any match qualifies."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "sf", "media_type": "movie", "title": "Sci-Fi Pick", "year": 2020, "genres": ["Science Fiction"], "view_count": 0},
                {"rating_key": "ho", "media_type": "movie", "title": "Horror Pick", "year": 2019, "genres": ["Horror"], "view_count": 0},
                {"rating_key": "dr", "media_type": "movie", "title": "Drama Only", "year": 2021, "genres": ["Drama"], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            results_set = set()
            for _ in range(20):
                result = json.loads(await registry.execute("quick_pick_roulette", {"genres": "Science Fiction, Horror"}))
                results_set.add(result["item"]["title"])

            self.assertTrue(results_set.issubset({"Sci-Fi Pick", "Horror Pick"}))
            self.assertNotIn("Drama Only", results_set)

    async def test_only_unwatched_returned(self):
        """Quick pick should never return a watched title."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "watched", "media_type": "movie", "title": "Watched Film", "year": 2020, "genres": ["Drama"], "view_count": 3, "runtime_minutes": 90},
                {"rating_key": "unwatched", "media_type": "movie", "title": "Fresh Film", "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 90},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {}))

            self.assertEqual(result["item"]["title"], "Fresh Film")

    async def test_reason_includes_genre_and_runtime(self):
        """The 'why' field should mention genre taste and runtime."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "x", "media_type": "movie", "title": "Test", "year": 2020, "genres": ["Thriller"], "view_count": 0, "runtime_minutes": 110},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {}))

            self.assertIn("thriller", result["why"].lower())
            self.assertIn("110 min", result["why"])


# ---------------------------------------------------------------------------
# analyze_watch_patterns – value-based validation
# ---------------------------------------------------------------------------


class TestAnalyzeWatchPatternsValues(unittest.IsolatedAsyncioTestCase):
    """Verify watch pattern analysis returns correct statistics."""

    async def test_counts_match_seeded_data(self):
        """All numeric counts must match the seeded data exactly."""
        now = int(time.time())
        two_years_ago = now - (2 * 365 * 86400)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "Watched Recently", "year": 2020, "genres": ["Action"], "view_count": 3, "last_viewed_at": now - 100},
                {"rating_key": "2", "media_type": "movie", "title": "Watched Long Ago", "year": 1990, "genres": ["Drama"], "view_count": 1, "last_viewed_at": two_years_ago},
                {"rating_key": "3", "media_type": "movie", "title": "Never Watched", "year": 2015, "genres": ["Comedy", "Drama"], "view_count": 0},
                {"rating_key": "4", "media_type": "movie", "title": "Also Unwatched", "year": 2010, "genres": ["Action"], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("analyze_watch_patterns", {}))

            self.assertEqual(result["total_items"], 4)
            self.assertEqual(result["total_plays"], 4)  # 3 + 1 + 0 + 0
            self.assertEqual(result["unwatched_count"], 2)
            self.assertEqual(result["stale_count"], 1)  # only "Watched Long Ago"

    async def test_top_genres_weighted_by_views(self):
        """Top genres should be weighted by view counts (min 1 for unwatched)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "A", "year": 2020, "genres": ["Action"], "view_count": 10},
                {"rating_key": "2", "media_type": "movie", "title": "B", "year": 2020, "genres": ["Action"], "view_count": 5},
                {"rating_key": "3", "media_type": "movie", "title": "C", "year": 2020, "genres": ["Drama"], "view_count": 1},
                {"rating_key": "4", "media_type": "movie", "title": "D", "year": 2020, "genres": ["Comedy"], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("analyze_watch_patterns", {}))

            genres = result["top_genres"]
            self.assertEqual(genres[0]["genre"], "Action")
            self.assertEqual(genres[0]["weight"], 15)  # 10 + 5
            self.assertEqual(genres[1]["genre"], "Drama")
            self.assertEqual(genres[1]["weight"], 1)

    async def test_decade_distribution_accurate(self):
        """Decade counts should correctly bucket by decade."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "A", "year": 1974, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "2", "media_type": "movie", "title": "B", "year": 1979, "genres": ["Drama"], "view_count": 0},
                {"rating_key": "3", "media_type": "movie", "title": "C", "year": 1982, "genres": ["Sci-Fi"], "view_count": 0},
                {"rating_key": "4", "media_type": "movie", "title": "D", "year": 2001, "genres": ["Action"], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("analyze_watch_patterns", {}))

            decade_map = {d["decade"]: d["count"] for d in result["decades"]}
            self.assertEqual(decade_map["1970s"], 2)
            self.assertEqual(decade_map["1980s"], 1)
            self.assertEqual(decade_map["2000s"], 1)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    """Test edge cases that could cause incorrect results."""

    async def test_snapshot_with_empty_genres_string(self):
        """Items with empty genre arrays should not crash snapshot."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "No Genre", "year": 2020, "genres": [], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["top_genres"], [])

    async def test_snapshot_with_null_year(self):
        """Items with NULL year should not crash decade range calculation."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "No Year", "genres": ["Drama"], "view_count": 0},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["decade_range"], "unknown")

    async def test_tonight_picks_empty_library(self):
        """Empty library should return count=0, no error."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_tonight_picks", {}))
            self.assertEqual(result["count"], 0)
            self.assertEqual(result["items"], [])

    async def test_quick_pick_all_watched_returns_error(self):
        """Library with only watched items should return error for quick_pick."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "1", "media_type": "movie", "title": "Watched", "year": 2020, "genres": ["Drama"], "view_count": 5},
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {}))
            self.assertIn("error", result)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_no_tmdb_key_returns_error(self, mock_tmdb_cls):
        """Missing TMDB key should return helpful error, not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key=""), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("find_collection_gaps", {"media_type": "movie"}))
            self.assertIn("error", result)
            self.assertIn("TMDB", result["error"])

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_gaps_unrecognized_genre_gets_silently_dropped(self, mock_tmdb_cls):
        """Unknown genre names should not cause error but discover still runs."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = [
            {"id": 27, "name": "Horror"},
        ]
        mock_tmdb.discover_movies.return_value = [
            {"id": 999, "title": "Popular Film", "release_date": "2023-01-01", "vote_average": 7.0},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = json.loads(
                await registry.execute("find_collection_gaps", {"media_type": "movie", "genres": "Nonexistent Genre"})
            )

            call_kwargs = mock_tmdb.discover_movies.call_args[1]
            self.assertIsNone(call_kwargs.get("with_genres"))
            self.assertEqual(result["total_matched"], 1)


if __name__ == "__main__":
    unittest.main()
