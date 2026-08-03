"""Focused Phase 3 session/completion correlation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker import store
from projectionist.watch_tracker.store import ingest_watch_events


class WatchCorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")
        self.db.upsert_plex_user(
            user_id="user-a",
            display_name="Ada",
            email=None,
            plex_user_id="4242",
            role="owner",
        )
        self.db.upsert_plex_user(
            user_id="user-b",
            display_name="Bea",
            email=None,
            plex_user_id="9999",
            role="member",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _event(
        self,
        event_id: str,
        *,
        at: int,
        progress: int | None,
        kind: str = "session_progress",
        title: str = "movie-1",
        user_key: str = "4242",
        client: str | None = "living-room",
        media_type: str = "movie",
        parent: str | None = None,
        terminal: bool = False,
        manual: bool = False,
        source: str = "plex_session",
    ) -> WatchEventInput:
        return WatchEventInput(
            source=source,
            source_event_id=event_id,
            source_event_kind=kind,
            server_machine_id="server-1",
            source_user_key=user_key,
            rating_key=title,
            parent_rating_key=parent,
            media_type=media_type,  # type: ignore[arg-type]
            occurred_at_ms=at,
            client_key=client,
            progress_ms=progress,
            duration_ms=6_000_000,
            terminal=terminal,
            manual=manual,
        )

    def test_ingest_materializes_pause_resume_threshold_crossing(self) -> None:
        start = 1_700_000_000_000
        result = ingest_watch_events(
            self.db,
            [
                self._event("a", at=start, progress=300_000),
                self._event("b", at=start + 900_000, progress=2_000_000, kind="session_pause"),
                self._event("c", at=start + 2_000_000, progress=4_000_000),
                self._event(
                    "d",
                    at=start + 3_500_000,
                    progress=5_500_000,
                    kind="session_stop",
                    terminal=True,
                ),
            ],
        )

        self.assertEqual(result.inserted, 4)
        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["logical_viewings"], 1)
        self.assertEqual(summary["tracked_completions"], 1)
        self.assertEqual(summary["sittings_observed"], 4)
        self.assertEqual(summary["completion_confidence"]["certain"], 1)

    def test_reconnect_scrobbles_link_duplicate_evidence(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event(
                    "scrobble-1",
                    at=start,
                    progress=None,
                    kind="plex_scrobble",
                    terminal=True,
                    source="plex_webhook",
                ),
                self._event(
                    "scrobble-2",
                    at=start + 60_000,
                    progress=None,
                    kind="history_played",
                    terminal=True,
                    source="plex_history",
                ),
            ],
        )

        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT duplicate_of_event_id FROM watch_events ORDER BY occurred_at_ms"
            ).fetchall()
        self.assertIsNone(rows[0]["duplicate_of_event_id"])
        self.assertIsNotNone(rows[1]["duplicate_of_event_id"])
        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["tracked_completions"], 1)
        self.assertEqual(summary["completion_confidence"]["plex_event_only"], 1)

    def test_exact_fingerprint_ignores_provider_event_id(self) -> None:
        start = 1_700_000_000_000
        first = self._event(
            "provider-a",
            at=start,
            progress=None,
            kind="history_played",
            terminal=True,
            source="plex_history",
        )
        second = self._event(
            "provider-b",
            at=start,
            progress=None,
            kind="history_played",
            terminal=True,
            source="plex_history",
        )

        result = ingest_watch_events(self.db, [first, second])

        self.assertEqual(result.inserted, 1)
        self.assertEqual(result.deduped, 1)

    def test_clear_restart_allows_next_day_rewatch(self) -> None:
        start = 1_700_000_000_000
        day = 24 * 60 * 60 * 1000
        ingest_watch_events(
            self.db,
            [
                self._event("first-low", at=start, progress=200_000),
                self._event(
                    "first-done",
                    at=start + 3_000_000,
                    progress=5_500_000,
                    kind="session_stop",
                    terminal=True,
                ),
                self._event("second-low", at=start + day, progress=100_000),
                self._event(
                    "second-done",
                    at=start + day + 3_000_000,
                    progress=5_600_000,
                    kind="session_stop",
                    terminal=True,
                ),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["logical_viewings"], 2)
        self.assertEqual(summary["tracked_completions"], 2)
        self.assertEqual(summary["completion_confidence"]["certain"], 2)

    def test_manual_unscrobble_supersedes_manual_only_completion(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event(
                    "mark",
                    at=start,
                    progress=None,
                    kind="manual_scrobble",
                    terminal=True,
                    manual=True,
                    client=None,
                    source="manual",
                ),
                self._event(
                    "unmark",
                    at=start + 1_000,
                    progress=None,
                    kind="manual_unscrobble",
                    manual=True,
                    client=None,
                    source="manual",
                ),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["tracked_completions"], 0)

    def test_manual_scrobble_never_exceeds_plex_event_only_confidence(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event("progress", at=start, progress=4_000_000),
                self._event(
                    "mark",
                    at=start + 1_000,
                    progress=None,
                    kind="manual_scrobble",
                    terminal=True,
                    manual=True,
                    source="manual",
                ),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["tracked_completions"], 1)
        self.assertEqual(summary["completion_confidence"]["plex_event_only"], 1)
        self.assertEqual(summary["completion_confidence"]["likely"], 0)

    def test_history_completion_linked_to_progress_is_likely(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event("progress", at=start, progress=4_500_000),
                self._event(
                    "history",
                    at=start + 1_000,
                    progress=None,
                    kind="history_played",
                    terminal=True,
                    source="plex_history",
                ),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["tracked_completions"], 1)
        self.assertEqual(summary["completion_confidence"]["likely"], 1)

    def test_implausible_terminal_recompletion_without_restart_is_suppressed(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event(
                    "played-1",
                    at=start,
                    progress=None,
                    kind="history_played",
                    terminal=True,
                    source="plex_history",
                ),
                self._event(
                    "played-2",
                    at=start + 5 * 60 * 60 * 1000,
                    progress=None,
                    kind="history_played",
                    terminal=True,
                    source="plex_history",
                ),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["logical_viewings"], 2)
        self.assertEqual(summary["tracked_completions"], 1)

    def test_client_handoff_merges_only_within_thirty_minutes(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event("a", at=start, progress=100_000, client="tv"),
                self._event("b", at=start + 20 * 60_000, progress=1_000_000, client="tablet"),
                self._event("c", at=start + 60 * 60_000, progress=2_000_000, client="browser"),
            ],
        )

        summary = store.list_user_watch_summary(self.db, user_id="user-a", rating_key="movie-1")
        self.assertEqual(summary["logical_viewings"], 2)

    def test_episode_units_roll_up_to_show_without_cross_user_leakage(self) -> None:
        start = 1_700_000_000_000
        events = [
            self._event(
                "a-low",
                at=start,
                progress=100_000,
                title="episode-1",
                media_type="episode",
                parent="show-1",
            ),
            self._event(
                "a-done",
                at=start + 2_000_000,
                progress=5_500_000,
                kind="session_stop",
                title="episode-1",
                media_type="episode",
                parent="show-1",
                terminal=True,
            ),
            self._event(
                "b-played",
                at=start + 3_000_000,
                progress=None,
                kind="history_played",
                title="episode-2",
                user_key="9999",
                media_type="episode",
                parent="show-1",
                terminal=True,
                source="plex_history",
            ),
        ]
        ingest_watch_events(self.db, events)

        show_a = store.list_user_show_watch_summary(self.db, user_id="user-a", rating_key="show-1")
        show_b = store.list_user_show_watch_summary(self.db, user_id="user-b", rating_key="show-1")
        self.assertEqual(show_a["unique_episodes_completed"], 1)
        self.assertEqual(show_a["total_episode_completions"], 1)
        self.assertEqual(show_b["unique_episodes_completed"], 1)
        self.assertEqual(show_b["total_episode_completions"], 1)

    def test_rebuild_is_stable(self) -> None:
        start = 1_700_000_000_000
        ingest_watch_events(
            self.db,
            [
                self._event("a", at=start, progress=100_000),
                self._event(
                    "b",
                    at=start + 2_000_000,
                    progress=5_500_000,
                    kind="session_stop",
                    terminal=True,
                ),
            ],
        )
        with self.db.connect() as conn:
            before = [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, rating_key, started_at_ms, ended_at_ms FROM watch_sessions"
                ).fetchall()
            ]
        rebuild_watch_derivations(self.db, user_id="user-a")
        with self.db.connect() as conn:
            after = [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, rating_key, started_at_ms, ended_at_ms FROM watch_sessions"
                ).fetchall()
            ]
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
