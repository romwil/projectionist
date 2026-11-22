"""SES-003: a session has an owner, a screen, a position, and a level."""

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


class SharedSessionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-shared-session-secret-value"
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
        for user_id, name, plex_id, role in (
            ("screen-1", "Screen", "1", "member"),
            ("starter-1", "Starter", "2", "member"),
            ("other-1", "Other", "3", "member"),
        ):
            db.upsert_plex_user(
                user_id=user_id,
                display_name=name,
                email=None,
                plex_user_id=plex_id,
                role=role,
            )
        self._add_screen(user_id="screen-1")

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

    def _add_screen(self, *, user_id: str) -> None:
        db = self.app_mod._db()

        def _write() -> None:
            with db.connect() as conn:
                begin_immediate(conn)
                conn.execute(
                    """
                    INSERT INTO paired_devices (
                        id, user_id, label, credential_hash, created_at, kind
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (TV, user_id, "Living Room", f"hash-{TV}", 10.0, "tv"),
                )

        db.run_write(_write, label="test_screen")

    def _as(self, user_id: str) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user_id))

    def test_owner_screen_and_everyone_else(self) -> None:
        self._as("starter-1")
        opened = self.client.post(
            "/api/sessions",
            json={"screen_id": TV, "rating_key": "movie-1", "level": "moments"},
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["owner_id"], "starter-1")
        self.assertEqual(body["screen_id"], TV)
        self.assertEqual(body["level"], "moments")
        self.assertEqual(body["state"], "playing")
        self.assertEqual(body["position_ms"], 0)
        session_id = body["id"]
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["session_object"], 1)

        self._as("other-1")
        hidden = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(hidden.status_code, 404, hidden.text)
        self.assertNotIn("movie-1", hidden.text)

        self._as("screen-1")
        seen = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(seen.status_code, 200, seen.text)
        moved = self.client.patch(
            f"/api/sessions/{session_id}",
            json={"position_ms": 1500, "state": "paused"},
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["position_ms"], 1500)
        self.assertEqual(moved.json()["state"], "paused")
        blocked = self.client.patch(f"/api/sessions/{session_id}", json={"level": "class"})
        self.assertEqual(blocked.status_code, 403, blocked.text)
        ended = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(ended.status_code, 403, ended.text)

        self._as("starter-1")
        leveled = self.client.patch(f"/api/sessions/{session_id}", json={"level": "class"})
        self.assertEqual(leveled.status_code, 200, leveled.text)
        self.assertEqual(leveled.json()["level"], "class")
        closed = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(closed.status_code, 200, closed.text)
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 404)

    def test_a_new_session_on_a_screen_replaces_the_old_one(self) -> None:
        self._as("starter-1")
        first = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": "movie-1"}
        ).json()["id"]
        second = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": "movie-2", "level": "off"}
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(self.client.get(f"/api/sessions/{first}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/sessions/{second.json()['id']}").json()["rating_key"], "movie-2")
        missing = self.client.post(
            "/api/sessions",
            json={"screen_id": "00000000-0000-4000-8000-0000000000ff", "rating_key": "movie-1"},
        )
        self.assertEqual(missing.status_code, 404, missing.text)
        bad = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": "movie-1", "level": "loud"}
        )
        self.assertEqual(bad.status_code, 400, bad.text)
