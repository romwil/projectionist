"""Release 4 — owner demand catch-up: kinship miss → idle priority."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.facets.closed_loop import bind_closed_loop_database
from projectionist.library.db import Database
from projectionist.library.feeds import neighbors_payload
from projectionist.notifications.recommendation_reasons import pick_linked_unwatched
from projectionist.scheduler.tasks import plot_neighbors
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync
from projectionist.telemetry.kinship_miss import (
    EVENT_KINSHIP_MISS,
    KINSHIP_MISS_QUEUE_CAP,
    preferred_item_ids,
    prioritize_enrichment_rows,
    schedule_kinship_miss,
)


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 2015,
        "genres": ["Drama"],
        "keywords": [],
        "summary": "A quiet story about bakers and rivalry.",
        "tmdb_overview": "Amateur bakers compete.",
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


class KinshipMissEmitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "miss.db")
        bind_closed_loop_database(lambda: self.db)

    def tearDown(self) -> None:
        bind_closed_loop_database(None)
        self.db.close()
        self._tmpdir.cleanup()

    def _wait_closed_loop(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("closed-loop-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_empty_more_like_this_records_miss(self) -> None:
        seed = _title(self.db, rating_key="bake", tmdb_id=101, title="Bake Show")
        payload = neighbors_payload(self.db, seed, mode="similar", limit=8)
        self.assertEqual(payload["items"], [])
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(
            event_type=EVENT_KINSHIP_MISS, entity_type="title"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entity_key"], str(seed))
        self.assertEqual(int(rows[0]["hit_count"]), 1)

    def test_queue_cap_blocks_new_keys_allows_hit_bump(self) -> None:
        with patch(
            "projectionist.telemetry.kinship_miss.KINSHIP_MISS_QUEUE_CAP",
            2,
        ):
            upsert_closed_loop_event_sync(
                self.db,
                event_type=EVENT_KINSHIP_MISS,
                priority_tier="P2",
                entity_type="title",
                entity_key="1",
                payload={"item_id": 1, "reason": "more_like_this_empty"},
            )
            upsert_closed_loop_event_sync(
                self.db,
                event_type=EVENT_KINSHIP_MISS,
                priority_tier="P2",
                entity_type="title",
                entity_key="2",
                payload={"item_id": 2, "reason": "more_like_this_empty"},
            )
            # Cap is 2 — new key blocked.
            ok = schedule_kinship_miss(item_id=3, reason="more_like_this_empty")
            self.assertFalse(ok)
            self._wait_closed_loop()
            self.assertEqual(
                len(
                    self.db.list_closed_loop_events(
                        event_type=EVENT_KINSHIP_MISS, entity_type="title", limit=20
                    )
                ),
                2,
            )
            # Existing key still bumps.
            ok_bump = schedule_kinship_miss(item_id=1, reason="more_like_this_empty")
            self.assertTrue(ok_bump)
            self._wait_closed_loop()
            rows = self.db.list_closed_loop_events(
                event_type=EVENT_KINSHIP_MISS, entity_type="title", limit=20
            )
            by_key = {r["entity_key"]: int(r["hit_count"]) for r in rows}
            self.assertEqual(by_key["1"], 2)


class DemandPriorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "prio.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_idle_batch_prefers_missed_item_id(self) -> None:
        cold = _title(
            self.db,
            rating_key="cold",
            tmdb_id=201,
            title="Cold Title",
            release_date="",
            tmdb_overview="",
        )
        hot = _title(
            self.db,
            rating_key="hot",
            tmdb_id=202,
            title="Hot Miss",
            release_date="",
            tmdb_overview="",
        )
        # Bump hot harder so list_closed_loop_events orders it first.
        for _ in range(3):
            upsert_closed_loop_event_sync(
                self.db,
                event_type=EVENT_KINSHIP_MISS,
                priority_tier="P2",
                entity_type="title",
                entity_key=str(hot),
                payload={"item_id": hot, "reason": "more_like_this_empty"},
            )
        prefer = preferred_item_ids(self.db, limit=10)
        self.assertEqual(prefer[0], hot)

        def _prefer_metadata(database: Database, item_id: int):
            if not database.item_still_needs_metadata(int(item_id)):
                return None
            return database.library_item_by_id(int(item_id))

        backlog = prioritize_enrichment_rows(
            self.db,
            self.db.items_needing_metadata_enrichment(limit=10),
            limit=10,
            include_item_id=_prefer_metadata,
        )
        self.assertGreaterEqual(len(backlog), 2)
        self.assertEqual(int(backlog[0]["id"]), hot)
        self.assertIn(cold, {int(r["id"]) for r in backlog})

    def test_plot_neighbors_orders_demand_seeds_first(self) -> None:
        a = _title(self.db, rating_key="a", tmdb_id=301, title="Alpha")
        b = _title(self.db, rating_key="b", tmdb_id=302, title="Beta")
        self.db.set_embeddings([(a, [1.0, 0.0]), (b, [0.0, 1.0])])
        upsert_closed_loop_event_sync(
            self.db,
            event_type=EVENT_KINSHIP_MISS,
            priority_tier="P2",
            entity_type="title",
            entity_key=str(b),
            payload={"item_id": b, "reason": "more_like_this_empty"},
        )

        async def _run() -> dict:
            return await plot_neighbors.run(self.db, Settings(), lambda: False)

        result = asyncio.run(_run())
        self.assertEqual(result.get("demand_prioritized"), 1)
        self.assertGreaterEqual(int(result.get("seeds") or 0), 1)


class BridgeZeroPeersTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "bridge.db")
        bind_closed_loop_database(lambda: self.db)

    def tearDown(self) -> None:
        bind_closed_loop_database(None)
        self.db.close()
        self._tmpdir.cleanup()

    def _wait_closed_loop(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("closed-loop-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_bridge_zero_peers_records_miss_for_seeds(self) -> None:
        seed = _title(
            self.db,
            rating_key="seed",
            tmdb_id=401,
            title="Finished Seed",
            view_count=1,
        )
        watched = [
            {
                "id": seed,
                "title": "Finished Seed",
                "year": 2015,
                "media_type": "movie",
                "view_count": 1,
                "seed_source": "completion",
                "tmdb_collection_id": None,
            }
        ]
        pick = pick_linked_unwatched(self.db, watched_rows=watched)
        self.assertIsNone(pick)
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(
            event_type=EVENT_KINSHIP_MISS, entity_type="title"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entity_key"], str(seed))


class QueueCapConstantTests(unittest.TestCase):
    def test_cap_is_bounded(self) -> None:
        self.assertGreaterEqual(KINSHIP_MISS_QUEUE_CAP, 50)
        self.assertLessEqual(KINSHIP_MISS_QUEUE_CAP, 5000)


if __name__ == "__main__":
    unittest.main()
