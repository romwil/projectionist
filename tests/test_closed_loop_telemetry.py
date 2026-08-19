"""Phase 0 closed-loop substrate: migration, ingestion, hit_count upserts."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.db.migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS
from projectionist.telemetry.ingestion import (
    schedule_closed_loop_event,
    scrub_closed_loop_payload,
    upsert_closed_loop_event,
    upsert_closed_loop_event_sync,
)


class ClosedLoopMigrationTests(unittest.TestCase):
    def test_migration_43_registered(self) -> None:
        versions = {version: name for version, name, _ in MIGRATIONS}
        self.assertEqual(versions[43], "closed_loop_augmentation")
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 43)

    def test_tables_created_on_database_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            try:
                with db.connect() as conn:
                    tables = {
                        str(row[0])
                        for row in conn.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                    self.assertIn("telemetry_events", tables)
                    self.assertIn("staged_augmentations", tables)
                    applied = {
                        int(row[0])
                        for row in conn.execute("SELECT version FROM schema_version").fetchall()
                    }
                    self.assertIn(43, applied)
            finally:
                db.close()


class ClosedLoopIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def _wait_for_closed_loop_threads(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("closed-loop-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_upsert_increments_hit_count(self) -> None:
        upsert_closed_loop_event_sync(
            self.db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key="history miniseries",
            payload={"media_type": "tv"},
        )
        upsert_closed_loop_event_sync(
            self.db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key="history miniseries",
            payload={"media_type": "tv", "source": "gaps"},
        )
        rows = self.db.list_closed_loop_events(event_type="unmapped_token", entity_type="facet")
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["hit_count"]), 2)
        payload = json.loads(rows[0]["payload_json"])
        self.assertEqual(payload.get("source"), "gaps")
        self.assertNotIn("api_key", payload)

    def test_scrub_strips_secrets(self) -> None:
        cleaned = scrub_closed_loop_payload(
            {
                "token": "secret-value",
                "plex_token": "abc",
                "api_key": "k",
                "media_type": "movie",
                "prompt": "should not persist",
            }
        )
        self.assertEqual(cleaned, {"media_type": "movie"})

    def test_sync_upsert_never_stores_secrets(self) -> None:
        upsert_closed_loop_event_sync(
            self.db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key="noir",
            payload={"api_token": "leak", "alias": "film noir"},
        )
        rows = [
            r
            for r in self.db.list_closed_loop_events(entity_type="facet")
            if r["entity_key"] == "noir"
        ]
        self.assertEqual(len(rows), 1)
        payload = json.loads(rows[0]["payload_json"])
        self.assertEqual(payload, {"alias": "film noir"})

    def test_async_upsert_via_to_thread(self) -> None:
        asyncio.run(
            upsert_closed_loop_event(
                self.db,
                event_type="search_miss",
                priority_tier="P2",
                entity_type="title",
                entity_key="tmdb:123",
                payload={"reason": "sparse"},
            )
        )
        rows = self.db.list_closed_loop_events(priority_tier="P2", entity_type="title")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entity_key"], "tmdb:123")

    def test_schedule_fire_and_forget_without_loop(self) -> None:
        schedule_closed_loop_event(
            self.db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key="cyberpunk",
            payload={"hit": 1},
        )
        self._wait_for_closed_loop_threads()
        rows = self.db.list_closed_loop_events(entity_type="facet")
        keys = {r["entity_key"] for r in rows}
        self.assertIn("cyberpunk", keys)

    def test_staged_augmentation_insert(self) -> None:
        row_id = self.db.insert_staged_augmentation(
            task_name="facet_taxonomy_audit",
            priority_tier="P1",
            target_entity_type="facet",
            target_entity_id="cyberpunk",
            candidate_data_json=json.dumps({"alias": "cyber-punk"}),
            confidence_score=0.85,
        )
        self.assertGreater(row_id, 0)
        staged = self.db.list_staged_augmentations(task_name="facet_taxonomy_audit")
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["status"], "pending")
        self.assertAlmostEqual(float(staged[0]["confidence_score"]), 0.85)

    def test_closed_loop_unique_keys_are_capped(self) -> None:
        from projectionist.library.db import _telemetry as telemetry_mod

        original = telemetry_mod.TELEMETRY_EVENTS_MAX_ROWS
        telemetry_mod.TELEMETRY_EVENTS_MAX_ROWS = 5
        try:
            for i in range(12):
                upsert_closed_loop_event_sync(
                    self.db,
                    event_type="unmapped_token",
                    priority_tier="P3",
                    entity_type="facet",
                    entity_key=f"cap-{i}",
                )
            rows = self.db.list_closed_loop_events(entity_type="facet")
            capped = [row for row in rows if str(row["entity_key"]).startswith("cap-")]
            self.assertLessEqual(len(capped), 5)
        finally:
            telemetry_mod.TELEMETRY_EVENTS_MAX_ROWS = original


if __name__ == "__main__":
    unittest.main()
