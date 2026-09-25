"""Rematch studio routes: scan / skip / retry, owner-only."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.connectors.radarr import RadarrMovie
from projectionist.library.admin_execution import reset_admin_execution_for_tests
from projectionist.library.db import Database


class RematchRoutesTests(unittest.TestCase):
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

    def test_rematch_routes_module_exports_register(self) -> None:
        from projectionist.web.rematch_routes import register_rematch_routes, router

        self.assertTrue(callable(register_rematch_routes))
        paths = {getattr(route, "path", None) for route in router.routes}
        self.assertIn("/api/admin/rematch/scan", paths)
        self.assertIn("/api/admin/rematch/skip", paths)
        self.assertIn("/api/admin/rematch/retry", paths)
        self.assertIn("/api/admin/rematch/repairs", paths)

    def test_scan_lists_path_conflict(self) -> None:
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-presence",
                    "media_type": "movie",
                    "title": "Presence",
                    "year": 2025,
                    "tmdb_id": 1388150,
                    "in_radarr": 0,
                }
            ]
        )
        catalog = [
            RadarrMovie(
                id=9,
                title="Savages",
                year=2012,
                tmdb_id=111,
                monitored=True,
                has_file=True,
                folder_path="/movies/Presence (2025)",
            )
        ]
        with patch(
            "projectionist.library.rematch.radarr_add_configuration_error",
            return_value=None,
        ), patch(
            "projectionist.library.rematch.resolve_radarr_root_folder",
            return_value="/movies",
        ), patch(
            "projectionist.library.rematch.RadarrClient"
        ) as client_cls:
            client_cls.return_value.movies.return_value = catalog
            resp = self.client.get("/api/admin/rematch/scan")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["kind"], "path_conflict")
        self.assertIn("FileBot", body["investigators_note"])

    def test_skip_persists(self) -> None:
        db = Database(Path(self._tmpdir.name) / "projectionist.db")
        db.upsert_library_items(
            [
                {
                    "rating_key": "rk-x",
                    "media_type": "movie",
                    "title": "Unknown Reel",
                    "year": 1999,
                    "in_radarr": 0,
                }
            ]
        )
        item_id = int(db.library_item_by_rating_key("rk-x")["id"])
        resp = self.client.post("/api/admin/rematch/skip", json={"item_id": item_id, "skipped": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["skipped"])
        self.assertIn(item_id, resp.json()["skipped_ids"])


if __name__ == "__main__":
    unittest.main()
