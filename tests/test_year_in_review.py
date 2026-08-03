"""Year in Review snapshot + delivery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.year_in_review.delivery import deliver_year_in_review
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
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        loaded = get_snapshot(self.db, user_id="owner-1", year=year)
        self.assertIsNotNone(loaded)
        self.assertIsNotNone(loaded["notified_at"])

    def test_empty_year_skips_delivery(self) -> None:
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=2020,
            user_ids=["owner-1"],
        )
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["delivered"], 0)


if __name__ == "__main__":
    unittest.main()
