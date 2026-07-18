"""Serve /release-notes.json from frontend/dist (not only Vite /assets)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from curatorx.web.app import FRONTEND_DIST, app


class ReleaseNotesStaticTests(unittest.TestCase):
    def test_about_route_serves_html_without_auth(self) -> None:
        client = TestClient(app)
        response = client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_release_notes_json_served(self) -> None:
        dist_notes = FRONTEND_DIST / "release-notes.json"
        public_notes = FRONTEND_DIST.parent / "public" / "release-notes.json"
        if not dist_notes.is_file() and not public_notes.is_file():
            self.skipTest("release-notes.json not present in frontend/dist or public")

        client = TestClient(app)
        response = client.get("/release-notes.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.headers.get("content-type", ""))
        body = response.json()
        self.assertIn("releases", body)
        self.assertIsInstance(body["releases"], list)
        self.assertGreaterEqual(len(body["releases"]), 1)
        self.assertTrue(body["releases"][0].get("version"))

    def test_release_notes_json_404_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_root = Path(tmp)
            empty_dist = empty_root / "dist"
            empty_dist.mkdir()
            with mock.patch("curatorx.web.app.FRONTEND_DIST", empty_dist):
                client = TestClient(app)
                response = client.get("/release-notes.json")
                self.assertEqual(response.status_code, 404)

    def test_release_notes_prefers_newer_of_dist_and_public(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            public = root / "public"
            dist.mkdir()
            public.mkdir()
            dist_file = dist / "release-notes.json"
            public_file = public / "release-notes.json"
            dist_file.write_text(
                '{"generated_at":"2026-01-01T00:00:00Z","releases":[{"version":"1.0.0","date":"2026-01-01","summary":"","sections":[]}]}',
                encoding="utf-8",
            )
            public_file.write_text(
                '{"generated_at":"2026-07-17T00:00:00Z","releases":[{"version":"9.9.9","date":"2026-07-17","summary":"","sections":[]}]}',
                encoding="utf-8",
            )
            # Ensure public is newer
            import os
            import time

            now = time.time()
            os.utime(dist_file, (now - 100, now - 100))
            os.utime(public_file, (now, now))

            with mock.patch("curatorx.web.app.FRONTEND_DIST", dist):
                client = TestClient(app)
                response = client.get("/release-notes.json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["releases"][0]["version"], "9.9.9")


if __name__ == "__main__":
    unittest.main()
