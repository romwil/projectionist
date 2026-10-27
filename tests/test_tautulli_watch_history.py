"""Optional Tautulli history adapter: skip when off, merge without duplicating Plex."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.watch_tracker.tautulli_history import (
    fetch_tautulli_history_events,
    normalize_tautulli_history_row,
)
from projectionist.watch_tracker.year_backfill import backfill_member_year_history
from projectionist.year_in_review.snapshot import build_reel_for_user


class TautulliHistoryAdapterTests(unittest.TestCase):
    def test_normalize_movie_play(self) -> None:
        event = normalize_tautulli_history_row(
            {
                "row_id": 42,
                "user_id": 111,
                "rating_key": 9001,
                "media_type": "movie",
                "date": 1_704_067_200,
                "stopped": 1_704_067_200,
                "duration": 7200,
                "percent_complete": 100,
            },
            server_machine_id="server-1",
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.source, "tautulli_history")
        self.assertEqual(event.source_event_kind, "tautulli_history")
        self.assertEqual(event.source_user_key, "111")
        self.assertEqual(event.rating_key, "9001")
        self.assertEqual(event.source_event_id, "tautulli:42")
        self.assertTrue(event.terminal)
        self.assertEqual(event.duration_ms, 7_200_000)
        self.assertEqual(event.progress_ms, 7_200_000)

    def test_skips_live_and_missing_identity(self) -> None:
        self.assertIsNone(
            normalize_tautulli_history_row(
                {"user_id": 111, "rating_key": 1, "media_type": "live", "date": 1},
                server_machine_id="server-1",
            )
        )
        self.assertIsNone(
            normalize_tautulli_history_row(
                {"user_id": 0, "rating_key": 1, "media_type": "movie", "date": 1},
                server_machine_id="server-1",
            )
        )


class TautulliHistoryIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "tautulli-history.db")
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )
        self.year = 2024
        self.start_ms, _ = year_bounds_ms(self.year)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_unconfigured_tautulli_skips_cleanly(self) -> None:
        events, meta = fetch_tautulli_history_events(
            Settings(),
            server_machine_id="server-1",
            account_ids=["111"],
            since_ms=self.start_ms,
        )
        self.assertEqual(events, [])
        self.assertEqual(meta["status"], "skipped")
        self.assertEqual(meta["reason"], "tautulli_not_configured")

    def test_merges_without_duplicating_a_plex_row(self) -> None:
        occurred = self.start_ms + 86_400_000
        plex = WatchEventInput(
            source="plex_history",
            source_event_id="plex-1",
            source_event_kind="history_played",
            server_machine_id="server-1",
            source_user_key="111",
            rating_key="shared-1",
            media_type="movie",
            occurred_at_ms=occurred,
            terminal=True,
        )
        tautulli = WatchEventInput(
            source="tautulli_history",
            source_event_id="tautulli:9",
            source_event_kind="tautulli_history",
            server_machine_id="server-1",
            source_user_key="111",
            rating_key="shared-1",
            media_type="movie",
            occurred_at_ms=occurred + 30_000,
            terminal=True,
        )
        ingest_watch_events(self.db, [plex])
        result = ingest_watch_events(self.db, [tautulli])
        self.assertEqual(result.inserted, 1)
        with self.db.connect() as conn:
            rows = list(
                conn.execute(
                    """
                    SELECT source, duplicate_of_event_id
                    FROM watch_events
                    ORDER BY occurred_at_ms
                    """
                )
            )
            completions = conn.execute(
                """
                SELECT COUNT(*) AS c FROM watch_completions
                WHERE user_id = 'owner-1' AND superseded_by_completion_id IS NULL
                """
            ).fetchone()
        self.assertEqual(rows[0]["source"], "plex_history")
        self.assertIsNone(rows[0]["duplicate_of_event_id"])
        self.assertEqual(rows[1]["source"], "tautulli_history")
        self.assertIsNotNone(rows[1]["duplicate_of_event_id"])
        self.assertEqual(int(completions["c"]), 1)

    def test_year_backfill_tautulli_on_merges_with_plex(self) -> None:
        titles = ["Alpha", "Bravo", "Charlie", "Delta"]
        for i, title in enumerate(titles):
            self.db.upsert_library_item(
                {
                    "rating_key": f"movie-{i}",
                    "media_type": "movie",
                    "title": title,
                    "year": 2020,
                }
            )

        from projectionist.watch_tracker.plex_history import PlexHistoryItem, PlexHistoryPage

        items = [
            PlexHistoryItem(
                rating_key="movie-0",
                media_type="movie",
                account_id="111",
                viewed_at_ms=self.start_ms + 86_400_000,
                history_key="plex-0",
            )
        ]
        page = PlexHistoryPage(items=items, total_size=1, size=1, start=0)
        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"

        def history_page(*, start=0, size=250, since_ms=None, until_ms=None, account_id=None):
            if start > 0:
                return PlexHistoryPage(items=[], total_size=1, size=0, start=start)
            return page

        client.history_page.side_effect = history_page

        tautulli_rows = [
            {
                "row_id": 1,
                "user_id": 111,
                "rating_key": "movie-0",
                "media_type": "movie",
                "date": (self.start_ms + 86_400_000) // 1000 + 20,
                "duration": 5400,
            },
            *[
                {
                    "row_id": i + 2,
                    "user_id": 111,
                    "rating_key": f"movie-{i + 1}",
                    "media_type": "movie",
                    "date": (self.start_ms + (i + 2) * 86_400_000) // 1000,
                    "duration": 5400,
                }
                for i in range(3)
            ],
        ]
        tautulli_client = unittest.mock.Mock()
        tautulli_client.get_history.return_value = {
            "data": tautulli_rows,
            "recordsFiltered": len(tautulli_rows),
            "recordsTotal": len(tautulli_rows),
        }
        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="secret",
            tautulli_url="http://tautulli.test",
            tautulli_api_key="k",
        )
        with (
            patch(
                "projectionist.watch_tracker.year_backfill._plex_client",
                return_value=client,
            ),
            patch(
                "projectionist.watch_tracker.year_backfill.sync_plex_watch_identities",
                return_value={"alias": {"status": "ok"}},
            ),
            patch(
                "projectionist.watch_tracker.tautulli_history._client",
                return_value=tautulli_client,
            ),
        ):
            backfill = backfill_member_year_history(
                self.db, settings, user_id="owner-1", year=self.year
            )
            snap = build_reel_for_user(self.db, user_id="owner-1", year=self.year)

        self.assertEqual(backfill["tautulli"]["status"], "ok")
        with self.db.connect() as conn:
            plex_rows = conn.execute(
                "SELECT id FROM watch_events WHERE source = 'plex_history' AND rating_key = 'movie-0'"
            ).fetchall()
            tautulli_dupes = conn.execute(
                """
                SELECT duplicate_of_event_id FROM watch_events
                WHERE source = 'tautulli_history' AND rating_key = 'movie-0'
                """
            ).fetchall()
            completions = conn.execute(
                """
                SELECT rating_key, COUNT(*) AS c FROM watch_completions
                WHERE user_id = 'owner-1' AND superseded_by_completion_id IS NULL
                GROUP BY rating_key
                """
            ).fetchall()
        self.assertEqual(len(plex_rows), 1)
        self.assertEqual(len(tautulli_dupes), 1)
        self.assertEqual(tautulli_dupes[0]["duplicate_of_event_id"], plex_rows[0]["id"])
        counts = {str(row["rating_key"]): int(row["c"]) for row in completions}
        self.assertEqual(counts.get("movie-0"), 1)
        self.assertEqual(snap["status"], "ready")
        reel_keys = {row["rating_key"] for row in snap["reel"]["rollup"]["top_movies"]}
        self.assertIn("movie-0", reel_keys)
        self.assertIn("movie-1", reel_keys)
