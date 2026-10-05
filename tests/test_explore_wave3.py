"""Value-based tests for Wave 3: Explore feeds, title_relations, neighbors API."""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.agent.tools import ToolRegistry
from projectionist.config_store import Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.explore_hub import (
    get_explore_hub,
    invalidate_explore_hub_cache,
)
from projectionist.library.feeds import (
    feed_afterglow,
    feed_continue_watching,
    feed_director_spotlight,
    feed_genre_spotlight,
    feed_on_this_day,
    feed_recent_releases,
    feed_recently_added,
    feed_recently_added_episodes,
    feed_revisit_these,
    feed_seasonal_spotlight,
    feed_unfinished,
    neighbors_payload,
)
from projectionist.persona.presets import get_preset
from projectionist.reviews.store import save_review
from projectionist.library.query import LibraryFilters, query_library
from projectionist.library.relations import refresh_title_relations
from projectionist.scheduler.tasks import title_relations_refresh


class TitleRelationsMigrationTests(unittest.TestCase):
    def test_title_relations_table_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                tables = {
                    str(r["name"])
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                self.assertIn("title_relations", tables)


class FeedHelperTests(unittest.TestCase):
    def test_recently_added_filters_by_added_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            db.upsert_library_item(
                {
                    "rating_key": "new",
                    "media_type": "movie",
                    "title": "New Arrival",
                    "year": 2024,
                    "added_at": now - 86400,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "old",
                    "media_type": "movie",
                    "title": "Old Stock",
                    "year": 1990,
                    "added_at": now - 90 * 86400,
                }
            )
            payload = feed_recently_added(db, limit=12, days=30)
            self.assertEqual(payload["feed"], "recently-added")
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["items"][0]["title"], "New Arrival")
            self.assertIn("poster_url", payload["items"][0])

    def test_recently_added_pagination_and_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            for idx in range(5):
                db.upsert_library_item(
                    {
                        "rating_key": f"movie-{idx}",
                        "media_type": "movie",
                        "title": f"Movie {idx}",
                        "year": 2024,
                        "added_at": now - idx * 60,
                    }
                )
            for idx in range(3):
                db.upsert_library_item(
                    {
                        "rating_key": f"show-{idx}",
                        "media_type": "show",
                        "title": f"Show {idx}",
                        "year": 2024,
                        "added_at": now - idx * 60,
                    }
                )
            page = feed_recently_added(db, limit=2, offset=2, days=30)
            self.assertEqual(page["total"], 8)
            self.assertEqual(page["offset"], 2)
            self.assertEqual(page["limit"], 2)
            self.assertEqual(len(page["items"]), 2)
            self.assertTrue(page["has_more"])

            all_items = feed_recently_added(db, limit=10, days=30)
            self.assertEqual(
                [item["title"] for item in all_items["items"]],
                [
                    "Movie 0",
                    "Show 0",
                    "Movie 1",
                    "Show 1",
                    "Movie 2",
                    "Show 2",
                    "Movie 3",
                    "Movie 4",
                ],
            )

            movies = feed_recently_added(db, limit=10, days=30, media_type="movie")
            self.assertEqual(movies["total"], 5)
            self.assertTrue(all(item["media_type"] == "movie" for item in movies["items"]))

            shows = feed_recently_added(db, limit=10, days=30, media_type="show")
            self.assertEqual(shows["total"], 3)
            self.assertTrue(all(item["media_type"] == "show" for item in shows["items"]))

    def test_recently_added_returns_distinct_rating_keys_for_shared_tmdb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            for idx, rating_key in enumerate(["dup-a", "dup-b"]):
                db.upsert_library_item(
                    {
                        "rating_key": rating_key,
                        "media_type": "movie",
                        "title": "72 Hours",
                        "year": 2026,
                        "tmdb_id": 999001,
                        "added_at": now - idx * 60,
                    }
                )
            payload = feed_recently_added(db, limit=10, days=30, media_type="movie")
            self.assertEqual(payload["total"], 2)
            keys = [item["rating_key"] for item in payload["items"]]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(set(keys), {"dup-a", "dup-b"})

    def test_recently_added_episodes_prefers_freshest_episode_per_show(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            show_a = db.upsert_library_item(
                {
                    "rating_key": "show-a",
                    "media_type": "show",
                    "title": "Severance",
                    "year": 2022,
                    "added_at": now - 90 * 86400,
                }
            )
            show_b = db.upsert_library_item(
                {
                    "rating_key": "show-b",
                    "media_type": "show",
                    "title": "The Bear",
                    "year": 2022,
                    "added_at": now - 90 * 86400,
                }
            )
            db.upsert_library_episodes(
                [
                    {
                        "show_item_id": show_a,
                        "rating_key": "ep-a-old",
                        "season_number": 1,
                        "episode_number": 1,
                        "title": "Good News About Hell",
                        "added_at": now - 20 * 86400,
                    },
                    {
                        "show_item_id": show_a,
                        "rating_key": "ep-a-new",
                        "season_number": 2,
                        "episode_number": 1,
                        "title": "Hello, Ms. Cobel",
                        "added_at": now - 3600,
                    },
                    {
                        "show_item_id": show_b,
                        "rating_key": "ep-b",
                        "season_number": 3,
                        "episode_number": 2,
                        "title": "Tomorrow",
                        "added_at": now - 7200,
                    },
                ]
            )
            payload = feed_recently_added_episodes(db, limit=12, days=30)
            self.assertEqual(payload["feed"], "recently-added-episodes")
            self.assertEqual(payload["total"], 2)
            titles = [item["title"] for item in payload["items"]]
            self.assertEqual(titles, ["Severance", "The Bear"])
            self.assertEqual(payload["items"][0]["episode_label"], "S2E1 · Hello, Ms. Cobel")
            self.assertEqual(payload["items"][0]["play_rating_key"], "ep-a-new")

    def test_episode_added_at_sort_orders_shows_by_freshest_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            older_show = db.upsert_library_item(
                {
                    "rating_key": "older-show",
                    "media_type": "show",
                    "title": "Older Ep",
                    "year": 2020,
                    "added_at": now,
                }
            )
            newer_show = db.upsert_library_item(
                {
                    "rating_key": "newer-show",
                    "media_type": "show",
                    "title": "Newer Ep",
                    "year": 2020,
                    "added_at": now - 10,
                }
            )
            db.upsert_library_episodes(
                [
                    {
                        "show_item_id": older_show,
                        "rating_key": "ep-older",
                        "season_number": 1,
                        "episode_number": 1,
                        "title": "Pilot",
                        "added_at": now - 10_000,
                    },
                    {
                        "show_item_id": newer_show,
                        "rating_key": "ep-newer",
                        "season_number": 1,
                        "episode_number": 1,
                        "title": "Pilot",
                        "added_at": now - 100,
                    },
                ]
            )
            result = query_library(
                db,
                LibraryFilters(media_type="show", sort="episode_added_at", sort_dir="desc", limit=10),
            )
            self.assertEqual(
                [item["title"] for item in result["items"]],
                ["Newer Ep", "Older Ep"],
            )

    def test_explore_hub_caches_and_includes_episode_rail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            invalidate_explore_hub_cache()
            settings = Settings()
            # Explicit rebuild fills memory + disk (cold path is non-blocking).
            first = get_explore_hub(db, settings, rail_limit=8, bypass_cache=True)
            self.assertEqual(first["feed"], "explore-hub")
            self.assertFalse(first.get("cached"))
            self.assertFalse(first.get("warming"))
            self.assertIn("recently_added_episodes", first["rails"])
            second = get_explore_hub(db, settings, rail_limit=8)
            self.assertTrue(second.get("cached"))
            self.assertFalse(second.get("stale"))
            invalidate_explore_hub_cache()
            third = get_explore_hub(db, settings, rail_limit=8, bypass_cache=True)
            self.assertFalse(third.get("cached"))

    def test_explore_hub_swr_serves_stale_without_blocking(self) -> None:
        """Soft-expired hub must return immediately; recompute stays off-request."""
        from projectionist.library import explore_hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            invalidate_explore_hub_cache()
            settings = Settings()
            seeded = get_explore_hub(db, settings, rail_limit=8, bypass_cache=True)
            self.assertFalse(seeded.get("warming"))

            # Expire soft TTL while keeping the hard window.
            with hub_mod._LOCK:
                soft, hard, payload = hub_mod._CACHE[
                    "youth=0|uid=|limit=8"
                ]
                hub_mod._CACHE["youth=0|uid=|limit=8"] = (
                    time.monotonic() - 1.0,
                    hard,
                    payload,
                )

            build_calls = {"n": 0}
            real_build = hub_mod.build_explore_hub

            def counting_build(*args, **kwargs):
                build_calls["n"] += 1
                time.sleep(0.35)  # prove request path does not wait
                return real_build(*args, **kwargs)

            with patch.object(hub_mod, "build_explore_hub", side_effect=counting_build):
                t0 = time.perf_counter()
                stale = get_explore_hub(db, settings, rail_limit=8)
                elapsed = time.perf_counter() - t0
            self.assertTrue(stale.get("cached"))
            self.assertTrue(stale.get("stale"))
            self.assertLess(elapsed, 0.2, f"SWR request blocked for {elapsed:.3f}s")
            # Background refresh was scheduled (may still be running).
            deadline = time.time() + 2.0
            while build_calls["n"] < 1 and time.time() < deadline:
                time.sleep(0.05)
            self.assertGreaterEqual(build_calls["n"], 1)

    def test_explore_hub_cold_miss_returns_warming_immediately(self) -> None:
        from projectionist.library import explore_hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            invalidate_explore_hub_cache()
            # Drop durable cache too.
            with hub_mod._LOCK:
                hub_mod._CACHE.clear()
            settings = Settings()

            build_calls = {"n": 0}
            real_build = hub_mod.build_explore_hub

            def slow_build(*args, **kwargs):
                build_calls["n"] += 1
                time.sleep(0.4)
                return real_build(*args, **kwargs)

            with patch.object(hub_mod, "build_explore_hub", side_effect=slow_build):
                t0 = time.perf_counter()
                cold = get_explore_hub(db, settings, rail_limit=8)
                elapsed = time.perf_counter() - t0
            self.assertTrue(cold.get("warming"))
            self.assertFalse(cold.get("cached"))
            self.assertLess(elapsed, 0.2, f"cold hub blocked for {elapsed:.3f}s")
            self.assertIn("recently_added_episodes", cold["rails"])
            deadline = time.time() + 2.0
            while build_calls["n"] < 1 and time.time() < deadline:
                time.sleep(0.05)
            self.assertGreaterEqual(build_calls["n"], 1)
            # Wait for background fill, then a normal hit should be cached.
            deadline = time.time() + 2.0
            while time.time() < deadline:
                warm = get_explore_hub(db, settings, rail_limit=8)
                if not warm.get("warming"):
                    self.assertTrue(warm.get("cached") or not warm.get("stale"))
                    break
                time.sleep(0.05)
            else:
                self.fail("background hub refresh never completed")

    def test_hub_survives_legacy_db_missing_episode_added_at(self) -> None:
        """Prod footgun: migration 10 ran before 1.37.11 stuffed added_at into phase4."""
        from projectionist.library.db.migrations import CURRENT_SCHEMA_VERSION

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            # Bootstrap a fully-migrated DB, then strip episode.added_at and
            # rewind schema_version so migration 50 re-applies on reopen.
            db = Database(db_path)
            db.close()
            raw = sqlite3.connect(db_path)
            raw.execute("DROP INDEX IF EXISTS idx_episodes_added_at")
            raw.execute("ALTER TABLE library_episodes DROP COLUMN added_at")
            raw.execute("DELETE FROM schema_version WHERE version = ?", (50,))
            cols = {
                str(r[1]) for r in raw.execute("PRAGMA table_info(library_episodes)")
            }
            self.assertNotIn("added_at", cols)
            raw.commit()
            raw.close()

            reopened = Database(db_path)
            with reopened.connect() as conn:
                cols = {
                    str(r["name"])
                    for r in conn.execute("PRAGMA table_info(library_episodes)")
                }
                ver = conn.execute(
                    "SELECT MAX(version) AS v FROM schema_version"
                ).fetchone()
            self.assertIn("added_at", cols)
            self.assertEqual(int(ver["v"]), CURRENT_SCHEMA_VERSION)

            invalidate_explore_hub_cache()
            payload = get_explore_hub(reopened, Settings(), rail_limit=8, bypass_cache=True)
            self.assertEqual(payload["feed"], "explore-hub")
            self.assertIn("recently_added_episodes", payload["rails"])
            # Must not 500 — empty rail is fine on a barren legacy DB.
            self.assertIn("items", payload["rails"]["recently_added_episodes"])

    def test_recent_releases_honest_empty_without_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "no-date",
                    "media_type": "movie",
                    "title": "Undated",
                    "year": 2020,
                }
            )
            payload = feed_recent_releases(db, limit=12, days=365)
            self.assertEqual(payload["feed"], "recent-releases")
            self.assertEqual(payload["items"], [])
            self.assertEqual(payload["total"], 0)
            self.assertIn("release_date", payload["note"] or "")

    def test_recent_releases_filters_on_release_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            today = date.today()
            recent = (today.toordinal() - 10)
            recent_iso = date.fromordinal(recent).isoformat()
            old_iso = date(today.year - 5, 1, 1).isoformat()
            db.upsert_library_item(
                {
                    "rating_key": "fresh",
                    "media_type": "movie",
                    "title": "Fresh Release",
                    "year": today.year,
                    "release_date": recent_iso,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "stale",
                    "media_type": "movie",
                    "title": "Old Release",
                    "year": today.year - 5,
                    "release_date": old_iso,
                }
            )
            payload = feed_recent_releases(db, limit=12, days=30)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["items"][0]["title"], "Fresh Release")
            self.assertEqual(payload["items"][0]["release_date"], recent_iso)

    def test_recent_releases_pagination_and_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            today = date.today()
            recent_iso = (today.toordinal() - 5)
            recent_iso = date.fromordinal(recent_iso).isoformat()
            db.upsert_library_item(
                {
                    "rating_key": "movie-a",
                    "media_type": "movie",
                    "title": "Movie A",
                    "year": today.year,
                    "release_date": recent_iso,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "movie-b",
                    "media_type": "movie",
                    "title": "Movie B",
                    "year": today.year,
                    "release_date": recent_iso,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "show-a",
                    "media_type": "show",
                    "title": "Show A",
                    "year": today.year,
                    "first_air_date": recent_iso,
                }
            )
            page = feed_recent_releases(db, limit=1, offset=1, days=30)
            self.assertEqual(page["total"], 3)
            self.assertEqual(len(page["items"]), 1)
            self.assertTrue(page["has_more"])

            movies = feed_recent_releases(db, limit=10, days=30, media_type="movie")
            self.assertEqual(movies["total"], 2)
            self.assertTrue(all(item["media_type"] == "movie" for item in movies["items"]))

            shows = feed_recent_releases(db, limit=10, days=30, media_type="show")
            self.assertEqual(shows["total"], 1)
            self.assertEqual(shows["items"][0]["title"], "Show A")

    def test_revisit_these_selects_idle_partial_shows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            stale = now - 90 * 86400
            recent = now - 5 * 86400
            db.upsert_library_item(
                {
                    "rating_key": "stale-partial",
                    "media_type": "show",
                    "title": "Stale Partial",
                    "year": 2018,
                    "total_episode_count": 10,
                    "unwatched_episode_count": 4,
                    "last_viewed_at": stale,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fresh-partial",
                    "media_type": "show",
                    "title": "Fresh Partial",
                    "year": 2022,
                    "total_episode_count": 8,
                    "unwatched_episode_count": 2,
                    "last_viewed_at": recent,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fully-watched",
                    "media_type": "show",
                    "title": "Fully Watched",
                    "year": 2015,
                    "total_episode_count": 6,
                    "unwatched_episode_count": 0,
                    "last_viewed_at": stale,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "movie-partial",
                    "media_type": "movie",
                    "title": "Movie Progress",
                    "year": 2020,
                    "view_count": 0,
                    "view_offset_ms": 12_000,
                    "last_viewed_at": stale,
                }
            )
            payload = feed_revisit_these(db, limit=20, idle_days=60)
            self.assertEqual(payload["feed"], "revisit-these")
            self.assertEqual(payload["idle_days"], 60)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["title"], "Stale Partial")
            self.assertEqual(payload["items"][0]["media_type"], "show")
            self.assertIn("view_count", payload["items"][0])
            self.assertIn("unwatched_episode_count", payload["items"][0])

    def test_revisit_these_honest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            payload = feed_revisit_these(db, limit=20, idle_days=60)
            self.assertEqual(payload["items"], [])
            self.assertEqual(payload["total"], 0)
            self.assertIn("partially watched", (payload["note"] or "").lower())

    def test_continue_watching_local_in_progress_movie(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            db.upsert_library_item(
                {
                    "rating_key": "cw-movie",
                    "media_type": "movie",
                    "title": "Half Watched",
                    "year": 2020,
                    "view_count": 0,
                    "view_offset_ms": 1_200_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": now,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "done-movie",
                    "media_type": "movie",
                    "title": "Finished",
                    "year": 2019,
                    "view_count": 1,
                    "view_offset_ms": 0,
                    "last_viewed_at": now,
                }
            )
            payload = feed_continue_watching(db, limit=12)
            self.assertEqual(payload["feed"], "continue-watching")
            self.assertEqual(payload["source"], "local")
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["title"], "Half Watched")
            self.assertEqual(payload["items"][0]["card_kind"], "continue_watching")
            self.assertIn("resume_label", payload["items"][0])
            self.assertEqual(payload["items"][0]["play_rating_key"], "cw-movie")

    def test_continue_watching_prefers_plex_on_deck(self) -> None:
        from projectionist.connectors.plex import PlexOnDeckItem

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "show-1",
                    "media_type": "show",
                    "title": "The Wire",
                    "year": 2002,
                    "total_episode_count": 13,
                    "unwatched_episode_count": 10,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "movie-1",
                    "media_type": "movie",
                    "title": "Heat",
                    "year": 1995,
                    "view_count": 0,
                    "view_offset_ms": 100,
                }
            )

            class FakePlex:
                def on_deck(self, *, limit: int = 20):
                    del limit
                    return [
                        PlexOnDeckItem(
                            rating_key="ep-9",
                            media_type="episode",
                            title="Pilot",
                            show_rating_key="show-1",
                            show_title="The Wire",
                            season_number=1,
                            episode_number=1,
                            view_offset_ms=600_000,
                            duration_ms=3_600_000,
                        ),
                        PlexOnDeckItem(
                            rating_key="movie-1",
                            media_type="movie",
                            title="Heat",
                            view_offset_ms=1_000_000,
                            duration_ms=10_000_000,
                        ),
                    ]

            payload = feed_continue_watching(db, limit=12, plex_client=FakePlex())
            self.assertEqual(payload["source"], "plex_on_deck")
            self.assertEqual(len(payload["items"]), 2)
            self.assertEqual(payload["items"][0]["title"], "The Wire")
            self.assertEqual(payload["items"][0]["play_rating_key"], "ep-9")
            self.assertIn("S1E1", payload["items"][0]["resume_label"])
            self.assertEqual(payload["items"][1]["title"], "Heat")

    def test_continue_watching_honest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            payload = feed_continue_watching(db, limit=12)
            self.assertEqual(payload["items"], [])
            self.assertIn("in progress", (payload["note"] or "").lower())

    def test_unfinished_selects_leftover_runtime_not_idle_revisit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            stale = now - 90 * 86400
            recent = now - 2 * 86400
            db.upsert_library_item(
                {
                    "rating_key": "leftover-movie",
                    "media_type": "movie",
                    "title": "Forty Minutes Left",
                    "year": 2021,
                    "view_count": 0,
                    "view_offset_ms": 3_600_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": recent,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "idle-movie",
                    "media_type": "movie",
                    "title": "Forgotten Sitting",
                    "year": 2019,
                    "view_count": 0,
                    "view_offset_ms": 1_200_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": stale,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "fresh-partial-show",
                    "media_type": "show",
                    "title": "Still Going",
                    "year": 2022,
                    "total_episode_count": 10,
                    "unwatched_episode_count": 3,
                    "last_viewed_at": recent,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "stale-partial-show",
                    "media_type": "show",
                    "title": "Idle Show",
                    "year": 2018,
                    "total_episode_count": 10,
                    "unwatched_episode_count": 4,
                    "last_viewed_at": stale,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "near-complete",
                    "media_type": "movie",
                    "title": "Almost Done",
                    "year": 2020,
                    "view_count": 0,
                    "view_offset_ms": 5_400_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": recent,
                }
            )
            unfinished = feed_unfinished(db, limit=12, idle_days=60)
            titles = {item["title"] for item in unfinished["items"]}
            self.assertEqual(unfinished["feed"], "unfinished")
            self.assertEqual(unfinished["idle_days"], 60)
            self.assertIn("Forty Minutes Left", titles)
            self.assertIn("Still Going", titles)
            self.assertNotIn("Forgotten Sitting", titles)
            self.assertNotIn("Idle Show", titles)
            self.assertNotIn("Almost Done", titles)
            leftover_movie = next(item for item in unfinished["items"] if item["title"] == "Forty Minutes Left")
            self.assertEqual(leftover_movie["card_kind"], "unfinished")
            self.assertIn("minutes left", leftover_movie["leftover_label"])
            leftover_show = next(item for item in unfinished["items"] if item["title"] == "Still Going")
            self.assertIn("episodes left", leftover_show["leftover_label"])

            revisit = feed_revisit_these(db, limit=20, idle_days=60)
            revisit_titles = {item["title"] for item in revisit["items"]}
            self.assertIn("Idle Show", revisit_titles)
            self.assertNotIn("Still Going", revisit_titles)
            self.assertTrue(titles.isdisjoint(revisit_titles))

    def test_unfinished_honest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            payload = feed_unfinished(db, limit=12, idle_days=60)
            self.assertEqual(payload["items"], [])
            self.assertIn("leftover", (payload["note"] or "").lower())

    def test_afterglow_uses_existing_review_dialogue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            now = int(time.time())
            preset = get_preset("classic-curator")
            assert preset is not None
            db.upsert_persona(
                persona_preset_id=preset.id,
                curator_name="Atlas",
                val_bro_prof=preset.val_bro_prof,
                val_dipl_snark=preset.val_dipl_snark,
                val_pass_auto=preset.val_pass_auto,
            )
            db.upsert_library_item(
                {
                    "rating_key": "just-finished",
                    "media_type": "movie",
                    "title": "Warm Credits",
                    "year": 2024,
                    "view_count": 1,
                    "view_offset_ms": 0,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": now - 3600,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "near-done",
                    "media_type": "movie",
                    "title": "Almost Through",
                    "year": 2023,
                    "view_count": 0,
                    "view_offset_ms": 5_400_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": now - 1800,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "already-reviewed",
                    "media_type": "movie",
                    "title": "Already Rated",
                    "year": 2022,
                    "view_count": 1,
                    "last_viewed_at": now - 1200,
                }
            )
            save_review(
                db,
                stars=4,
                title="Already Rated",
                media_type="movie",
                rating_key="already-reviewed",
            )
            db.upsert_library_item(
                {
                    "rating_key": "old-finish",
                    "media_type": "movie",
                    "title": "Last Year",
                    "year": 2020,
                    "view_count": 1,
                    "last_viewed_at": now - 40 * 86400,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "mid-sit",
                    "media_type": "movie",
                    "title": "Halfway",
                    "year": 2021,
                    "view_count": 0,
                    "view_offset_ms": 1_200_000,
                    "duration_ms": 6_000_000,
                    "last_viewed_at": now - 600,
                }
            )
            payload = feed_afterglow(db, limit=12, days=14)
            titles = {item["title"] for item in payload["items"]}
            self.assertEqual(payload["feed"], "afterglow")
            self.assertEqual(payload["days"], 14)
            self.assertIn("Warm Credits", titles)
            self.assertIn("Almost Through", titles)
            self.assertNotIn("Already Rated", titles)
            self.assertNotIn("Last Year", titles)
            self.assertNotIn("Halfway", titles)
            finished = next(item for item in payload["items"] if item["title"] == "Warm Credits")
            self.assertEqual(finished["card_kind"], "afterglow")
            self.assertIn("Warm Credits", finished["afterglow_opener"])
            self.assertGreaterEqual(len(finished["afterglow_questions"]), 3)
            self.assertEqual(finished["dialogue_band"], "warm")
            self.assertEqual(finished["review_dialogue"]["questions"], finished["afterglow_questions"])
            self.assertIn("still warm", finished["afterglow_opener"])
            near = next(item for item in payload["items"] if item["title"] == "Almost Through")
            self.assertGreaterEqual(near["completion_pct"], 85)

    def test_afterglow_honest_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            payload = feed_afterglow(db, limit=12, days=14)
            self.assertEqual(payload["items"], [])
            self.assertIn("warm", (payload["note"] or "").lower())

    def test_on_this_day_calendar_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            today = date.today()
            release = date(today.year - 10, today.month, today.day).isoformat()
            db.upsert_library_item(
                {
                    "rating_key": "anni",
                    "media_type": "movie",
                    "title": "Anniversary Film",
                    "year": today.year - 10,
                    "release_date": release,
                }
            )
            payload = feed_on_this_day(db, limit=5)
            self.assertEqual(payload["mode"], "calendar")
            self.assertEqual(payload["total"], 1)
            self.assertIn("10 years ago", payload["items"][0]["anniversary_context"])

    def test_on_this_day_milestone_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            today = date.today()
            # Year milestone but different calendar month-day (and no ISO dates).
            other_month = 1 if today.month != 1 else 2
            db.upsert_library_item(
                {
                    "rating_key": "mile",
                    "media_type": "movie",
                    "title": "Milestone Only",
                    "year": today.year - 10,
                    "release_date": f"{today.year - 10}-{other_month:02d}-15",
                }
            )
            payload = feed_on_this_day(db, limit=5)
            self.assertEqual(payload["mode"], "milestone_fallback")
            self.assertGreaterEqual(payload["total"], 1)
            self.assertEqual(payload["items"][0]["anniversary_type"], "milestone_year")

    def test_rotating_director_and_genre_spotlights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for index in range(4):
                db.upsert_library_item(
                    {
                        "rating_key": f"spotlight-{index}",
                        "media_type": "movie",
                        "title": f"Spotlight {index}",
                        "year": 2000 + index,
                        "directors": ["Jane Director"],
                        "genres": ["Drama"],
                    }
                )
            selected_day = date(2026, 7, 20)
            directors = feed_director_spotlight(db, limit=3, today=selected_day)
            genres = feed_genre_spotlight(db, limit=3, today=selected_day)
            self.assertEqual(directors["director"], "Jane Director")
            self.assertEqual(directors["total"], 4)
            self.assertEqual(len(directors["items"]), 3)
            self.assertEqual(genres["genre"], "Drama")
            self.assertEqual(genres["total"], 4)
            self.assertEqual(len(genres["items"]), 3)

    def test_seasonal_spotlight_uses_editable_holiday_calendar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "arbor",
                    "media_type": "movie",
                    "title": "The Forest",
                    "year": 2016,
                    "keywords": ["forest"],
                }
            )
            payload = feed_seasonal_spotlight(db, today=date(2026, 4, 24))
            self.assertEqual(payload["label"], "Arbor Day")
            self.assertEqual(payload["mode"], "holiday")
            self.assertEqual(payload["items"][0]["title"], "The Forest")


class RelationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_collection_edges_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            a = db.upsert_library_item(
                {
                    "rating_key": "br1",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "tmdb_collection_id": 10,
                    "collection_name": "Blade Runner Collection",
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "br2",
                    "media_type": "movie",
                    "title": "Blade Runner 2049",
                    "year": 2017,
                    "tmdb_collection_id": 10,
                    "collection_name": "Blade Runner Collection",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "other",
                    "media_type": "movie",
                    "title": "Solo",
                    "year": 2000,
                    "tmdb_collection_id": 99,
                }
            )

            result = await title_relations_refresh.run(
                db, Settings(), should_stop=lambda: False
            )
            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["collection"], 2)

            rows = db.list_title_relations(a, relation="collection", limit=10)
            to_ids = {int(r["to_id"]) for r in rows}
            self.assertIn(b, to_ids)

            counts = refresh_title_relations(db)
            self.assertGreaterEqual(counts["collection"], 2)

    async def test_refresh_skips_orphan_neighbor_fk(self) -> None:
        """Legacy orphan item_neighbors must not break title_relations rebuild under FK ON."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = Database(db_path)
            a = db.upsert_library_item(
                {
                    "rating_key": "alive",
                    "media_type": "movie",
                    "title": "Alive",
                    "year": 2020,
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "peer",
                    "media_type": "movie",
                    "title": "Peer",
                    "year": 2021,
                }
            )
            db.set_neighbors(a, [(b, 0.95, 0.1)])

            # Simulate pre–FK-enforcement orphans still sitting in item_neighbors.
            raw = sqlite3.connect(db_path)
            try:
                raw.execute("PRAGMA foreign_keys=OFF")
                raw.execute(
                    """
                    INSERT INTO item_neighbors (item_id, neighbor_id, score, surprise_score)
                    VALUES (?, ?, 0.99, 0.0)
                    """,
                    (a, 9_999_999),
                )
                raw.execute(
                    """
                    INSERT INTO item_neighbors (item_id, neighbor_id, score, surprise_score)
                    VALUES (?, ?, 0.98, 0.0)
                    """,
                    (9_999_998, b),
                )
                raw.commit()
            finally:
                raw.close()

            # Without the join/filter, INSERT into title_relations would raise
            # sqlite3.IntegrityError: FOREIGN KEY constraint failed.
            result = await title_relations_refresh.run(
                db, Settings(), should_stop=lambda: False
            )
            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["neighbor"], 1)

            rows = db.list_title_relations(a, relation="neighbor", limit=20)
            to_ids = {int(r["to_id"]) for r in rows}
            self.assertIn(b, to_ids)
            self.assertNotIn(9_999_999, to_ids)


    def test_theme_facets_queryable_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "t1",
                    "media_type": "movie",
                    "title": "Noir Night",
                    "year": 1945,
                    "genres": ["Crime"],
                }
            )
            db.replace_facets_of_type("theme", [(item_id, "theme", "neo-noir")])
            filtered = query_library(db, LibraryFilters(themes=["neo-noir"]))
            self.assertEqual(filtered["returned"], 1)
            from projectionist.library.facets import rebuild_library_facets

            rebuild_library_facets(db)
            filtered_after = query_library(db, LibraryFilters(themes=["neo-noir"]))
            self.assertEqual(filtered_after["returned"], 1)


class NeighborsFeedTests(unittest.TestCase):
    def test_neighbors_payload_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = db.upsert_library_item(
                {
                    "rating_key": "seed",
                    "media_type": "movie",
                    "title": "Seed",
                    "year": 2000,
                    "genres": ["Sci-Fi"],
                    "summary": (
                        "Amateur bakers compete around a signature bake inside a failing colony."
                    ),
                }
            )
            twin = db.upsert_library_item(
                {
                    "rating_key": "twin",
                    "media_type": "movie",
                    "title": "Twin",
                    "year": 2001,
                    "genres": ["Sci-Fi"],
                }
            )
            odd = db.upsert_library_item(
                {
                    "rating_key": "odd",
                    "media_type": "movie",
                    "title": "Odd",
                    "year": 2002,
                    "genres": ["Romance"],
                    "summary": (
                        "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."
                    ),
                }
            )
            db.set_neighbors(seed, [(twin, 0.99, 0.1), (odd, 0.9, 0.85)])
            similar = neighbors_payload(db, seed, mode="similar", limit=5)
            surprising = neighbors_payload(db, seed, mode="surprising", limit=5)
            self.assertEqual(similar["items"][0]["title"], "Twin")
            self.assertEqual(surprising["items"][0]["title"], "Odd")
            self.assertIn("amateur bakers", surprising["items"][0]["plot_link"].lower())
            self.assertNotIn("almost no shared", surprising["items"][0]["plot_link"].lower())
            self.assertIn("score", similar["items"][0])
            self.assertIn("surprise_score", similar["items"][0])
            # surprise = cosine × (1 − overlap) → Odd: 0.85 = 0.9 × (1 − overlap)
            self.assertAlmostEqual(surprising["items"][0]["metadata_overlap"], 1.0 - (0.85 / 0.9), places=5)
            self.assertEqual(surprising["seed"]["genres"], ["Sci-Fi"])


class ExploreFeedApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_feed_endpoints(self) -> None:
        now = int(time.time())
        today = date.today()
        self.db.upsert_library_item(
            {
                "rating_key": "rk-new",
                "media_type": "movie",
                "title": "Just Added",
                "year": today.year,
                "added_at": now - 1000,
                "release_date": today.isoformat(),
                "poster_url": "https://example.com/p.jpg",
            }
        )
        recent = self.client.get("/api/library/feeds/recently-added", params={"days": 7})
        self.assertEqual(recent.status_code, 200)
        body = recent.json()
        self.assertEqual(body["feed"], "recently-added")
        self.assertGreaterEqual(body["total"], 1)

        releases = self.client.get("/api/library/feeds/recent-releases", params={"days": 30})
        self.assertEqual(releases.status_code, 200)
        self.assertEqual(releases.json()["feed"], "recent-releases")

        paged = self.client.get(
            "/api/library/feeds/recently-added",
            params={"days": 7, "limit": 1, "offset": 0, "media_type": "movie"},
        )
        self.assertEqual(paged.status_code, 200)
        body_paged = paged.json()
        self.assertEqual(body_paged["feed"], "recently-added")
        self.assertIn("total", body_paged)
        self.assertIn("has_more", body_paged)
        self.assertEqual(body_paged["media_type"], "movie")

        otd = self.client.get("/api/library/feeds/on-this-day")
        self.assertEqual(otd.status_code, 200)
        self.assertEqual(otd.json()["feed"], "on-this-day")
        self.assertIn(otd.json()["mode"], {"calendar", "milestone_fallback"})

        for feed in ("director-spotlight", "genre-spotlight", "seasonal-spotlight", "unfinished", "afterglow"):
            spotlight = self.client.get(f"/api/library/feeds/{feed}")
            self.assertEqual(spotlight.status_code, 200)
            self.assertEqual(spotlight.json()["feed"], feed)

        motifs = self.client.get("/api/library/motifs", params={"limit": 10})
        self.assertEqual(motifs.status_code, 200)
        self.assertEqual(motifs.json()["facet_type"], "motif")

    def test_neighbors_endpoint_by_item_id(self) -> None:
        seed = self.db.upsert_library_item(
            {
                "rating_key": "s1",
                "media_type": "movie",
                "title": "Seed",
                "year": 1982,
                "tmdb_id": 1,
            }
        )
        other = self.db.upsert_library_item(
            {
                "rating_key": "s2",
                "media_type": "movie",
                "title": "Neighbor",
                "year": 1984,
                "tmdb_id": 2,
            }
        )
        self.db.set_neighbors(seed, [(other, 0.88, 0.4)])
        response = self.client.get(
            f"/api/library/neighbors/{seed}",
            params={"mode": "similar", "limit": 5},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["item_id"], seed)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["title"], "Neighbor")
        self.assertAlmostEqual(payload["items"][0]["score"], 0.88, places=2)


class AgentRelationToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_relations_and_titles_by_person(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            a = db.upsert_library_item(
                {
                    "rating_key": "a",
                    "media_type": "movie",
                    "title": "Alpha",
                    "year": 2000,
                    "tmdb_collection_id": 7,
                    "structured_credits": [
                        {
                            "tmdb_person_id": 42,
                            "name": "Jane Director",
                            "department": "Directing",
                            "job": "Director",
                            "character": "",
                            "billing_order": 0,
                        }
                    ],
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "b",
                    "media_type": "movie",
                    "title": "Beta",
                    "year": 2001,
                    "tmdb_collection_id": 7,
                    "structured_credits": [
                        {
                            "tmdb_person_id": 42,
                            "name": "Jane Director",
                            "department": "Directing",
                            "job": "Director",
                            "character": "",
                            "billing_order": 0,
                        }
                    ],
                }
            )
            refresh_title_relations(db)
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)

            rel = json.loads(
                await registry.execute("list_relations", {"item_id": a, "relation": "collection"})
            )
            self.assertGreaterEqual(rel["returned"], 1)
            self.assertEqual(rel["items"][0]["to_id"], b)

            people = json.loads(
                await registry.execute("titles_by_person", {"tmdb_person_id": 42})
            )
            titles = {item["title"] for item in people["items"]}
            self.assertEqual(titles, {"Alpha", "Beta"})


if __name__ == "__main__":
    unittest.main()
