"""Tests for granular library-sync phase checkpoints and resume."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.connectors.plex import PlexClient, PlexLibraryItem
from curatorx.library.db import Database
from curatorx.library.sync import (
    SYNC_CHECKPOINT_KEY,
    SYNC_CHECKPOINT_MAX_AGE_SECONDS,
    _clear_sync_checkpoint,
    _load_sync_checkpoint,
    _save_sync_checkpoint,
    _should_run_phase,
    sync_library,
)


def _movie(rating_key: str, title: str, *, tmdb_id: str | None = "1") -> PlexLibraryItem:
    return PlexLibraryItem(
        rating_key=rating_key,
        media_type="movie",
        title=title,
        year=2020,
        tmdb_id=tmdb_id,
    )


def _seed_library(db: Database, n: int = 3) -> None:
    for index in range(n):
        db.upsert_library_item(
            {
                "rating_key": f"rk-{index}",
                "media_type": "movie",
                "title": f"Title {index}",
                "year": 2000 + index,
            }
        )


class CheckpointHelperTests(unittest.TestCase):
    def test_should_run_phase_after_episodes(self) -> None:
        self.assertFalse(_should_run_phase("episodes", "movies"))
        self.assertFalse(_should_run_phase("episodes", "tv"))
        self.assertFalse(_should_run_phase("episodes", "enriching"))
        self.assertFalse(_should_run_phase("episodes", "indexing"))
        self.assertFalse(_should_run_phase("episodes", "episodes"))
        self.assertTrue(_should_run_phase("episodes", "finishing"))
        self.assertTrue(_should_run_phase(None, "movies"))

    def test_empty_checkpoint_string_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.set_sync_state(SYNC_CHECKPOINT_KEY, "")
            self.assertIsNone(_load_sync_checkpoint(db))
            _clear_sync_checkpoint(db)
            self.assertIsNone(_load_sync_checkpoint(db))

    def test_stale_age_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            _seed_library(db, 3)
            payload = {
                "phase_completed": "episodes",
                "movies": 3,
                "shows": 0,
                "items": 3,
                "timestamp": time.time() - SYNC_CHECKPOINT_MAX_AGE_SECONDS - 10,
            }
            db.set_sync_state(SYNC_CHECKPOINT_KEY, json.dumps(payload))
            self.assertIsNone(_load_sync_checkpoint(db))

    def test_item_count_mismatch_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            # Empty DB vs checkpoint with items — must not resume past enrich.
            payload = {
                "phase_completed": "episodes",
                "movies": 10,
                "shows": 0,
                "items": 10,
                "timestamp": time.time(),
            }
            db.set_sync_state(SYNC_CHECKPOINT_KEY, json.dumps(payload))
            self.assertIsNone(_load_sync_checkpoint(db))

            _seed_library(db, 3)
            _save_sync_checkpoint(db, "episodes", movies=3, shows=0, items=3)
            loaded = _load_sync_checkpoint(db)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["phase_completed"], "episodes")


class SyncCheckpointResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_after_episodes_skips_prior_phases(self) -> None:
        items = [_movie(f"rk-{i}", f"Title {i}", tmdb_id=str(i)) for i in range(3)]

        def instant_row(item, *_args, **_kwargs):
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            for item in items:
                db.upsert_library_item(instant_row(item))
            _save_sync_checkpoint(db, "episodes", movies=3, shows=0, items=3)

            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            phases: list[str] = []
            movie_calls = 0
            show_calls = 0
            enrich_calls = 0
            episode_calls = 0

            def on_progress(phase: str, current: int, total: int, message: str) -> None:
                phases.append(phase)

            def movie_items(*_a, **_k):
                nonlocal movie_calls
                movie_calls += 1
                return items

            def show_items(*_a, **_k):
                nonlocal show_calls
                show_calls += 1
                return []

            def track_enrich(*_a, **_k):
                nonlocal enrich_calls
                enrich_calls += 1
                return instant_row(_movie("x", "x"))

            def track_episodes(*_a, **_k):
                nonlocal episode_calls
                episode_calls += 1
                return {"shows_synced": 0, "episodes_synced": 0}

            with patch.object(PlexClient, "movie_items", side_effect=movie_items), patch.object(
                PlexClient, "show_items", side_effect=show_items
            ), patch(
                "curatorx.library.sync._row_from_plex_item",
                side_effect=track_enrich,
            ), patch(
                "curatorx.library.sync.rebuild_library_facets",
                return_value=0,
            ) as facets_mock, patch(
                "curatorx.library.sync.rebuild_library_fts",
                return_value=0,
            ) as fts_mock, patch(
                "curatorx.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=3),
            ) as embed_mock, patch(
                "curatorx.library.sync.sync_tv_episodes",
                side_effect=track_episodes,
            ), patch(
                "curatorx.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings, progress=on_progress)

            self.assertEqual(movie_calls, 0)
            self.assertEqual(show_calls, 0)
            self.assertEqual(enrich_calls, 0)
            self.assertEqual(episode_calls, 0)
            facets_mock.assert_not_called()
            fts_mock.assert_not_called()
            embed_mock.assert_awaited()
            self.assertEqual(result["resumed_after"], "episodes")
            self.assertEqual(result["items_synced"], 3)
            self.assertEqual(result["embeddings"], 3)
            self.assertIsNone(_load_sync_checkpoint(db))
            self.assertEqual(db.get_sync_state(SYNC_CHECKPOINT_KEY), "")
            self.assertIn("finishing", phases)

    async def test_stale_checkpoint_runs_full_sync(self) -> None:
        items = [_movie("rk-1", "One", tmdb_id="1")]

        def instant_row(item, *_args, **_kwargs):
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            # Checkpoint claims 50 items but DB is empty → ignored.
            db.set_sync_state(
                SYNC_CHECKPOINT_KEY,
                json.dumps(
                    {
                        "phase_completed": "episodes",
                        "movies": 50,
                        "shows": 0,
                        "items": 50,
                        "timestamp": time.time(),
                    }
                ),
            )
            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            movie_calls = 0

            def movie_items(*_a, **_k):
                nonlocal movie_calls
                movie_calls += 1
                return items

            with patch.object(PlexClient, "movie_items", side_effect=movie_items), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "curatorx.library.sync._row_from_plex_item",
                side_effect=instant_row,
            ), patch(
                "curatorx.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=1),
            ), patch(
                "curatorx.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "curatorx.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            self.assertEqual(movie_calls, 1)
            self.assertIsNone(result.get("resumed_after"))
            self.assertEqual(result["items_synced"], 1)
            self.assertIsNone(_load_sync_checkpoint(db))

    async def test_empty_library_first_run_does_not_double_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            movie_calls = 0
            show_calls = 0

            def movie_items(*_a, **_k):
                nonlocal movie_calls
                movie_calls += 1
                return []

            def show_items(*_a, **_k):
                nonlocal show_calls
                show_calls += 1
                return []

            with patch.object(PlexClient, "movie_items", side_effect=movie_items), patch.object(
                PlexClient, "show_items", side_effect=show_items
            ), patch(
                "curatorx.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "curatorx.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "curatorx.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            self.assertEqual(movie_calls, 1)
            self.assertEqual(show_calls, 1)
            self.assertEqual(result["items_synced"], 0)
            self.assertIsNone(_load_sync_checkpoint(db))

    async def test_resume_enrich_refetches_skipped_scans(self) -> None:
        items = [_movie("rk-1", "One", tmdb_id="1")]

        def instant_row(item, *_args, **_kwargs):
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            _save_sync_checkpoint(db, "tv", movies=1, shows=0, items=0)
            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            movie_calls = 0
            show_calls = 0

            def movie_items(*_a, **_k):
                nonlocal movie_calls
                movie_calls += 1
                return items

            def show_items(*_a, **_k):
                nonlocal show_calls
                show_calls += 1
                return []

            with patch.object(PlexClient, "movie_items", side_effect=movie_items), patch.object(
                PlexClient, "show_items", side_effect=show_items
            ), patch(
                "curatorx.library.sync._row_from_plex_item",
                side_effect=instant_row,
            ), patch(
                "curatorx.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=1),
            ), patch(
                "curatorx.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "curatorx.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            # movies+tv skipped → one re-fetch each before enrich
            self.assertEqual(movie_calls, 1)
            self.assertEqual(show_calls, 1)
            self.assertEqual(result["resumed_after"], "tv")
            self.assertEqual(result["items_synced"], 1)
            self.assertIsNone(_load_sync_checkpoint(db))


if __name__ == "__main__":
    unittest.main()
