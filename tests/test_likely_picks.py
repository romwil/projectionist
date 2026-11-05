"""GRO-010: a separate "likely" tier for picks played in native Plex within 7 days."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from projectionist.library.db import Database
from projectionist.telemetry.likely_picks import (
    LIKELY_WINDOW_SECONDS,
    likely_pick_watch_count,
    refresh_likely_pick_watches,
)

DAY = 86400.0


class LikelyPickTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        for name in ("alex", "sam"):
            self.db.create_local_user(
                user_id=f"local-{name}", display_name=name, password_hash="x", role="member"
            )
        self.now = time.time()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _share(self, to_user: str, rating_key: str, at: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_recommendations
                    (id, from_user_id, to_user_id, media_type, rating_key, title, created_at)
                VALUES (?, 'local-sam', ?, 'movie', ?, 'Heat', ?)
                """,
                (uuid.uuid4().hex, to_user, rating_key, at),
            )

    def _notify(self, user_id: str, kind: str, rating_key: str, at: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_notifications (id, user_id, kind, title, rating_key, created_at)
                VALUES (?, ?, ?, 'Heat', ?, ?)
                """,
                (uuid.uuid4().hex, user_id, kind, rating_key, at),
            )

    def _plex_play(self, user_id: str, rating_key: str, at: float, *, parent: str | None = None) -> str:
        event_id = uuid.uuid4().hex
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_events (
                    id, source, source_event_kind, server_machine_id, source_user_key, user_id,
                    rating_key, parent_rating_key, media_type, occurred_at_ms, payload_hash, ingested_at
                ) VALUES (?, 'plex_history', 'history', 'srv', 'acct', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    user_id,
                    rating_key,
                    parent,
                    "episode" if parent else "movie",
                    int(at * 1000),
                    event_id,
                    at,
                ),
            )
        return event_id

    def _rows(self) -> list:
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM pick_watched_likely ORDER BY watched_at")]

    def test_same_person_within_seven_days_counts_once(self) -> None:
        shared_at = self.now - 3 * DAY
        self._share("local-alex", "rk-heat", shared_at)
        first = self._plex_play("local-alex", "rk-heat", shared_at + DAY)
        self._plex_play("local-alex", "rk-heat", shared_at + DAY + 600)

        self.assertEqual(refresh_likely_pick_watches(self.db, now=self.now)["inserted"], 1)
        self.assertEqual(refresh_likely_pick_watches(self.db, now=self.now)["inserted"], 0)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], "local-alex")
        self.assertEqual(rows[0]["surface"], "share")
        self.assertEqual(rows[0]["watch_event_id"], first)
        self.assertAlmostEqual(rows[0]["lag_hours"], 24.0, places=1)

    def test_other_person_before_surfacing_or_after_window_do_not_count(self) -> None:
        shared_at = self.now - 20 * DAY
        self._share("local-alex", "rk-heat", shared_at)
        self._plex_play("local-sam", "rk-heat", shared_at + DAY)
        self._plex_play("local-alex", "rk-heat", shared_at - 60)
        self._plex_play("local-alex", "rk-heat", shared_at + LIKELY_WINDOW_SECONDS + 60)
        refresh_likely_pick_watches(self.db, now=self.now)
        self.assertEqual(self._rows(), [])

    def test_episode_of_a_surfaced_show_and_notification_surfaces(self) -> None:
        at = self.now - 2 * DAY
        self._notify("local-alex", "digest", "rk-show", at)
        self._notify("local-alex", "arrival", "rk-film", at)
        self._plex_play("local-alex", "rk-ep-1", at + 3600, parent="rk-show")
        self._plex_play("local-alex", "rk-film", at + 3600)
        refresh_likely_pick_watches(self.db, now=self.now)
        rows = self._rows()
        self.assertEqual([(r["rating_key"], r["surface"]) for r in rows], [("rk-show", "digest")])

    def test_verified_in_app_count_is_unchanged(self) -> None:
        at = self.now - DAY
        self._share("local-alex", "rk-heat", at)
        self._plex_play("local-alex", "rk-heat", at + 3600)
        refresh_likely_pick_watches(self.db, now=self.now)
        counts = self.db.local_event_counts(days=7)
        self.assertEqual(counts["plays_from_picks"], 0)
        self.assertEqual(counts["plays"], 0)
        self.assertEqual(counts["plays_likely_from_picks"], 1)
        self.assertEqual(likely_pick_watch_count(self.db, days=7, now=self.now), 1)

    def test_in_export_and_removed_by_purge(self) -> None:
        at = self.now - DAY
        self._share("local-alex", "rk-heat", at)
        self._plex_play("local-alex", "rk-heat", at + 3600)
        self._share("local-sam", "rk-heat", at)
        self._plex_play("local-sam", "rk-heat", at + 3600)
        refresh_likely_pick_watches(self.db, now=self.now)

        exported = json.dumps(self.db.export_user_memory("local-alex"))
        self.assertIn("pick_watched_likely", exported)
        self.assertIn("rk-heat", exported)

        self.db.erase_user_data("local-alex")
        self.assertEqual([r["user_id"] for r in self._rows()], ["local-sam"])

    def test_rows_older_than_retention_are_pruned(self) -> None:
        at = self.now - 100 * DAY
        self._share("local-alex", "rk-heat", at)
        self._plex_play("local-alex", "rk-heat", at + 3600)
        refresh_likely_pick_watches(self.db, now=at + 2 * DAY)
        self.assertEqual(len(self._rows()), 1)
        self.assertEqual(refresh_likely_pick_watches(self.db, now=self.now)["pruned"], 1)
        self.assertEqual(self._rows(), [])


if __name__ == "__main__":
    unittest.main()
