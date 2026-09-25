"""Thin include/health tests for the Wave 0 investigate routes stub."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class InvestigateRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
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

    def test_investigate_health_placeholder(self) -> None:
        resp = self.client.get("/api/admin/investigate/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIs(body["available"], False)
