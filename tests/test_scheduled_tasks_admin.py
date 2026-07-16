"""Owner-only scheduled-tasks admin API and run-log behavior."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.scheduler.run_log import TaskRunLogStore, emit_task_event
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


async def _noop_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    emit_task_event("noop progress")
    return {"status": "completed", "processed": 1}


async def _slow_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings
    emit_task_event("slow started")
    for _ in range(20):
        if should_stop():
            return {"status": "interrupted"}
        await asyncio.sleep(0.05)
    return {"status": "completed"}


class TaskRunLogStoreTests(unittest.TestCase):
    def test_start_emit_end_and_poll(self) -> None:
        store = TaskRunLogStore()
        run_id = store.start_run("demo", trigger="manual")
        token = store.bind_emitter("demo")
        try:
            emit_task_event("halfway", level="info", step=1)
        finally:
            store.reset_emitter(token)
        store.end_run("demo", status="completed", duration_ms=12, result={"processed": 3})

        payload = store.get_events(task="demo", after_seq=0)
        messages = [event["message"] for event in payload["events"]]
        self.assertTrue(any("Started" in msg for msg in messages))
        self.assertIn("halfway", messages)
        self.assertTrue(any("Finished" in msg for msg in messages))
        self.assertEqual(payload["last_run"]["run_id"], run_id)
        self.assertEqual(payload["last_run"]["status"], "completed")
        self.assertIsNone(payload["current_run"])

    def test_after_seq_filters(self) -> None:
        store = TaskRunLogStore()
        store.start_run("a", trigger="schedule")
        store.emit("a", "one")
        store.emit("a", "two")
        first = store.get_events(task="a", after_seq=0)
        latest = first["latest_seq"]
        second = store.get_events(task="a", after_seq=latest)
        self.assertEqual(second["events"], [])


class SchedulerRunLogIntegrationTests(unittest.TestCase):
    def test_trigger_records_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="logged", run_interval_seconds=3600, run_fn=_noop_task)
            )
            result = asyncio.run(scheduler.trigger_task("logged"))
            self.assertEqual(result["status"], "completed")
            log = scheduler.get_task_run_log("logged")
            messages = [event["message"] for event in log["events"]]
            self.assertTrue(any("Started" in msg for msg in messages))
            self.assertIn("noop progress", messages)
            states = scheduler.get_task_states()
            logged = next(item for item in states if item["name"] == "logged")
            self.assertIsNotNone(logged["last_started_at"])
            self.assertIsNotNone(logged["last_finished_at"])
            self.assertFalse(logged["running"])

    def test_background_trigger_sets_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="slow", run_interval_seconds=3600, run_fn=_slow_task)
            )

            async def _exercise() -> None:
                started = scheduler.trigger_task_background("slow")
                self.assertEqual(started["status"], "started")
                # Allow the runner to mark itself running.
                for _ in range(40):
                    if scheduler._running_task == "slow":
                        break
                    await asyncio.sleep(0.02)
                self.assertEqual(scheduler._running_task, "slow")
                log = scheduler.get_task_run_log("slow")
                self.assertIsNotNone(log["current_run"])
                busy = scheduler.trigger_task_background("slow")
                self.assertEqual(busy["status"], "busy")
                while scheduler._busy_task_name() is not None:
                    await asyncio.sleep(0.02)

            asyncio.run(_exercise())


class ScheduledTasksAdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-scheduled-tasks-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        # Context manager ensures FastAPI lifespan starts the idle scheduler.
        self._client_cm = TestClient(app_mod.app)
        self._client_cm.__enter__()
        self.client = self._client_cm

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        try:
            self._client_cm.__exit__(None, None, None)
        except Exception:
            pass
        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _write_settings(self, *, multi_user: bool = False, local: bool = False) -> None:
        payload: Dict[str, Any] = {
            "features": {"multi_user_enabled": multi_user},
            "llm_provider": "ollama",
        }
        if local:
            payload["auth"] = {
                "mode": "local",
                "plex_login_enabled": False,
                "local_login_enabled": True,
            }
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_list_and_log_owner_open_when_multi_user_disabled(self) -> None:
        self._write_settings(multi_user=False)
        listed = self.client.get("/api/admin/scheduled-tasks")
        self.assertEqual(listed.status_code, 200, listed.text)
        body = listed.json()
        self.assertIn("items", body)
        self.assertGreaterEqual(len(body["items"]), 1)
        name = body["items"][0]["name"]
        log = self.client.get(f"/api/admin/scheduled-tasks/{name}/log")
        self.assertEqual(log.status_code, 200, log.text)
        self.assertIn("events", log.json())

    def test_run_background_and_poll_log(self) -> None:
        self._write_settings(multi_user=False)
        listed = self.client.get("/api/admin/scheduled-tasks")
        name = "health_metrics"
        names = {item["name"] for item in listed.json()["items"]}
        self.assertIn(name, names)

        with patch.object(
            self.app_mod.app.state.idle_scheduler._definitions[name],
            "run_fn",
            _noop_task,
        ):
            run = self.client.post(f"/api/admin/scheduled-tasks/{name}/run")
            self.assertEqual(run.status_code, 200, run.text)
            self.assertEqual(run.json()["status"], "started")

            deadline = time.time() + 3
            events: list[dict[str, Any]] = []
            while time.time() < deadline:
                log = self.client.get(f"/api/admin/scheduled-tasks/{name}/log")
                self.assertEqual(log.status_code, 200)
                events = log.json().get("events") or []
                if any("Finished" in (event.get("message") or "") for event in events):
                    break
                time.sleep(0.05)
            self.assertTrue(any("Started" in (event.get("message") or "") for event in events))

    def test_member_denied_when_multi_user_enabled(self) -> None:
        self._write_settings(multi_user=True, local=True)
        owner = self.client.post(
            "/api/auth/local/register",
            json={"username": "owner1", "password": "password123"},
        )
        self.assertEqual(owner.status_code, 200, owner.text)
        member = self.client.post(
            "/api/auth/local/register",
            json={"username": "member1", "password": "password123"},
        )
        self.assertEqual(member.status_code, 200, member.text)
        self.assertEqual(member.json()["user"]["role"], "member")

        # Fresh client with only the member session.
        member_cookie = member.cookies.get(SESSION_COOKIE_NAME)
        self.assertIsNotNone(member_cookie)
        bare = TestClient(self.app_mod.app)
        bare.cookies.set(SESSION_COOKIE_NAME, member_cookie)
        denied = bare.get("/api/admin/scheduled-tasks")
        self.assertEqual(denied.status_code, 403)
        denied_run = bare.post("/api/admin/scheduled-tasks/health_metrics/run")
        self.assertEqual(denied_run.status_code, 403)
        denied_log = bare.get("/api/admin/scheduled-tasks/health_metrics/log")
        self.assertEqual(denied_log.status_code, 403)


if __name__ == "__main__":
    unittest.main()
