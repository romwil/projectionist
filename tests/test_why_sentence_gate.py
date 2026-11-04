"""A "why" reaches a card only when it reads as a sentence (PRD-001, UX-012)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import feed_for_you
from projectionist.library.plot_kinship import (
    honest_plot_link,
    readable_why,
    specific_plot_link,
)
from projectionist.notifications.recommendation_reasons import watched_bridge
from tests.test_household_bridges import _explainable_neighbor, _insert_completion, _title

# Wikipedia-style production history: the phrases the review saw on QA.
PRODUCTION_SEED = (
    "The series took place in Chicago and was a spin off of an earlier show. "
    "It began airing on a broadcasting company and won a primetime emmy."
)
PRODUCTION_PEER = (
    "The film took place in Ohio as a spin off; it began airing via a "
    "broadcasting company and earned a primetime emmy nomination."
)
# Corpus of reasons the 2026-11-01 walk saw on Explore and Inbox.
BROKEN_REASONS = (
    "both stories turn on a spin off",
    "both stories turn on a took place",
    "both stories turn on a broadcasting company and a began airing",
    "both stories turn on a primetime emmy",
    "both stories turn on",
    "worked on",
)
BAKE_PLOT = "Amateur bakers compete around a signature bake inside a failing colony."
RIVAL_PLOT = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."


class ReadableWhyTests(unittest.TestCase):
    def test_reasons_seen_on_qa_are_refused(self) -> None:
        for reason in BROKEN_REASONS:
            with self.subTest(reason=reason):
                self.assertFalse(readable_why(reason))

    def test_real_reasons_pass(self) -> None:
        for reason in (
            "both stories turn on amateur bakers",
            "both stories turn on a haunted house",
            "both stories turn on street racing",
            "Adam McKay worked on both",
            "both are part of The Godfather Collection",
        ):
            with self.subTest(reason=reason):
                self.assertTrue(readable_why(reason))

    def test_production_history_never_becomes_a_plot_link(self) -> None:
        link = specific_plot_link(
            seed_text=PRODUCTION_SEED, peer_text=PRODUCTION_PEER, shelf_labels=set()
        )
        self.assertIsNone(link)

    def test_stored_junk_link_is_refused_on_read(self) -> None:
        stored = {
            "sentence": "Both stories turn on a took place and a spin off.",
            "terms": ["took place", "spin off", "began airing"],
        }
        self.assertIsNone(honest_plot_link(stored, shelf_labels=set()))

    def test_activity_noun_takes_no_article(self) -> None:
        link = specific_plot_link(
            seed_text="Two brothers join illegal street racing crews across the desert at dawn.",
            peer_text="A cop goes undercover with street racing gangs in the desert city.",
            shelf_labels=set(),
        )
        assert link is not None
        self.assertIn("street racing", link["sentence"])
        self.assertNotIn("a street racing", link["sentence"])


class WatchedBridgeGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "why.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_person_name_keeps_its_capital(self) -> None:
        seed = _title(self.db, rating_key="rk-a", tmdb_id=1, title="The Big Short", year=2015)
        peer = _title(self.db, rating_key="rk-b", tmdb_id=2, title="Vice", year=2018)
        credit = [
            {
                "tmdb_person_id": 55,
                "name": "Adam McKay",
                "department": "Directing",
                "job": "Director",
                "billing_order": 0,
            }
        ]
        self.db.upsert_credits_for_item(seed, credit)
        self.db.upsert_credits_for_item(peer, credit)
        seed_row = {"id": seed, "title": "The Big Short", "year": 2015, "seed_source": "completion"}
        peer_row = {"id": peer, "title": "Vice", "year": 2018}
        explanation = watched_bridge(self.db, peer_row, seed_row)
        assert explanation is not None
        self.assertIn("Adam McKay worked on both", explanation["sentence"])

    def test_plot_clause_still_folds_both(self) -> None:
        seed = _title(self.db, rating_key="rk-c", tmdb_id=3, title="Bake Off", summary=BAKE_PLOT)
        peer = _title(self.db, rating_key="rk-d", tmdb_id=4, title="Rivals", summary=RIVAL_PLOT)
        _explainable_neighbor(self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=RIVAL_PLOT)
        seed_row = {"id": seed, "title": "Bake Off", "year": 2015, "summary": BAKE_PLOT}
        peer_row = {"id": peer, "title": "Rivals", "year": 2015, "summary": RIVAL_PLOT}
        explanation = watched_bridge(self.db, peer_row, seed_row)
        assert explanation is not None
        self.assertIn("— both stories turn on", explanation["sentence"])


class ForYouRailTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "rail.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_production_history_peer_gets_no_card(self) -> None:
        seed = _title(
            self.db, rating_key="rk-seed", tmdb_id=10, title="Seed Show", summary=PRODUCTION_SEED
        )
        peer = _title(
            self.db, rating_key="rk-peer", tmdb_id=11, title="Peer Film", summary=PRODUCTION_PEER
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, 0.9, 0.7, 1, ?)
                """,
                (
                    seed,
                    peer,
                    '{"sentence":"Both stories turn on a took place.","terms":["took place"]}',
                ),
            )
        _insert_completion(
            self.db, user_id="will", rating_key="rk-seed", completed_at_ms=1_700_000_000_000
        )
        feed = feed_for_you(self.db, limit=8)
        self.assertEqual(feed["items"], [])

    def test_one_seed_explains_at_most_two_of_eight_cards(self) -> None:
        seed_a = _title(self.db, rating_key="rk-sa", tmdb_id=100, title="Seed A", summary=BAKE_PLOT)
        seed_b = _title(self.db, rating_key="rk-sb", tmdb_id=101, title="Seed B", summary=BAKE_PLOT)
        for index in range(6):
            peer = _title(
                self.db,
                rating_key=f"rk-p{index}",
                tmdb_id=200 + index,
                title=f"Peer {index}",
                summary=RIVAL_PLOT,
            )
            _explainable_neighbor(self.db, seed_a, peer, seed_text=BAKE_PLOT, peer_text=RIVAL_PLOT)
        _insert_completion(
            self.db, user_id="will", rating_key="rk-sa", completed_at_ms=1_700_000_000_000
        )
        _insert_completion(
            self.db, user_id="will", rating_key="rk-sb", completed_at_ms=1_700_000_100_000
        )
        feed = feed_for_you(self.db, limit=8)
        per_seed: dict[int, int] = {}
        for item in feed["items"]:
            for seed_id in (item.get("explanation") or {}).get("seed_ids") or []:
                per_seed[int(seed_id)] = per_seed.get(int(seed_id), 0) + 1
        self.assertEqual(len(feed["items"]), 4)
        self.assertLessEqual(per_seed.get(seed_a, 0), 2)
        self.assertLessEqual(per_seed.get(seed_b, 0), 2)


if __name__ == "__main__":
    unittest.main()
