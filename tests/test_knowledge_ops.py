"""Knowledge Operations dashboard APIs and coverage closed-loop tests."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from projectionist.facets.closed_loop import bind_closed_loop_database
from projectionist.library.db import Database
from projectionist.scheduler.tasks.coverage_deficit_audit import CoverageDeficitAudit, TASK_NAME
from projectionist.scheduler.tasks.coverage_signals import emit_unmapped_keyword_signals
from projectionist.scheduler.tasks.keyword_theme_tagging import run as keyword_theme_run
from projectionist.telemetry.coverage import EVENT_COVERAGE_DEFICIT
from projectionist.telemetry.explore import (
    EVENT_BAD_NEIGHBOR,
    EVENT_EXPLORE_MISS,
    schedule_bad_neighbor_match,
    schedule_explore_miss,
)
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync
from projectionist.web import augmentation_routes as aug_routes
from projectionist.web import knowledge_ops_routes as routes
from projectionist.web.staged_augmentation_promote import act_label_for_row


class KnowledgeOpsDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_summary_funnel_and_aggregates(self) -> None:
        upsert_closed_loop_event_sync(
            self.db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key="noirish",
            payload={"context_source": "gaps"},
        )
        self.db.insert_staged_augmentation(
            task_name="facet_taxonomy_audit",
            priority_tier="P1",
            target_entity_type="facet",
            target_entity_id="noirish",
            candidate_data_json=json.dumps({"alias": "noirish", "hit_count": 4}),
            confidence_score=0.72,
            status="pending",
        )
        summary = self.db.closed_loop_knowledge_ops_summary()
        self.assertGreaterEqual(summary["pending_facet_candidates"], 1)
        self.assertIn("funnel", summary)
        funnel = self.db.closed_loop_funnel_stats(min_hit_count=1)
        self.assertGreaterEqual(funnel["observed"], 1)
        agg = self.db.staged_augmentations_aggregates()
        self.assertIn("facet_taxonomy_audit", agg["by_task"])
        top = self.db.top_closed_loop_events(event_type="unmapped_token", limit=5)
        self.assertEqual(top[0]["entity_key"], "noirish")


class KnowledgeOpsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name) / "config"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "test.db")
        routes._db_factory = lambda: self.db
        routes._data_dir = self.data_dir
        bind_closed_loop_database(lambda: self.db)
        self._old_data = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.data_dir)

    def tearDown(self) -> None:
        bind_closed_loop_database(None)
        if self._old_data is not None:
            os.environ["DATA_DIR"] = self._old_data
        else:
            os.environ.pop("DATA_DIR", None)
        routes._db_factory = None
        routes._data_dir = None
        self.db.close()
        self._tmpdir.cleanup()

    def test_route_handlers(self) -> None:
        upsert_closed_loop_event_sync(
            self.db,
            event_type=EVENT_COVERAGE_DEFICIT,
            priority_tier="P2",
            entity_type="library_item",
            entity_key="42",
            payload={"deficit_kind": "metadata"},
        )
        summary = routes.knowledge_ops_summary(user={"role": "owner"})
        self.assertIn("registry", summary)
        self.assertIn("coverage", summary)

        registry = routes.knowledge_ops_taxonomy_registry(user={"role": "owner"})
        self.assertIn("top_unresolved_facets", registry)
        self.assertIn("concept_count", registry["registry"])

        trend = routes.knowledge_ops_telemetry_trend(days=7, user={"role": "owner"})
        self.assertEqual(trend["days"], 7)

        top = routes.knowledge_ops_top_events(limit=10, user={"role": "owner"})
        self.assertGreaterEqual(top["count"], 1)


class CoverageClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_emit_unmapped_keyword_signals(self) -> None:
        bind_closed_loop_database(lambda: self.db)
        items = [
            {"id": 1, "keywords": json.dumps(["totally unknown keyword", "revenge"])},
            {"id": 2, "keywords": json.dumps(["totally unknown keyword"])},
            {"id": 3, "keywords": json.dumps(["totally unknown keyword"])},
        ]
        emitted = emit_unmapped_keyword_signals(items, min_item_count=2)
        self.assertGreaterEqual(emitted, 1)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            rows = self.db.list_closed_loop_events(event_type=EVENT_COVERAGE_DEFICIT)
            if any(r["entity_type"] == "keyword" for r in rows):
                break
            time.sleep(0.05)
        rows = self.db.list_closed_loop_events(event_type=EVENT_COVERAGE_DEFICIT)
        self.assertTrue(any(r["entity_type"] == "keyword" for r in rows))

    def test_coverage_deficit_audit_stages(self) -> None:
        upsert_closed_loop_event_sync(
            self.db,
            event_type=EVENT_COVERAGE_DEFICIT,
            priority_tier="P2",
            entity_type="keyword",
            entity_key="obscure motif",
            payload={"deficit_kind": "theme_keyword", "item_count": 5},
        )
        upsert_closed_loop_event_sync(
            self.db,
            event_type=EVENT_COVERAGE_DEFICIT,
            priority_tier="P2",
            entity_type="keyword",
            entity_key="obscure motif",
            payload={"deficit_kind": "theme_keyword", "item_count": 5},
        )
        task = CoverageDeficitAudit(self.db, min_hit_count=2)

        async def _run() -> None:
            stats = await task.execute_run()
            self.assertGreaterEqual(stats["staged"], 1)

        asyncio.run(_run())
        pending = self.db.list_staged_augmentations(status="pending", task_name=TASK_NAME)
        self.assertEqual(len(pending), 1)
        candidate = json.loads(pending[0]["candidate_data_json"])
        self.assertEqual(candidate["deficit_kind"], "theme_keyword")

    def test_keyword_theme_task_emits_signals(self) -> None:
        from projectionist.config_store import Settings

        bind_closed_loop_database(lambda: self.db)
        self.db.upsert_library_item(
            {
                "rating_key": "rk1",
                "title": "Test Movie",
                "media_type": "movie",
                "keywords": json.dumps(["unmapped keyword xyz", "revenge"]),
            }
        )
        settings = Settings()
        result = asyncio.run(keyword_theme_run(self.db, settings, lambda: False))
        self.assertEqual(result["status"], "completed")
        self.assertIn("coverage_signals", result)


class StagedPromoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name) / "config"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.data_dir / "test.db")
        aug_routes._db_factory = lambda: self.db
        aug_routes._data_dir = self.data_dir
        aug_routes._settings_factory = lambda: __import__(
            "projectionist.config_store", fromlist=["Settings"]
        ).Settings()
        self._scheduler_calls: list[str] = []
        aug_routes._scheduler_trigger = lambda name: (
            self._scheduler_calls.append(name) or {"status": "started", "task": name}
        )

    def tearDown(self) -> None:
        aug_routes._db_factory = None
        aug_routes._data_dir = None
        aug_routes._settings_factory = None
        aug_routes._scheduler_trigger = None
        self.db.close()
        self._tmpdir.cleanup()

    def test_act_labels_for_non_facet_rows(self) -> None:
        demand_row = {
            "task_name": "entity_memory_enrichment",
            "target_entity_type": "title",
            "status": "pending",
        }
        self.assertEqual(act_label_for_row(demand_row), "Run enrichment")
        coverage_row = {
            "task_name": "coverage_deficit_audit",
            "target_entity_type": "keyword",
            "candidate_data_json": json.dumps({"deficit_kind": "theme_keyword"}),
        }
        self.assertEqual(act_label_for_row(coverage_row), "Run theme tagging")

    def test_approve_coverage_theme_keyword_queues_task(self) -> None:
        row_id = self.db.insert_staged_augmentation(
            task_name="coverage_deficit_audit",
            priority_tier="P2",
            target_entity_type="keyword",
            target_entity_id="obscure motif",
            candidate_data_json=json.dumps(
                {"deficit_kind": "theme_keyword", "keyword": "obscure motif", "hit_count": 4}
            ),
            confidence_score=0.72,
            status="pending",
        )

        async def _approve() -> None:
            result = await aug_routes.approve_staged_augmentation(
                row_id, user={"role": "owner"}
            )
            self.assertEqual(result["acted"]["action"], "queued_keyword_theme_tagging")

        asyncio.run(_approve())
        self.assertEqual(self._scheduler_calls, ["keyword_theme_tagging"])
        updated = self.db.get_staged_augmentation(row_id)
        self.assertEqual(updated["status"], "approved")

    def test_approve_entity_memory_runs_research(self) -> None:
        from unittest.mock import patch

        from projectionist.config_store import Settings

        settings = Settings()
        settings.tmdb_api_key = "test-key"
        aug_routes._settings_factory = lambda: settings

        row_id = self.db.insert_staged_augmentation(
            task_name="entity_memory_enrichment",
            priority_tier="P2",
            target_entity_type="title",
            target_entity_id="inception",
            candidate_data_json=json.dumps(
                {"name": "Inception", "entity_type": "title", "hit_count": 3, "reason": "sparse"}
            ),
            confidence_score=0.64,
            status="pending",
        )

        async def _approve() -> None:
            with patch(
                "projectionist.web.staged_augmentation_promote._enrich_entity",
                return_value=True,
            ) as mocked:
                result = await aug_routes.approve_staged_augmentation(
                    row_id, user={"role": "owner"}
                )
                self.assertTrue(mocked.called)
            self.assertEqual(result["acted"]["action"], "repository_research")

        asyncio.run(_approve())


class ExploreTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        bind_closed_loop_database(lambda: self.db)

    def tearDown(self) -> None:
        bind_closed_loop_database(None)
        self.db.close()
        self._tmpdir.cleanup()

    def _wait_closed_loop(self, timeout: float = 2.0) -> None:
        import threading
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("closed-loop-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_explore_miss_and_bad_neighbor_emit(self) -> None:
        schedule_explore_miss(
            feed_id="seasonal-spotlight",
            entity_key="seasonal-spotlight",
            extra={"note": "No matches"},
        )
        schedule_bad_neighbor_match(seed_item_id=1, neighbor_item_id=2)
        self._wait_closed_loop()
        explore_rows = self.db.list_closed_loop_events(event_type=EVENT_EXPLORE_MISS)
        neighbor_rows = self.db.list_closed_loop_events(event_type=EVENT_BAD_NEIGHBOR)
        self.assertEqual(len(explore_rows), 1)
        self.assertEqual(len(neighbor_rows), 1)
        self.assertEqual(neighbor_rows[0]["entity_key"], "1:2")

    def test_remove_neighbor_edge(self) -> None:
        self.db.upsert_library_item(
            {"rating_key": "rk-seed", "title": "Seed", "media_type": "movie"}
        )
        self.db.upsert_library_item(
            {"rating_key": "rk-neighbor", "title": "Neighbor", "media_type": "movie"}
        )
        seed_id = int(self.db.library_item_by_rating_key("rk-seed")["id"])
        neighbor_id = int(self.db.library_item_by_rating_key("rk-neighbor")["id"])
        self.db.set_neighbors(seed_id, [(neighbor_id, 0.9, 0.4)])
        self.assertTrue(self.db.remove_neighbor_edge(seed_id, neighbor_id))
        self.assertFalse(self.db.remove_neighbor_edge(seed_id, neighbor_id))
        self.assertEqual(len(self.db.get_neighbors(seed_id)), 0)


if __name__ == "__main__":
    unittest.main()
