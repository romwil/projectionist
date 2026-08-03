"""Watch tracker ledger, correlation, and year rollups."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.plex_history import parse_history_page
from projectionist.watch_tracker.rollups import build_year_rollup, year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events, watch_tracker_status


class WatchTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.db.upsert_plex_user(
            user_id="user-a",
            display_name="Ada",
            email="ada@example.com",
            plex_user_id="4242",
            role="owner",
        )
        self.db.upsert_plex_user(
            user_id="user-b",
            display_name="Bea",
            email="bea@example.com",
            plex_user_id="9999",
            role="member",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_history_fixture_normalizes(self) -> None:
        xml_path = Path(__file__).parent / "fixtures" / "plex" / "history_page_1.xml"
        root = ElementTree.fromstring(xml_path.read_text(encoding="utf-8"))
        page, events = parse_history_page(root, server_machine_id="server-1")
        self.assertEqual(page.size, 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].source_event_kind, "history_played")
        self.assertEqual(events[0].source_user_key, "4242")

    def test_ingest_idempotent_and_user_isolation(self) -> None:
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id="e1",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="4242",
                rating_key="m1",
                media_type="movie",
                occurred_at_ms=1_700_000_000_000,
                terminal=True,
            ),
            WatchEventInput(
                source="plex_history",
                source_event_id="e2",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="9999",
                rating_key="m1",
                media_type="movie",
                occurred_at_ms=1_700_000_100_000,
                terminal=True,
            ),
        ]
        first = ingest_watch_events(self.db, events)
        second = ingest_watch_events(self.db, events)
        self.assertEqual(first.inserted, 2)
        self.assertEqual(second.inserted, 0)
        self.assertEqual(second.deduped, 2)
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT user_id, source_user_key FROM watch_events ORDER BY occurred_at_ms"
            ).fetchall()
        self.assertEqual(str(rows[0]["user_id"]), "user-a")
        self.assertEqual(str(rows[1]["user_id"]), "user-b")

    def test_correlation_threshold_crossing_certain(self) -> None:
        start = 1_704_067_200_000  # ~2024-01-01
        events = [
            WatchEventInput(
                source="plex_webhook",
                source_event_id="p1",
                source_event_kind="session_progress",
                server_machine_id="srv",
                source_user_key="4242",
                rating_key="movie-x",
                media_type="movie",
                occurred_at_ms=start,
                progress_ms=1_000_000,
                duration_ms=6_000_000,
            ),
            WatchEventInput(
                source="plex_webhook",
                source_event_id="p2",
                source_event_kind="session_stop",
                server_machine_id="srv",
                source_user_key="4242",
                rating_key="movie-x",
                media_type="movie",
                occurred_at_ms=start + 3_600_000,
                progress_ms=5_500_000,
                duration_ms=6_000_000,
                terminal=True,
            ),
        ]
        ingest_watch_events(self.db, events)
        result = rebuild_watch_derivations(self.db, user_id="user-a")
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(result["completions"], 1)
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT confidence, basis FROM watch_completions WHERE user_id = ?",
                ("user-a",),
            ).fetchone()
        self.assertEqual(row["confidence"], "certain")

    def test_year_rollup_scoped_to_user(self) -> None:
        year = 2024
        start_ms, _ = year_bounds_ms(year)
        for i, (plex_id, uid) in enumerate((("4242", "user-a"), ("9999", "user-b"))):
            events = [
                WatchEventInput(
                    source="plex_history",
                    source_event_id=f"{uid}-{j}",
                    source_event_kind="history_played",
                    server_machine_id="srv",
                    source_user_key=plex_id,
                    rating_key=f"m-{uid}-{j}",
                    media_type="movie",
                    occurred_at_ms=start_ms + j * 86_400_000,
                    terminal=True,
                )
                for j in range(3)
            ]
            ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db)
        rollup_a = build_year_rollup(self.db, user_id="user-a", year=year)
        rollup_b = build_year_rollup(self.db, user_id="user-b", year=year)
        self.assertEqual(rollup_a.completion_count, 3)
        self.assertEqual(rollup_b.completion_count, 3)
        self.assertTrue(rollup_a.has_enough_data)
        status = watch_tracker_status(self.db)
        self.assertEqual(status["completions"], 6)
        self.assertNotIn("4242", str(status))


if __name__ == "__main__":
    unittest.main()
