"""Release 2 — household bridges: watch/watchlist seeds with watched_bridge why."""

from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path
from typing import Optional

from projectionist.library.db import Database
from projectionist.library.plot_kinship import plot_link_json, specific_plot_link
from projectionist.notifications.nudges import pick_nudge_title
from projectionist.library.feeds import feed_for_you
from projectionist.notifications.recommendation_reasons import (
    bridge_between,
    list_linked_unwatched,
    pick_linked_unwatched,
    watched_library_rows,
)
from projectionist.notifications.whisper import pick_whisper_title

BAKE_PLOT = "Amateur bakers compete around a signature bake inside a failing colony."
SPY_PLOT = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."
GRAVITY_PLOT = "Astronauts fight to survive after debris destroys their orbiting shuttle."


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 2015,
        "genres": ["Drama"],
        "keywords": [],
        "summary": "",
        "view_count": 0,
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


def _explainable_neighbor(db: Database, seed_id: int, peer_id: int, *, seed_text: str, peer_text: str) -> None:
    link = specific_plot_link(seed_text=seed_text, peer_text=peer_text, shelf_labels=set())
    link_json = plot_link_json(link) or "{}"
    explainable = 1 if link else 0
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO item_neighbors
                (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(seed_id), int(peer_id), 0.92, 0.8, explainable, link_json),
        )


def _ensure_user(db: Database, user_id: str) -> None:
    db.upsert_plex_user(
        user_id=user_id,
        display_name=user_id.title(),
        email=f"{user_id}@example.com",
        plex_user_id=f"plex-{user_id}",
        role="member",
    )


def _insert_completion(
    db: Database,
    *,
    user_id: Optional[str],
    rating_key: str,
    completed_at_ms: int,
    media_type: str = "movie",
    parent_rating_key: Optional[str] = None,
) -> None:
    if user_id:
        _ensure_user(db, user_id)
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    completion_id = f"cmp-{uuid.uuid4().hex[:12]}"
    source_user_key = str(user_id or "household")
    now = time.time()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_events (
                id, source, source_event_id, source_event_kind, server_machine_id,
                source_user_key, user_id, rating_key, parent_rating_key, media_type,
                occurred_at_ms, terminal, manual, payload_hash, ingested_at
            ) VALUES (?, 'plex', ?, 'scrobble', 'server', ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (
                event_id,
                event_id,
                source_user_key,
                user_id,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms,
                f"hash-{event_id}",
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO watch_sessions (
                id, user_id, source_user_key, rating_key, parent_rating_key, media_type,
                started_at_ms, ended_at_ms, first_event_id, last_event_id,
                client_count, event_count, algorithm_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?, ?)
            """,
            (
                session_id,
                user_id,
                source_user_key,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms - 1000,
                completed_at_ms,
                event_id,
                event_id,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO watch_completions (
                id, session_id, user_id, rating_key, parent_rating_key, media_type,
                completed_at_ms, confidence, basis, threshold_pct, evidence_event_id,
                algorithm_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'certain', 'threshold', 0.9, ?, 1, ?)
            """,
            (
                completion_id,
                session_id,
                user_id,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms,
                event_id,
                now,
            ),
        )


class HouseholdBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "bridges.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_no_watch_evidence_does_not_invent_because_you_watched(self) -> None:
        seed = _title(
            self.db,
            rating_key="rk-bake",
            tmdb_id=1,
            title="Bake Show",
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="rk-spy",
            tmdb_id=2,
            title="Covert Kitchen",
            summary=SPY_PLOT,
        )
        _explainable_neighbor(
            self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
        )
        # Neither title has watch ledger, pins, or view_count.
        seeds = watched_library_rows(self.db)
        self.assertEqual(seeds, [])
        self.assertIsNone(pick_linked_unwatched(self.db))
        self.assertIsNone(pick_nudge_title(self.db))
        self.assertIsNone(pick_whisper_title(self.db, user_id="member-1"))

    def test_completion_seed_plus_explainable_peer_cites_seed_title(self) -> None:
        seed = _title(
            self.db,
            rating_key="rk-heat",
            tmdb_id=949,
            title="Heat",
            year=1995,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="rk-thief",
            tmdb_id=11334,
            title="Thief",
            year=1981,
            summary=SPY_PLOT,
        )
        _explainable_neighbor(
            self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
        )
        _insert_completion(
            self.db,
            user_id="will",
            rating_key="rk-heat",
            completed_at_ms=1_700_000_000_000,
        )

        pick = pick_linked_unwatched(self.db)
        self.assertIsNotNone(pick)
        assert pick is not None
        why = str(pick["why"])
        self.assertIn("Heat", why)
        self.assertIn("Thief", why)
        self.assertIn("amateur bakers", why.lower())
        self.assertTrue(why.lower().startswith("you finished"))
        self.assertTrue(why.endswith("."))
        explanation = pick.get("explanation") or {}
        self.assertEqual(explanation.get("kind"), "watched_bridge")
        self.assertEqual(explanation.get("seed_ids"), [seed])
        self.assertEqual(explanation.get("peer_id"), peer)

    def test_high_cosine_without_plot_link_is_excluded(self) -> None:
        seed = _title(
            self.db,
            rating_key="rk-bake",
            tmdb_id=1,
            title="Bake Show",
            summary=BAKE_PLOT,
            view_count=1,
            last_viewed_at=1_700_000_000.0,
        )
        noise = _title(
            self.db,
            rating_key="rk-gravity",
            tmdb_id=2,
            title="Gravity",
            summary=GRAVITY_PLOT,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (seed, noise, 0.99, 0.9, "{}"),
            )
        self.assertIsNone(pick_linked_unwatched(self.db))
        explanation = bridge_between(
            self.db,
            {"id": noise, "title": "Gravity", "year": 2013, "summary": GRAVITY_PLOT},
            {
                "id": seed,
                "title": "Bake Show",
                "year": 2015,
                "summary": BAKE_PLOT,
                "seed_source": "library_view",
            },
        )
        self.assertIsNone(explanation)

    def test_watchlist_pin_uses_pinned_verb(self) -> None:
        seed = _title(
            self.db,
            rating_key="rk-heat",
            tmdb_id=949,
            title="Heat",
            year=1995,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="rk-thief",
            tmdb_id=11334,
            title="Thief",
            year=1981,
            summary=SPY_PLOT,
        )
        _explainable_neighbor(
            self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
        )
        self.db.add_watchlist_pin(
            pin_id="pin-heat",
            user_id=None,
            tmdb_id=949,
            tvdb_id=None,
            media_type="movie",
            title="Heat",
            plex_rating_key="rk-heat",
        )
        pick = pick_linked_unwatched(self.db)
        self.assertIsNotNone(pick)
        assert pick is not None
        self.assertTrue(str(pick["why"]).lower().startswith("you pinned"))
        self.assertIn("Heat", pick["why"])

    def test_multi_user_prefers_member_completion_then_household(self) -> None:
        seed_a = _title(
            self.db,
            rating_key="rk-heat",
            tmdb_id=949,
            title="Heat",
            year=1995,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="rk-thief",
            tmdb_id=11334,
            title="Thief",
            year=1981,
            summary=SPY_PLOT,
        )
        _explainable_neighbor(
            self.db, seed_a, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
        )
        _insert_completion(
            self.db,
            user_id="alice",
            rating_key="rk-heat",
            completed_at_ms=1_700_000_000_000,
        )
        member_pick = pick_linked_unwatched(
            self.db, user_id="alice", multi_user_enabled=True
        )
        self.assertIsNotNone(member_pick)
        assert member_pick is not None
        self.assertIn("Heat", member_pick["why"])

        stranger_pick = pick_linked_unwatched(
            self.db, user_id="bob", multi_user_enabled=True
        )
        # Bob has no personal evidence; household completion still bridges.
        self.assertIsNotNone(stranger_pick)
        assert stranger_pick is not None
        self.assertIn("Heat", stranger_pick["why"])

    def test_list_and_feed_for_you_reuse_watched_bridge_refusal(self) -> None:
        seed = _title(
            self.db,
            rating_key="rk-heat",
            tmdb_id=949,
            title="Heat",
            year=1995,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="rk-thief",
            tmdb_id=11334,
            title="Thief",
            year=1981,
            summary=SPY_PLOT,
        )
        noise = _title(
            self.db,
            rating_key="rk-gravity",
            tmdb_id=2,
            title="Gravity",
            summary=GRAVITY_PLOT,
        )
        _explainable_neighbor(
            self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (seed, noise, 0.99, 0.9, "{}"),
            )
        _insert_completion(
            self.db,
            user_id="will",
            rating_key="rk-heat",
            completed_at_ms=1_700_000_000_000,
        )

        picks = list_linked_unwatched(self.db, limit=8)
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["title"], "Thief")
        self.assertEqual((picks[0].get("explanation") or {}).get("kind"), "watched_bridge")

        feed = feed_for_you(self.db, limit=8)
        self.assertEqual(feed["feed"], "for-you")
        self.assertEqual(feed["mode"], "watched_bridge")
        self.assertEqual(feed["total"], 1)
        self.assertEqual(feed["items"][0]["title"], "Thief")
        self.assertIn("Heat", feed["items"][0]["why"])
        # Cosine-only Gravity stays refused.
        self.assertFalse(any(item.get("title") == "Gravity" for item in feed["items"]))

    def test_tv_episode_completion_prefers_episode_plot_peer_not_cosine_movie(self) -> None:
        show = _title(
            self.db,
            rating_key="rk-colony",
            tmdb_id=101,
            title="Colony Bake-Off",
            year=2018,
            media_type="show",
            summary="A workplace competition series about craft and teamwork.",
        )
        peer = _title(
            self.db,
            rating_key="rk-spy",
            tmdb_id=2,
            title="Covert Kitchen",
            year=2019,
            summary=SPY_PLOT,
        )
        noise = _title(
            self.db,
            rating_key="rk-gravity",
            tmdb_id=3,
            title="Gravity",
            year=2013,
            summary=GRAVITY_PLOT,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (show, noise, 0.99, 0.9, "{}"),
            )
        self.db.upsert_library_episode(
            {
                "show_item_id": show,
                "rating_key": "ep-signature",
                "season_number": 1,
                "episode_number": 8,
                "title": "Signature Bake",
                "summary": BAKE_PLOT,
            }
        )
        _insert_completion(
            self.db,
            user_id="will",
            rating_key="ep-signature",
            parent_rating_key="rk-colony",
            media_type="episode",
            completed_at_ms=1_700_000_000_000,
        )

        pick = pick_linked_unwatched(self.db)
        self.assertIsNotNone(pick)
        assert pick is not None
        self.assertEqual(pick["title"], "Covert Kitchen")
        why = str(pick["why"]).lower()
        self.assertIn("colony bake-off", why)
        self.assertIn("signature bake", why)
        self.assertIn("amateur bakers", why)
        self.assertTrue(str(pick["why"]).lower().startswith("you finished"))
        evidence = (pick.get("explanation") or {}).get("evidence") or {}
        self.assertEqual(evidence.get("episode_rating_key"), "ep-signature")
        self.assertEqual(evidence.get("episode_title"), "Signature Bake")
        self.assertNotEqual(pick["title"], "Gravity")

        feed = feed_for_you(self.db, limit=8)
        self.assertEqual(feed["mode"], "watched_bridge")
        self.assertEqual(feed["items"][0]["title"], "Covert Kitchen")
        self.assertFalse(any(item.get("title") == "Gravity" for item in feed["items"]))


if __name__ == "__main__":
    unittest.main()
