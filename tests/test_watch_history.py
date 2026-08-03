"""Phase 1 Plex history ledger and scheduler tests."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient
from projectionist.library.db import Database
from projectionist.scheduler.tasks import watch_history_ingest
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.plex_history import (
    PlexHistoryItem,
    PlexHistoryPage,
    parse_history_page,
)
from projectionist.watch_tracker.store import (
    get_ingest_cursor,
    ingest_watch_events,
    set_ingest_cursor,
)


FIXTURES = Path(__file__).parent / "fixtures" / "plex"


class PlexHistoryParserTests(unittest.TestCase):
    def test_history_page_parses_movies_episodes_and_paging(self) -> None:
        root = ElementTree.fromstring(
            (FIXTURES / "history_page_1.xml").read_text(encoding="utf-8")
        )
        requested: list[str] = []
        client = PlexClient("http://plex.test:32400", "secret")
        client._machine_identifier = "server-1"

        def request(path: str):
            requested.append(path)
            return root

        with patch.object(client, "_request_xml", side_effect=request):
            page = client.history_page(start=250, size=250, since_ms=1_704_000_000_000)

        self.assertEqual(page.size, 2)
        self.assertEqual([item.media_type for item in page.items], ["movie", "episode"])
        self.assertEqual(page.items[1].parent_rating_key, "show-50")
        query = parse_qs(urlsplit(requested[0]).query)
        self.assertEqual(query["X-Plex-Container-Start"], ["250"])
        self.assertEqual(query["X-Plex-Container-Size"], ["250"])
        self.assertEqual(query["viewedAt>"], ["1704000000"])
        self.assertNotIn("secret", requested[0])

    def test_parser_skips_malformed_rows_without_breaking_page_offset(self) -> None:
        root = ElementTree.fromstring(
            (FIXTURES / "history_page_2.xml").read_text(encoding="utf-8")
        )
        page, events = parse_history_page(root, server_machine_id="server-1", start=2)

        self.assertEqual(page.size, 3)
        self.assertEqual(len(events), 2)
        self.assertIsNone(events[0].duration_ms)
        self.assertIsNone(events[1].source_event_id)
        self.assertEqual(events[1].source_user_key, "unknown-account")

    def test_history_endpoint_failure_is_propagated(self) -> None:
        client = PlexClient("http://plex.test:32400", "secret")
        client._machine_identifier = "server-1"
        with patch.object(client, "_request_xml", side_effect=RuntimeError("HTTP 404")):
            with self.assertRaisesRegex(RuntimeError, "404"):
                client.history_page(start=0, size=250, since_ms=None)


class WatchLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.db.upsert_plex_user(
            user_id="user-a",
            display_name="A",
            email=None,
            plex_user_id="4242",
            role="owner",
        )
        self.db.upsert_plex_user(
            user_id="user-b",
            display_name="B",
            email=None,
            plex_user_id="9999",
            role="member",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_migration_creates_phase_one_tables_and_indexes(self) -> None:
        with self.db.connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            indexes = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                ).fetchall()
            }
        self.assertTrue(
            {"watch_ingest_cursors", "watch_source_identities", "watch_events"}.issubset(
                tables
            )
        )
        self.assertTrue(
            {
                "idx_watch_events_source_id",
                "idx_watch_events_fingerprint",
                "idx_watch_events_correlation",
                "idx_watch_events_user_time",
            }.issubset(indexes)
        )

    def test_replay_is_idempotent_and_accounts_stay_isolated(self) -> None:
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"history-{plex_id}",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key=plex_id,
                rating_key="same-title",
                media_type="movie",
                occurred_at_ms=1_704_067_200_000,
                terminal=True,
            )
            for plex_id in ("4242", "9999", "unknown")
        ]
        first = ingest_watch_events(self.db, events)
        second = ingest_watch_events(self.db, events)

        self.assertEqual((first.inserted, second.inserted, second.deduped), (3, 0, 3))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT source_user_key, user_id FROM watch_events ORDER BY source_user_key"
            ).fetchall()
        mapped = {row["source_user_key"]: row["user_id"] for row in rows}
        self.assertEqual(mapped["4242"], "user-a")
        self.assertEqual(mapped["9999"], "user-b")
        self.assertIsNone(mapped["unknown"])


class WatchHistorySchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="secret",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    @staticmethod
    def _event(event_id: str, occurred_at_ms: int) -> WatchEventInput:
        return WatchEventInput(
            source="plex_history",
            source_event_id=event_id,
            source_event_kind="history_played",
            server_machine_id="server-1",
            source_user_key="4242",
            rating_key=event_id,
            media_type="movie",
            occurred_at_ms=occurred_at_ms,
            terminal=True,
        )

    def test_missing_plex_configuration_is_skipped(self) -> None:
        result = asyncio.run(
            watch_history_ingest.run(self.db, Settings(), lambda: False)
        )
        self.assertEqual(result["status"], "skipped")

    def test_initial_poll_is_bounded_to_ninety_days(self) -> None:
        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"
        seen_since: list[int | None] = []

        def page(*, start: int, size: int, since_ms: int | None):
            seen_since.append(since_ms)
            return PlexHistoryPage(items=[], total_size=0, size=0, start=start)

        client.history_page.side_effect = page
        with (
            patch.object(watch_history_ingest, "_plex_client", return_value=client),
            patch.object(watch_history_ingest.time, "time", return_value=2_000_000_000.0),
        ):
            result = asyncio.run(
                watch_history_ingest.run(self.db, self.settings, lambda: False)
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            seen_since,
            [2_000_000_000_000 - watch_history_ingest.INITIAL_LOOKBACK_MS],
        )

    def test_incremental_poll_replays_ten_minute_overlap(self) -> None:
        watermark = 1_704_067_200_000
        set_ingest_cursor(
            self.db,
            source="plex_history",
            server_machine_id="server-1",
            high_watermark_ms=watermark,
        )
        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"
        seen_since: list[int | None] = []

        def page(*, start: int, size: int, since_ms: int | None):
            seen_since.append(since_ms)
            return PlexHistoryPage(
                items=[
                    PlexHistoryItem(
                        rating_key="new",
                        media_type="movie",
                        account_id="4242",
                        viewed_at_ms=watermark + 1_000,
                        parent_rating_key=None,
                        duration_ms=None,
                        progress_ms=None,
                        history_key="new",
                    )
                ],
                total_size=1,
                size=1,
                start=start,
            )

        client.history_page.side_effect = page
        with (
            patch.object(watch_history_ingest, "_plex_client", return_value=client),
        ):
            result = asyncio.run(
                watch_history_ingest.run(self.db, self.settings, lambda: False)
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(seen_since, [watermark - 10 * 60 * 1000])
        self.assertEqual(result["high_watermark_ms"], watermark + 1_000)

    def test_page_failure_preserves_prior_cursor(self) -> None:
        watermark = 1_704_067_200_000
        set_ingest_cursor(
            self.db,
            source="plex_history",
            server_machine_id="server-1",
            high_watermark_ms=watermark,
        )
        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"
        first_page = PlexHistoryPage(
            items=[
                PlexHistoryItem(
                    rating_key="committed-before-failure",
                    media_type="movie",
                    account_id="4242",
                    viewed_at_ms=watermark + 1_000,
                    parent_rating_key=None,
                    duration_ms=None,
                    progress_ms=None,
                    history_key="committed-before-failure",
                )
            ],
            total_size=500,
            size=watch_history_ingest.PAGE_SIZE,
            start=0,
        )
        client.history_page.side_effect = [
            first_page,
            RuntimeError("page unavailable"),
        ]

        with (
            patch.object(watch_history_ingest, "_plex_client", return_value=client),
        ):
            result = asyncio.run(
                watch_history_ingest.run(self.db, self.settings, lambda: False)
            )

        cursor = get_ingest_cursor(
            self.db, source="plex_history", server_machine_id="server-1"
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(cursor["high_watermark_ms"], watermark)
        self.assertEqual(cursor["last_error"], "Plex history page failed (RuntimeError)")
        with self.db.connect() as conn:
            event_count = conn.execute(
                "SELECT COUNT(*) AS c FROM watch_events"
            ).fetchone()["c"]
        self.assertEqual(event_count, 1)

    def test_cancellation_preserves_prior_cursor(self) -> None:
        watermark = 1_704_067_200_000
        set_ingest_cursor(
            self.db,
            source="plex_history",
            server_machine_id="server-1",
            high_watermark_ms=watermark,
        )
        calls = 0

        def should_stop() -> bool:
            nonlocal calls
            calls += 1
            return calls > 1

        client = unittest.mock.Mock()
        client.machine_identifier.return_value = "server-1"
        with patch.object(watch_history_ingest, "_plex_client", return_value=client):
            result = asyncio.run(
                watch_history_ingest.run(self.db, self.settings, should_stop)
            )

        cursor = get_ingest_cursor(
            self.db, source="plex_history", server_machine_id="server-1"
        )
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(cursor["high_watermark_ms"], watermark)

    def test_task_registers_at_fifteen_minutes(self) -> None:
        definitions = []
        scheduler = unittest.mock.Mock()
        scheduler.register.side_effect = definitions.append

        watch_history_ingest.register(scheduler)

        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].name, "watch_history_ingest")
        self.assertEqual(definitions[0].run_interval_seconds, 15 * 60)


if __name__ == "__main__":
    unittest.main()
