"""TML-001: a media file is fingerprinted from size, mtime, and duration."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.timeline.files import file_fingerprint
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)


class FingerprintTests(unittest.TestCase):
    def test_the_same_numbers_hash_the_same_and_a_change_does_not(self) -> None:
        first = file_fingerprint(size=10, mtime_ns=20, duration_ms=30)
        self.assertEqual(first, file_fingerprint(size=10, mtime_ns=20, duration_ms=30))
        self.assertNotEqual(first, file_fingerprint(size=11, mtime_ns=20, duration_ms=30))
        self.assertEqual(len(first), 64)


class TimelineFileApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-timeline-file-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "local_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        db = app_mod._db()
        db.upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email=None,
            plex_user_id="1",
            role="member",
        )
        db.upsert_library_item(
            {
                "rating_key": "movie-1",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "content_rating": "R",
                "duration_ms": 1000,
            }
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        self._tmpdir.cleanup()

    def test_a_file_version_is_recorded_once(self) -> None:
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["timeline_files"], 1)
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["timeline"], 0)
        body = {"rating_key": "movie-1", "size": 100, "mtime_ns": 200, "duration_ms": 3000}
        first = self.client.post("/api/library/timeline/files", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertNotIn("text", first.json())
        again = self.client.post("/api/library/timeline/files", json=body)
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(again.json()["file_fingerprint"], first.json()["file_fingerprint"])
        changed = self.client.post(
            "/api/library/timeline/files",
            json={**body, "mtime_ns": 201},
        )
        self.assertNotEqual(changed.json()["id"], first.json()["id"])
        listed = self.client.get("/api/library/timeline/files/movie-1")
        self.assertEqual(len(listed.json()["files"]), 2)
        missing = self.client.post(
            "/api/library/timeline/files",
            json={"rating_key": "../secret", "size": 1, "mtime_ns": 1, "duration_ms": 1},
        )
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertNotIn("secret", missing.text)
