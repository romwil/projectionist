"""Tests for chat delight agent tools (items 21-25)."""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from curatorx.agent.tools import ToolRegistry, build_system_prompt
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database

from conftest import seed_library as _seed_library


class TestGetTodaysAnniversaries(unittest.IsolatedAsyncioTestCase):
    async def test_returns_anniversary_items(self) -> None:
        current_year = date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Classic Film",
                    "year": current_year - 25,
                    "genres": ["Drama"],
                    "view_count": 3,
                },
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Recent Film",
                    "year": current_year - 2,
                    "genres": ["Comedy"],
                    "view_count": 0,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))
            self.assertGreaterEqual(result["count"], 1)
            matched_titles = [item["title"] for item in result["items"]]
            self.assertIn("Classic Film", matched_titles)

    async def test_returns_empty_when_no_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Odd Year Film",
                    "year": date.today().year - 3,
                    "genres": ["Action"],
                    "view_count": 0,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_todays_anniversaries", {}))
            self.assertEqual(result["items"], [])


class TestGetLibrarySnapshot(unittest.IsolatedAsyncioTestCase):
    async def test_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Sci-Fi Classic",
                    "year": 1982,
                    "genres": ["Sci-Fi", "Action"],
                    "view_count": 2,
                },
                {
                    "rating_key": "2",
                    "media_type": "show",
                    "title": "Drama Series",
                    "year": 2020,
                    "genres": ["Drama"],
                    "view_count": 0,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["movies"], 1)
            self.assertEqual(result["shows"], 1)
            self.assertIn("decade_range", result)

    async def test_empty_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_library_snapshot", {}))
            self.assertEqual(result["total"], 0)


class TestGetTonightPicks(unittest.IsolatedAsyncioTestCase):
    async def test_filters_by_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Short Film",
                    "year": 2020,
                    "genres": ["Drama"],
                    "view_count": 0,
                    "runtime_minutes": 85,
                },
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Long Film",
                    "year": 2019,
                    "genres": ["Action"],
                    "view_count": 0,
                    "runtime_minutes": 180,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(
                await registry.execute("get_tonight_picks", {"max_runtime_minutes": 100})
            )
            titles = [item["title"] for item in result["items"]]
            self.assertIn("Short Film", titles)
            self.assertNotIn("Long Film", titles)

    async def test_excludes_watched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Watched Film",
                    "year": 2020,
                    "genres": ["Drama"],
                    "view_count": 5,
                    "runtime_minutes": 90,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("get_tonight_picks", {}))
            self.assertEqual(result["count"], 0)


class TestSuggestDoubleFeature(unittest.IsolatedAsyncioTestCase):
    async def test_returns_two_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": str(i),
                    "media_type": "movie",
                    "title": f"Film {i}",
                    "year": 2000 + i,
                    "genres": ["Drama", "Thriller"],
                    "view_count": i,
                    "runtime_minutes": 100 + i * 5,
                }
                for i in range(5)
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {}))
            self.assertTrue(result.get("double_feature"))
            self.assertIn("title_a", result)
            self.assertIn("title_b", result)
            self.assertIn("bridge_text", result)
            self.assertGreater(result["combined_runtime"], 0)

    async def test_error_with_too_few_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Solo Film",
                    "year": 2020,
                    "genres": ["Drama"],
                    "view_count": 0,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("suggest_double_feature", {}))
            self.assertIn("error", result)


class TestQuickPickRoulette(unittest.IsolatedAsyncioTestCase):
    async def test_returns_single_unwatched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Unwatched Gem",
                    "year": 2021,
                    "genres": ["Sci-Fi"],
                    "view_count": 0,
                    "runtime_minutes": 110,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {}))
            self.assertTrue(result.get("quick_pick"))
            self.assertEqual(result["item"]["title"], "Unwatched Gem")
            self.assertIn("why", result)

    async def test_genre_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_library(db, [
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Sci-Fi Pick",
                    "year": 2021,
                    "genres": ["Sci-Fi"],
                    "view_count": 0,
                },
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Drama Pick",
                    "year": 2020,
                    "genres": ["Drama"],
                    "view_count": 0,
                },
            ])
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(
                await registry.execute("quick_pick_roulette", {"genres": "Sci-Fi"})
            )
            self.assertEqual(result["item"]["title"], "Sci-Fi Pick")

    async def test_no_matches_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = json.loads(await registry.execute("quick_pick_roulette", {}))
            self.assertIn("error", result)


class TestNightOwlPrompt(unittest.TestCase):
    def test_night_owl_prompt_includes_time_block_at_night(self) -> None:
        from datetime import datetime

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            fake_now = datetime(2024, 1, 15, 23, 30, 0)
            with patch("curatorx.agent.tools._dt") as mock_dt:
                mock_dt.now.return_value = fake_now
                prompt = build_system_prompt(db, persona_id="night-owl-host")
                self.assertIn("late night mode", prompt)

    def test_non_night_owl_has_no_time_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            prompt = build_system_prompt(db, persona_id="classic-curator")
            self.assertNotIn("late night mode", prompt)


if __name__ == "__main__":
    unittest.main()
