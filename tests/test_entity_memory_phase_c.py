"""Phase C P2 pilot: metadata_demand telemetry + entity_memory_enrichment staging."""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

from projectionist.config_store import Settings
from projectionist.facets.closed_loop import bind_closed_loop_database
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks import register_all
from projectionist.scheduler.tasks.entity_memory_enrichment import (
    TASK_NAME,
    EntityMemoryDemandPilot,
    confidence_for_demand_hits,
    entities_from_demand_signals,
    run,
)
from projectionist.telemetry.demand import EVENT_METADATA_DEMAND, schedule_metadata_demand
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync


class MetadataDemandEmitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
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

    def test_schedule_metadata_demand_upserts_p2_event(self) -> None:
        schedule_metadata_demand(
            entity_type="person",
            name="Akira Kurosawa",
            reason="stale_snapshot",
            entity_id="ent-1",
            context_source="recall",
        )
        schedule_metadata_demand(
            entity_type="person",
            name="akira kurosawa",
            reason="stale_snapshot",
            context_source="recall",
        )
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(
            event_type=EVENT_METADATA_DEMAND, entity_type="person"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["priority_tier"], "P2")
        self.assertEqual(rows[0]["entity_key"], "akira kurosawa")
        self.assertEqual(int(rows[0]["hit_count"]), 2)
        payload = json.loads(rows[0]["payload_json"])
        self.assertEqual(payload.get("reason"), "stale_snapshot")
        # Last upsert wins for payload_json; entity_key remains the aggregate key.
        self.assertEqual(str(payload.get("name") or "").casefold(), "akira kurosawa")

    def test_schedule_skips_invalid_entity_type(self) -> None:
        schedule_metadata_demand(entity_type="facet", name="noir")
        self._wait_closed_loop()
        self.assertEqual(self.db.list_closed_loop_events(event_type=EVENT_METADATA_DEMAND), [])


class EntityMemoryDemandPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def _seed_hits(self, name: str, *, entity_type: str = "person", hits: int = 3) -> None:
        for _ in range(hits):
            upsert_closed_loop_event_sync(
                self.db,
                event_type=EVENT_METADATA_DEMAND,
                priority_tier="P2",
                entity_type=entity_type,
                entity_key=name.casefold(),
                payload={"name": name, "reason": "stale_snapshot", "context_source": "recall"},
            )

    def test_confidence_below_floor_for_single_hit(self) -> None:
        self.assertEqual(confidence_for_demand_hits(1), 0.0)
        self.assertGreaterEqual(confidence_for_demand_hits(2), 0.60)
        self.assertLess(confidence_for_demand_hits(100), 0.90)

    def test_pilot_stages_never_direct_commits(self) -> None:
        self._seed_hits("Akira Kurosawa", hits=3)
        task = EntityMemoryDemandPilot(self.db, min_hit_count=2)
        self.assertFalse(task.enable_direct_commit)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)
        pending = self.db.list_staged_augmentations(status="pending", task_name=TASK_NAME)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["priority_tier"], "P2")
        self.assertEqual(pending[0]["target_entity_type"], "person")
        candidate = json.loads(pending[0]["candidate_data_json"])
        self.assertEqual(candidate["action"], "refresh_repository_research")
        self.assertEqual(candidate["name"], "Akira Kurosawa")

    def test_pilot_skips_already_pending(self) -> None:
        self._seed_hits("Akira Kurosawa", hits=3)
        task = EntityMemoryDemandPilot(self.db)
        first = asyncio.run(task.execute_run())
        second = asyncio.run(task.execute_run())
        self.assertEqual(first["staged"], 1)
        self.assertEqual(second["staged"], 0)
        self.assertEqual(second["skipped"], 1)

    def test_async_db_paths_offload_via_run_db(self) -> None:
        """fetch_telemetry_signals / _already_staged must await run_db (to_thread)."""
        task = EntityMemoryDemandPilot(self.db, min_hit_count=2)
        with patch(
            "projectionist.scheduler.tasks.entity_memory_enrichment.run_db",
            new_callable=AsyncMock,
        ) as run_db_mock:
            run_db_mock.return_value = []
            signals = asyncio.run(task.fetch_telemetry_signals())
            self.assertEqual(signals, [])
            run_db_mock.assert_awaited()
            passed = run_db_mock.await_args.args[0]
            self.assertIs(passed.__self__, self.db)
            self.assertIs(passed.__func__, type(self.db).list_closed_loop_events)

            run_db_mock.reset_mock()
            run_db_mock.return_value = [
                {
                    "target_entity_type": "person",
                    "target_entity_id": "akira kurosawa",
                    "status": "pending",
                }
            ]
            staged = asyncio.run(task._already_staged("person", "Akira Kurosawa"))
            self.assertTrue(staged)
            run_db_mock.assert_awaited_once()
            passed = run_db_mock.await_args.args[0]
            self.assertIs(passed.__self__, self.db)
            self.assertIs(passed.__func__, type(self.db).list_staged_augmentations)

    def test_entities_from_demand_prefers_known_rows(self) -> None:
        saved = self.db.save_repository_research(
            entity_type="person",
            name="Akira Kurosawa",
            payload={"identity": {"name": "Akira Kurosawa"}, "warnings": []},
            external_ids={"tmdb_id": 5026},
        )
        self._seed_hits("Akira Kurosawa", hits=1)
        self._seed_hits("Nobody Known", hits=1)
        entities = entities_from_demand_signals(self.db, limit=5)
        names = [e["name"] for e in entities]
        self.assertIn("Akira Kurosawa", names)
        known = next(e for e in entities if e["name"] == "Akira Kurosawa")
        self.assertEqual(known["id"], saved["entity_id"])
        self.assertEqual(known["external_ids"].get("tmdb_id"), 5026)
        stub = next(e for e in entities if e["name"] == "Nobody Known")
        self.assertTrue(stub.get("from_demand_stub"))


class EntityMemoryEnrichmentRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        self.settings = Settings(tmdb_api_key="test-key")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_run_demand_prioritizes_and_uses_research_writer(self) -> None:
        self.db.save_repository_research(
            entity_type="person",
            name="Akira Kurosawa",
            payload={"identity": {"name": "Akira Kurosawa"}, "warnings": []},
            external_ids={"tmdb_id": 5026},
        )
        for _ in range(2):
            upsert_closed_loop_event_sync(
                self.db,
                event_type=EVENT_METADATA_DEMAND,
                priority_tier="P2",
                entity_type="person",
                entity_key="akira kurosawa",
                payload={"name": "Akira Kurosawa", "reason": "stale_snapshot"},
            )

        calls: list[Dict[str, Any]] = []

        def _fake_person(settings, *, name, tmdb_id=None, db=None):  # noqa: ANN001
            calls.append({"name": name, "tmdb_id": tmdb_id})
            return {"identity": {"name": name, "tmdb_id": tmdb_id}}

        with patch(
            "projectionist.scheduler.tasks.entity_memory_enrichment.research_person",
            side_effect=_fake_person,
        ):
            result = asyncio.run(run(self.db, self.settings, lambda: False))

        self.assertEqual(result["status"], "completed")
        self.assertGreaterEqual(result["enriched"], 1)
        self.assertGreaterEqual(result["demand_prioritized"], 1)
        self.assertGreaterEqual(result["staged"], 1)
        self.assertEqual(calls[0]["name"], "Akira Kurosawa")
        self.assertEqual(calls[0]["tmdb_id"], 5026)
        # No confidence-driven commit_direct path — only staging + explicit research_*.
        self.assertEqual(result.get("stage_direct_commits", 0), 0)

    def test_register_all_includes_severity_task(self) -> None:
        scheduler = IdleScheduler(self.db, Path(self._tmpdir.name))
        register_all(scheduler)
        self.assertIn(TASK_NAME, scheduler._definitions)
        definition = scheduler._definitions[TASK_NAME]
        self.assertEqual(definition.run_interval_seconds, 86400)


if __name__ == "__main__":
    unittest.main()
