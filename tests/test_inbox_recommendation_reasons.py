"""Inbox recommendations need a named link, not a recent watch or a new arrival."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.notifications.newsletters import build_member_newsletter
from projectionist.notifications.nudges import pick_nudge_title
from projectionist.notifications.whisper import pick_whisper_title

PANEL_PLOT = (
    "A British panel show hosts comedians who dissect the week's newspapers "
    "on Friday nights in a studio."
)
SPONGE_PLOT = (
    "A sea sponge lives in a pineapple and flips crabby patties under the sea "
    "for a greedy crab."
)
BAKE_PLOT = "Amateur bakers compete around a signature bake inside a failing colony."
SPY_PLOT = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."


def _neighbor(db: Database, seed_id: int, peer_id: int, *, seed_plot: str = "", peer_plot: str = "") -> None:
    from projectionist.library.plot_kinship import plot_link_json, specific_plot_link

    link = None
    if seed_plot and peer_plot:
        link = specific_plot_link(
            seed_text=seed_plot, peer_text=peer_plot, shelf_labels=set()
        )
    link_json = plot_link_json(link) if link else "{}"
    explainable = 1 if link else 0
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO item_neighbors
                (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(seed_id), int(peer_id), 0.92, 0.8, explainable, link_json or "{}"),
        )


class InboxRecommendationReasonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "reasons.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_recent_watch_without_a_specific_link_is_not_worth_a_look(self) -> None:
        seed_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-panel",
                "media_type": "show",
                "title": "Have I Got News for You",
                "year": 1990,
                "tmdb_id": 1,
                "view_count": 1,
                "last_viewed_at": 1_700_000_000.0,
                "summary": PANEL_PLOT,
                "genres": ["Comedy"],
            }
        )
        peer_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-sponge",
                "media_type": "show",
                "title": "SpongeBob SquarePants",
                "year": 1999,
                "tmdb_id": 2,
                "view_count": 0,
                "vote_average": 9.9,
                "summary": SPONGE_PLOT,
                "genres": ["Comedy", "Animation"],
            }
        )
        _neighbor(self.db, seed_id, peer_id, seed_plot=PANEL_PLOT, peer_plot=SPONGE_PLOT)

        nudge = pick_nudge_title(self.db)
        whisper = pick_whisper_title(self.db, user_id="member-1")
        self.assertIsNone(nudge)
        self.assertIsNone(whisper)

    def test_shared_subject_names_the_link_in_a_complete_sentence(self) -> None:
        seed_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "tmdb_id": 949,
                "view_count": 1,
                "last_viewed_at": 1_700_000_000.0,
                "summary": BAKE_PLOT,
                "genres": ["Drama"],
            }
        )
        peer_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-thief",
                "media_type": "movie",
                "title": "Thief",
                "year": 1981,
                "tmdb_id": 11334,
                "view_count": 0,
                "summary": SPY_PLOT,
                "genres": ["Thriller"],
            }
        )
        _neighbor(self.db, seed_id, peer_id, seed_plot=BAKE_PLOT, peer_plot=SPY_PLOT)

        pick = pick_nudge_title(self.db)
        self.assertIsNotNone(pick)
        assert pick is not None
        why = str(pick["why"])
        self.assertIn("amateur bakers", why)
        self.assertIn("Heat", why)
        self.assertIn("Thief", why)
        self.assertTrue(why.endswith("."))
        self.assertTrue(why.lower().startswith("you watched") or why.lower().startswith("you finished"))
        self.assertNotIn("recently watched", why.lower())
        self.assertNotIn("still belongs", why.lower())

    def test_weekly_note_skips_bare_arrivals_and_names_a_real_link(self) -> None:
        now = time.time()
        self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "tmdb_id": 949,
                "view_count": 1,
                "last_viewed_at": now - 86400,
                "added_at": int(now - 30 * 86400),
                "summary": BAKE_PLOT,
                "genres": ["Drama"],
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-sponge",
                "media_type": "show",
                "title": "SpongeBob SquarePants",
                "year": 1999,
                "tmdb_id": 2,
                "view_count": 0,
                "added_at": int(now - 3600),
                "summary": SPONGE_PLOT,
                "genres": ["Comedy"],
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-thief",
                "media_type": "movie",
                "title": "Thief",
                "year": 1981,
                "tmdb_id": 11334,
                "view_count": 0,
                "added_at": int(now - 1800),
                "summary": SPY_PLOT,
                "genres": ["Thriller"],
            }
        )
        content = build_member_newsletter(
            self.db,
            user={"preferred_name": "Will", "display_name": "Will", "role": "owner"},
            now=now,
        )
        body = content["body"]
        self.assertNotIn("New in the library this week", body)
        self.assertNotIn("Open CuratorX", body)
        self.assertNotIn("SpongeBob", body)
        self.assertIn("amateur bakers", body)
        self.assertIn("Thief", body)
        self.assertIn("Heat", body)
        self.assertTrue(body.rstrip().endswith("."))
        titles = [pick["title"] for pick in content["picks"]]
        self.assertEqual(titles, ["Thief"])
        self.assertIn("amateur bakers", content["picks"][0]["why"])
        self.assertIn("amateur bakers", content["blurb"])


if __name__ == "__main__":
    unittest.main()
