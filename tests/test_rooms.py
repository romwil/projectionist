"""SES-002: named screens are visible; what is playing is not."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db._shared import begin_immediate
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

TV = "00000000-0000-4000-8000-0000000000aa"
PHONE = "00000000-0000-4000-8000-0000000000bb"
GONE = "00000000-0000-4000-8000-0000000000cc"


class RoomsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-rooms-session-secret-value"
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

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
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

    def _add(self, device_id: str, user_id: str, label: str, kind: str, *, revoked: float | None = None) -> None:
        db = self.app_mod._db()

        def _write() -> None:
            with db.connect() as conn:
                begin_immediate(conn)
                conn.execute(
                    """
                    INSERT INTO paired_devices (
                        id, user_id, label, credential_hash, created_at, revoked_at, kind
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, user_id, label, f"hash-{device_id}", 10.0, revoked, kind),
                )

        db.run_write(_write, label="test_room")

    def test_screens_are_rooms_and_playback_is_absent(self) -> None:
        self.client.get("/api/features")
        owner_id = self.client.get("/api/features").json()["user"]["id"]
        self._add(TV, owner_id, "Living Room", "tv")
        self._add(PHONE, owner_id, "Pocket", "iphone")
        self._add(GONE, owner_id, "Old TV", "tv", revoked=20.0)
        body = self.client.get("/api/rooms")
        self.assertEqual(body.status_code, 200, body.text)
        self.assertEqual(body.json()["rooms"], [{"id": TV, "name": "Living Room", "kind": "tv"}])
        self.assertEqual(self.client.get("/api/features").json()["capabilities"]["rooms"], 1)
        renamed = self.client.patch(f"/api/rooms/{TV}", json={"name": "  Den  "})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Den")
        missing = self.client.patch(f"/api/rooms/{PHONE}", json={"name": "Nope"})
        self.assertEqual(missing.status_code, 404, missing.text)
        blank = self.client.patch(f"/api/rooms/{TV}", json={"name": "   "})
        self.assertEqual(blank.status_code, 400, blank.text)

    def test_a_member_can_see_rooms_and_cannot_rename_someone_elses(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "local_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email=None,
            plex_user_id="1",
            role="owner",
        )
        db.upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email=None,
            plex_user_id="2",
            role="member",
        )
        self._add(TV, "owner-1", "Living Room", "tv")
        signed_out = self.client.get("/api/rooms")
        self.assertEqual(signed_out.status_code, 401, signed_out.text)
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))
        seen = self.client.get("/api/rooms")
        self.assertEqual(seen.status_code, 200, seen.text)
        self.assertEqual(seen.json()["rooms"][0]["name"], "Living Room")
        self.assertNotIn("user_id", seen.json()["rooms"][0])
        denied = self.client.patch(f"/api/rooms/{TV}", json={"name": "Mine"})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("owner-1"))
        allowed = self.client.patch(f"/api/rooms/{TV}", json={"name": "Den"})
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json(), {"id": TV, "name": "Den", "kind": "tv"})
