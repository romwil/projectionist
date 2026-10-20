"""Release 1 — explainable kinship: materialize named plot links, filter cosine-only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import neighbors_payload
from projectionist.library.neighbors import enrich_neighbors_with_explanations
from projectionist.library.plot_kinship import build_explanation, specific_plot_link
from projectionist.library.query import compute_knowledge_coverage
from projectionist.library.relations import (
    build_neighbor_relations,
    list_relations_for_item,
)

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
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


class ExplanationObjectTests(unittest.TestCase):
    def test_build_explanation_shape(self) -> None:
        explanation = build_explanation(
            kind="plot_link",
            sentence="Both stories turn on amateur bakers.",
            terms=["amateur bakers"],
            seed_ids=[1],
            peer_id=2,
            evidence={"shared_story": ["amateur bakers"]},
        )
        self.assertEqual(explanation["kind"], "plot_link")
        self.assertIn("amateur bakers", explanation["sentence"])
        self.assertEqual(explanation["terms"], ["amateur bakers"])
        self.assertEqual(explanation["seed_ids"], [1])
        self.assertEqual(explanation["peer_id"], 2)
        self.assertEqual(explanation["evidence"]["shared_story"], ["amateur bakers"])


class ExplainableNeighborMaterializeTests(unittest.TestCase):
    def test_high_cosine_without_plot_link_is_not_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "kin.db")
            seed = _title(
                db,
                rating_key="bake",
                tmdb_id=1,
                title="Bake Show",
                summary=BAKE_PLOT,
                genres=["Reality"],
            )
            noise = _title(
                db,
                rating_key="gravity",
                tmdb_id=2,
                title="Gravity",
                summary=GRAVITY_PLOT,
                genres=["Science Fiction"],
            )
            enriched = enrich_neighbors_with_explanations(
                db, seed, [(noise, 0.99, 0.5)]
            )
            self.assertEqual(len(enriched), 1)
            _nid, _score, _surprise, explainable, link_json = enriched[0]
            self.assertEqual(explainable, 0)
            self.assertEqual(link_json, "{}")
            self.assertIsNone(
                specific_plot_link(
                    seed_text=BAKE_PLOT,
                    peer_text=GRAVITY_PLOT,
                    shelf_labels={"reality", "science fiction"},
                )
            )

    def test_shared_subject_is_explainable_with_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "kin.db")
            seed = _title(
                db,
                rating_key="bake",
                tmdb_id=1,
                title="Bake Show",
                summary=BAKE_PLOT,
                genres=["Reality"],
                keywords=["food"],
            )
            peer = _title(
                db,
                rating_key="spy",
                tmdb_id=2,
                title="Covert Kitchen",
                summary=SPY_PLOT,
                genres=["Thriller"],
                keywords=["espionage"],
            )
            enriched = enrich_neighbors_with_explanations(
                db, seed, [(peer, 0.84, 0.6)]
            )
            self.assertEqual(enriched[0][3], 1)
            self.assertIn("amateur bakers", (enriched[0][4] or "").lower())
            db.set_neighbors(seed, enriched)
            rows = db.get_neighbors(seed, explainable_only=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(int(rows[0]["neighbor_id"]), peer)
            self.assertEqual(int(rows[0]["explainable"]), 1)


class ExplainableCoverageTests(unittest.TestCase):
    def test_coverage_includes_raw_and_explainable_percents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "cov.db")
            seed = _title(
                db,
                rating_key="bake",
                tmdb_id=1,
                title="Bake Show",
                summary=BAKE_PLOT,
            )
            peer = _title(
                db,
                rating_key="spy",
                tmdb_id=2,
                title="Covert Kitchen",
                summary=SPY_PLOT,
            )
            noise = _title(
                db,
                rating_key="gravity",
                tmdb_id=3,
                title="Gravity",
                summary=GRAVITY_PLOT,
            )
            db.set_neighbors(
                seed,
                enrich_neighbors_with_explanations(
                    db, seed, [(peer, 0.84, 0.6), (noise, 0.99, 0.5)]
                ),
            )
            coverage = compute_knowledge_coverage(db)
            self.assertIn("with_neighbors_pct", coverage)
            self.assertIn("with_explainable_neighbors_pct", coverage)
            self.assertEqual(coverage["total_titles"], 3)
            # One seed has raw neighbors; one seed has ≥1 explainable peer.
            self.assertEqual(coverage["with_neighbors_pct"], 33.3)
            self.assertEqual(coverage["with_explainable_neighbors_pct"], 33.3)
            self.assertEqual(coverage["neighbor_edges"], 2)
            self.assertEqual(coverage["explainable_neighbor_edges"], 1)


class ExplainableRelationsAndFeedTests(unittest.TestCase):
    def test_relations_and_more_like_this_omit_cosine_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "rel.db")
            seed = _title(
                db,
                rating_key="bake",
                tmdb_id=1,
                title="Bake Show",
                summary=BAKE_PLOT,
                genres=["Reality"],
            )
            peer = _title(
                db,
                rating_key="spy",
                tmdb_id=2,
                title="Covert Kitchen",
                summary=SPY_PLOT,
                genres=["Thriller"],
            )
            noise = _title(
                db,
                rating_key="gravity",
                tmdb_id=3,
                title="Gravity",
                summary=GRAVITY_PLOT,
                genres=["Science Fiction"],
            )
            db.set_neighbors(
                seed,
                enrich_neighbors_with_explanations(
                    db, seed, [(peer, 0.84, 0.6), (noise, 0.99, 0.5)]
                ),
            )
            mirrored = build_neighbor_relations(db, top_k=10)
            mirrored_peers = {to_id for _from, to_id, _rel, _w, _src in mirrored}
            self.assertIn(peer, mirrored_peers)
            self.assertNotIn(noise, mirrored_peers)

            db.replace_relations_of_types({"neighbor": mirrored})
            payload = list_relations_for_item(db, seed, limit=10)
            titles = {edge["title"] for edge in payload["items"]}
            self.assertIn("Covert Kitchen", titles)
            self.assertNotIn("Gravity", titles)
            why = next(
                edge["why"] for edge in payload["items"] if edge["title"] == "Covert Kitchen"
            )
            self.assertTrue(why.get("plot_link"))
            self.assertIsNotNone(why.get("explanation"))
            self.assertEqual(why["explanation"]["kind"], "plot_link")
            self.assertIn("amateur bakers", why["explanation"]["sentence"].lower())

            similar = neighbors_payload(db, seed, mode="similar", limit=5)
            similar_titles = {item["title"] for item in similar["items"]}
            self.assertIn("Covert Kitchen", similar_titles)
            self.assertNotIn("Gravity", similar_titles)
            self.assertTrue(similar["items"][0].get("plot_link"))
            self.assertEqual(similar["items"][0]["explanation"]["kind"], "plot_link")


if __name__ == "__main__":
    unittest.main()
