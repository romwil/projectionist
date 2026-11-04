"""Unknown pages boot the app; API and file 404s stay as they were (UX-008, ARCH-010)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import reset_admin_execution_for_tests


class SpaNotFoundTests(unittest.TestCase):
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
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_unknown_page_returns_the_app_shell(self) -> None:
        for path in ("/this-route-does-not-exist", "/explore/nope/deeper", "/titles/42"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 404)
                self.assertIn("text/html", resp.headers.get("content-type", ""))
                self.assertEqual(resp.headers.get("cache-control"), "no-cache")
                self.assertNotIn('"detail"', resp.text)
                self.assertIn("<", resp.text)

    def test_unknown_api_path_stays_json(self) -> None:
        for path in ("/api/does-not-exist", "/api/nope"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 404)
                self.assertIn("application/json", resp.headers.get("content-type", ""))
                self.assertEqual(resp.json(), {"detail": "Not Found"})

    def test_missing_files_and_assets_are_not_pages(self) -> None:
        for path in ("/robots.txt", "/assets/missing-chunk.js", "/mcp/missing"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertNotIn("text/html", resp.headers.get("content-type", ""))

    def test_post_to_unknown_page_is_not_the_shell(self) -> None:
        resp = self.client.post("/this-route-does-not-exist", json={})
        self.assertNotIn("text/html", resp.headers.get("content-type", ""))

    def test_known_routes_are_unchanged(self) -> None:
        for path in ("/chat", "/whisper", "/explore/related"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/html", resp.headers.get("content-type", ""))
        tour = self.client.get("/tour", follow_redirects=False)
        self.assertIn(tour.status_code, {302, 307})


if __name__ == "__main__":
    unittest.main()
