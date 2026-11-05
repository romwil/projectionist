"""Subtitle enrichment task and the owner backfill.

The idle pass runs without TMDB and prefers lineup titles. A manual backfill
keeps going through chat activity, resumes from DB rows after a restart,
survives a hung OpenSubtitles call, pauses on quota, and runs once at a time.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.config_store import Settings
from projectionist.library import subtitle_state
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks import subtitle_enrichment as task

from tests.test_phase2_trust_core import _HouseholdApp
from tests.test_subtitle_player_proxy import GOOD_SRT, _FakeOpenSubtitles

_OS_ENV = ("PROJECTIONIST_OPENSUBTITLES_API_KEY", "OPENSUBTITLES_API_KEY")


def _seed(db: Database, movies: int = 4) -> list[str]:
    now = time.time()
    keys = []
    with db.connect() as conn:
        for idx in range(movies):
            key = str(1000 + idx)
            conn.execute(
                "INSERT INTO library_items (rating_key, media_type, title, year, imdb_id, updated_at) "
                "VALUES (?, 'movie', ?, 2000, ?, ?)",
                (key, f"Movie {idx}", f"tt{1000000 + idx}", now),
            )
            keys.append(key)
    return keys


class _Recorder:
    """Stand-in for ensure_household_subtitle that records state like the real one."""

    def __init__(self, on_call=None) -> None:
        self.calls: list[str] = []
        self.on_call = on_call

    def __call__(self, settings, key, *, db=None, **_kwargs):
        self.calls.append(str(key))
        if self.on_call:
            outcome = self.on_call(len(self.calls), str(key))
            if outcome is not None:
                return outcome
        subtitle_state.record_cached(db, key, "en", source="plex")
        return {"track": {"id": "cached-en"}, "reason": "copied_from_plex", "opensubtitles_called": False}


class _TaskBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self._env = patch.dict(os.environ, {"DATA_DIR": self._tmp.name})
        self._env.start()
        for name in _OS_ENV:
            os.environ.pop(name, None)
        self.db = Database(self.data_dir / "library.db")
        self.keys = _seed(self.db)
        self._sleep = patch.object(task, "_sleep", new=self._no_sleep)
        self._sleep.start()
        self._lineup = patch.object(task, "upcoming_lineup_keys", return_value=[])
        self.lineup = self._lineup.start()

    async def _no_sleep(self, _seconds):
        return None

    def tearDown(self) -> None:
        self._lineup.stop()
        self._sleep.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _scheduler(self) -> IdleScheduler:
        scheduler = IdleScheduler(self.db, self.data_dir)
        task.register(scheduler)
        scheduler._last_activity = time.time() - 3600
        return scheduler


class IdlePassTests(_TaskBase):
    def test_runs_without_tmdb_key_and_prefers_lineup_title(self) -> None:
        settings = Settings()
        self.assertFalse((settings.tmdb_api_key or "").strip())
        self.lineup.return_value = [self.keys[3]]
        recorder = _Recorder()
        with patch.object(task, "resolve_batch_size", return_value=1), patch.object(
            task, "ensure_household_subtitle", new=recorder
        ):
            result = asyncio.run(task.run(self.db, settings, lambda: False))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(recorder.calls, [self.keys[3]])
        self.assertTrue(result["has_more"])
        self.assertEqual(result["processed"], 1)

    def test_real_pass_without_any_key_or_plex_records_no_key(self) -> None:
        result = asyncio.run(task.run(self.db, Settings(), lambda: False))
        self.assertEqual(result["status"], "completed")
        state = subtitle_state.get_state(self.db, self.keys[0], "en")
        self.assertEqual(state["status"], subtitle_state.STATUS_NO_KEY)

    def test_task_is_registered_beside_metadata_enrichment(self) -> None:
        from projectionist.scheduler.tasks import register_all

        scheduler = IdleScheduler(self.db, self.data_dir)
        register_all(scheduler)
        names = list(scheduler._definitions)
        self.assertIn(task.TASK_NAME, names)
        self.assertEqual(names.index(task.TASK_NAME), names.index("metadata_enrichment") + 1)
        from projectionist.scheduler.bootstrap import FOUNDATIONAL_SEQUENCE

        self.assertNotIn(task.TASK_NAME, FOUNDATIONAL_SEQUENCE)


class BackfillTests(_TaskBase):
    def _idle_breaker(self, scheduler: IdleScheduler):
        def on_call(count: int, _key: str):
            if count == 1:
                scheduler.record_activity()  # a chat message arrives mid-run
            return None

        return _Recorder(on_call)

    def test_manual_run_survives_idle_transition_scheduled_cycle_does_not(self) -> None:
        scheduler = self._scheduler()
        defn = scheduler._definitions[task.TASK_NAME]

        recorder = self._idle_breaker(scheduler)
        with patch.object(task, "resolve_batch_size", return_value=10), patch.object(
            task, "ensure_household_subtitle", new=recorder
        ):
            scheduled = asyncio.run(scheduler._execute_task(defn))
        self.assertEqual(scheduled["status"], "interrupted")
        self.assertEqual(len(recorder.calls), 1)

        scheduler._last_activity = time.time() - 3600
        task.save_backfill(self.db, {"state": task.STATE_RUNNING})
        recorder = self._idle_breaker(scheduler)
        with patch.object(task, "ensure_household_subtitle", new=recorder):
            manual = asyncio.run(scheduler._execute_task(defn, force=True))
        self.assertEqual(manual["status"], "completed")
        self.assertEqual(len(recorder.calls), 3, "the three unfinished titles all ran")
        self.assertEqual(task.load_backfill(self.db)["state"], task.STATE_DONE)

    def test_restart_resumes_unfinished_rows_without_refetching_done_ones(self) -> None:
        subtitle_state.record_cached(self.db, self.keys[0], "en", source="plex")
        subtitle_state.record_cached(self.db, self.keys[1], "en", source="opensubtitles")
        task.save_backfill(self.db, {"state": task.STATE_RUNNING, "processed": 2})
        scheduler = self._scheduler()
        scheduler._last_activity = time.time()  # chatting right now; backfill still runs
        recorder = _Recorder()

        async def _restart():
            self.assertTrue(task.resume_backfill_if_active(scheduler))
            for _ in range(200):
                await asyncio.sleep(0.02)
                if task.load_backfill(self.db).get("state") == task.STATE_DONE:
                    break
            while scheduler._manual_tasks:
                await asyncio.sleep(0.02)

        with patch.object(task, "ensure_household_subtitle", new=recorder):
            asyncio.run(_restart())
        self.assertEqual(sorted(recorder.calls), sorted(self.keys[2:]))
        state = task.load_backfill(self.db)
        self.assertEqual(state["state"], task.STATE_DONE)
        self.assertEqual(state["processed"], 4)

    def test_hung_opensubtitles_call_fails_only_that_title(self) -> None:
        from projectionist.library import subtitle_cache

        hung = _FakeOpenSubtitles(hang=2.0)
        healthy = _FakeOpenSubtitles(body=GOOD_SRT)
        clients = iter([hung, healthy, healthy, healthy])
        task.save_backfill(self.db, {"state": task.STATE_RUNNING})
        with patch.dict(os.environ, {"PROJECTIONIST_OPENSUBTITLES_API_KEY": "os-key"}), patch.object(
            subtitle_cache, "TITLE_LOOKUP_TIMEOUT_SECONDS", 0.2
        ), patch.object(
            subtitle_cache, "OpenSubtitlesClient", side_effect=lambda *_a, **_k: next(clients)
        ), patch("projectionist.library.subtitles.plex_client_from_settings", return_value=None):
            result = asyncio.run(task.run(self.db, Settings(), lambda: False))
        self.assertEqual(result["status"], "completed")
        first = subtitle_state.get_state(self.db, self.keys[0], "en")
        self.assertEqual(first["status"], subtitle_state.STATUS_RETRY)
        self.assertIn("longer than", first["last_error"])
        for key in self.keys[1:]:
            self.assertEqual(subtitle_state.get_state(self.db, key, "en")["status"], "cached")

    def test_quota_pauses_the_run(self) -> None:
        def on_call(count: int, _key: str):
            if count == 2:
                return {"track": None, "reason": "quota", "quota": True, "opensubtitles_called": True}
            return None

        recorder = _Recorder(on_call)
        task.save_backfill(self.db, {"state": task.STATE_RUNNING})
        with patch.object(task, "ensure_household_subtitle", new=recorder):
            result = asyncio.run(task.run(self.db, Settings(), lambda: False))
        self.assertTrue(result["quota_paused"])
        self.assertEqual(len(recorder.calls), 2)
        self.assertEqual(task.load_backfill(self.db)["state"], task.STATE_PAUSED_QUOTA)
        self.assertGreater(task.opensubtitles_paused_until(self.db), time.time())
        self.assertIsNone(subtitle_state.get_state(self.db, self.keys[1], "en"))

    def test_stop_ends_between_titles(self) -> None:
        def on_call(count: int, _key: str):
            if count == 1:
                current = task.load_backfill(self.db)
                task.save_backfill(self.db, {**current, "state": task.STATE_STOPPING})
            return None

        recorder = _Recorder(on_call)
        task.save_backfill(self.db, {"state": task.STATE_RUNNING})
        with patch.object(task, "ensure_household_subtitle", new=recorder):
            result = asyncio.run(task.run(self.db, Settings(), lambda: False))
        self.assertTrue(result["stopped"])
        self.assertEqual(len(recorder.calls), 1)
        self.assertEqual(task.load_backfill(self.db)["state"], task.STATE_STOPPED)

    def test_second_confirm_does_not_start_a_second_run(self) -> None:
        scheduler = self._scheduler()

        def fake_trigger(name):
            scheduler._pending_trigger = name
            return {"status": "started"}

        trigger = MagicMock(side_effect=fake_trigger)

        async def _confirm_twice():
            with patch.object(scheduler, "trigger_task_background", trigger):
                first = task.start_backfill(scheduler)
                second = task.start_backfill(scheduler)
            return first, second

        first, second = asyncio.run(_confirm_twice())
        self.assertEqual(first["status"], "started")
        self.assertEqual(second["status"], "already_running")
        self.assertEqual(trigger.call_count, 1)
        self.assertIn("remaining", second)


class BackfillRouteTests(_HouseholdApp):
    def test_backfill_route_is_owner_only(self) -> None:
        scheduler = IdleScheduler(self.db, self.data_dir)
        task.register(scheduler)
        self.app_mod.app.state.idle_scheduler = scheduler
        try:
            for name in ("member", "youth"):
                client = self._client_for(name)
                self.assertEqual(client.post("/api/admin/subtitles/backfill").status_code, 403)
                self.assertEqual(client.get("/api/admin/subtitles/backfill").status_code, 403)
                self.assertEqual(client.post("/api/admin/subtitles/backfill/stop").status_code, 403)
            owner = self._client_for("owner")
            with patch.object(scheduler, "trigger_task_background", return_value={"status": "started"}):
                resp = owner.post("/api/admin/subtitles/backfill")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["state"], task.STATE_RUNNING)
            status = owner.get("/api/admin/subtitles/backfill").json()
            self.assertIn("done", status)
            self.assertIn("last_error", status)
        finally:
            self.app_mod.app.state.idle_scheduler = None


if __name__ == "__main__":
    unittest.main()
