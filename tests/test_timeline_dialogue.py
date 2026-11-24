"""TML-002: dialogue comes from the household subtitle cache."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

SRT = "1\n00:00:21,380 --> 00:00:21,900\nWho was that?\n"


class TimelineDialogueApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-timeline-dialogue-secret"
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
        folder = Path(self._tmpdir.name, "subtitles", "movie-1")
        folder.mkdir(parents=True)
        (folder / "en.srt").write_text(SRT, encoding="utf-8")
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))
        recorded = self.client.post(
            "/api/library/timeline/files",
            json={"rating_key": "movie-1", "size": 5, "mtime_ns": 6, "duration_ms": 7000},
        )
        self.file_id = recorded.json()["id"]

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        self._tmpdir.cleanup()

    def test_import_stores_the_line_and_a_second_import_replaces_it(self) -> None:
        self.assertEqual(
            self.client.get("/api/features").json()["capabilities"]["timeline_dialogue"], 1
        )
        imported = self.client.post(f"/api/library/timeline/files/{self.file_id}/dialogue")
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["imported"], 1)
        self.assertNotIn("Who was that?", imported.text)
        with self.app_mod._db().connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM timeline_events WHERE file_id = ? AND kind = 'dialogue'",
                (self.file_id,),
            ).fetchall()
        self.assertEqual(json.loads(rows[0]["payload"])["text"], "Who was that?")
        folder = Path(self._tmpdir.name, "subtitles", "movie-1")
        (folder / "en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nA different line\n",
            encoding="utf-8",
        )
        again = self.client.post(f"/api/library/timeline/files/{self.file_id}/dialogue")
        self.assertEqual(again.json()["imported"], 1)
        with self.app_mod._db().connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM timeline_events WHERE file_id = ? AND kind = 'dialogue'",
                (self.file_id,),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["payload"])["text"], "A different line")
        missing = self.client.post("/api/library/timeline/files/999/dialogue")
        self.assertEqual(missing.status_code, 404, missing.text)
