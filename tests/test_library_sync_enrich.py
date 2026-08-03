"""Tests for parallel library metadata enrichment during sync."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient, PlexLibraryItem
from projectionist.library.db import Database
from projectionist.library.sync import (
    DEFAULT_LIBRARY_ENRICH_WORKERS,
    DEFAULT_LIBRARY_UPSERT_BATCH_SIZE,
    _enrich_plex_item,
    _resolve_enrich_workers,
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


class PruneLibraryItemsTests(unittest.TestCase):
    def test_prune_refuses_empty_seen_set(self) -> None:
        """Belt-and-suspenders: empty seen_rating_keys must never delete rows."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-survive",
                    "media_type": "movie",
                    "title": "Should Stay",
                    "year": 2020,
                    "tmdb_id": 1,
                }
            )
            pruned = db.prune_library_items_not_in_plex_scan([])
            self.assertEqual(pruned, 0)
            self.assertEqual(len(db.all_library_items()), 1)


class ResolveEnrichWorkersTests(unittest.TestCase):
    def test_default_and_clamp(self) -> None:
        self.assertEqual(_resolve_enrich_workers(Settings()), DEFAULT_LIBRARY_ENRICH_WORKERS)
        self.assertEqual(_resolve_enrich_workers(Settings(library_enrich_workers=4)), 4)
        self.assertEqual(_resolve_enrich_workers(Settings(library_enrich_workers=0)), 1)
        self.assertEqual(_resolve_enrich_workers(Settings(library_enrich_workers=99)), 16)


class EnrichPlexItemTests(unittest.TestCase):
    def test_skips_missing_rating_key(self) -> None:
        item = _movie("", "No Key")
        item.rating_key = ""
        outcome = _enrich_plex_item(item, PlexClient("http://plex", "t"), None, None, set(), set())
        self.assertEqual(outcome.status, "skip")
        self.assertIsNone(outcome.row)

    def test_returns_error_without_raising(self) -> None:
        item = _movie("rk-boom", "Boom")

        def boom(*_args, **_kwargs):
            raise RuntimeError("tmdb down")

        with patch("projectionist.library.sync._row_from_plex_item", side_effect=boom):
            outcome = _enrich_plex_item(item, PlexClient("http://plex", "t"), None, None, set(), set())
        self.assertEqual(outcome.status, "error")
        self.assertIsInstance(outcome.error, RuntimeError)


class ParallelEnrichSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_enriches_in_parallel_and_upserts_serially(self) -> None:
        items = [_movie(f"rk-{i}", f"Title {i}", tmdb_id=str(i)) for i in range(8)]
        active = 0
        peak = 0
        lock = threading.Lock()
        upsert_thread_ids: set[int] = set()
        batch_calls: list[int] = []

        def slow_row(item, *_args, **_kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            real_batch = db.upsert_library_items

            def tracking_batch(rows):
                upsert_thread_ids.add(threading.get_ident())
                batch_calls.append(len(rows))
                return real_batch(rows)

            db.upsert_library_items = tracking_batch  # type: ignore[method-assign]
            settings = Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                library_enrich_workers=4,
            )
            progress_events: list[tuple[str, int, int]] = []

            def on_progress(phase: str, current: int, total: int, _message: str) -> None:
                if phase == "enriching":
                    progress_events.append((phase, current, total))

            with patch.object(PlexClient, "movie_items", return_value=items), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "projectionist.library.sync._row_from_plex_item",
                side_effect=slow_row,
            ), patch(
                "projectionist.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "projectionist.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "projectionist.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings, progress=on_progress)

            self.assertEqual(result["items_synced"], 8)
            self.assertEqual(len(db.all_library_items()), 8)
            self.assertGreaterEqual(peak, 2)
            self.assertEqual(len(upsert_thread_ids), 1)
            self.assertEqual(sum(batch_calls), 8)
            self.assertLessEqual(len(batch_calls), 8)
            self.assertLessEqual(max(batch_calls), DEFAULT_LIBRARY_UPSERT_BATCH_SIZE)
            self.assertTrue(progress_events)
            self.assertEqual(progress_events[-1][1], progress_events[-1][2])

    async def test_sync_batches_upserts_above_threshold(self) -> None:
        n = DEFAULT_LIBRARY_UPSERT_BATCH_SIZE + 7
        items = [_movie(f"rk-{i}", f"Title {i}", tmdb_id=str(i)) for i in range(n)]
        batch_calls: list[int] = []

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
            real_batch = db.upsert_library_items

            def tracking_batch(rows):
                batch_calls.append(len(rows))
                return real_batch(rows)

            db.upsert_library_items = tracking_batch  # type: ignore[method-assign]
            settings = Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                library_enrich_workers=2,
            )
            with patch.object(PlexClient, "movie_items", return_value=items), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "projectionist.library.sync._row_from_plex_item",
                side_effect=instant_row,
            ), patch(
                "projectionist.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "projectionist.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "projectionist.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            self.assertEqual(result["items_synced"], n)
            self.assertEqual(sum(batch_calls), n)
            self.assertGreaterEqual(len(batch_calls), 2)
            self.assertIn(DEFAULT_LIBRARY_UPSERT_BATCH_SIZE, batch_calls)

    async def test_sync_continues_when_one_item_fails(self) -> None:
        items = [
            _movie("rk-ok-1", "Good One", tmdb_id="11"),
            _movie("rk-bad", "Bad One", tmdb_id="22"),
            _movie("rk-ok-2", "Good Two", tmdb_id="33"),
            _movie("", "No Key", tmdb_id="44"),
        ]
        items[-1].rating_key = ""

        def maybe_fail(item, *_args, **_kwargs):
            if item.rating_key == "rk-bad":
                raise RuntimeError("enrich failed")
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            settings = Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                library_enrich_workers=2,
            )
            with patch.object(PlexClient, "movie_items", return_value=items), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "projectionist.library.sync._row_from_plex_item",
                side_effect=maybe_fail,
            ), patch(
                "projectionist.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "projectionist.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "projectionist.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            self.assertEqual(result["items_synced"], 2)
            titles = {row["title"] for row in db.all_library_items()}
            self.assertEqual(titles, {"Good One", "Good Two"})

    async def test_sync_prunes_stale_rating_keys_after_plex_rematch(self) -> None:
        """When Plex keeps one title but assigns a new ratingKey, drop the old index row."""
        items = [_movie("rk-new", "72 Hours", tmdb_id="991")]
        stale_row = {
            "rating_key": "rk-old",
            "media_type": "movie",
            "title": "72 Hours",
            "year": 2024,
            "tmdb_id": 991,
            "added_at": int(time.time()) - 86400,
        }

        def instant_row(item, *_args, **_kwargs):
            return {
                "rating_key": item.rating_key,
                "media_type": item.media_type,
                "title": item.title,
                "year": item.year,
                "tmdb_id": int(item.tmdb_id) if item.tmdb_id else None,
                "added_at": int(time.time()),
            }

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(stale_row)
            self.assertEqual(len(db.all_library_items()), 1)
            settings = Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                library_enrich_workers=1,
            )
            with patch.object(PlexClient, "movie_items", return_value=items), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "projectionist.library.sync._row_from_plex_item",
                side_effect=instant_row,
            ), patch(
                "projectionist.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "projectionist.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "projectionist.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            rows = db.all_library_items()
            self.assertEqual(result["items_pruned"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0]["rating_key"]), "rk-new")

    async def test_sync_does_not_prune_when_plex_scan_empty(self) -> None:
        """Failed or empty Plex scan must not wipe existing library index rows."""
        existing_rows = [
            {
                "rating_key": "rk-keep-1",
                "media_type": "movie",
                "title": "Saved One",
                "year": 2020,
                "tmdb_id": 101,
                "added_at": int(time.time()) - 86400,
            },
            {
                "rating_key": "rk-keep-2",
                "media_type": "movie",
                "title": "Saved Two",
                "year": 2021,
                "tmdb_id": 102,
                "added_at": int(time.time()) - 43200,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            for row in existing_rows:
                db.upsert_library_item(row)
            self.assertEqual(len(db.all_library_items()), 2)

            settings = Settings(
                plex_url="http://plex.test:32400",
                plex_token="token",
                library_enrich_workers=1,
            )
            with patch.object(PlexClient, "movie_items", return_value=[]), patch.object(
                PlexClient, "show_items", return_value=[]
            ), patch(
                "projectionist.library.sync.rebuild_embeddings",
                new=AsyncMock(return_value=0),
            ), patch(
                "projectionist.library.sync.sync_tv_episodes",
                return_value={"shows_synced": 0, "episodes_synced": 0},
            ), patch(
                "projectionist.library.sync.scan_for_rating_prompts",
                return_value=0,
            ):
                result = await sync_library(db, settings)

            rows = db.all_library_items()
            self.assertEqual(result["items_pruned"], 0)
            self.assertEqual(result["items_synced"], 0)
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {str(row["rating_key"]) for row in rows},
                {"rk-keep-1", "rk-keep-2"},
            )


if __name__ == "__main__":
    unittest.main()
