"""Year in Review generate backfills that member's Plex year (not live sessions)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.plex_history import PlexHistoryItem, PlexHistoryPage
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.year_backfill import backfill_member_year_history
from projectionist.year_in_review.delivery import deliver_year_in_review
from projectionist.year_in_review.snapshot import build_reel_for_user, get_snapshot


class YearInReviewPlexHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir-history.db")
        self.settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="secret",
        )
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )
        self.db.update_user_profile(
            "owner-1", year_in_review_opt_in=True, notify_channel_inbox=True
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _page_for(self, year: int, account_id: str, titles: list[str]) -> PlexHistoryPage:
        start_ms, _ = year_bounds_ms(year)
        items = [
            PlexHistoryItem(
                rating_key=f"yir-{i}",
                media_type="movie",
                account_id=account_id,
                viewed_at_ms=start_ms + (i + 1) * 86_400_000,
                history_key=f"hist-{i}",
                title=title,
            )
            for i, title in enumerate(titles)
        ]
        return PlexHistoryPage(
            items=items,
            total_size=len(items),
            size=len(items),
            start=0,
        )

    def _mock_client(self, page: PlexHistoryPage):
        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"

        def history_page(*, start=0, size=250, since_ms=None, until_ms=None, account_id=None):
            if start > 0:
                return PlexHistoryPage(items=[], total_size=page.total_size, size=0, start=start)
            if account_id and page.items and str(page.items[0].account_id) != str(account_id):
                return PlexHistoryPage(items=[], total_size=0, size=0, start=start)
            return page

        client.history_page.side_effect = history_page
        return client

    def test_generate_from_plex_year_history_without_live_sessions(self) -> None:
        year = 2024
        titles = ["January Watch", "Spring Watch", "Summer Watch", "Autumn Watch"]
        for i, title in enumerate(titles):
            self.db.upsert_library_item(
                {
                    "rating_key": f"yir-{i}",
                    "media_type": "movie",
                    "title": title,
                    "year": 2020,
                }
            )
        page = self._page_for(year, "111", titles)
        client = self._mock_client(page)

        with (
            patch(
                "projectionist.watch_tracker.year_backfill._plex_client",
                return_value=client,
            ),
            patch(
                "projectionist.watch_tracker.year_backfill.sync_plex_watch_identities",
                return_value={"alias": {"status": "ok"}},
            ),
        ):
            result = deliver_year_in_review(
                self.db,
                self.settings,
                year=year,
                user_ids=["owner-1"],
                status_hint="ready",
            )

        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["status"], "ready")
        snap = get_snapshot(self.db, user_id="owner-1", year=year)
        self.assertIsNotNone(snap)
        assert snap is not None
        reel_titles = {row["title"] for row in snap["reel"]["rollup"]["top_movies"]}
        self.assertTrue({"January Watch", "Spring Watch", "Summer Watch"}.issubset(reel_titles))
        self.assertGreaterEqual(snap["reel"]["rollup"]["completion_count"], 4)
        self.assertEqual(snap["reel"]["rollup"]["confidence"]["plex_event_only"], 4)
        self.assertEqual(snap["reel"]["rollup"]["confidence"]["certain"], 0)
        self.assertIn("this account", snap["reel"]["honesty"]["footnote"])
        self.assertIn("played", snap["reel"]["honesty"]["confidence_note"].lower())
        # No live session rows — Plex history plays only.
        with self.db.connect() as conn:
            kinds = {
                str(row["source_event_kind"])
                for row in conn.execute("SELECT source_event_kind FROM watch_events")
            }
        self.assertEqual(kinds, {"history_played"})

    def test_tautulli_off_still_builds_from_plex(self) -> None:
        year = 2024
        page = self._page_for(year, "111", ["One", "Two", "Three", "Four"])
        client = self._mock_client(page)
        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="secret",
            tautulli_url="",
            tautulli_api_key="",
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
            ) as tautulli_ctor,
        ):
            backfill = backfill_member_year_history(
                self.db, settings, user_id="owner-1", year=year
            )
            snap = build_reel_for_user(self.db, user_id="owner-1", year=year)

        tautulli_ctor.assert_not_called()
        self.assertEqual(backfill["tautulli"]["status"], "skipped")
        self.assertEqual(snap["status"], "ready")
        self.assertGreaterEqual(snap["reel"]["rollup"]["completion_count"], 4)

    def test_unmapped_account_stays_empty(self) -> None:
        year = 2024
        self.db.create_local_user(
            user_id="stranger-1",
            display_name="Stranger",
            password_hash="x",
            role="member",
        )
        page = self._page_for(year, "999", ["Household Hit"] * 4)
        client = self._mock_client(page)
        with (
            patch(
                "projectionist.watch_tracker.year_backfill._plex_client",
                return_value=client,
            ),
            patch(
                "projectionist.watch_tracker.year_backfill.sync_plex_watch_identities",
                return_value={"alias": {"status": "ok"}},
            ),
        ):
            backfill = backfill_member_year_history(
                self.db, self.settings, user_id="stranger-1", year=year
            )
            snap = build_reel_for_user(self.db, user_id="stranger-1", year=year)

        self.assertEqual(backfill["status"], "skipped")
        self.assertEqual(backfill["reason"], "unmapped")
        self.assertEqual(snap["status"], "empty")
        self.assertEqual(snap["reel"]["rollup"]["completion_count"], 0)
        client.history_page.assert_not_called()
