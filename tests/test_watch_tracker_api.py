"""Owner-only watch tracker status API tests."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.auth import SESSION_COOKIE_NAME
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    clear_session_secret_cache,
    create_session_token,
)
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.store import ingest_watch_events, set_ingest_cursor


class WatchTrackerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["CURATORX_SESSION_SECRET"] = "watch-tracker-test-secret"
        clear_session_secret_cache()
        clear_rate_limits()
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
        for key in (
            "DATA_DIR",
            "CURATORX_SKIP_DOTENV",
            "CURATORX_SESSION_SECRET",
        ):
            os.environ.pop(key, None)
        self._tmp.cleanup()

    def _seed_status(self) -> None:
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="owner-real",
            display_name="Owner",
            email=None,
            plex_user_id="4242",
            role="owner",
        )
        ingest_watch_events(
            db,
            [
                WatchEventInput(
                    source="plex_history",
                    source_event_id="history-secret",
                    source_event_kind="history_played",
                    server_machine_id="server-secret",
                    source_user_key="4242",
                    rating_key="title-secret",
                    media_type="movie",
                    occurred_at_ms=1_704_067_200_000,
                    terminal=True,
                ),
                WatchEventInput(
                    source="plex_history",
                    source_event_id="history-unmapped",
                    source_event_kind="history_played",
                    server_machine_id="server-secret",
                    source_user_key="unmapped-secret",
                    rating_key="other-secret",
                    media_type="movie",
                    occurred_at_ms=1_704_067_201_000,
                    terminal=True,
                ),
            ],
        )
        set_ingest_cursor(
            db,
            source="plex_history",
            server_machine_id="server-secret",
            high_watermark_ms=1_704_067_201_000,
        )

    def test_owner_status_reports_health_without_identity_or_title_leaks(self) -> None:
        self._seed_status()
        response = self.client.get("/api/admin/watch-tracker/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["events_total"], 2)
        self.assertEqual(body["events_mapped"], 1)
        self.assertEqual(body["events_unmapped"], 1)
        self.assertEqual(body["sources"][0]["source"], "plex_history")
        self.assertEqual(body["sources"][0]["capability"], "available")
        serialized = json.dumps(body)
        for secret in (
            "server-secret",
            "4242",
            "unmapped-secret",
            "title-secret",
            "other-secret",
            "history-secret",
        ):
            self.assertNotIn(secret, serialized)

    def test_member_cannot_read_owner_status(self) -> None:
        (Path(self._tmp.name) / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                }
            ),
            encoding="utf-8",
        )
        self.app_mod._db().upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email=None,
            plex_user_id="9999",
            role="member",
        )
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))

        response = member.get("/api/admin/watch-tracker/status")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
