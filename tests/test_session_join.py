"""SES-005: join with a code or the owner's approval. Guests get a limited remote."""

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


class SessionJoinApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-session-join-secret-value"
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

    def _open(self) -> str:
        self._as("starter-1")
        opened = self.client.post(
            "/api/sessions", json={"screen_id": TV, "rating_key": "movie-1", "level": "off"}
        )
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertNotIn("join_code", opened.json())
        return opened.json()["id"]

    def test_code_join_and_guest_remote(self) -> None:
        session_id = self._open()
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["session_join"], 1)
        code = self.client.get(f"/api/sessions/{session_id}/code")
        self.assertEqual(code.status_code, 200, code.text)
        secret = code.json()["code"]
        self.assertEqual(len(secret), 8)

        self._as("other-1")
        hidden = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(hidden.status_code, 404, hidden.text)
        self.assertNotIn("movie-1", hidden.text)
        asked = self.client.post(f"/api/rooms/{TV}/join", json={})
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertEqual(asked.json()["status"], "pending")
        self.assertNotIn("movie-1", asked.text)
        self.assertNotIn(secret, asked.text)
        wrong = self.client.post(f"/api/rooms/{TV}/join", json={"code": "00000000"})
        self.assertEqual(wrong.status_code, 403, wrong.text)
        self.assertNotIn("movie-1", wrong.text)

        joined = self.client.post(f"/api/rooms/{TV}/join", json={"code": secret})
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertEqual(joined.json()["status"], "joined")
        self.assertEqual(joined.json()["rating_key"], "movie-1")
        self.assertNotIn(secret, joined.text)
        seen = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(seen.status_code, 200, seen.text)
        self.assertNotIn("code", seen.json())
        stolen = self.client.get(f"/api/sessions/{session_id}/code")
        self.assertEqual(stolen.status_code, 404, stolen.text)
        self.assertNotIn(secret, stolen.text)
        blocked = self.client.post(
            f"/api/sessions/{session_id}/commands", json={"command": "pause"}
        )
        self.assertEqual(blocked.status_code, 403, blocked.text)
        captions = self.client.post(
            f"/api/sessions/{session_id}/commands", json={"command": "captions", "id": "en"}
        )
        self.assertEqual(captions.status_code, 403, captions.text)
        ended = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(ended.status_code, 403, ended.text)
        moved = self.client.patch(f"/api/sessions/{session_id}", json={"position_ms": 10})
        self.assertEqual(moved.status_code, 403, moved.text)

        self._as("starter-1")
        allowed = self.client.patch(
            f"/api/sessions/{session_id}", json={"guests_may_remote": True}
        )
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertTrue(allowed.json()["guests_may_remote"])
        self._as("other-1")
        paused = self.client.post(
            f"/api/sessions/{session_id}/commands", json={"command": "pause"}
        )
        self.assertEqual(paused.status_code, 200, paused.text)
        self.assertEqual(paused.json()["state"], "paused")
        still = self.client.post(
            f"/api/sessions/{session_id}/commands", json={"command": "level", "level": "class"}
        )
        self.assertEqual(still.status_code, 403, still.text)
        left = self.client.delete(f"/api/sessions/{session_id}/guests/me")
        self.assertEqual(left.status_code, 200, left.text)
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 404)

    def test_owner_approval_and_not_now(self) -> None:
        session_id = self._open()
        self._as("other-1")
        asked = self.client.post(f"/api/rooms/{TV}/join", json={})
        request_id = asked.json()["request_id"]
        answer = self.client.post(
            f"/api/sessions/{session_id}/join-requests/{request_id}",
            json={"decision": "approve"},
        )
        self.assertEqual(answer.status_code, 404, answer.text)
        self.assertNotIn("movie-1", answer.text)

        self._as("starter-1")
        listed = self.client.get(f"/api/sessions/{session_id}/join-requests")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()["requests"][0]["display_name"], "Other")
        self.assertNotIn("movie-1", listed.text)
        approved = self.client.post(
            f"/api/sessions/{session_id}/join-requests/{request_id}",
            json={"decision": "approve"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        self._as("other-1")
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 200)

        self._as("starter-1")
        self.client.delete(f"/api/sessions/{session_id}/guests/me")
        # The owner is not a guest; the other member leaves, then asks again.
        self._as("other-1")
        self.client.delete(f"/api/sessions/{session_id}/guests/me")
        again = self.client.post(f"/api/rooms/{TV}/join", json={})
        self._as("starter-1")
        declined = self.client.post(
            f"/api/sessions/{session_id}/join-requests/{again.json()['request_id']}",
            json={"decision": "not_now"},
        )
        self.assertEqual(declined.status_code, 200, declined.text)
        self.assertEqual(declined.json()["status"], "declined")
        self._as("other-1")
        quiet = self.client.post(f"/api/rooms/{TV}/join", json={})
        self.assertEqual(quiet.json()["status"], "declined")
        self.assertNotIn("movie-1", quiet.text)
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 404)

    def test_wrong_codes_stop_after_a_few_tries(self) -> None:
        self._open()
        self._as("other-1")
        for _ in range(8):
            failed = self.client.post(f"/api/rooms/{TV}/join", json={"code": "ffffffff"})
            self.assertEqual(failed.status_code, 403, failed.text)
            self.assertNotIn("movie-1", failed.text)
        limited = self.client.post(f"/api/rooms/{TV}/join", json={"code": "ffffffff"})
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertNotIn("movie-1", limited.text)
