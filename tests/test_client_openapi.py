"""NAT-003: client route tags and the OpenAPI snapshot."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from projectionist.web.client_contract import (
    CLIENT_ROUTES,
    CLIENT_TAG,
    SNAPSHOT_PATH,
    iter_api_routes,
    render_client_openapi,
    tagged_client_routes,
)


class ClientOpenAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.app as app_mod

        cls.app = app_mod.app

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_client_tag_matches_the_route_set(self) -> None:
        self.assertEqual(tagged_client_routes(self.app), set(CLIENT_ROUTES))

    def test_admin_routes_are_not_client_routes(self) -> None:
        for route in iter_api_routes(self.app):
            if "/admin" in route.path or route.path.startswith("/api/admin"):
                self.assertNotIn(CLIENT_TAG, route.tags or [])
                self.assertNotIn(route.path, {path for _method, path in CLIENT_ROUTES})

    def test_snapshot_matches_the_mounted_routes(self) -> None:
        snapshot = Path(SNAPSHOT_PATH).read_text(encoding="utf-8")
        self.assertEqual(snapshot, render_client_openapi(self.app))
        self.assertIn('"/api/features"', snapshot)
        self.assertNotIn("/api/admin/", snapshot)
