"""SES-009: a Youth member asks, and approval tightens the room."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db._shared import begin_immediate
from projectionist.sessions.shared import reset_shared_sessions
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

TV = "00000000-0000-4000-8000-0000000000aa"


class YouthJoinApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-youth-join-secret-value"
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
            ("youth-1", "Sam", "3"),
        ):
            db.upsert_plex_user(
                user_id=user_id,
                display_name=name,
                email=None,
                plex_user_id=plex_id,
                role="member",
            )
        db.set_user_youth("youth-1", True)
        for key, title, rating in (("movie-r", "Heat", "R"), ("movie-g", "Wonder", "G")):
            db.upsert_library_item(
                {
                    "rating_key": key,
                    "media_type": "movie",
                    "title": title,
                    "year": 1995,
                    "content_rating": rating,
                    "duration_ms": 1000,
                }
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

    def _as(self, user_id: str) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user_id))

    def _open(self, rating_key: str) -> str:
        self._as("starter-1")
        opened = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": rating_key}
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        return opened.json()["id"]

    def test_approval_stops_a_title_above_the_ceiling_and_relaxes_on_the_next_one(self) -> None:
        features = self.client.get("/api/features").json()["capabilities"]
        self.assertEqual(features["youth_join"], 1)
        self.assertEqual(features["push"], 0)
        self.assertEqual(features["approvals"], 0)
        session_id = self._open("movie-r")
        code = self.client.get(f"/api/sessions/{session_id}/code").json()["code"]
        self._as("youth-1")
        asked = self.client.post(f"/api/rooms/{TV}/join", json={"code": code})
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertEqual(asked.json()["status"], "pending")
        self.assertNotIn("Heat", asked.text)
        self.assertNotIn("movie-r", asked.text)
        mine = self.client.get("/api/session-approvals")
        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertNotIn("Heat", mine.text)
        self.assertEqual(mine.json()["approvals"][0]["status"], "pending")
        self.assertNotIn("title", mine.json()["approvals"][0])
        approval_id = asked.json()["request_id"]
        denied = self.client.post(
            f"/api/session-approvals/{approval_id}", json={"decision": "approve"}
        )
        self.assertEqual(denied.status_code, 404, denied.text)
        self.assertNotIn("Heat", denied.text)

        self._as("starter-1")
        listed = self.client.get("/api/session-approvals")
        body = listed.json()["approvals"][0]
        self.assertEqual(body["requester_name"], "Sam")
        self.assertEqual(body["ceiling"], "PG-13")
        self.assertEqual(body["title"], "Heat")
        self.assertTrue(body["title_above"])
        approved = self.client.post(
            f"/api/session-approvals/{approval_id}", json={"decision": "approve"}
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json(), {"status": "approved"})
        self.assertNotIn("Heat", approved.text)
        again = self.client.post(
            f"/api/session-approvals/{approval_id}", json={"decision": "approve"}
        )
        self.assertEqual(again.status_code, 404, again.text)
        room = self.client.get(f"/api/sessions/{session_id}").json()
        self.assertEqual(room["state"], "paused")
        self.assertTrue(room["held_for_ceiling"])
        self.assertEqual(room["ceiling"], "PG-13")
        self.assertIn("youth-1", room["guests"])
        playing = self.client.post(
            f"/api/sessions/{session_id}/commands", json={"command": "play"}
        )
        self.assertEqual(playing.status_code, 403, playing.text)

        self._as("youth-1")
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 200)
        self.client.delete(f"/api/sessions/{session_id}/guests/me")
        self._as("starter-1")
        held = self.client.get(f"/api/sessions/{session_id}").json()
        self.assertEqual(held["ceiling"], "PG-13")
        nxt = self.client.patch(f"/api/sessions/{session_id}", json={"rating_key": "movie-g"})
        self.assertEqual(nxt.status_code, 200, nxt.text)
        self.assertEqual(nxt.json()["rating_key"], "movie-g")
        self.assertEqual(nxt.json()["ceiling"], "")
        self.assertFalse(nxt.json()["held_for_ceiling"])

    def test_not_now_does_not_name_the_title(self) -> None:
        self._open("movie-r")
        self._as("youth-1")
        asked = self.client.post(f"/api/rooms/{TV}/join", json={})
        self._as("starter-1")
        declined = self.client.post(
            f"/api/session-approvals/{asked.json()['request_id']}",
            json={"decision": "not_now"},
        )
        self.assertEqual(declined.json()["status"], "declined")
        self.assertNotIn("Heat", declined.text)
        self._as("youth-1")
        quiet = self.client.post(f"/api/rooms/{TV}/join", json={})
        self.assertEqual(quiet.json()["status"], "declined")
        self.assertNotIn("Heat", quiet.text)
        self.assertNotIn("movie-r", quiet.text)

    def test_a_title_within_the_ceiling_keeps_playing(self) -> None:
        session_id = self._open("movie-g")
        self._as("youth-1")
        asked = self.client.post(f"/api/rooms/{TV}/join", json={})
        self._as("starter-1")
        self.client.post(
            f"/api/session-approvals/{asked.json()['request_id']}",
            json={"decision": "approve"},
        )
        room = self.client.get(f"/api/sessions/{session_id}").json()
        self.assertEqual(room["state"], "playing")
        self.assertFalse(room["held_for_ceiling"])
        self.assertEqual(room["ceiling"], "PG-13")
