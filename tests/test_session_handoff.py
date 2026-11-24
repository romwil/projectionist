"""SES-007: handoff keeps the session and moves the screen."""

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

LIVING = "00000000-0000-4000-8000-0000000000aa"
DEN = "00000000-0000-4000-8000-0000000000bb"


class SessionHandoffApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-session-handoff-secret"
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
            ("living-1", "Living", "1"),
            ("den-1", "Den", "2"),
            ("starter-1", "Starter", "3"),
            ("other-1", "Other", "4"),
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
                    ) VALUES (?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        LIVING, "living-1", "Living Room", "hash-a", 10.0, "tv",
                        DEN, "den-1", "Den", "hash-b", 10.0, "tv",
                    ),
                )

        db.run_write(_write, label="test_screens")
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("starter-1"))
        opened = self.client.post(
            "/api/sessions",
            json={"screen_id": LIVING, "rating_key": "movie-1", "level": "moments"},
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        self.session_id = opened.json()["id"]
        self.client.patch(f"/api/sessions/{self.session_id}", json={"position_ms": 42000})

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_shared_sessions()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        self._tmpdir.cleanup()

    def test_the_session_moves_and_keeps_its_place(self) -> None:
        self.assertEqual(
            self.client.get("/api/features").json()["capabilities"]["session_handoff"], 1
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("other-1"))
        refused = self.client.post(
            f"/api/sessions/{self.session_id}/handoff", json={"screen_id": DEN}
        )
        self.assertEqual(refused.status_code, 404, refused.text)
        self.assertNotIn("movie-1", refused.text)

        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("starter-1"))
        moved = self.client.post(
            f"/api/sessions/{self.session_id}/handoff", json={"screen_id": DEN}
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        body = moved.json()
        self.assertEqual(body["id"], self.session_id)
        self.assertEqual(body["screen_id"], DEN)
        self.assertEqual(body["position_ms"], 42000)
        self.assertEqual(body["level"], "moments")

        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("living-1"))
        self.assertEqual(self.client.get(f"/api/sessions/{self.session_id}").status_code, 404)
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("den-1"))
        seen = self.client.get(f"/api/sessions/{self.session_id}")
        self.assertEqual(seen.status_code, 200, seen.text)
        self.assertEqual(seen.json()["position_ms"], 42000)
