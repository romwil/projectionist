"""Value-based tests for Wave 3: Explore feeds, title_relations, neighbors API."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.agent.tools import ToolRegistry
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.library.feeds import (
    feed_on_this_day,
    feed_recent_releases,
    feed_recently_added,
    neighbors_payload,
)
from curatorx.library.query import LibraryFilters, query_library
from curatorx.library.relations import refresh_title_relations
from curatorx.scheduler.tasks import llm_theme_tagging, title_relations_refresh


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

    async def test_llm_theme_stub_skips_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            result = await llm_theme_tagging.run(db, Settings(), should_stop=lambda: False)
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_llm_api_key")

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
            from curatorx.library.facets import rebuild_library_facets

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
                }
            )
            db.set_neighbors(seed, [(twin, 0.99, 0.1), (odd, 0.9, 0.85)])
            similar = neighbors_payload(db, seed, mode="similar", limit=5)
            surprising = neighbors_payload(db, seed, mode="surprising", limit=5)
            self.assertEqual(similar["items"][0]["title"], "Twin")
            self.assertEqual(surprising["items"][0]["title"], "Odd")
            self.assertIn("score", similar["items"][0])
            self.assertIn("surprise_score", similar["items"][0])


class ExploreFeedApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
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

        otd = self.client.get("/api/library/feeds/on-this-day")
        self.assertEqual(otd.status_code, 200)
        self.assertEqual(otd.json()["feed"], "on-this-day")
        self.assertIn(otd.json()["mode"], {"calendar", "milestone_fallback"})

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
