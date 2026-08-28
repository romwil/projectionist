"""Durable job manager persistence tests."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from projectionist.web.jobs import (
    INTERRUPTED_BY_RESTART,
    JOBS_STATE_FILENAME,
    Job,
    JobManager,
    JobProgress,
    reset_job_manager_for_tests,
)


class DurableJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_job_manager_for_tests()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        reset_job_manager_for_tests()
        self._tmpdir.cleanup()

    def _write_jobs_file(self, jobs: list[dict]) -> None:
        path = self.data_dir / JOBS_STATE_FILENAME
        path.write_text(
            json.dumps({"version": 1, "jobs": jobs}),
            encoding="utf-8",
        )

    def test_init_marks_running_jobs_interrupted(self) -> None:
        self._write_jobs_file(
            [
                {
                    "id": "run1",
                    "job_type": "library_sync",
                    "status": "running",
                    "created_at": 100.0,
                    "started_at": 101.0,
                    "finished_at": None,
                    "summary": {},
                    "progress": {
                        "phase": "movies",
                        "current": 10,
                        "total": 100,
                        "message": "Scanning movies…",
                    },
                    "error": None,
                },
                {
                    "id": "done1",
                    "job_type": "library_sync",
                    "status": "completed",
                    "created_at": 90.0,
                    "started_at": 91.0,
                    "finished_at": 95.0,
                    "summary": {"items_synced": 1},
                    "progress": {
                        "phase": "completed",
                        "current": 1,
                        "total": 1,
                        "message": "Done",
                    },
                    "error": None,
                },
            ]
        )

        manager = JobManager(self.data_dir)
        jobs = {job.id: job for job in manager.list_jobs()}

        self.assertEqual(jobs["run1"].status, "failed")
        self.assertEqual(jobs["run1"].error, INTERRUPTED_BY_RESTART)
        self.assertEqual(jobs["done1"].status, "completed")

        payload = json.loads((self.data_dir / JOBS_STATE_FILENAME).read_text(encoding="utf-8"))
        persisted = {entry["id"]: entry for entry in payload["jobs"]}
        self.assertEqual(persisted["run1"]["status"], "failed")
        self.assertEqual(persisted["run1"]["error"], INTERRUPTED_BY_RESTART)

    def test_start_sync_persists_queued_job(self) -> None:
        manager = JobManager(self.data_dir)
        settings = MagicMock()

        with patch.object(manager, "_run_sync"):
            # Avoid starting a real thread work; patch Thread to no-op start
            with patch("projectionist.web.jobs.threading.Thread") as thread_cls:
                thread_cls.return_value.start = MagicMock()
                job = manager.start_sync(settings)

        self.assertEqual(job.status, "queued")
        self.assertTrue((self.data_dir / JOBS_STATE_FILENAME).exists())
        payload = json.loads((self.data_dir / JOBS_STATE_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(payload["jobs"][0]["id"], job.id)
        self.assertEqual(payload["jobs"][0]["status"], "queued")

    def test_progress_updates_are_persisted(self) -> None:
        manager = JobManager(self.data_dir)
        job = Job(
            id="prog1",
            job_type="library_sync",
            status="running",
            created_at=1.0,
            started_at=1.0,
            progress=JobProgress(phase="preparing", current=0, total=1, message="Connecting to Plex…"),
        )
        with manager._lock:
            manager._jobs[job.id] = job
            manager._persist_locked()

        manager._update_progress("prog1", "movies", 12, 100, "Scanning movies…")
        payload = json.loads((self.data_dir / JOBS_STATE_FILENAME).read_text(encoding="utf-8"))
        entry = payload["jobs"][0]
        self.assertEqual(entry["progress"]["phase"], "movies")
        self.assertEqual(entry["progress"]["current"], 12)
        self.assertEqual(entry["progress"]["total"], 100)
        self.assertIn("Scanning", entry["progress"]["message"])

    def test_init_does_not_call_facet_index(self) -> None:
        """Regression: facet rebuild must not block JobManager / FastAPI startup."""
        import projectionist.web.jobs as jobs_mod

        self.assertFalse(
            hasattr(jobs_mod, "ensure_library_facet_index"),
            "JobManager must not import ensure_library_facet_index (blocks startup)",
        )
        with patch("projectionist.library.facets.ensure_library_facet_index") as ensure_facets:
            manager = JobManager(self.data_dir)
        self.assertIsNotNone(manager.db)
        ensure_facets.assert_not_called()

    def test_init_survives_corrupt_and_oversized_jobs_state(self) -> None:
        path = self.data_dir / JOBS_STATE_FILENAME
        path.write_text("{not-json", encoding="utf-8")
        manager = JobManager(self.data_dir)
        self.assertEqual(manager.list_jobs(), [])

        reset_job_manager_for_tests()
        # Oversized file should be skipped without hanging startup.
        path.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        manager = JobManager(self.data_dir)
        self.assertEqual(manager.list_jobs(), [])

    def test_init_survives_garbage_job_entries(self) -> None:
        self._write_jobs_file(
            [
                {"id": "bad", "status": "completed", "created_at": "not-a-float"},
                {
                    "id": "ok1",
                    "job_type": "library_sync",
                    "status": "completed",
                    "created_at": 1.0,
                    "summary": {},
                    "progress": {"phase": "completed", "current": 1, "total": 1, "message": "Done"},
                    "error": None,
                },
            ]
        )
        # created_at="not-a-float" raises in float(); load must continue with valid entries.
        manager = JobManager(self.data_dir)
        ids = {job.id for job in manager.list_jobs()}
        self.assertIn("ok1", ids)
        self.assertNotIn("bad", ids)

    def test_api_shape_includes_progress_fields(self) -> None:
        job = Job(
            id="shape1",
            job_type="library_sync",
            status="running",
            created_at=1.0,
            progress=JobProgress(phase="tv", current=5, total=20, message="Scanning Plex TV shows…"),
        )
        payload = job.to_dict()
        self.assertEqual(payload["id"], "shape1")
        self.assertEqual(payload["status"], "running")
        self.assertIn("percent", payload["progress"])
        self.assertIn("label", payload["progress"])
        self.assertIn("message", payload["progress"])
        self.assertEqual(payload["progress"]["phase"], "tv")


class StartupLifespanTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_job_manager_for_tests()
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"

    def tearDown(self) -> None:
        reset_job_manager_for_tests()
        import projectionist.web.jobs as jobs

        jobs._scheduler = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_lifespan_completes_even_if_facet_warmup_blocks(self) -> None:
        """Facet warm-up must run in a background thread, not block HTTP bind."""
        release = threading.Event()

        def blocking_ensure(_db: object) -> int:
            release.wait(timeout=30)
            return 0

        import projectionist.web.app as app_mod
        import projectionist.web.jobs as jobs_mod

        jobs_mod._manager = None
        jobs_mod._scheduler = None
        importlib.reload(app_mod)

        fake_scheduler = MagicMock()
        with patch.object(app_mod, "ensure_library_facet_index", side_effect=blocking_ensure):
            with patch.object(app_mod, "get_sync_scheduler", return_value=fake_scheduler):
                started = time.monotonic()
                with TestClient(app_mod.app) as client:
                    resp = client.get("/api/health")
                    elapsed = time.monotonic() - started
                    self.assertEqual(resp.status_code, 200)
                    self.assertLess(elapsed, 5.0, "startup blocked waiting on facet warm-up")
                release.set()
        fake_scheduler.start.assert_called()
        fake_scheduler.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
