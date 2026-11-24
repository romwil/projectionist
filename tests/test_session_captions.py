"""SES-006: a session caption feed for a device in the room."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db._shared import begin_immediate
from projectionist.sessions.captions import parse_cues
from projectionist.sessions.shared import reset_shared_sessions
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

TV = "00000000-0000-4000-8000-0000000000aa"
SRT = "1\n00:00:01,000 --> 00:00:02,500\nHello there\n"


class CaptionParseTests(unittest.TestCase):
    def test_srt_times_become_milliseconds(self) -> None:
        cues = parse_cues(SRT)
        self.assertEqual(cues, [{"start_ms": 1000, "end_ms": 2500, "text": "Hello there"}])


class SessionCaptionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-session-caption-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        reset_shared_sessions()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps({"features": {"multi_user_enabled": True}, "llm_provider": "ollama"}),
            encoding="utf-8",
        )
        db = app_mod._db()
        for user_id, name, plex_id in (
            ("screen-1", "Screen", "1"),
            ("starter-1", "Starter", "2"),
            ("other-1", "Other", "3"),
        ):
            db.upsert_plex_user(
                user_id=user_id, display_name=name, email=None, plex_user_id=plex_id, role="member"
            )

        def _write() -> None:
            with db.connect() as conn:
                begin_immediate(conn)
                conn.execute(
                    """
                    INSERT INTO paired_devices (
                        id, user_id, label, credential_hash, created_at, kind
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (TV, "screen-1", "Living Room", f"hash-{TV}", 10.0, "tv"),
                )

        db.run_write(_write, label="test_screen")
        folder = Path(self._tmpdir.name, "subtitles", "movie-1")
        folder.mkdir(parents=True)
        (folder / "en.srt").write_text(SRT, encoding="utf-8")
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("starter-1"))
        opened = self.client.post("/api/sessions", json={"screen_id": TV, "rating_key": "movie-1"})
        self.session_id = opened.json()["id"]
        self.code = self.client.get(f"/api/sessions/{self.session_id}/code").json()["code"]

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_shared_sessions()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        self._tmpdir.cleanup()

    def test_a_guest_reads_cues_and_a_stranger_does_not(self) -> None:
        features = self.client.get("/api/features").json()["capabilities"]
        self.assertEqual(features["session_captions"], 1)
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("other-1"))
        hidden = self.client.get(f"/api/sessions/{self.session_id}/captions")
        self.assertEqual(hidden.status_code, 404, hidden.text)
        self.assertNotIn("Hello there", hidden.text)
        joined = self.client.post(f"/api/rooms/{TV}/join", json={"code": self.code})
        self.assertEqual(joined.status_code, 200, joined.text)
        feed = self.client.get(f"/api/sessions/{self.session_id}/captions", params={"language": "en"})
        self.assertEqual(feed.status_code, 200, feed.text)
        self.assertEqual(feed.json()["cues"][0]["text"], "Hello there")
        self.assertNotIn(str(Path(self._tmpdir.name)), feed.text)
        room = self.client.get(f"/api/sessions/{self.session_id}").json()
        self.assertNotIn("captions", room)
