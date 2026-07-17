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
from curatorx.scheduler.run_outcome import (
    build_run_summary,
    extract_outcome_detail,
    format_run_outcome_message,
)
from curatorx.scheduler.tasks import llm_theme_tagging
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


async def _skipped_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    return {
        "status": "skipped",
        "reason": "no_llm_api_key",
        "note": "LLM theme tagging stays empty until an LLM is configured.",
    }


async def _metrics_task(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db, settings, should_stop
    return {"status": "completed", "enriched": 5, "errors": 0, "has_more": True}


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

    def test_end_run_includes_skip_reason_in_message(self) -> None:
        store = TaskRunLogStore()
        store.start_run("theme", trigger="manual")
        store.end_run(
            "theme",
            status="skipped",
            duration_ms=3,
            result={
                "status": "skipped",
                "reason": "no_llm_api_key",
                "note": "LLM theme tagging stays empty until an LLM is configured.",
            },
        )
        payload = store.get_events(task="theme", after_seq=0)
        finished = [event for event in payload["events"] if "Skipped" in event["message"]]
        self.assertEqual(len(finished), 1)
        self.assertIn("LLM theme tagging stays empty", finished[0]["message"])
        self.assertEqual(payload["last_run"]["status"], "skipped")
        self.assertIn("LLM theme tagging stays empty", payload["last_run"]["outcome_reason"])
        self.assertIn("LLM theme tagging stays empty", payload["last_run"]["summary_line"])

    def test_end_run_includes_metrics_summary(self) -> None:
        store = TaskRunLogStore()
        store.start_run("meta", trigger="manual")
        store.end_run(
            "meta",
            status="completed",
            duration_ms=1200,
            result={"status": "completed", "enriched": 5, "errors": 1},
        )
        payload = store.get_events(task="meta", after_seq=0)
        finished = [event for event in payload["events"] if "succeeded" in event["message"]]
        self.assertEqual(len(finished), 1)
        self.assertIn("enriched", finished[0]["message"])
        self.assertEqual(payload["last_run"]["metrics"]["enriched"], 5)
        self.assertIn("5 enriched", payload["last_run"]["summary_line"])


class RunOutcomeFormattingTests(unittest.TestCase):
    def test_format_skip_message_prefers_note(self) -> None:
        message = format_run_outcome_message(
            "skipped",
            result={"reason": "stub_pending", "note": "Theme tagging stub"},
        )
        self.assertEqual(message, "Skipped — Theme tagging stub")

    def test_build_run_summary_for_completed_metrics(self) -> None:
        summary = build_run_summary(
            "completed",
            result={"status": "completed", "caches_built": 3, "library_size": 120},
        )
        self.assertIn("3 caches warmed", summary["summary_line"])
        self.assertEqual(summary["metrics"]["caches_built"], 3)

    def test_build_run_summary_for_title_relations(self) -> None:
        summary = build_run_summary(
            "completed",
            result={
                "status": "completed",
                "collection": 10,
                "neighbor": 4,
                "shared_crew": 2,
                "total": 16,
            },
        )
        self.assertIn("collection links", summary["summary_line"])
        self.assertEqual(summary["metrics"]["total"], 16)

    def test_error_statuses_align_message_summary_and_detail(self) -> None:
        for status in ("error", "error_timeout", "error: boom"):
            with self.subTest(status=status):
                result = {"status": status}
                detail = extract_outcome_detail(status, result=result)
                summary = build_run_summary(status, result=result)
                message = format_run_outcome_message(status, result=result)

                self.assertEqual(detail.get("outcome_reason"), "Task failed")
                self.assertEqual(summary["summary_line"], "Task failed")
                self.assertEqual(message, "Failed — Task failed")

        with self.subTest(status="error", error="connection reset"):
            result = {"status": "error", "error": "from result"}
            detail = extract_outcome_detail("error", error="connection reset", result=result)
            summary = build_run_summary("error", error="connection reset", result=result)
            message = format_run_outcome_message("error", error="connection reset", result=result)

            self.assertEqual(detail.get("outcome_reason"), "connection reset")
            self.assertEqual(summary["summary_line"], "connection reset")
            self.assertEqual(message, "Failed — connection reset")

        with self.subTest(status="error", result_error="from result"):
            result = {"status": "error", "error": "from result"}
            detail = extract_outcome_detail("error", result=result)
            summary = build_run_summary("error", result=result)
            message = format_run_outcome_message("error", result=result)

            self.assertEqual(detail.get("outcome_reason"), "from result")
            self.assertEqual(summary["summary_line"], "from result")
            self.assertEqual(message, "Failed — from result")

    def test_non_error_statuses_do_not_format_as_failed(self) -> None:
        for status in ("completed", "skipped", "interrupted"):
            with self.subTest(status=status):
                message = format_run_outcome_message(status)
                self.assertFalse(message.startswith("Failed —"))


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

    def test_trigger_skipped_persists_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="skipped_demo", run_interval_seconds=3600, run_fn=_skipped_task)
            )
            result = asyncio.run(scheduler.trigger_task("skipped_demo"))
            self.assertEqual(result["status"], "skipped")
            states = scheduler.get_task_states()
            demo = next(item for item in states if item["name"] == "skipped_demo")
            self.assertEqual(demo["last_status"], "skipped")
            self.assertIn("LLM theme tagging stays empty", demo["last_outcome_reason"] or "")
            log = scheduler.get_task_run_log("skipped_demo")
            finished = [event for event in log["events"] if event["message"].startswith("Skipped —")]
            self.assertEqual(len(finished), 1)

    def test_llm_theme_tagging_manual_skip_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            llm_theme_tagging.register(scheduler)
            result = asyncio.run(scheduler.trigger_task("llm_theme_tagging"))
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_llm_api_key")
            states = scheduler.get_task_states()
            theme = next(item for item in states if item["name"] == "llm_theme_tagging")
            self.assertEqual(theme["last_status"], "skipped")
            self.assertTrue(theme["last_outcome_reason"])

    def test_trigger_persists_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            scheduler = IdleScheduler(db, Path(tmp))
            scheduler.register(
                TaskDefinition(name="metrics", run_interval_seconds=3600, run_fn=_metrics_task)
            )
            result = asyncio.run(scheduler.trigger_task("metrics"))
            self.assertEqual(result["status"], "completed")
            states = scheduler.get_task_states()
            metrics = next(item for item in states if item["name"] == "metrics")
            self.assertEqual(metrics["last_status"], "completed")
            self.assertIn("5 enriched", metrics["last_run_summary_line"] or "")
            self.assertEqual(metrics["last_run_summary"]["metrics"]["enriched"], 5)


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
