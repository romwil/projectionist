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

    def _enable_multi_user(self) -> None:
        (Path(self._tmp.name) / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                }
            ),
            encoding="utf-8",
        )

    def _seed_user_summaries(self) -> None:
        db = self.app_mod._db()
        for user_id, plex_id, role in (
            ("user-a", "4242", "owner"),
            ("user-b", "9999", "member"),
        ):
            db.upsert_plex_user(
                user_id=user_id,
                display_name=user_id,
                email=None,
                plex_user_id=plex_id,
                role=role,
            )
        base = 1_704_067_200_000
        events = []
        for index, (user_key, title) in enumerate(
            (("4242", "movie-shared"), ("9999", "movie-shared"))
        ):
            events.extend(
                [
                    WatchEventInput(
                        source="plex_session",
                        source_event_id=f"{user_key}-low",
                        source_event_kind="session_progress",
                        server_machine_id="server",
                        source_user_key=user_key,
                        rating_key=title,
                        media_type="movie",
                        occurred_at_ms=base + index * 10_000_000,
                        progress_ms=100_000,
                        duration_ms=1_000_000,
                    ),
                    WatchEventInput(
                        source="plex_session",
                        source_event_id=f"{user_key}-done",
                        source_event_kind="session_stop",
                        server_machine_id="server",
                        source_user_key=user_key,
                        rating_key=title,
                        media_type="movie",
                        occurred_at_ms=base + index * 10_000_000 + 600_000,
                        progress_ms=950_000,
                        duration_ms=1_000_000,
                        terminal=True,
                    ),
                ]
            )
        events.extend(
            [
                WatchEventInput(
                    source="plex_session",
                    source_event_id="episode-low",
                    source_event_kind="session_progress",
                    server_machine_id="server",
                    source_user_key="4242",
                    rating_key="episode-1",
                    parent_rating_key="show-1",
                    media_type="episode",
                    occurred_at_ms=base + 20_000_000,
                    progress_ms=100_000,
                    duration_ms=1_000_000,
                ),
                WatchEventInput(
                    source="plex_session",
                    source_event_id="episode-done",
                    source_event_kind="session_stop",
                    server_machine_id="server",
                    source_user_key="4242",
                    rating_key="episode-1",
                    parent_rating_key="show-1",
                    media_type="episode",
                    occurred_at_ms=base + 20_600_000,
                    progress_ms=950_000,
                    duration_ms=1_000_000,
                    terminal=True,
                ),
            ]
        )
        ingest_watch_events(db, events)

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
        self._enable_multi_user()
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

    def test_current_user_summary_is_scoped_to_authenticated_user(self) -> None:
        self._enable_multi_user()
        self._seed_user_summaries()
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("user-b"))

        response = member.get("/api/watch-tracker/summary/movie-shared")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tracked_completions"], 1)
        self.assertEqual(body["completion_confidence"]["certain"], 1)
        self.assertEqual(len(body["completion_timeline"]), 1)
        self.assertEqual(body["completion_timeline"][0]["confidence"], "certain")
        self.assertEqual(
            body["completion_timeline"][0]["basis"],
            "observed_threshold_crossing",
        )
        self.assertNotIn("user-a", json.dumps(body))
        self.assertNotIn("4242", json.dumps(body))

    def test_show_summary_rolls_up_episode_completions(self) -> None:
        self._enable_multi_user()
        self._seed_user_summaries()
        owner = TestClient(self.app_mod.app)
        owner.cookies.set(SESSION_COOKIE_NAME, create_session_token("user-a"))

        response = owner.get("/api/watch-tracker/shows/show-1/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unique_episodes_completed"], 1)
        self.assertEqual(response.json()["total_episode_completions"], 1)
        self.assertEqual(response.json()["repeat_episode_completions"], 0)
        self.assertEqual(
            response.json()["recent_activity"][0]["rating_key"],
            "episode-1",
        )
        self.assertEqual(
            response.json()["episode_completions"]["episode-1"]["tracked_completions"],
            1,
        )

    def test_library_cards_adopt_only_current_users_tracker_summary(self) -> None:
        self._enable_multi_user()
        self._seed_user_summaries()
        self.app_mod._db().upsert_library_item(
            {
                "rating_key": "movie-shared",
                "media_type": "movie",
                "title": "Shared Movie",
                "view_count": 4,
            }
        )
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("user-b"))

        response = member.get("/api/library/query", params={"query": "Shared Movie"})

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["tracked_completions"], 1)
        self.assertEqual(item["completion_confidence"]["certain"], 1)
        self.assertEqual(item["plex_played_event_count"], 4)
        self.assertNotIn("rating_key", item)

    def test_owner_evidence_diagnostics_are_sanitized_and_member_forbidden(self) -> None:
        self._enable_multi_user()
        self._seed_user_summaries()
        owner = TestClient(self.app_mod.app)
        owner.cookies.set(SESSION_COOKIE_NAME, create_session_token("user-a"))
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("user-b"))

        response = owner.get(
            "/api/admin/watch-tracker/evidence",
            params={"rating_key": "movie-shared", "limit": 20},
        )
        forbidden = member.get("/api/admin/watch-tracker/evidence")

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["count"], 0)
        serialized = json.dumps(response.json())
        self.assertNotIn("source_user_key", serialized)
        self.assertNotIn("4242", serialized)
        self.assertNotIn("9999", serialized)
        self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
