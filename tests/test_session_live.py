"""SES-004: command authorization, the live channel, and the clock."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db._shared import begin_immediate
from projectionist.sessions.live import estimate_playhead
from projectionist.sessions.shared import reset_shared_sessions
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

TV = "00000000-0000-4000-8000-0000000000aa"


class PlayheadClockTests(unittest.TestCase):
    def test_playing_advances_and_paused_holds(self) -> None:
        self.assertEqual(estimate_playhead(1000, 5000, 5600, "playing"), 1600)
        self.assertEqual(estimate_playhead(1000, 5000, 5600, "paused"), 1000)
        self.assertEqual(estimate_playhead(1000, 9000, 5000, "playing"), 1000)


class SessionLiveApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-session-live-secret-value"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        reset_shared_sessions()
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
        for user_id, name, plex_id in (
            ("screen-1", "Screen", "1"),
            ("starter-1", "Starter", "2"),
            ("other-1", "Other", "3"),
        ):
            db.upsert_plex_user(
                user_id=user_id,
                display_name=name,
                email=None,
                plex_user_id=plex_id,
                role="member",
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
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("starter-1"))
        opened = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": "movie-1"}
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        self.session_id = opened.json()["id"]

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_shared_sessions()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_the_owner_channel_pauses_and_the_clock_is_on_the_event(self) -> None:
        with self.client.websocket_connect(f"/api/sessions/{self.session_id}/live") as socket:
            hello = socket.receive_json()
            self.assertEqual(hello["type"], "state")
            self.assertIn("server_time_ms", hello)
            self.assertEqual(hello["state"], "playing")
            socket.send_json({"command": "pause"})
            event = socket.receive_json()
        self.assertEqual(event["state"], "paused")
        self.assertGreater(event["server_time_ms"], 0)
        self.assertEqual(
            self.client.get(f"/api/sessions/{self.session_id}").json()["state"],
            "paused",
        )
        refused = self.client.post(
            f"/api/sessions/{self.session_id}/commands",
            json={"command": "rate", "value": 3},
        )
        self.assertEqual(refused.status_code, 400, refused.text)

    def test_the_screen_cannot_change_level_and_a_stranger_cannot_connect(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("screen-1"))
        with self.client.websocket_connect(f"/api/sessions/{self.session_id}/live") as socket:
            socket.receive_json()
            socket.send_json({"command": "level", "level": "class"})
            event = socket.receive_json()
        self.assertEqual(event["type"], "error")
        self.assertEqual(
            self.client.get(f"/api/sessions/{self.session_id}").json()["level"],
            "off",
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("other-1"))
        with self.client.websocket_connect(f"/api/sessions/{self.session_id}/live") as socket:
            denied = socket.receive_json()
        self.assertEqual(denied["type"], "error")
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["shared_sessions"], 1)
