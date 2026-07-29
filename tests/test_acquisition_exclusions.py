"""Acquisition exclusions: deleted titles must not be re-recommended or re-added."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.agent.tools import (
    ToolRegistry,
    _excluded_add_tmdb_ids,
    execute_confirmed_action,
)
from projectionist.config_store import Settings
from projectionist.connectors.radarr import RadarrMovie
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.full_remove import full_remove_library_items
from projectionist.models.schemas import TitleCard


def _make_db() -> Database:
    tmp = tempfile.mkdtemp()
    return Database(Path(tmp) / "test.db")


class AcquisitionExclusionDbTests(unittest.TestCase):
    def test_record_and_query_movie_exclusion(self) -> None:
        db = _make_db()
        db.record_acquisition_exclusion(
            media_type="movie",
            tmdb_id=670292,
            title="The Creator",
            source="full_remove",
        )
        self.assertTrue(
            db.is_acquisition_excluded(media_type="movie", tmdb_id=670292)
        )
        self.assertEqual(db.excluded_tmdb_ids("movie"), {670292})
        self.assertFalse(
            db.is_acquisition_excluded(media_type="movie", tmdb_id=1)
        )

    def test_record_and_query_show_exclusion_by_tvdb(self) -> None:
        db = _make_db()
        db.record_acquisition_exclusion(
            media_type="show",
            tvdb_id=555,
            tmdb_id=999,
            title="Some Show",
            source="full_remove",
        )
        self.assertTrue(db.is_acquisition_excluded(media_type="show", tvdb_id=555))
        self.assertEqual(db.excluded_tvdb_ids(), {555})
        self.assertEqual(db.excluded_tmdb_ids("show"), {999})


class ExcludedAddIdsTests(unittest.TestCase):
    def test_excluded_add_tmdb_ids_includes_acquisition_exclusions(self) -> None:
        db = _make_db()
        db.record_acquisition_exclusion(
            media_type="movie",
            tmdb_id=670292,
            title="The Creator",
        )
        self.assertIn(670292, _excluded_add_tmdb_ids(db, "movie"))


class FullRemoveRecordsExclusionTests(unittest.TestCase):
    def test_full_remove_records_acquisition_exclusion(self) -> None:
        db = _make_db()
        db.upsert_library_item(
            {
                "rating_key": "rk-creator",
                "title": "The Creator",
                "media_type": "movie",
                "tmdb_id": 670292,
                "year": 2023,
            }
        )
        settings = MagicMock()
        settings.radarr_url = "http://radarr.test"
        settings.radarr_api_key = "key"
        settings.plex_url = ""
        settings.plex_token = ""
        settings.sonarr_url = ""
        settings.sonarr_api_key = ""

        with (
            patch(
                "projectionist.library.full_remove.resolve_arr_removal_target",
                return_value={
                    "arr_id": 7,
                    "title": "The Creator",
                    "tmdb_id": 670292,
                },
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch(
                "projectionist.library.full_remove.plex_configuration_error",
                return_value="skip",
            ),
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            radarr = MagicMock()
            radarr.movie_by_id.return_value = {
                "path": "/movies/The Creator (2023)",
                "sizeOnDisk": 100,
                "movieFile": {
                    "path": "/movies/The Creator (2023)/movie.mkv",
                    "size": 100,
                },
            }
            radarr_cls.return_value = radarr
            payload = full_remove_library_items(db, settings, ["rk-creator"])

        self.assertEqual(payload["deleted"], 1)
        self.assertTrue(
            db.is_acquisition_excluded(media_type="movie", tmdb_id=670292)
        )
        radarr.delete_movie.assert_called_once_with(
            7, delete_files=True, add_exclusion=True
        )


class AgentRemovePassesAddExclusionTests(unittest.IsolatedAsyncioTestCase):
    async def test_remove_from_arr_pending_payload_includes_add_exclusion(self) -> None:
        db = _make_db()
        registry = ToolRegistry(
            db,
            Settings(radarr_url="http://radarr", radarr_api_key="secret"),
            DEFAULT_LENS_ID,
        )
        movie = RadarrMovie(
            id=42,
            title="The Creator",
            year=2023,
            tmdb_id=670292,
            monitored=True,
            has_file=True,
        )
        with patch(
            "projectionist.agent.tools.RadarrClient.movie_by_tmdb_id",
            return_value=movie,
        ):
            result = await registry.execute(
                "remove_from_arr",
                {
                    "media_type": "movie",
                    "tmdb_id": 670292,
                    "title": "The Creator",
                    "delete_files": True,
                },
            )
        payload = json.loads(result)
        token = payload["confirmation_token"]
        with db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM pending_actions WHERE token = ?",
                (token,),
            ).fetchone()
        pending = json.loads(row["payload_json"])
        self.assertTrue(pending.get("add_exclusion"))


class ConfirmedAddHonorsExclusionTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_radarr_blocked_when_acquisition_excluded(self) -> None:
        db = _make_db()
        db.record_acquisition_exclusion(
            media_type="movie",
            tmdb_id=670292,
            title="The Creator",
            source="full_remove",
        )
        settings = Settings(
            radarr_url="http://radarr",
            radarr_api_key="secret",
            radarr_root_folder="/movies",
            radarr_quality_profile_id=1,
        )
        token = "add-excluded"
        db.save_pending_action(
            token,
            "add_radarr",
            {
                "action": "add_radarr",
                "tmdb_id": 670292,
                "title": "The Creator",
            },
        )
        with self.assertRaises(RuntimeError) as ctx:
            await execute_confirmed_action(db, settings, token)
        self.assertIn("exclu", str(ctx.exception).lower())


class RecommendationCardsSkipExcludedTests(unittest.TestCase):
    def test_append_recommendation_cards_skips_excluded_titles(self) -> None:
        from projectionist.agent.tools import _append_recommendation_cards

        db = _make_db()
        db.record_acquisition_exclusion(
            media_type="movie",
            tmdb_id=670292,
            title="The Creator",
        )
        registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
        _append_recommendation_cards(
            registry,
            [
                TitleCard(
                    media_type="movie",
                    title="The Creator",
                    year=2023,
                    tmdb_id=670292,
                    reason="would re-add",
                )
            ],
        )
        self.assertEqual(registry._cards, [])


if __name__ == "__main__":
    unittest.main()
