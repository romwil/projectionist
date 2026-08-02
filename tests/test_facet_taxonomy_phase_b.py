"""Phase B: P1 miss telemetry, FacetTaxonomyAudit staging, overlay promote."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from projectionist.facets.closed_loop import (
    bind_closed_loop_database,
    resolve_closed_loop_database,
    schedule_unmapped_facet_tokens,
)
from projectionist.facets.overlay import promote_facet_alias_to_overlay
from projectionist.facets.registry import reload_registry, reset_registry_cache
from projectionist.facets.resolve import resolve_genre_ids
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks import register_all
from projectionist.scheduler.tasks.facet_taxonomy_audit import (
    FacetTaxonomyAudit,
    TASK_NAME,
    confidence_for_hit_count,
)
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync


class FacetMissTelemetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        bind_closed_loop_database(lambda: self.db)
        reset_registry_cache()
        self._old_data = os.environ.pop("DATA_DIR", None)
        reload_registry()

    def tearDown(self) -> None:
        bind_closed_loop_database(None)
        reset_registry_cache()
        if self._old_data is not None:
            os.environ["DATA_DIR"] = self._old_data
        else:
            os.environ.pop("DATA_DIR", None)
        self.db.close()
        self._tmpdir.cleanup()

    def _wait_closed_loop(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("closed-loop-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_resolve_unmapped_schedules_p1_facet_event(self) -> None:
        meta = resolve_genre_ids(
            [{"id": 18, "name": "Drama"}],
            "TotallyUnknownFacetToken",
            context_source="gaps",
            media_type="movie",
        )
        self.assertEqual(meta["genre_ids"], "")
        self.assertIn("TotallyUnknownFacetToken", meta["unresolved"])
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(
            event_type="unmapped_token", entity_type="facet"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["priority_tier"], "P1")
        self.assertEqual(rows[0]["entity_key"], "totallyunknownfacettoken")
        payload = json.loads(rows[0]["payload_json"])
        self.assertEqual(payload.get("context_source"), "gaps")
        self.assertEqual(payload.get("media_type"), "movie")

    def test_resolve_emit_telemetry_false_skips(self) -> None:
        resolve_genre_ids(
            [{"id": 18, "name": "Drama"}],
            "SkipMePlease",
            emit_telemetry=False,
        )
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(entity_type="facet")
        self.assertEqual(rows, [])

    def test_schedule_helper_increments_hits(self) -> None:
        schedule_unmapped_facet_tokens(["Noirish"], context_source="explore")
        schedule_unmapped_facet_tokens(["noirish"], context_source="explore")
        self._wait_closed_loop()
        rows = self.db.list_closed_loop_events(entity_type="facet")
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["hit_count"]), 2)

    def test_resolve_closed_loop_database_unbound_and_provider_errors(self) -> None:
        """Bound provider failures must never raise into resolve/demand callers."""
        bind_closed_loop_database(None)
        self.assertIsNone(resolve_closed_loop_database())

        def _boom():
            raise RuntimeError("db unavailable")

        bind_closed_loop_database(_boom)
        self.assertIsNone(resolve_closed_loop_database())

        bind_closed_loop_database(lambda: self.db)
        self.assertIs(resolve_closed_loop_database(), self.db)

        # Unbound schedule is a silent no-op (no thread, no raise).
        bind_closed_loop_database(None)
        schedule_unmapped_facet_tokens(["orphan-token"], context_source="test")
        self._wait_closed_loop()
        self.assertEqual(self.db.list_closed_loop_events(entity_type="facet"), [])


class FacetTaxonomyAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        reset_registry_cache()
        self._old_data = os.environ.pop("DATA_DIR", None)
        reload_registry()

    def tearDown(self) -> None:
        reset_registry_cache()
        if self._old_data is not None:
            os.environ["DATA_DIR"] = self._old_data
        else:
            os.environ.pop("DATA_DIR", None)
        self.db.close()
        self._tmpdir.cleanup()

    def _seed_hits(self, token: str, hits: int) -> None:
        for _ in range(hits):
            upsert_closed_loop_event_sync(
                self.db,
                event_type="unmapped_token",
                priority_tier="P1",
                entity_type="facet",
                entity_key=token.casefold(),
                payload={"raw": token, "context_source": "test"},
            )

    def test_confidence_never_reaches_direct_commit_floor(self) -> None:
        self.assertLess(confidence_for_hit_count(100), 0.90)
        self.assertGreaterEqual(confidence_for_hit_count(3), 0.60)
        self.assertEqual(confidence_for_hit_count(1), 0.0)

    def test_audit_stages_never_commits(self) -> None:
        self._seed_hits("cyberpunk-ish", 5)
        task = FacetTaxonomyAudit(self.db, min_hit_count=3)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["direct_commits"], 0)
        self.assertEqual(stats["staged"], 1)
        staged = self.db.list_staged_augmentations(task_name=TASK_NAME)
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["status"], "pending")
        self.assertEqual(staged[0]["target_entity_type"], "facet")
        data = json.loads(staged[0]["candidate_data_json"])
        self.assertEqual(data["alias"], "cyberpunk-ish")
        self.assertEqual(int(data["hit_count"]), 5)

    def test_audit_skips_already_pending(self) -> None:
        self._seed_hits("dup-token", 4)
        task = FacetTaxonomyAudit(self.db, min_hit_count=3)
        first = asyncio.run(task.execute_run())
        second = asyncio.run(task.execute_run())
        self.assertEqual(first["staged"], 1)
        self.assertEqual(second["staged"], 0)
        self.assertEqual(len(self.db.list_staged_augmentations(task_name=TASK_NAME)), 1)

    def test_async_db_paths_offload_via_run_db(self) -> None:
        """fetch_telemetry_signals / _already_staged must await run_db (to_thread)."""
        task = FacetTaxonomyAudit(self.db, min_hit_count=3)
        with mock.patch(
            "projectionist.scheduler.tasks.facet_taxonomy_audit.run_db",
            new_callable=mock.AsyncMock,
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
                {"target_entity_id": "already-there", "status": "pending"}
            ]
            staged = asyncio.run(task._already_staged("already-there"))
            self.assertTrue(staged)
            run_db_mock.assert_awaited_once()
            passed = run_db_mock.await_args.args[0]
            self.assertIs(passed.__self__, self.db)
            self.assertIs(passed.__func__, type(self.db).list_staged_augmentations)

    def test_registered_with_idle_scheduler(self) -> None:
        scheduler = IdleScheduler(self.db, Path(self._tmpdir.name))
        register_all(scheduler)
        self.assertIn(TASK_NAME, scheduler._definitions)
        defn = scheduler._definitions[TASK_NAME]
        self.assertEqual(defn.run_interval_seconds, 3600)


class FacetOverlayPromoteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        self.db = Database(self.data_dir / "lib.db")
        reset_registry_cache()
        self._old_data = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.data_dir)
        reload_registry()

    def tearDown(self) -> None:
        reset_registry_cache()
        if self._old_data is not None:
            os.environ["DATA_DIR"] = self._old_data
        else:
            os.environ.pop("DATA_DIR", None)
        self.db.close()
        self._tmpdir.cleanup()

    def test_promote_writes_layered_overlay_not_seed(self) -> None:
        seed_path = (
            Path(__file__).resolve().parents[1]
            / "projectionist/facets/data/taxonomy.json"
        )
        seed_before = seed_path.read_text(encoding="utf-8")
        result = promote_facet_alias_to_overlay(
            alias="noirish",
            concept_id="documentary",
            data_dir=self.data_dir,
            reload=True,
        )
        overlay_path = Path(result["path"])
        self.assertTrue(overlay_path.is_file())
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        self.assertEqual(overlay["aliases"]["noirish"], "documentary")
        self.assertNotIn("tmdb_genre_ids", json.dumps(overlay))
        self.assertEqual(seed_path.read_text(encoding="utf-8"), seed_before)

        genres = [{"id": 99, "name": "Documentary"}]
        meta = resolve_genre_ids(genres, "noirish", emit_telemetry=False)
        self.assertEqual(meta["genre_ids"], "99")

    def test_admin_approve_reject_handlers(self) -> None:
        # Stage a pending row with a suggested concept.
        row_id = self.db.insert_staged_augmentation(
            task_name=TASK_NAME,
            priority_tier="P1",
            target_entity_type="facet",
            target_entity_id="space-opera",
            candidate_data_json=json.dumps(
                {
                    "alias": "space-opera",
                    "suggested_concept_id": "science_fiction",
                    "suggested_canonical_name": "Science Fiction",
                    "hit_count": 6,
                }
            ),
            confidence_score=0.74,
        )
        reject_id = self.db.insert_staged_augmentation(
            task_name=TASK_NAME,
            priority_tier="P1",
            target_entity_type="facet",
            target_entity_id="junk-token",
            candidate_data_json=json.dumps({"alias": "junk-token", "hit_count": 3}),
            confidence_score=0.62,
        )

        from projectionist.web import augmentation_routes as routes

        # Rebind factories without re-including the router (avoids duplicate routes).
        routes._db_factory = lambda: self.db
        routes._data_dir = self.data_dir

        listed = routes.list_staged_augmentations_endpoint(
            status="pending", task_name=TASK_NAME, limit=50, user={"role": "owner"}
        )
        self.assertGreaterEqual(listed["count"], 2)
        self.assertIn("candidate", listed["items"][0])

        # status=all clears the filter (contract for Admin Taxonomy UI).
        all_listed = routes.list_staged_augmentations_endpoint(
            status="all", task_name=TASK_NAME, limit=50, user={"role": "owner"}
        )
        self.assertGreaterEqual(all_listed["count"], listed["count"])

        # Approve without suggested mapping and without body overrides → 400.
        bare_id = self.db.insert_staged_augmentation(
            task_name=TASK_NAME,
            priority_tier="P1",
            target_entity_type="facet",
            target_entity_id="needs-map",
            candidate_data_json=json.dumps({"alias": "needs-map", "hit_count": 4}),
            confidence_score=0.65,
        )
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as bare_exc:
            routes.approve_staged_augmentation(
                bare_id, routes.ApproveStagedPayload(), user={"role": "owner"}
            )
        self.assertEqual(bare_exc.exception.status_code, 400)

        body = routes.approve_staged_augmentation(
            row_id, routes.ApproveStagedPayload(), user={"role": "owner"}
        )
        self.assertEqual(body["item"]["status"], "approved")
        self.assertTrue(Path(body["overlay_path"]).is_file())
        overlay = json.loads(Path(body["overlay_path"]).read_text(encoding="utf-8"))
        self.assertEqual(overlay["aliases"]["space-opera"], "science_fiction")

        # Double-approve is a conflict, not a silent re-write.
        with self.assertRaises(HTTPException) as again:
            routes.approve_staged_augmentation(
                row_id, routes.ApproveStagedPayload(), user={"role": "owner"}
            )
        self.assertEqual(again.exception.status_code, 409)

        rejected = routes.reject_staged_augmentation(reject_id, user={"role": "owner"})
        self.assertEqual(rejected["item"]["status"], "rejected")

        # Reject does not invent an overlay entry for junk-token.
        self.assertNotIn("junk-token", json.dumps(overlay))

        # Seed file untouched.
        seed_path = (
            Path(__file__).resolve().parents[1]
            / "projectionist/facets/data/taxonomy.json"
        )
        self.assertNotIn("space-opera", seed_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
