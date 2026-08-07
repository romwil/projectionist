"""Year in Review snapshot + delivery + admin generate."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from projectionist.year_in_review.delivery import (
    current_calendar_year,
    deliver_year_in_review,
    prior_calendar_year,
)
from projectionist.year_in_review.snapshot import build_reel_for_user, get_snapshot


class YearInReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir.db")
        self.settings = Settings()
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )
        self.db.update_user_profile("owner-1", year_in_review_opt_in=True, notify_channel_inbox=True)
        self.db.create_local_user(
            user_id="guest-1",
            display_name="Guest",
            password_hash="x",
            role="guest",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _seed_completions(self, *, user_id: str, plex_id: str, year: int, count: int = 4) -> None:
        start_ms, _ = year_bounds_ms(year)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"{user_id}-{i}",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key=plex_id,
                rating_key=f"movie-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(count)
        ]
        ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db, user_id=user_id)

    def test_calendar_year_helpers(self) -> None:
        mid_2026 = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
        self.assertEqual(current_calendar_year(mid_2026), 2026)
        self.assertEqual(prior_calendar_year(mid_2026), 2025)

    def test_build_reel_adaptive_chapters(self) -> None:
        year = 2024
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        snap = build_reel_for_user(self.db, user_id="owner-1", year=year)
        self.assertEqual(snap["status"], "ready")
        chapters = snap["reel"]["chapters"]
        self.assertGreaterEqual(len(chapters), 3)
        kinds = {c["kind"] for c in chapters}
        self.assertIn("overture", kinds)
        self.assertIn("honesty", kinds)
        # No social signals → no ratings/shares/live chapters required
        self.assertNotIn("ratings", kinds)

    def test_guest_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_reel_for_user(self.db, user_id="guest-1", year=2024)

    def test_delivery_opt_in_and_inbox(self) -> None:
        year = 2024
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            status_hint="ready",
        )
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["path"], f"/year-in-review/{year}")
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertIn(str(year), notes[0]["title"])
        loaded = get_snapshot(self.db, user_id="owner-1", year=year)
        self.assertIsNotNone(loaded)
        self.assertIsNotNone(loaded["notified_at"])

    def test_force_delivers_inbox_without_opt_in(self) -> None:
        """Owner test-send must create the production-shaped inbox item even without opt-in."""
        year = current_calendar_year()
        self.db.update_user_profile("owner-1", year_in_review_opt_in=False)
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            status_hint="ready",
            force=True,
        )
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["path"], f"/year-in-review/{year}")
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["kind"], "year-in-review")
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertEqual(notes[0]["title"], f"Your {year} Year in Review is ready")

    def test_force_without_notify_gate_still_skips_empty(self) -> None:
        year = current_calendar_year()
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            force=True,
        )
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["delivered"], 0)
        self.assertEqual(result["status"], "empty")
        self.assertIsNone(result["path"])
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 0)

    def test_empty_year_skips_delivery(self) -> None:
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=2020,
            user_ids=["owner-1"],
        )
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["delivered"], 0)


class YearInReviewAdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-yir-secret"
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
            "CURATORX_SKIP_DOTENV",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _seed_owner_completions(self, year: int) -> str:
        db = self.app_mod._db()
        me = self.client.get("/api/auth/me").json()["user"]
        user_id = str(me["id"])
        db.update_user_profile(
            user_id,
            year_in_review_opt_in=True,
            notify_channel_inbox=True,
        )

        def _map_plex() -> None:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE users SET plex_user_id = ? WHERE id = ?",
                    ("111", user_id),
                )

        db.run_write(_map_plex, label="map_bootstrap_plex")
        start_ms, _ = year_bounds_ms(year)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"api-{i}",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="111",
                rating_key=f"api-movie-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(4)
        ]
        ingest_watch_events(db, events)
        rebuild_watch_derivations(db, user_id=user_id)
        return user_id

    def test_admin_generate_defaults_to_current_year_and_is_ready(self) -> None:
        year = current_calendar_year()
        user_id = self._seed_owner_completions(year)
        with patch(
            "projectionist.year_in_review.delivery.prior_calendar_year",
            return_value=year - 1,
        ):
            resp = self.client.post(
                "/api/admin/year-in-review/generate",
                json={"scope": "self", "notify": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["year"], year)
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["path"], f"/year-in-review/{year}")
        self.assertEqual(body["delivered"], 1)
        self.assertEqual(body["generated"], 1)

        got = self.client.get(f"/api/year-in-review/{year}")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()["status"], "ready")
        self.assertGreaterEqual(len(got.json()["reel"]["chapters"]), 3)

        notes = self.app_mod._db().list_notifications_for_user(user_id, kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertEqual(notes[0]["title"], f"Your {year} Year in Review is ready")

    def test_admin_generate_empty_year_omits_path(self) -> None:
        year = current_calendar_year()
        resp = self.client.post(
            "/api/admin/year-in-review/generate",
            json={"scope": "self", "notify": False, "year": year},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["year"], year)
        self.assertEqual(body["status"], "empty")
        self.assertIsNone(body.get("path"))
        self.assertEqual(
            self.client.get(f"/api/year-in-review/{year}").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
