"""Durable coverage for Plex watch identity mapping + attribution repair.

Encodes the Automat prod failure mode: auth stores plex.tv ``id`` on
``users.plex_user_id``, while PMS history/session keys for the server owner use
the local ``/accounts`` id (commonly ``1``). Shared-library accounts usually
already use plex.tv ids as their PMS account ids and stay unmapped until they
link a Projectionist user — that NULL is intentional.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.identity import (
    MAPPING_PLEX_ACCOUNT_ID,
    MAPPING_PLEX_SERVER_ACCOUNT,
    MAPPING_UNMAPPED,
    discover_server_owner_local_account,
    repair_watch_attribution,
    resolve_user_id,
    sync_plex_watch_identities,
)
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.rollups import MIN_COMPLETIONS_FOR_YIR, build_year_rollup, year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events


class ResolveUserIdTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "identity.db")
        self.db.upsert_plex_user(
            user_id="plex-148223",
            display_name="romwil",
            email=None,
            plex_user_id="148223",
            role="owner",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_exact_plex_user_id_match(self) -> None:
        user_id, method = resolve_user_id(self.db, "148223")
        self.assertEqual(user_id, "plex-148223")
        self.assertEqual(method, MAPPING_PLEX_ACCOUNT_ID)

    def test_unknown_shared_account_stays_unmapped(self) -> None:
        # Prod shape: shared user plex.tv/PMS id with no Projectionist login.
        user_id, method = resolve_user_id(self.db, "371018327")
        self.assertIsNone(user_id)
        self.assertEqual(method, MAPPING_UNMAPPED)

    def test_username_alone_does_not_resolve(self) -> None:
        user_id, method = resolve_user_id(self.db, "romwil")
        self.assertIsNone(user_id)
        self.assertEqual(method, MAPPING_UNMAPPED)

    def test_server_owner_local_account_alias_resolves(self) -> None:
        # Prod failure mode: owner watches arrive as local account "1".
        now = 1_700_000_000.0
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_source_identities (
                    source, server_machine_id, source_user_key, user_id, display_name,
                    mapping_method, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "plex_history",
                    "server-1",
                    "1",
                    "plex-148223",
                    "romwil",
                    MAPPING_PLEX_SERVER_ACCOUNT,
                    now,
                    now,
                ),
            )
        user_id, method = resolve_user_id(self.db, "1")
        self.assertEqual(user_id, "plex-148223")
        self.assertEqual(method, MAPPING_PLEX_SERVER_ACCOUNT)


class DiscoverOwnerLocalAccountTests(unittest.TestCase):
    def test_matches_local_account_by_plex_tv_username(self) -> None:
        with patch(
            "projectionist.connectors.plex_account.fetch_plex_account",
            return_value={"id": 148223, "username": "romwil", "title": "romwil"},
        ):
            discovered = discover_server_owner_local_account(
                plex_token="token",
                accounts=[
                    {"id": "0", "name": ""},
                    {"id": "1", "name": "romwil"},
                    {"id": "178276", "name": "cassie.rompala"},
                ],
            )
        self.assertEqual(
            discovered,
            {
                "plex_user_id": "148223",
                "local_account_id": "1",
                "username": "romwil",
                "display_name": "romwil",
            },
        )

    def test_does_not_alias_unrelated_shared_usernames(self) -> None:
        with patch(
            "projectionist.connectors.plex_account.fetch_plex_account",
            return_value={"id": 148223, "username": "romwil"},
        ):
            discovered = discover_server_owner_local_account(
                plex_token="token",
                accounts=[{"id": "371018327", "name": "jmccollough27"}],
            )
        self.assertIsNone(discovered)


class IngestAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "ingest.db")
        self.db.upsert_plex_user(
            user_id="plex-148223",
            display_name="romwil",
            email=None,
            plex_user_id="148223",
            role="owner",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _event(self, *, key: str, rating_key: str, occurred_at_ms: int) -> WatchEventInput:
        return WatchEventInput(
            source="plex_history",
            source_event_id=f"history-{key}-{rating_key}",
            source_event_kind="history_played",
            server_machine_id="server-1",
            source_user_key=key,
            rating_key=rating_key,
            media_type="movie",
            occurred_at_ms=occurred_at_ms,
            terminal=True,
        )

    def test_mapped_local_account_writes_user_id_on_completion(self) -> None:
        sync = sync_plex_watch_identities
        with patch(
            "projectionist.watch_tracker.identity.refresh_plex_server_account_aliases",
            return_value={
                "status": "ok",
                "aliases_upserted": 2,
                "local_account_id": "1",
                "plex_user_id": "148223",
                "user_id": "plex-148223",
            },
        ):
            # Seed the alias the refresh would have written.
            now = 1_700_000_000.0
            with self.db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO watch_source_identities (
                        source, server_machine_id, source_user_key, user_id, display_name,
                        mapping_method, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "plex_history",
                        "server-1",
                        "1",
                        "plex-148223",
                        "romwil",
                        MAPPING_PLEX_SERVER_ACCOUNT,
                        now,
                        now,
                    ),
                )
            del sync

        start_ms, _ = year_bounds_ms(2026)
        result = ingest_watch_events(
            self.db,
            [self._event(key="1", rating_key="movie-owner", occurred_at_ms=start_ms)],
        )
        self.assertEqual(result.mapped, 1)
        self.assertEqual(result.unmapped, 0)
        rebuild_watch_derivations(self.db, user_id="plex-148223")
        with self.db.connect() as conn:
            event = conn.execute(
                "SELECT user_id FROM watch_events WHERE rating_key = ?",
                ("movie-owner",),
            ).fetchone()
            completion = conn.execute(
                "SELECT user_id FROM watch_completions WHERE rating_key = ?",
                ("movie-owner",),
            ).fetchone()
            identity = conn.execute(
                """
                SELECT mapping_method FROM watch_source_identities
                WHERE source_user_key = '1'
                """
            ).fetchone()
        self.assertEqual(event["user_id"], "plex-148223")
        self.assertEqual(completion["user_id"], "plex-148223")
        self.assertEqual(identity["mapping_method"], MAPPING_PLEX_SERVER_ACCOUNT)

    def test_unknown_account_completion_stays_null_and_unmapped(self) -> None:
        start_ms, _ = year_bounds_ms(2026)
        result = ingest_watch_events(
            self.db,
            [
                self._event(
                    key="371018327",
                    rating_key="movie-shared",
                    occurred_at_ms=start_ms,
                )
            ],
        )
        self.assertEqual(result.mapped, 0)
        self.assertEqual(result.unmapped, 1)
        rebuild_watch_derivations(self.db, source_user_key="371018327")
        with self.db.connect() as conn:
            completion = conn.execute(
                "SELECT user_id FROM watch_completions WHERE rating_key = ?",
                ("movie-shared",),
            ).fetchone()
            identity = conn.execute(
                """
                SELECT user_id, mapping_method FROM watch_source_identities
                WHERE source_user_key = '371018327'
                """
            ).fetchone()
        self.assertIsNone(completion["user_id"])
        self.assertIsNone(identity["user_id"])
        self.assertEqual(identity["mapping_method"], MAPPING_UNMAPPED)


class RepairAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "repair.db")
        self.db.upsert_plex_user(
            user_id="plex-148223",
            display_name="romwil",
            email=None,
            plex_user_id="148223",
            role="owner",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_repair_is_idempotent_and_preserves_attributed_rows(self) -> None:
        start_ms, _ = year_bounds_ms(2026)
        # Owner watches under local account "1" (NULL at ingest time).
        null_events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"null-{i}",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key="1",
                rating_key=f"movie-null-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(3)
        ]
        # Already-correct exact plex_user_id rows.
        good_events = [
            WatchEventInput(
                source="plex_history",
                source_event_id="good-0",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key="148223",
                rating_key="movie-good",
                media_type="movie",
                occurred_at_ms=start_ms + 10 * 86_400_000,
                terminal=True,
            )
        ]
        # Truly unknown shared account — must stay NULL.
        unknown = [
            WatchEventInput(
                source="plex_history",
                source_event_id="unk-0",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key="371018327",
                rating_key="movie-unk",
                media_type="movie",
                occurred_at_ms=start_ms + 11 * 86_400_000,
                terminal=True,
            )
        ]
        ingest_watch_events(self.db, null_events + good_events + unknown)
        rebuild_watch_derivations(self.db, source_user_key="1")
        rebuild_watch_derivations(self.db, user_id="plex-148223")
        rebuild_watch_derivations(self.db, source_user_key="371018327")

        now = 1_700_000_000.0
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_source_identities (
                    source, server_machine_id, source_user_key, user_id, display_name,
                    mapping_method, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, server_machine_id, source_user_key) DO UPDATE SET
                    user_id = excluded.user_id,
                    mapping_method = excluded.mapping_method
                """,
                (
                    "plex_history",
                    "server-1",
                    "1",
                    "plex-148223",
                    "romwil",
                    MAPPING_PLEX_SERVER_ACCOUNT,
                    now,
                    now,
                ),
            )

        first = repair_watch_attribution(self.db)
        second = repair_watch_attribution(self.db)
        self.assertGreaterEqual(first["completions_updated"], 3)
        self.assertEqual(second["completions_updated"], 0)
        self.assertEqual(second["events_updated"], 0)

        with self.db.connect() as conn:
            owner_nulls = conn.execute(
                """
                SELECT COUNT(*) AS c FROM watch_completions c
                JOIN watch_sessions s ON s.id = c.session_id
                WHERE s.source_user_key = '1' AND c.user_id IS NULL
                """
            ).fetchone()["c"]
            owner_ok = conn.execute(
                """
                SELECT COUNT(*) AS c FROM watch_completions
                WHERE user_id = 'plex-148223'
                """
            ).fetchone()["c"]
            unknown_null = conn.execute(
                """
                SELECT COUNT(*) AS c FROM watch_completions c
                JOIN watch_sessions s ON s.id = c.session_id
                WHERE s.source_user_key = '371018327' AND c.user_id IS NULL
                """
            ).fetchone()["c"]
            good_still = conn.execute(
                """
                SELECT user_id FROM watch_completions WHERE rating_key = 'movie-good'
                """
            ).fetchone()["user_id"]
        self.assertEqual(owner_nulls, 0)
        self.assertGreaterEqual(owner_ok, 4)  # 3 repaired + 1 exact
        self.assertEqual(unknown_null, 1)
        self.assertEqual(good_still, "plex-148223")


class YearInReviewIdentitySmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir-identity.db")
        self.db.upsert_plex_user(
            user_id="plex-148223",
            display_name="romwil",
            email=None,
            plex_user_id="148223",
            role="owner",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_null_user_finishes_do_not_satisfy_yir_floor(self) -> None:
        start_ms, _ = year_bounds_ms(2026)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"null-yir-{i}",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key="1",
                rating_key=f"movie-yir-null-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(MIN_COMPLETIONS_FOR_YIR + 2)
        ]
        ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db, source_user_key="1")
        rollup = build_year_rollup(self.db, user_id="plex-148223", year=2026)
        self.assertEqual(rollup.completion_count, 0)
        self.assertFalse(rollup.has_enough_data)

    def test_attributed_finishes_satisfy_yir_floor(self) -> None:
        start_ms, _ = year_bounds_ms(2026)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"ok-yir-{i}",
                source_event_kind="history_played",
                server_machine_id="server-1",
                source_user_key="148223",
                rating_key=f"movie-yir-ok-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(MIN_COMPLETIONS_FOR_YIR)
        ]
        ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db, user_id="plex-148223")
        rollup = build_year_rollup(self.db, user_id="plex-148223", year=2026)
        self.assertEqual(rollup.completion_count, MIN_COMPLETIONS_FOR_YIR)
        self.assertTrue(rollup.has_enough_data)


if __name__ == "__main__":
    unittest.main()
