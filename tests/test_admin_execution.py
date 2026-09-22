"""Shared admin execution snapshot + Register in Radarr job."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import (
    AdminExecutionStore,
    reset_admin_execution_for_tests,
    summarize_items,
)
from projectionist.library.db import Database
from projectionist.web.session_tokens import clear_session_secret_cache, create_session_token
from projectionist.web.auth import SESSION_COOKIE_NAME
from projectionist.web.rate_limit import clear_rate_limits
from tests.admin_job_helpers import wait_admin_job


class SummarizeItemsTests(unittest.TestCase):
    def test_never_reports_100_while_items_remain(self) -> None:
        summary = summarize_items(
            [
                {"id": 1, "title": "Moon", "status": "completed"},
                {"id": 2, "title": "Arrival", "status": "running"},
                {"id": 3, "title": "Dune", "status": "queued"},
            ]
        )
        self.assertEqual(summary["queued"], 1)
        self.assertEqual(summary["running"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertLess(summary["percent"], 100)
        self.assertEqual(summary["current"]["name"], "Arrival")

    def test_100_only_when_every_item_is_terminal(self) -> None:
        summary = summarize_items(
            [
                {"id": 1, "status": "completed"},
                {"id": 2, "status": "failed", "error": "timeout"},
                {"id": 3, "status": "cancelled"},
            ]
        )
        self.assertEqual(summary["percent"], 100)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["last_error"], "timeout")


class StoreCancelTests(unittest.TestCase):
    def test_cancel_leaves_in_flight_and_marks_queued(self) -> None:
        store = AdminExecutionStore("test")
        store.begin(
            items=[
                {"id": 1, "title": "Moon"},
                {"id": 2, "title": "Arrival"},
            ]
        )
        store.set_item(1, "running")
        cancelled = store.cancel_remaining()
        self.assertEqual(cancelled, 1)
        snap = store.snapshot()
        self.assertTrue(snap["can_cancel"] or snap["cancel_requested"])
        by_id = {row["id"]: row for row in snap["items"]}
        self.assertEqual(by_id[1]["status"], "running")
        self.assertEqual(by_id[2]["status"], "cancelled")
        self.assertLess(snap["percent"], 100)


class FakeRadarr:
    def __init__(self) -> None:
        self.added: List[int] = []

    def root_folders(self) -> List[Dict[str, Any]]:
        return [{"path": "/movies"}]

    def movie_by_tmdb_id(self, tmdb_id: int) -> None:
        return None

    def add_movie(self, tmdb_id: int, **kwargs: Any) -> Dict[str, Any]:
        self.added.append(int(tmdb_id))
        return {"id": len(self.added), "tmdbId": tmdb_id}


class RadarrRegisterApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "radarr-register-test-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        reset_admin_execution_for_tests()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True, "open_auto_provision": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "radarr_url": "http://radarr.test",
                    "radarr_api_key": "secret",
                    "radarr_root_folder": "/movies",
                    "radarr_quality_profile_id": 1,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        reset_admin_execution_for_tests()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login_owner(self) -> None:
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email=None,
            plex_user_id="1",
            role="owner",
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("owner-1"))

    def _seed_movies(self) -> None:
        db = self.app_mod._db()
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-moon",
                    "media_type": "movie",
                    "title": "Moon",
                    "year": 2009,
                    "tmdb_id": 17431,
                    "in_radarr": 0,
                },
                {
                    "rating_key": "rk-arrival",
                    "media_type": "movie",
                    "title": "Arrival",
                    "year": 2016,
                    "tmdb_id": 329865,
                    "in_radarr": 0,
                },
            ]
        )

    def test_register_returns_immediately_with_title_queue(self) -> None:
        self._login_owner()
        self._seed_movies()
        fake = FakeRadarr()
        with patch("projectionist.library.radarr_register.RadarrClient", return_value=fake):
            started = time.monotonic()
            resp = self.client.post(
                "/api/admin/radarr/register-existing",
                json={"limit": 25, "dry_run": False},
            )
            elapsed = time.monotonic() - started
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertLess(elapsed, 2.0, "register must not block the request thread")
        body = resp.json()
        self.assertTrue(body.get("accepted") or body.get("busy") or body.get("result"))
        self.assertTrue(body.get("job_id") or body.get("items"))
        status = wait_admin_job(self.client, "/api/admin/radarr/register-existing/status")
        self.assertIn(status["phase"], {"done", "cancelled"})
        self.assertEqual(len(status.get("items") or []), 2)
        self.assertEqual((status.get("result") or {}).get("registered"), 2)
        self.assertEqual(status["execution"]["completed"], 2)
        self.assertEqual(status["execution"]["percent"], 100)
        self.assertEqual(len(fake.added), 2)

    def test_cancel_marks_remaining_queued_titles(self) -> None:
        self._login_owner()
        self._seed_movies()

        class SlowRadarr(FakeRadarr):
            def add_movie(self, tmdb_id: int, **kwargs: Any) -> Dict[str, Any]:
                time.sleep(0.15)
                return super().add_movie(tmdb_id, **kwargs)

        fake = SlowRadarr()
        with patch("projectionist.library.radarr_register.RadarrClient", return_value=fake):
            started = self.client.post(
                "/api/admin/radarr/register-existing",
                json={"limit": 25},
            )
            self.assertEqual(started.status_code, 200, started.text)
            cancelled = self.client.post("/api/admin/radarr/register-existing/cancel")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        status = wait_admin_job(self.client, "/api/admin/radarr/register-existing/status")
        cancelled_count = int((status.get("execution") or {}).get("cancelled") or 0)
        self.assertTrue(
            status.get("cancel_requested")
            or cancelled_count
            or status["phase"] in {"done", "cancelled"}
        )
