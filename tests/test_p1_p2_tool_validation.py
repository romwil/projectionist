"""Value-based validation tests for P1 and P2 priority agent tools.

These tests seed known datasets into real SQLite, call actual tool
functions, and verify **exact computed values** — not just key existence.
"""

import json
import tempfile
import time
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from curatorx.agent.tools import ToolRegistry, _card_to_tool_item
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_library(db: Database, items: list[dict]) -> None:
    for item in items:
        db.upsert_library_item(item)


def _seed_episodes(db: Database, show_item_id: int, episodes: list[dict]) -> None:
    rows = []
    for ep in episodes:
        ep.setdefault("show_item_id", show_item_id)
        rows.append(ep)
    db.upsert_library_episodes(rows)


def _seed_watchlist_pin(db: Database, pin: dict) -> Dict[str, Any]:
    return db.add_watchlist_pin(
        pin_id=pin.get("id", uuid.uuid4().hex),
        user_id=pin.get("user_id"),
        tmdb_id=pin.get("tmdb_id"),
        tvdb_id=pin.get("tvdb_id"),
        media_type=pin.get("media_type", "movie"),
        title=pin["title"],
    )


def _make_registry(db: Database, **settings_kw) -> ToolRegistry:
    return ToolRegistry(db, Settings(**settings_kw), DEFAULT_LENS_ID)


def _insert_review_row(db: Database, review: dict) -> None:
    """Insert a review directly via SQL for test seeding."""
    now = time.time()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO user_title_reviews (
                id, rating_key, tmdb_id, tvdb_id, media_type, title,
                stars, review_text, review_tags, prompted_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.get("id", uuid.uuid4().hex),
                review.get("rating_key"),
                review.get("tmdb_id"),
                review.get("tvdb_id"),
                review.get("media_type", "movie"),
                review["title"],
                review["stars"],
                review.get("review_text", ""),
                json.dumps(review.get("review_tags", [])),
                review.get("prompted_by", "user"),
                review.get("created_at", now),
                review.get("updated_at", now),
            ),
        )


# ===================================================================
# P1: explore_genre
# ===================================================================


class TestExploreGenreValues(unittest.IsolatedAsyncioTestCase):
    """Verify explore_genre returns exact counts for owned library items."""

    async def test_owned_items_counted_correctly(self):
        """Seed 3 Action, 2 Drama -> explore_genre(Action) = total_in_library 3."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "a1", "media_type": "movie", "title": "Action 1", "year": 2020, "genres": ["Action"]},
                {"rating_key": "a2", "media_type": "movie", "title": "Action 2", "year": 2021, "genres": ["Action", "Thriller"]},
                {"rating_key": "a3", "media_type": "movie", "title": "Action 3", "year": 2019, "genres": ["Action"]},
                {"rating_key": "d1", "media_type": "movie", "title": "Drama 1", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "d2", "media_type": "movie", "title": "Drama 2", "year": 2022, "genres": ["Drama"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "Action", "include_missing": False}
            ))

            self.assertEqual(result["genre"], "Action")
            self.assertEqual(result["total_in_library"], 3)
            self.assertEqual(result["returned_in_library"], 3)
            self.assertEqual(result["returned_missing"], 0)

    async def test_empty_genre_returns_all(self):
        """No genre filter -> returns all items in library."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "A", "year": 2020, "genres": ["Action"]},
                {"rating_key": "m2", "media_type": "movie", "title": "B", "year": 2021, "genres": ["Drama"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "", "include_missing": False}
            ))

            self.assertEqual(result["total_in_library"], 2)

    async def test_genre_not_in_library_returns_zero(self):
        """Genre with no matching items -> total_in_library=0."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "A", "year": 2020, "genres": ["Action"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "Western", "include_missing": False}
            ))

            self.assertEqual(result["total_in_library"], 0)
            self.assertEqual(result["returned_in_library"], 0)

    async def test_pagination_offset_and_limit(self):
        """Offset/limit should paginate library results correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": f"m{i}", "media_type": "movie", "title": f"Action {i}", "year": 2000 + i, "genres": ["Action"]}
                for i in range(5)
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "Action", "include_missing": False, "limit": 2, "offset": 0}
            ))

            self.assertEqual(result["returned_in_library"], 2)
            self.assertEqual(result["total_in_library"], 5)
            self.assertTrue(result["library_has_more"])

    async def test_show_media_type_filter(self):
        """media_type=show should only count shows."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Movie Drama", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "s1", "media_type": "show", "title": "Show Drama", "year": 2021, "genres": ["Drama"]},
                {"rating_key": "s2", "media_type": "show", "title": "Show Drama 2", "year": 2022, "genres": ["Drama"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "Drama", "media_type": "show", "include_missing": False}
            ))

            self.assertEqual(result["total_in_library"], 2)

    async def test_null_genre_items_excluded(self):
        """Items with empty genre arrays should not match any specific genre."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "No Genre", "year": 2020, "genres": []},
                {"rating_key": "m2", "media_type": "movie", "title": "Has Genre", "year": 2021, "genres": ["Action"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "explore_genre", {"genre": "Action", "include_missing": False}
            ))

            self.assertEqual(result["total_in_library"], 1)


# ===================================================================
# P1: summarize_tv_progress
# ===================================================================


class TestSummarizeTvProgressValues(unittest.IsolatedAsyncioTestCase):
    """Verify percentage calculations, next-up logic, partial season handling."""

    async def test_completion_percent_exact(self):
        """Show with 10 total, 3 unwatched -> 70.0% completion."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "show1",
                    "media_type": "show",
                    "title": "Breaking Bad",
                    "year": 2008,
                    "genres": ["Drama"],
                    "total_episode_count": 10,
                    "unwatched_episode_count": 3,
                },
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("summarize_tv_progress", {"group_by": "show"}))

            self.assertEqual(len(result["buckets"]), 1)
            bucket = result["buckets"][0]
            self.assertEqual(bucket["show_title"], "Breaking Bad")
            self.assertEqual(bucket["total_episodes"], 10)
            self.assertEqual(bucket["watched_episodes"], 7)
            self.assertEqual(bucket["unwatched_episodes"], 3)
            self.assertEqual(bucket["completion_percent"], 70.0)

    async def test_fully_watched_and_not_started(self):
        """100% and 0% shows should appear unless in_progress_only is set."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "done",
                    "media_type": "show",
                    "title": "Finished Show",
                    "year": 2020,
                    "genres": ["Comedy"],
                    "total_episode_count": 20,
                    "unwatched_episode_count": 0,
                },
                {
                    "rating_key": "new",
                    "media_type": "show",
                    "title": "New Show",
                    "year": 2023,
                    "genres": ["Drama"],
                    "total_episode_count": 12,
                    "unwatched_episode_count": 12,
                },
                {
                    "rating_key": "partial",
                    "media_type": "show",
                    "title": "In Progress Show",
                    "year": 2021,
                    "genres": ["Thriller"],
                    "total_episode_count": 8,
                    "unwatched_episode_count": 4,
                },
            ])
            registry = _make_registry(db)

            all_result = json.loads(await registry.execute("summarize_tv_progress", {"group_by": "show"}))
            self.assertEqual(len(all_result["buckets"]), 3)

            in_progress = json.loads(await registry.execute(
                "summarize_tv_progress", {"group_by": "show", "in_progress_only": True}
            ))
            self.assertEqual(len(in_progress["buckets"]), 1)
            self.assertEqual(in_progress["buckets"][0]["show_title"], "In Progress Show")
            self.assertEqual(in_progress["buckets"][0]["completion_percent"], 50.0)

    async def test_group_by_season_with_episodes(self):
        """group_by=season should break down per-season from library_episodes."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "show1",
                    "media_type": "show",
                    "title": "Stranger Things",
                    "year": 2016,
                    "genres": ["Sci-Fi"],
                    "total_episode_count": 5,
                    "unwatched_episode_count": 2,
                },
            ])
            show_row = db.library_item_by_title("Stranger Things", media_type="show")
            show_id = int(show_row["id"])
            _seed_episodes(db, show_id, [
                {"rating_key": "s1e1", "season_number": 1, "episode_number": 1, "title": "Chapter One", "view_count": 1},
                {"rating_key": "s1e2", "season_number": 1, "episode_number": 2, "title": "Chapter Two", "view_count": 1},
                {"rating_key": "s1e3", "season_number": 1, "episode_number": 3, "title": "Chapter Three", "view_count": 1},
                {"rating_key": "s2e1", "season_number": 2, "episode_number": 1, "title": "Chapter Four", "view_count": 0},
                {"rating_key": "s2e2", "season_number": 2, "episode_number": 2, "title": "Chapter Five", "view_count": 0},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("summarize_tv_progress", {"group_by": "season"}))

            self.assertEqual(result["group_by"], "season")
            self.assertEqual(len(result["buckets"]), 2)

            s1 = next(b for b in result["buckets"] if b["season_number"] == 1)
            self.assertEqual(s1["total_episodes"], 3)
            self.assertEqual(s1["watched_episodes"], 3)
            self.assertEqual(s1["completion_percent"], 100.0)

            s2 = next(b for b in result["buckets"] if b["season_number"] == 2)
            self.assertEqual(s2["total_episodes"], 2)
            self.assertEqual(s2["watched_episodes"], 0)
            self.assertEqual(s2["completion_percent"], 0.0)

    async def test_zero_episode_shows_excluded(self):
        """Shows with total_episode_count=0 should not appear."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "empty",
                    "media_type": "show",
                    "title": "Empty Show",
                    "year": 2023,
                    "genres": ["Drama"],
                    "total_episode_count": 0,
                    "unwatched_episode_count": 0,
                },
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("summarize_tv_progress", {"group_by": "show"}))

            self.assertEqual(result["returned"], 0)
            self.assertEqual(result["buckets"], [])

    async def test_sort_order_by_completion_desc(self):
        """Buckets should be sorted by completion_percent descending."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "low",
                    "media_type": "show",
                    "title": "Low Progress",
                    "year": 2020,
                    "genres": ["Drama"],
                    "total_episode_count": 10,
                    "unwatched_episode_count": 8,
                },
                {
                    "rating_key": "high",
                    "media_type": "show",
                    "title": "High Progress",
                    "year": 2021,
                    "genres": ["Comedy"],
                    "total_episode_count": 10,
                    "unwatched_episode_count": 1,
                },
                {
                    "rating_key": "mid",
                    "media_type": "show",
                    "title": "Mid Progress",
                    "year": 2022,
                    "genres": ["Action"],
                    "total_episode_count": 10,
                    "unwatched_episode_count": 5,
                },
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("summarize_tv_progress", {"group_by": "show"}))

            pcts = [b["completion_percent"] for b in result["buckets"]]
            self.assertEqual(pcts, [90.0, 50.0, 20.0])


# ===================================================================
# P1: query_tv_episodes
# ===================================================================


class TestQueryTvEpisodesValues(unittest.IsolatedAsyncioTestCase):
    """Verify season/episode filtering, watched status tracking."""

    def _setup_show_with_episodes(self, tmp: str):
        db = Database(Path(tmp) / "test.db")
        _seed_library(db, [
            {
                "rating_key": "tt",
                "media_type": "show",
                "title": "Test Show",
                "year": 2020,
                "genres": ["Drama"],
                "total_episode_count": 6,
                "unwatched_episode_count": 3,
            },
        ])
        show_row = db.library_item_by_title("Test Show", media_type="show")
        show_id = int(show_row["id"])
        _seed_episodes(db, show_id, [
            {"rating_key": "ep1", "season_number": 1, "episode_number": 1, "title": "Pilot", "view_count": 2, "runtime_minutes": 45},
            {"rating_key": "ep2", "season_number": 1, "episode_number": 2, "title": "Second", "view_count": 1, "runtime_minutes": 42},
            {"rating_key": "ep3", "season_number": 1, "episode_number": 3, "title": "Third", "view_count": 1, "runtime_minutes": 44},
            {"rating_key": "ep4", "season_number": 2, "episode_number": 1, "title": "New Season", "view_count": 0, "runtime_minutes": 50},
            {"rating_key": "ep5", "season_number": 2, "episode_number": 2, "title": "Midpoint", "view_count": 0, "runtime_minutes": 48},
            {"rating_key": "ep6", "season_number": 2, "episode_number": 3, "title": "Finale", "view_count": 0, "runtime_minutes": 55},
        ])
        return db

    async def test_all_episodes_for_show(self):
        """Query all episodes returns correct total."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute("query_tv_episodes", {"show": "Test Show"}))

            self.assertEqual(result["show_title"], "Test Show")
            self.assertEqual(result["total_matched"], 6)
            self.assertEqual(result["returned"], 6)
            self.assertEqual(result["items"][0]["title"], "Pilot")
            self.assertEqual(result["items"][0]["view_count"], 2)
            self.assertFalse(result["items"][0]["unwatched"])

    async def test_season_filter(self):
        """Filtering by season=2 returns only season 2 episodes."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Test Show", "season": 2}
            ))

            self.assertEqual(result["total_matched"], 3)
            titles = [ep["title"] for ep in result["items"]]
            self.assertEqual(titles, ["New Season", "Midpoint", "Finale"])
            for ep in result["items"]:
                self.assertEqual(ep["season_number"], 2)

    async def test_unwatched_only_filter(self):
        """unwatched_only=True returns only view_count=0 episodes."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Test Show", "unwatched_only": True}
            ))

            self.assertEqual(result["total_matched"], 3)
            for ep in result["items"]:
                self.assertTrue(ep["unwatched"])
                self.assertEqual(ep["view_count"], 0)

    async def test_season_and_unwatched_combined(self):
        """season=1 + unwatched_only=True -> 0 results (all S1 watched)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Test Show", "season": 1, "unwatched_only": True}
            ))

            self.assertEqual(result["total_matched"], 0)
            self.assertEqual(result["items"], [])

    async def test_show_not_found(self):
        """Querying a nonexistent show returns error."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Nonexistent Show"}
            ))

            self.assertIn("error", result)
            self.assertEqual(result["total_matched"], 0)

    async def test_episode_order_is_season_then_episode(self):
        """Episodes should be ordered by season_number, then episode_number."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Test Show"}
            ))

            pairs = [(ep["season_number"], ep["episode_number"]) for ep in result["items"]]
            self.assertEqual(pairs, [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)])

    async def test_pagination_limit_and_offset(self):
        """limit=2 offset=0 returns first 2, has_more=True."""
        with tempfile.TemporaryDirectory() as tmp:
            db = self._setup_show_with_episodes(tmp)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Test Show", "limit": 2, "offset": 0}
            ))

            self.assertEqual(result["returned"], 2)
            self.assertTrue(result["has_more"])
            self.assertEqual(result["items"][0]["title"], "Pilot")
            self.assertEqual(result["items"][1]["title"], "Second")

    async def test_null_view_count_treated_as_unwatched(self):
        """Episodes with NULL view_count should be treated as unwatched."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "s1",
                    "media_type": "show",
                    "title": "Null Show",
                    "year": 2020,
                    "genres": ["Drama"],
                    "total_episode_count": 1,
                    "unwatched_episode_count": 1,
                },
            ])
            show_row = db.library_item_by_title("Null Show", media_type="show")
            _seed_episodes(db, int(show_row["id"]), [
                {"rating_key": "ne1", "season_number": 1, "episode_number": 1, "title": "Ep Null", "view_count": None},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "query_tv_episodes", {"show": "Null Show", "unwatched_only": True}
            ))

            self.assertEqual(result["total_matched"], 1)
            self.assertTrue(result["items"][0]["unwatched"])


# ===================================================================
# P1: curate_watchlist
# ===================================================================


class TestCurateWatchlistValues(unittest.IsolatedAsyncioTestCase):
    """Verify priority scoring, dedup logic in curate_watchlist."""

    async def test_watched_items_suggested_for_removal(self):
        """Watchlist items already watched in library -> remove suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Already Watched", "year": 2020,
                 "genres": ["Drama"], "view_count": 3, "tmdb_id": 100},
                {"rating_key": "m2", "media_type": "movie", "title": "Not Watched", "year": 2021,
                 "genres": ["Action"], "view_count": 0, "tmdb_id": 200},
            ])
            _seed_watchlist_pin(db, {"title": "Already Watched", "media_type": "movie", "tmdb_id": 100})
            _seed_watchlist_pin(db, {"title": "Not Watched Yet", "media_type": "movie", "tmdb_id": 200})
            _seed_watchlist_pin(db, {"title": "Not In Library", "media_type": "movie", "tmdb_id": 300})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("curate_watchlist", {}))

            self.assertEqual(result["count_remove"], 1)
            self.assertEqual(result["remove_suggestions"][0]["title"], "Already Watched")
            self.assertIn("Already watched", result["remove_suggestions"][0]["reason"])

    async def test_empty_watchlist_no_suggestions(self):
        """Empty watchlist -> no remove suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("curate_watchlist", {}))

            self.assertEqual(result["count_remove"], 0)
            self.assertEqual(result["remove_suggestions"], [])

    async def test_unwatched_library_items_not_suggested_for_removal(self):
        """Watchlist items in library but unwatched should NOT be suggested for removal."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "In Library Unwatched", "year": 2020,
                 "genres": ["Action"], "view_count": 0, "tmdb_id": 400},
            ])
            _seed_watchlist_pin(db, {"title": "In Library Unwatched", "media_type": "movie", "tmdb_id": 400})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("curate_watchlist", {}))

            self.assertEqual(result["count_remove"], 0)

    async def test_limit_caps_remove_suggestions(self):
        """limit parameter should cap remove suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(5):
                _seed_library(db, [
                    {"rating_key": f"m{i}", "media_type": "movie", "title": f"Watched {i}",
                     "year": 2020, "genres": ["Drama"], "view_count": 2, "tmdb_id": 500 + i},
                ])
                _seed_watchlist_pin(db, {"title": f"Watched {i}", "media_type": "movie", "tmdb_id": 500 + i})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("curate_watchlist", {"limit": 2}))

            self.assertEqual(result["count_remove"], 2)


# ===================================================================
# P1: critique_watchlist
# ===================================================================


class TestCritiqueWatchlistValues(unittest.IsolatedAsyncioTestCase):
    """Verify critique_watchlist returns correct critique text and metadata."""

    async def test_empty_watchlist_critique(self):
        """Empty watchlist -> critique reflects emptiness with pin_count=0."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("critique_watchlist", {}))

            self.assertEqual(result["pin_count"], 0)
            self.assertIn("critique", result)
            self.assertTrue(len(result["critique"]) > 0)

    async def test_non_empty_watchlist_critique_count(self):
        """Critique should reflect the number of pins."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(4):
                _seed_watchlist_pin(db, {"title": f"Movie {i}", "media_type": "movie", "tmdb_id": 600 + i})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("critique_watchlist", {}))

            self.assertEqual(result["pin_count"], 4)
            self.assertIn("4", result["critique"])

    async def test_focus_title_mentioned_in_critique(self):
        """focus_title parameter should appear in the critique text."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_watchlist_pin(db, {"title": "The Matrix", "media_type": "movie", "tmdb_id": 700})
            _seed_watchlist_pin(db, {"title": "Inception", "media_type": "movie", "tmdb_id": 701})

            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "critique_watchlist", {"focus_title": "The Matrix"}
            ))

            self.assertEqual(result["focus_title"], "The Matrix")
            self.assertIn("Matrix", result["critique"])

    async def test_sample_titles_returned(self):
        """sample_titles should contain up to 8 watchlist titles."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(10):
                _seed_watchlist_pin(db, {"title": f"Title {i}", "media_type": "movie", "tmdb_id": 800 + i})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("critique_watchlist", {}))

            self.assertIn("sample_titles", result)
            self.assertLessEqual(len(result["sample_titles"]), 8)
            self.assertEqual(result["pin_count"], 10)


# ===================================================================
# P1: upcoming_premieres
# ===================================================================


class TestUpcomingPremieresValues(unittest.IsolatedAsyncioTestCase):
    """Verify date range boundaries for upcoming premieres."""

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_premiere_within_window_included(self, mock_tmdb_cls):
        """Shows with next episode within days_ahead window should be returned."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()
        air_date = today + timedelta(days=5)

        mock_tmdb.tv_details.return_value = {
            "next_episode_to_air": {
                "air_date": air_date.isoformat(),
                "name": "New Episode",
                "season_number": 2,
                "episode_number": 3,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Upcoming Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 1001},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["items"][0]["title"], "Upcoming Show")
            self.assertEqual(result["items"][0]["air_date"], air_date.isoformat())
            self.assertEqual(result["items"][0]["episode_name"], "New Episode")
            self.assertEqual(result["items"][0]["season_number"], 2)
            self.assertEqual(result["items"][0]["episode_number"], 3)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_premiere_outside_window_excluded(self, mock_tmdb_cls):
        """Shows with next episode beyond days_ahead should be excluded."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()
        far_future = today + timedelta(days=30)

        mock_tmdb.tv_details.return_value = {
            "next_episode_to_air": {
                "air_date": far_future.isoformat(),
                "name": "Future Episode",
                "season_number": 1,
                "episode_number": 1,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Far Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 1002},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 0)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_premiere_exactly_at_cutoff_included(self, mock_tmdb_cls):
        """Premiere exactly at cutoff day should be included (<=)."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()
        cutoff = today + timedelta(days=7)

        mock_tmdb.tv_details.return_value = {
            "next_episode_to_air": {
                "air_date": cutoff.isoformat(),
                "name": "Cutoff Episode",
                "season_number": 1,
                "episode_number": 1,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Cutoff Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 1003},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 7}))

            self.assertEqual(result["count"], 1)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_past_premiere_excluded(self, mock_tmdb_cls):
        """Episodes that aired yesterday should be excluded."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)

        mock_tmdb.tv_details.return_value = {
            "next_episode_to_air": {
                "air_date": yesterday.isoformat(),
                "name": "Yesterday Episode",
                "season_number": 1,
                "episode_number": 1,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Past Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 1004},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 0)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_today_premiere_included(self, mock_tmdb_cls):
        """Episodes airing today should be included (>= today)."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()

        mock_tmdb.tv_details.return_value = {
            "next_episode_to_air": {
                "air_date": today.isoformat(),
                "name": "Today Episode",
                "season_number": 3,
                "episode_number": 5,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Today Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 1005},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["items"][0]["tmdb_id"], 1005)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_movies_excluded(self, mock_tmdb_cls):
        """Only shows (not movies) should be checked for premieres."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.tv_details.side_effect = RuntimeError("not a show")

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "A Movie",
                 "year": 2023, "genres": ["Action"], "tmdb_id": 2000},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 0)
            mock_tmdb.tv_details.assert_not_called()

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_no_tmdb_key_returns_error(self, mock_tmdb_cls):
        """Missing TMDB key -> error."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db, tmdb_api_key="")
            result = json.loads(await registry.execute("upcoming_premieres", {}))

            self.assertIn("error", result)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_sorted_by_air_date(self, mock_tmdb_cls):
        """Multiple premieres should be sorted by air_date ascending."""
        mock_tmdb = mock_tmdb_cls.return_value
        today = datetime.now(timezone.utc).date()
        date_a = today + timedelta(days=10)
        date_b = today + timedelta(days=3)

        def details_side_effect(tmdb_id):
            if tmdb_id == 3001:
                return {"next_episode_to_air": {"air_date": date_a.isoformat(), "name": "Later", "season_number": 1, "episode_number": 1}}
            return {"next_episode_to_air": {"air_date": date_b.isoformat(), "name": "Sooner", "season_number": 1, "episode_number": 1}}

        mock_tmdb.tv_details.side_effect = details_side_effect

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "Later Show",
                 "year": 2023, "genres": ["Drama"], "tmdb_id": 3001},
                {"rating_key": "s2", "media_type": "show", "title": "Sooner Show",
                 "year": 2023, "genres": ["Comedy"], "tmdb_id": 3002},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 2)
            self.assertEqual(result["items"][0]["title"], "Sooner Show")
            self.assertEqual(result["items"][1]["title"], "Later Show")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_show_without_tmdb_id_skipped(self, mock_tmdb_cls):
        """Shows without tmdb_id should be silently skipped."""
        mock_tmdb = mock_tmdb_cls.return_value

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "No TMDB",
                 "year": 2023, "genres": ["Drama"]},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("upcoming_premieres", {"days_ahead": 14}))

            self.assertEqual(result["count"], 0)
            mock_tmdb.tv_details.assert_not_called()


# ===================================================================
# P2: suggest_titles_to_rate
# ===================================================================


class TestSuggestTitlesToRateValues(unittest.IsolatedAsyncioTestCase):
    """Verify intersection of watched+unrated items."""

    async def test_watched_unrated_items_suggested(self):
        """Items with view_count>0 and no review should be suggested."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "w1", "media_type": "movie", "title": "Watched No Review",
                 "year": 2020, "genres": ["Drama"], "view_count": 3, "last_viewed_at": int(time.time()) - 100},
                {"rating_key": "w2", "media_type": "movie", "title": "Watched With Review",
                 "year": 2021, "genres": ["Action"], "view_count": 2, "last_viewed_at": int(time.time()) - 200},
                {"rating_key": "uw1", "media_type": "movie", "title": "Unwatched",
                 "year": 2022, "genres": ["Comedy"], "view_count": 0},
            ])
            _insert_review_row(db, {
                "rating_key": "w2",
                "media_type": "movie",
                "title": "Watched With Review",
                "stars": 4,
            })
            registry = _make_registry(db)
            result = json.loads(await registry.execute("suggest_titles_to_rate", {"limit": 10}))

            titles = [item["title"] for item in result["items"]]
            self.assertIn("Watched No Review", titles)
            self.assertNotIn("Watched With Review", titles)
            self.assertNotIn("Unwatched", titles)

    async def test_empty_library_returns_empty(self):
        """Empty library -> no suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("suggest_titles_to_rate", {}))

            self.assertEqual(result["count"], 0)
            self.assertEqual(result["items"], [])

    async def test_all_reviewed_returns_empty(self):
        """All watched items reviewed -> no suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "r1", "media_type": "movie", "title": "Reviewed Film",
                 "year": 2020, "genres": ["Drama"], "view_count": 1, "last_viewed_at": int(time.time())},
            ])
            _insert_review_row(db, {
                "rating_key": "r1",
                "media_type": "movie",
                "title": "Reviewed Film",
                "stars": 5,
            })
            registry = _make_registry(db)
            result = json.loads(await registry.execute("suggest_titles_to_rate", {}))

            self.assertEqual(result["count"], 0)

    async def test_limit_parameter_respected(self):
        """Only return up to `limit` suggestions."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            for i in range(10):
                _seed_library(db, [
                    {"rating_key": f"m{i}", "media_type": "movie", "title": f"Film {i}",
                     "year": 2020, "genres": ["Drama"], "view_count": 1, "last_viewed_at": now - i * 100},
                ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("suggest_titles_to_rate", {"limit": 3}))

            self.assertLessEqual(result["count"], 3)


# ===================================================================
# P2: get_user_reviews
# ===================================================================


class TestGetUserReviewsValues(unittest.IsolatedAsyncioTestCase):
    """Verify pagination and sort ordering."""

    async def test_reviews_sorted_by_updated_at_desc(self):
        """Reviews should be returned most-recently-updated first."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = time.time()
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Old Review", "year": 2020, "genres": ["Drama"]},
                {"rating_key": "m2", "media_type": "movie", "title": "New Review", "year": 2021, "genres": ["Action"]},
                {"rating_key": "m3", "media_type": "movie", "title": "Mid Review", "year": 2022, "genres": ["Comedy"]},
            ])
            _insert_review_row(db, {
                "rating_key": "m1", "media_type": "movie", "title": "Old Review",
                "stars": 3, "updated_at": now - 3600,
            })
            _insert_review_row(db, {
                "rating_key": "m2", "media_type": "movie", "title": "New Review",
                "stars": 5, "updated_at": now,
            })
            _insert_review_row(db, {
                "rating_key": "m3", "media_type": "movie", "title": "Mid Review",
                "stars": 4, "updated_at": now - 1800,
            })

            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_user_reviews", {}))

            self.assertEqual(result["count"], 3)
            titles = [r["title"] for r in result["items"]]
            self.assertEqual(titles, ["New Review", "Mid Review", "Old Review"])

    async def test_filter_by_media_type(self):
        """media_type filter should restrict results."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _insert_review_row(db, {
                "rating_key": "m1", "media_type": "movie", "title": "Movie Review", "stars": 4,
            })
            _insert_review_row(db, {
                "rating_key": "s1", "media_type": "show", "title": "Show Review", "stars": 3,
            })

            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "get_user_reviews", {"media_type": "movie"}
            ))

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["items"][0]["title"], "Movie Review")

    async def test_filter_by_min_stars(self):
        """min_stars filter should exclude lower-rated reviews."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _insert_review_row(db, {"rating_key": "r1", "media_type": "movie", "title": "Great", "stars": 5})
            _insert_review_row(db, {"rating_key": "r2", "media_type": "movie", "title": "Good", "stars": 4})
            _insert_review_row(db, {"rating_key": "r3", "media_type": "movie", "title": "Ok", "stars": 3})
            _insert_review_row(db, {"rating_key": "r4", "media_type": "movie", "title": "Bad", "stars": 1})

            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "get_user_reviews", {"min_stars": 4}
            ))

            self.assertEqual(result["count"], 2)
            stars_returned = {r["stars"] for r in result["items"]}
            self.assertTrue(all(s >= 4 for s in stars_returned))

    async def test_filter_by_title_substring(self):
        """title filter should do substring matching (LIKE)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _insert_review_row(db, {"rating_key": "r1", "media_type": "movie", "title": "The Dark Knight", "stars": 5})
            _insert_review_row(db, {"rating_key": "r2", "media_type": "movie", "title": "Dark Shadows", "stars": 3})
            _insert_review_row(db, {"rating_key": "r3", "media_type": "movie", "title": "Bright Star", "stars": 4})

            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "get_user_reviews", {"title": "Dark"}
            ))

            self.assertEqual(result["count"], 2)
            titles = {r["title"] for r in result["items"]}
            self.assertEqual(titles, {"The Dark Knight", "Dark Shadows"})

    async def test_limit_parameter(self):
        """limit should cap returned reviews."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(10):
                _insert_review_row(db, {
                    "rating_key": f"r{i}", "media_type": "movie", "title": f"Film {i}", "stars": 3,
                })

            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_user_reviews", {"limit": 3}))

            self.assertEqual(result["count"], 3)

    async def test_empty_reviews_returns_empty(self):
        """No reviews -> empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_user_reviews", {}))

            self.assertEqual(result["count"], 0)
            self.assertEqual(result["items"], [])


# ===================================================================
# P2: list_plex_collections
# ===================================================================


class TestListPlexCollectionsValues(unittest.IsolatedAsyncioTestCase):
    """Verify list_plex_collections behaviour."""

    @patch("curatorx.agent.tools.plex_collections_configuration_error")
    async def test_no_plex_configured_returns_error(self, mock_config_err):
        """If Plex is not configured, return error."""
        mock_config_err.return_value = "Plex is not configured."
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("list_plex_collections", {}))

            self.assertIn("error", result)
            self.assertIn("Plex", result["error"])

    @patch("curatorx.agent.tools.plex_collections_configuration_error")
    async def test_no_section_configured_returns_error(self, mock_config_err):
        """If section mapping is missing, return error."""
        mock_config_err.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db, plex_url="http://plex:32400", plex_token="token")
            result = json.loads(await registry.execute(
                "list_plex_collections", {"media_type": "movie"}
            ))

            self.assertIn("error", result)
            self.assertIn("section", result["error"].lower())


# ===================================================================
# P2: query_watchlist
# ===================================================================


class TestQueryWatchlistValues(unittest.IsolatedAsyncioTestCase):
    """Verify query_watchlist status filtering correctness."""

    async def test_returns_all_pins(self):
        """query_watchlist returns all pins with enrichment."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Library Movie",
                 "year": 2020, "genres": ["Drama"], "view_count": 2, "tmdb_id": 5000},
            ])
            _seed_watchlist_pin(db, {"title": "Library Movie", "media_type": "movie", "tmdb_id": 5000})
            _seed_watchlist_pin(db, {"title": "External Movie", "media_type": "movie", "tmdb_id": 5001})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("query_watchlist", {}))

            self.assertEqual(result["count"], 2)
            items_by_title = {i["title"]: i for i in result["items"]}

            lib_item = items_by_title["Library Movie"]
            self.assertTrue(lib_item["in_library"])
            self.assertTrue(lib_item["watched"])
            self.assertEqual(lib_item["view_count"], 2)

            ext_item = items_by_title["External Movie"]
            self.assertFalse(ext_item["in_library"])
            self.assertFalse(ext_item["watched"])
            self.assertEqual(ext_item["view_count"], 0)

    async def test_empty_watchlist(self):
        """Empty watchlist returns count=0."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("query_watchlist", {}))

            self.assertEqual(result["count"], 0)
            self.assertEqual(result["items"], [])

    async def test_limit_parameter(self):
        """limit should cap returned pins."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(10):
                _seed_watchlist_pin(db, {"title": f"Pin {i}", "media_type": "movie", "tmdb_id": 6000 + i})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("query_watchlist", {"limit": 3}))

            self.assertEqual(result["count"], 3)

    async def test_show_tvdb_enrichment(self):
        """Shows with tvdb_id should be enriched via tvdb matching."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "s1", "media_type": "show", "title": "TVDB Show",
                 "year": 2020, "genres": ["Drama"], "view_count": 1, "tvdb_id": 9000},
            ])
            _seed_watchlist_pin(db, {"title": "TVDB Show", "media_type": "show", "tvdb_id": 9000})

            registry = _make_registry(db)
            result = json.loads(await registry.execute("query_watchlist", {}))

            self.assertEqual(result["count"], 1)
            self.assertTrue(result["items"][0]["in_library"])
            self.assertTrue(result["items"][0]["watched"])


# ===================================================================
# P2: get_todays_anniversaries (expanded)
# ===================================================================


class TestAnniversariesExpandedValues(unittest.IsolatedAsyncioTestCase):
    """Expanded anniversary tests: multiple milestones, boundary, edge cases."""

    async def test_all_milestone_years_matched(self):
        """Test 5, 10, 15, 20, 25, 30, 40, 50, 75 year milestones."""
        current_year = date.today().year
        milestones = [5, 10, 15, 20, 25, 30, 40, 50, 75]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            items = []
            for n in milestones:
                items.append({
                    "rating_key": f"ms{n}",
                    "media_type": "movie",
                    "title": f"{n} Year Film",
                    "year": current_year - n,
                    "genres": ["Drama"],
                })
            _seed_library(db, items)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "get_todays_anniversaries", {"limit": 50}
            ))

            returned_titles = {item["title"] for item in result["items"]}
            for n in milestones:
                self.assertIn(f"{n} Year Film", returned_titles, f"Missing {n}-year milestone")

    async def test_non_milestone_years_excluded(self):
        """Films from non-milestone years (1, 2, 3, 6, 7, 8, 11...) should be excluded."""
        current_year = date.today().year
        non_milestones = [1, 2, 3, 6, 7, 8, 11, 14, 16, 22, 33]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            items = []
            for n in non_milestones:
                items.append({
                    "rating_key": f"nm{n}",
                    "media_type": "movie",
                    "title": f"{n} Year Film",
                    "year": current_year - n,
                    "genres": ["Drama"],
                })
            _seed_library(db, items)
            registry = _make_registry(db)
            result = json.loads(await registry.execute(
                "get_todays_anniversaries", {"limit": 50}
            ))

            self.assertEqual(len(result["items"]), 0)

    async def test_years_ago_context_string_exact(self):
        """anniversary_context should say 'Released X years ago' with correct X."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "a50", "media_type": "movie", "title": "Half Century Film",
                 "year": current_year - 50, "genres": ["Western"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))

            self.assertEqual(result["count"], 1)
            self.assertIn("50 years ago", result["items"][0]["anniversary_context"])

    async def test_last_viewed_context_included(self):
        """Items with last_viewed_at should include 'Last watched X months ago'."""
        current_year = date.today().year
        three_months_ago = int(time.time()) - (90 * 86400)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "v25",
                    "media_type": "movie",
                    "title": "Viewed Anniversary Film",
                    "year": current_year - 25,
                    "genres": ["Drama"],
                    "view_count": 1,
                    "last_viewed_at": three_months_ago,
                },
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))

            context = result["items"][0]["anniversary_context"]
            self.assertIn("25 years ago", context)
            self.assertIn("Last watched", context)
            self.assertIn("month", context)

    async def test_limit_parameter(self):
        """limit should cap results even if more milestones exist."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            milestones = [5, 10, 15, 20, 25]
            for n in milestones:
                _seed_library(db, [
                    {"rating_key": f"lim{n}", "media_type": "movie", "title": f"Film {n}yr",
                     "year": current_year - n, "genres": ["Drama"]},
                ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {"limit": 2}))

            self.assertLessEqual(len(result["items"]), 2)

    async def test_empty_library_no_anniversaries(self):
        """Empty library -> no items, note returned."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))

            self.assertEqual(result["items"], [])
            self.assertIn("note", result)

    async def test_null_year_excluded(self):
        """Items with NULL year should not crash or appear."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "noyear", "media_type": "movie", "title": "No Year Film", "genres": ["Drama"]},
                {"rating_key": "valid", "media_type": "movie", "title": "Valid",
                 "year": current_year - 10, "genres": ["Drama"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {"limit": 10}))

            titles = {item["title"] for item in result["items"]}
            self.assertNotIn("No Year Film", titles)
            self.assertIn("Valid", titles)

    async def test_shows_included_alongside_movies(self):
        """Both movies and shows should appear if they hit milestone years."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "mv", "media_type": "movie", "title": "Anniversary Movie",
                 "year": current_year - 20, "genres": ["Drama"]},
                {"rating_key": "sh", "media_type": "show", "title": "Anniversary Show",
                 "year": current_year - 20, "genres": ["Comedy"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {"limit": 10}))

            titles = {item["title"] for item in result["items"]}
            self.assertIn("Anniversary Movie", titles)
            self.assertIn("Anniversary Show", titles)

    async def test_ordered_by_year_asc(self):
        """Results should be ordered by year ascending (oldest first)."""
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "new", "media_type": "movie", "title": "Newer Film",
                 "year": current_year - 5, "genres": ["Action"]},
                {"rating_key": "old", "media_type": "movie", "title": "Older Film",
                 "year": current_year - 50, "genres": ["Drama"]},
                {"rating_key": "mid", "media_type": "movie", "title": "Middle Film",
                 "year": current_year - 25, "genres": ["Thriller"]},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("get_todays_anniversaries", {"limit": 10}))

            titles = [item["title"] for item in result["items"]]
            self.assertEqual(titles, ["Older Film", "Middle Film", "Newer Film"])


# ===================================================================
# P2: Additional tool tests (recommend_hidden_gems, suggest_purge_candidates)
# ===================================================================


class TestRecommendHiddenGemsValues(unittest.IsolatedAsyncioTestCase):
    """Verify hidden gems excludes owned items and low-rated TMDB results."""

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_excludes_owned_titles(self, mock_tmdb_cls):
        """TMDB results already in library should be filtered out."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 100, "title": "Owned Film", "vote_average": 8.5, "release_date": "2020-01-01"},
            {"id": 200, "title": "Not Owned Film", "vote_average": 9.0, "release_date": "2019-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "m1", "media_type": "movie", "title": "Owned Film",
                 "year": 2020, "genres": ["Drama"], "tmdb_id": 100},
            ])
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("recommend_hidden_gems", {}))

            titles = [item["title"] for item in result.get("items", [])]
            self.assertNotIn("Owned Film", titles)
            self.assertIn("Not Owned Film", titles)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_excludes_low_rated(self, mock_tmdb_cls):
        """TMDB results with vote_average < 7.0 should be filtered out."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {"id": 300, "title": "High Rated", "vote_average": 8.0, "release_date": "2020-01-01"},
            {"id": 301, "title": "Low Rated", "vote_average": 5.0, "release_date": "2020-01-01"},
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db, tmdb_api_key="test-key")
            result = json.loads(await registry.execute("recommend_hidden_gems", {}))

            titles = [item["title"] for item in result.get("items", [])]
            self.assertIn("High Rated", titles)
            self.assertNotIn("Low Rated", titles)

    async def test_no_tmdb_key_returns_error(self):
        """Missing TMDB key -> error."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db, tmdb_api_key="")
            result = json.loads(await registry.execute("recommend_hidden_gems", {}))

            self.assertIn("error", result)


class TestSuggestPurgeCandidatesValues(unittest.IsolatedAsyncioTestCase):
    """Verify purge candidates returns low-rated watched items."""

    async def test_returns_low_rated_watched(self):
        """Purge candidates should be watched, low-rated items."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "bad", "media_type": "movie", "title": "Bad Movie",
                 "year": 2020, "genres": ["Horror"], "view_count": 1, "vote_average": 2.0,
                 "runtime_minutes": 90, "file_size": 5_000_000_000},
                {"rating_key": "good", "media_type": "movie", "title": "Good Movie",
                 "year": 2021, "genres": ["Drama"], "view_count": 5, "vote_average": 9.0,
                 "runtime_minutes": 120, "file_size": 3_000_000_000},
                {"rating_key": "unwatched", "media_type": "movie", "title": "Unwatched Movie",
                 "year": 2022, "genres": ["Action"], "view_count": 0, "vote_average": 1.0,
                 "runtime_minutes": 100, "file_size": 4_000_000_000},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("suggest_purge_candidates", {}))

            titles = [item["title"] for item in result.get("items", [])]
            self.assertIn("Bad Movie", titles)


# ===================================================================
# P2: what_to_watch_tonight
# ===================================================================


class TestWhatToWatchTonightValues(unittest.IsolatedAsyncioTestCase):
    """Verify tonight recommendations scoring."""

    async def test_unwatched_preferred_over_rewatched(self):
        """Unwatched items should score higher than multi-watched items."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "fresh", "media_type": "movie", "title": "Fresh Film",
                 "year": 2020, "genres": ["Drama"], "view_count": 0, "runtime_minutes": 100},
                {"rating_key": "once", "media_type": "movie", "title": "Seen Once",
                 "year": 2019, "genres": ["Action"], "view_count": 1, "runtime_minutes": 110},
                {"rating_key": "twice", "media_type": "movie", "title": "Seen Twice",
                 "year": 2018, "genres": ["Comedy"], "view_count": 2, "runtime_minutes": 95},
                {"rating_key": "many", "media_type": "movie", "title": "Seen Many",
                 "year": 2017, "genres": ["Thriller"], "view_count": 5, "runtime_minutes": 130},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("what_to_watch_tonight", {"limit": 10}))

            titles = [item["title"] for item in result["items"]]
            self.assertIn("Fresh Film", titles)
            self.assertNotIn("Seen Many", titles)

    async def test_heavily_watched_excluded(self):
        """Items with view_count > 2 should be excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {"rating_key": "many", "media_type": "movie", "title": "Over-watched",
                 "year": 2020, "genres": ["Drama"], "view_count": 3, "runtime_minutes": 100},
            ])
            registry = _make_registry(db)
            result = json.loads(await registry.execute("what_to_watch_tonight", {}))

            self.assertEqual(result["total_matched"], 0)

    async def test_empty_library_returns_empty(self):
        """Empty library -> no picks."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = _make_registry(db)
            result = json.loads(await registry.execute("what_to_watch_tonight", {}))

            self.assertEqual(result["total_matched"], 0)


if __name__ == "__main__":
    unittest.main()
