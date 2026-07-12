"""Tests for parallel library metadata enrichment during sync."""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.connectors.plex import PlexClient, PlexLibraryItem
from curatorx.library.db import Database
from curatorx.library.sync import (
    DEFAULT_LIBRARY_ENRICH_WORKERS,
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

        with patch("curatorx.library.sync._row_from_plex_item", side_effect=boom):
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
            real_upsert = db.upsert_library_item

            def tracking_upsert(row):
                upsert_thread_ids.add(threading.get_ident())
                return real_upsert(row)

            db.upsert_library_item = tracking_upsert  # type: ignore[method-assign]
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
                "curatorx.library.sync._row_from_plex_item",
                side_effect=slow_row,
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
                result = await sync_library(db, settings, progress=on_progress)

            self.assertEqual(result["items_synced"], 8)
            self.assertEqual(len(db.all_library_items()), 8)
            self.assertGreaterEqual(peak, 2)
            self.assertEqual(len(upsert_thread_ids), 1)
            self.assertTrue(progress_events)
            self.assertEqual(progress_events[-1][1], progress_events[-1][2])

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
                "curatorx.library.sync._row_from_plex_item",
                side_effect=maybe_fail,
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

            self.assertEqual(result["items_synced"], 2)
            titles = {row["title"] for row in db.all_library_items()}
            self.assertEqual(titles, {"Good One", "Good Two"})


if __name__ == "__main__":
    unittest.main()
