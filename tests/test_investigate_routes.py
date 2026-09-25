"""Investigate routes: health, shows, start/status/apply, stills, owner-only."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import reset_admin_execution_for_tests
from projectionist.library.db import Database


class InvestigateRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_investigate_routes_module_exports_register(self) -> None:
        from projectionist.web.investigate_routes import (
            register_investigate_routes,
            router,
        )

        self.assertTrue(callable(register_investigate_routes))
        paths = {getattr(route, "path", None) for route in router.routes}
        self.assertIn("/api/admin/investigate/health", paths)
        self.assertIn("/api/admin/investigate/start", paths)
        self.assertIn("/api/admin/investigate/apply", paths)

    def test_investigate_health_available(self) -> None:
        resp = self.client.get("/api/admin/investigate/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["available"])
        self.assertIn("leaves_lan", body["vision"])
        self.assertFalse(body["acrcloud"]["available"])
        self.assertFalse(body["acrcloud"]["deferred"])

    def test_investigate_shows_lists_library(self) -> None:
        db = Database(Path(self._tmpdir.name) / "projectionist.db")
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-bear",
                    "media_type": "show",
                    "title": "The Bear",
                    "year": 2022,
                    "tmdb_id": 136315,
                    "tvdb_id": 414005,
                    "season_count": 3,
                }
            ]
        )
        resp = self.client.get("/api/admin/investigate/shows")
        self.assertEqual(resp.status_code, 200)
        titles = [item["title"] for item in resp.json()["items"]]
        self.assertIn("The Bear", titles)

    def test_start_unknown_show_is_400(self) -> None:
        resp = self.client.post("/api/admin/investigate/start", json={"show_id": 999})
        self.assertEqual(resp.status_code, 400)

    def test_apply_without_review_is_400(self) -> None:
        resp = self.client.post("/api/admin/investigate/apply", json={"file_ids": ["1"]})
        self.assertEqual(resp.status_code, 400)

    def test_status_idle_snapshot(self) -> None:
        resp = self.client.get("/api/admin/investigate/status")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(resp.json().get("phase"), {"idle", "done", "queued", "running"})

    def test_still_404_and_serves_jpeg(self) -> None:
        missing = self.client.get("/api/admin/investigate/stills/nope/1/0.jpg")
        self.assertEqual(missing.status_code, 404)
        dest = Path(self._tmpdir.name) / "investigate" / "job1" / "9"
        dest.mkdir(parents=True)
        (dest / "0.jpg").write_bytes(b"jpeg-bytes")
        found = self.client.get("/api/admin/investigate/stills/job1/9/0.jpg")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.content, b"jpeg-bytes")

    def test_start_accepted_when_files_exist(self) -> None:
        db = Database(Path(self._tmpdir.name) / "projectionist.db")
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-bear",
                    "media_type": "show",
                    "title": "The Bear",
                    "tmdb_id": 136315,
                    "tvdb_id": 414005,
                    "season_count": 1,
                }
            ]
        )
        show_id = int(db.library_item_by_title("The Bear", media_type="show")["id"])
        fake_files = {
            "ok": True,
            "files": [
                {
                    "id": "9",
                    "file_id": 9,
                    "series_id": 4,
                    "path": "/tv/a.mkv",
                    "claimed": {
                        "source": "filename",
                        "filename": "a.mkv",
                        "label": "S01E01",
                        "evidence": False,
                    },
                    "sonarr": {"season": 1, "episode": 1, "evidence": False},
                }
            ],
            "catalog": [],
            "series_id": 4,
            "seasons": [1],
        }

        with patch(
            "projectionist.library.episode_investigate.job.list_episode_files",
            return_value=fake_files,
        ), patch(
            "projectionist.library.episode_investigate.job.investigate_files",
            return_value=[{"id": "9", "confidence": "likely", "same_show": True}],
        ):
            resp = self.client.post(
                "/api/admin/investigate/start",
                json={"show_id": show_id, "use_vision": False},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("accepted"))
        status = self.client.get("/api/admin/investigate/status")
        self.assertEqual(status.status_code, 200)

    def test_cancel_and_apply_status_ok(self) -> None:
        cancel = self.client.post("/api/admin/investigate/cancel")
        self.assertEqual(cancel.status_code, 200)
        apply_status = self.client.get("/api/admin/investigate/apply/status")
        self.assertEqual(apply_status.status_code, 200)
        apply_cancel = self.client.post("/api/admin/investigate/apply/cancel")
        self.assertEqual(apply_cancel.status_code, 200)
        undo = self.client.post("/api/admin/investigate/undo", json={"apply_id": "missing"})
        self.assertEqual(undo.status_code, 400)

    def test_new_routes_are_registered(self) -> None:
        from projectionist.web import investigate_routes as routes

        self.assertTrue(callable(routes.investigate_start))
        self.assertTrue(callable(routes.investigate_apply))
        self.assertTrue(callable(routes.investigate_undo))
        self.assertTrue(callable(routes.identify_settings))
        self.assertTrue(callable(routes.identify_test))

    def test_identify_settings_and_test_clip(self) -> None:
        from projectionist.web.investigate_routes import router

        paths = {getattr(route, "path", None) for route in router.routes}
        self.assertIn("/api/admin/investigate/identify/settings", paths)
        self.assertIn("/api/admin/investigate/identify/test", paths)
        listed = self.client.get("/api/admin/investigate/identify/settings")
        self.assertEqual(listed.status_code, 200)
        self.assertFalse(listed.json()["available"])
        saved = self.client.put(
            "/api/admin/investigate/identify/settings",
            json={
                "host": "identify-eu-west-1.acrcloud.com",
                "access_key": "k",
                "access_secret": "s",
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["available"])
        self.assertEqual(saved.json()["host"], "identify-eu-west-1.acrcloud.com")
        with patch(
            "projectionist.library.episode_investigate.acrcloud.identify_bytes",
            return_value={"ok": True, "found": False, "message": "No result", "title": "", "code": 1001},
        ):
            tested = self.client.post("/api/admin/investigate/identify/test", json={})
        self.assertEqual(tested.status_code, 200)
        self.assertFalse(tested.json()["renamed"])
        rejected = self.client.put(
            "/api/admin/investigate/identify/settings",
            json={"host": "https://bm-us-west-2.acrcloud.com", "access_key": "k", "access_secret": "s"},
        )
        self.assertEqual(rejected.status_code, 400)
