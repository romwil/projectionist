"""H1 remaining shell extract: spa / auth / setup routers stay registered."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import reset_admin_execution_for_tests


class H1ShellExtractTests(unittest.TestCase):
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

    def test_extracted_routers_export_register(self) -> None:
        from projectionist.web.auth_routes import register_auth_routes
        from projectionist.web.setup_routes import register_setup_routes
        from projectionist.web.spa_routes import register_spa_routes, router as spa_router

        self.assertTrue(callable(register_spa_routes))
        self.assertTrue(callable(register_auth_routes))
        self.assertTrue(callable(register_setup_routes))
        paths = {getattr(route, "path", None) for route in spa_router.routes}
        self.assertIn("/chat", paths)
        self.assertIn("/admin/{section}", paths)
        self.assertIn("/settings/{section}", paths)

    def test_health_and_setup_still_served(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json().get("status"), "ok")

        setup = self.client.get("/api/setup/status")
        self.assertEqual(setup.status_code, 200)
        self.assertIn("onboarding_complete", setup.json())

        me = self.client.get("/api/auth/me")
        self.assertIn(me.status_code, {200, 401})
