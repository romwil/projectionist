"""Tests for Plex rating write-back."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import FeatureFlags, Settings, save_settings
from curatorx.connectors.http import optional_int
from curatorx.connectors.plex import PlexClient, PlexEpisode, PlexLibraryItem, plex_rating_to_stars, stars_to_plex_rating
from curatorx.library.db import Database
from curatorx.library.episodes import _upsert_episodes_for_show
from curatorx.library.sync import _row_from_plex_item
from curatorx.reviews.plex_sync import (
    cache_plex_user_rating_stars,
    get_stored_plex_user_rating_stars,
    lookup_plex_user_rating_stars,
    sync_review_rating_to_plex,
)
from curatorx.reviews.store import save_review


class OptionalIntTests(unittest.TestCase):
    def test_optional_int_accepts_float_like_strings(self) -> None:
        self.assertEqual(optional_int("9.0"), 9)
        self.assertEqual(optional_int("8"), 8)
        self.assertEqual(optional_int("0"), 0)
        self.assertIsNone(optional_int(None))
        self.assertIsNone(optional_int(""))


class PlexRatingMappingTests(unittest.TestCase):
    def test_stars_to_plex_rating(self) -> None:
        self.assertEqual(stars_to_plex_rating(1), 2)
        self.assertEqual(stars_to_plex_rating(3), 6)
        self.assertEqual(stars_to_plex_rating(5), 10)
        self.assertEqual(stars_to_plex_rating(4.5), 9)
        self.assertEqual(stars_to_plex_rating(0.5), 1)

    def test_plex_rating_to_stars(self) -> None:
        self.assertEqual(plex_rating_to_stars(8), 4)
        self.assertEqual(plex_rating_to_stars(9), 4.5)
        self.assertEqual(plex_rating_to_stars(0), None)
        self.assertIsNone(plex_rating_to_stars(None))

    def test_invalid_stars_rejected(self) -> None:
        with self.assertRaises(ValueError):
            stars_to_plex_rating(0)
        with self.assertRaises(ValueError):
            stars_to_plex_rating(5.5)


class PlexClientRatingTests(unittest.TestCase):
    def test_set_user_rating_calls_put_rate_endpoint(self) -> None:
        client = PlexClient("http://plex.test:32400", "secret-token")
        captured: dict[str, str] = {}

        def fake_request_empty(url: str, *, method: str = "PUT", timeout: int = 30) -> None:
            captured["url"] = url
            captured["method"] = method

        with patch("curatorx.connectors.plex.request_empty", side_effect=fake_request_empty):
            client.set_user_rating("12345", 4)

        self.assertEqual(captured["method"], "PUT")
        self.assertIn("/:/rate?", captured["url"])
        self.assertIn("identifier=com.plexapp.plugins.library", captured["url"])
        self.assertIn("key=12345", captured["url"])
        self.assertIn("rating=8", captured["url"])
        self.assertIn("X-Plex-Token=secret-token", captured["url"])

    def test_parse_video_reads_user_rating(self) -> None:
        import xml.etree.ElementTree as ET

        client = PlexClient("http://plex.test:32400", "token")
        element = ET.fromstring(
            '<Video ratingKey="42" title="Arrival" type="movie" userRating="8" />'
        )
        item = client._parse_video(element, "movie")
        self.assertEqual(item.user_rating_stars, 4)

    def test_parse_video_accepts_float_user_rating(self) -> None:
        """Real Plex XML often emits userRating as a float string like '9.0'."""
        import xml.etree.ElementTree as ET

        client = PlexClient("http://plex.test:32400", "token")
        element = ET.fromstring(
            '<Video ratingKey="42" title="Arrival" type="movie" userRating="9.0" />'
        )
        item = client._parse_video(element, "movie")
        # 9.0 → 4.5★ (half-star scale: plex_rating / 2)
        self.assertEqual(item.user_rating_stars, 4.5)

        element_ten = ET.fromstring(
            '<Video ratingKey="43" title="Dune" type="movie" userRating="10.0" />'
        )
        self.assertEqual(client._parse_video(element_ten, "movie").user_rating_stars, 5)

    def test_parse_episode_reads_user_rating(self) -> None:
        import xml.etree.ElementTree as ET

        client = PlexClient("http://plex.test:32400", "token")
        element = ET.fromstring(
            '<Video ratingKey="99" title="Pilot" type="episode" userRating="6" parentIndex="1" index="1" />'
        )
        episodes = client._parse_episode_elements([element])
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].user_rating_stars, 3)

    def test_parse_episode_accepts_float_user_rating(self) -> None:
        import xml.etree.ElementTree as ET

        client = PlexClient("http://plex.test:32400", "token")
        element = ET.fromstring(
            '<Video ratingKey="99" title="Pilot" type="episode" userRating="8.0" '
            'parentIndex="1" index="1" />'
        )
        episodes = client._parse_episode_elements([element])
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].user_rating_stars, 4)

    def test_episode_rating_stored_on_library_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "episodes.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-1",
                    "media_type": "show",
                    "title": "Severance",
                }
            )
            episode = PlexEpisode(
                rating_key="ep-1",
                title="Pilot",
                season_number=1,
                episode_number=1,
                user_rating_stars=4,
            )
            synced = _upsert_episodes_for_show(db, show_id, [episode])
            self.assertEqual(synced, 1)
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT plex_user_rating_stars FROM library_episodes WHERE rating_key = ?",
                    ("ep-1",),
                ).fetchone()
            self.assertEqual(int(row["plex_user_rating_stars"]), 4)


class PlexReviewSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "reviews.db")
        self.settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            sync_reviews_to_plex=True,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_sync_marks_review_when_plex_call_succeeds(self) -> None:
        saved = save_review(
            self.db,
            stars=5,
            title="Arrival",
            media_type="movie",
            rating_key="999",
        )
        with patch.object(PlexClient, "set_user_rating") as mock_rate:
            result = sync_review_rating_to_plex(self.db, self.settings, saved)
        self.assertTrue(result["plex_rating_synced"])
        mock_rate.assert_called_once_with("999", 5)

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT plex_rating_synced FROM user_title_reviews WHERE id = ?",
                (saved["id"],),
            ).fetchone()
        self.assertEqual(int(row["plex_rating_synced"]), 1)

    def test_sync_skipped_when_disabled(self) -> None:
        saved = save_review(
            self.db,
            stars=4,
            title="Dune",
            media_type="movie",
            rating_key="111",
        )
        disabled = Settings(sync_reviews_to_plex=False)
        with patch.object(PlexClient, "set_user_rating") as mock_rate:
            result = sync_review_rating_to_plex(self.db, disabled, saved)
        self.assertFalse(result["plex_rating_synced"])
        mock_rate.assert_not_called()

    def test_sync_returns_conflict_when_plex_rating_differs(self) -> None:
        saved = save_review(
            self.db,
            stars=3,
            title="Blade Runner",
            media_type="movie",
            rating_key="555",
        )
        with patch(
            "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
            return_value=5,
        ), patch.object(PlexClient, "set_user_rating") as mock_rate:
            result = sync_review_rating_to_plex(self.db, self.settings, saved)
        self.assertEqual(result["reason"], "plex_rating_conflict")
        self.assertEqual(result["plex_stars"], 5)
        mock_rate.assert_not_called()

    def test_sync_replaces_plex_rating_when_requested(self) -> None:
        saved = save_review(
            self.db,
            stars=3,
            title="Blade Runner",
            media_type="movie",
            rating_key="555",
        )
        with patch(
            "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
            return_value=5,
        ), patch.object(PlexClient, "set_user_rating") as mock_rate:
            result = sync_review_rating_to_plex(
                self.db,
                self.settings,
                saved,
                replace_plex_rating=True,
            )
        self.assertTrue(result["plex_rating_synced"])
        mock_rate.assert_called_once_with("555", 3)

    def test_sync_updates_local_cache_immediately(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "888",
                "media_type": "movie",
                "title": "Dune",
                "plex_user_rating_stars": 5,
            }
        )
        saved = save_review(
            self.db,
            stars=3,
            title="Dune",
            media_type="movie",
            rating_key="888",
        )
        with patch(
            "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
            return_value=5,
        ), patch.object(PlexClient, "set_user_rating"):
            sync_review_rating_to_plex(
                self.db,
                self.settings,
                saved,
                replace_plex_rating=True,
            )
        self.assertEqual(get_stored_plex_user_rating_stars(self.db, "888"), 3)

    def test_cache_plex_user_rating_stars_updates_episode_row(self) -> None:
        show_id = self.db.upsert_library_item(
            {
                "rating_key": "show-2",
                "media_type": "show",
                "title": "Test Show",
            }
        )
        self.db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-2",
                "title": "Episode",
                "plex_user_rating_stars": 2,
            }
        )
        cache_plex_user_rating_stars(self.db, "ep-2", 5)
        self.assertEqual(get_stored_plex_user_rating_stars(self.db, "ep-2"), 5)

    def test_lookup_prefers_stored_library_rating(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "777",
                "media_type": "movie",
                "title": "Stored",
                "plex_user_rating_stars": 4,
            }
        )
        stars = lookup_plex_user_rating_stars(self.db, self.settings, "777")
        self.assertEqual(stars, 4)
        self.assertEqual(get_stored_plex_user_rating_stars(self.db, "777"), 4)

    def test_row_from_plex_item_includes_user_rating(self) -> None:
        item = PlexLibraryItem(
            rating_key="1",
            media_type="movie",
            title="Test",
            year=2020,
            user_rating_stars=2,
        )
        row = _row_from_plex_item(item, PlexClient("http://plex.test", "t"), None, None, in_radarr=False, in_sonarr=False)
        self.assertEqual(row["plex_user_rating_stars"], 2)


class PlexReviewApiSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        save_settings(
            self.data_dir,
            Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                sync_reviews_to_plex=True,
            ),
        )
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_post_review_syncs_to_plex_when_enabled(self) -> None:
        with patch.object(PlexClient, "set_user_rating") as mock_rate:
            response = self.client.post(
                "/api/reviews",
                json={
                    "title": "Blade Runner",
                    "media_type": "movie",
                    "stars": 3,
                    "rating_key": "555",
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["plex_rating_synced"])
        mock_rate.assert_called_once_with("555", 3)

    def test_post_review_returns_conflict_when_plex_rating_differs(self) -> None:
        with patch(
            "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
            return_value=5,
        ), patch.object(PlexClient, "set_user_rating") as mock_rate:
            response = self.client.post(
                "/api/reviews",
                json={
                    "title": "Blade Runner",
                    "media_type": "movie",
                    "stars": 3,
                    "rating_key": "555",
                },
            )
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "plex_rating_conflict")
        self.assertEqual(detail["plex_stars"], 5)
        self.assertIn("Plex has 5★", detail["message"])
        mock_rate.assert_not_called()


class PlexCollectionConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "tools.db")
        self.settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            plex_movie_section="1",
            features=FeatureFlags(plex_collections_enabled=True),
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_create_collection_returns_confirmation_token(self) -> None:
        import asyncio

        from curatorx.agent.tools import ToolRegistry

        registry = ToolRegistry(self.db, self.settings, lens_id="general")
        raw = asyncio.run(
            registry.execute(
                "create_plex_collection",
                {"title": "Sci-Fi Favorites", "media_type": "movie", "rating_keys": ["100"]},
            )
        )
        payload = json.loads(raw)
        self.assertIn("confirmation_token", payload)
        self.assertEqual(len(registry.pending_tokens), 1)

    def test_create_collection_blocked_when_disabled(self) -> None:
        import asyncio

        from curatorx.agent.tools import ToolRegistry

        disabled = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            plex_movie_section="1",
        )
        registry = ToolRegistry(self.db, disabled, lens_id="general")
        raw = asyncio.run(
            registry.execute(
                "create_plex_collection",
                {"title": "Sci-Fi Favorites", "media_type": "movie"},
            )
        )
        payload = json.loads(raw)
        self.assertIn("error", payload)
        self.assertIn("not enabled", payload["error"].lower())

    def test_list_plex_collections_returns_items(self) -> None:
        import asyncio
        from dataclasses import dataclass

        from curatorx.agent.tools import ToolRegistry

        @dataclass
        class FakeCollection:
            rating_key: str
            title: str
            section_id: str
            media_type: str

        registry = ToolRegistry(self.db, self.settings, lens_id="general")
        fake = [FakeCollection("900", "Favorites", "1", "movie")]
        with patch("curatorx.connectors.plex.PlexClient"), patch(
            "curatorx.connectors.plex_collections.list_collections",
            return_value=fake,
        ):
            raw = asyncio.run(
                registry.execute("list_plex_collections", {"media_type": "movie"})
            )
        payload = json.loads(raw)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "Favorites")


if __name__ == "__main__":
    unittest.main()
