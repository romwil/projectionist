"""Release 3 — catalog graph from free data (genre facets, person edges, keywords)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.facets import (
    ensure_library_facet_index,
    library_facet_catalog,
    rebuild_library_facets,
)
from projectionist.library.query import filters_from_mapping, query_library
from projectionist.library.relations import (
    build_person_centric_relations,
    list_relations_for_item,
    refresh_title_relations,
)


class GenreFacetTests(unittest.TestCase):
    def test_rebuild_emits_genre_facets_and_query_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "sf-1",
                    "media_type": "movie",
                    "title": "Inception",
                    "year": 2010,
                    "genres": ["Sci-Fi", "Thriller"],
                    "directors": ["Christopher Nolan"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "drama-1",
                    "media_type": "movie",
                    "title": "Manchester by the Sea",
                    "year": 2016,
                    "genres": ["Drama"],
                }
            )
            count = rebuild_library_facets(db)
            self.assertGreaterEqual(count, 3)

            catalog = library_facet_catalog(db, "genre", limit=20)
            self.assertEqual(catalog["facet_type"], "genre")
            values = {entry["value"] for entry in catalog["facets"]}
            self.assertIn("Sci-Fi", values)
            self.assertIn("Drama", values)

            with db.connect() as conn:
                genre_rows = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM library_facets WHERE facet_type = 'genre'"
                ).fetchone()["cnt"]
            self.assertGreaterEqual(int(genre_rows), 3)

            result = query_library(
                db, filters_from_mapping({"genres": "Sci-Fi", "limit": 20})
            )
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Inception")

    def test_ensure_backfills_genre_facets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "g-1",
                    "media_type": "movie",
                    "title": "Genre Only",
                    "genres": ["Comedy"],
                }
            )
            rebuilt = ensure_library_facet_index(db)
            self.assertGreater(rebuilt, 0)
            catalog = library_facet_catalog(db, "genre", limit=10)
            self.assertEqual(catalog["facets"][0]["value"], "Comedy")


class PersonCentricRelationTests(unittest.TestCase):
    def test_two_films_same_director_get_directed_by_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            a = db.upsert_library_item(
                {
                    "rating_key": "nolan-a",
                    "media_type": "movie",
                    "title": "Inception",
                    "year": 2010,
                    "genres": ["Sci-Fi"],
                    "keywords": ["dream", "subconscious"],
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "nolan-b",
                    "media_type": "movie",
                    "title": "The Prestige",
                    "year": 2006,
                    "genres": ["Drama"],
                    "keywords": ["magic", "rivalry"],
                }
            )
            credit = [
                {
                    "tmdb_person_id": 525,
                    "name": "Christopher Nolan",
                    "department": "Directing",
                    "job": "Director",
                    "billing_order": 0,
                }
            ]
            db.upsert_credits_for_item(a, credit)
            db.upsert_credits_for_item(b, credit)

            counts = refresh_title_relations(db, include_neighbors=False)
            self.assertGreaterEqual(counts["directed_by"], 2)

            payload = list_relations_for_item(db, a, relation="directed_by", limit=10)
            self.assertEqual(payload["returned"], 1)
            edge = payload["items"][0]
            self.assertEqual(edge["peer"]["title"], "The Prestige")
            self.assertEqual(edge["why"]["shared_people"], ["Christopher Nolan"])
            self.assertIn("Christopher Nolan", edge["why"]["label"])
            self.assertEqual(edge["why"]["explanation"]["kind"], "directed_by")

    def test_solo_writer_edge_names_person(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            a = db.upsert_library_item(
                {
                    "rating_key": "w-a",
                    "media_type": "movie",
                    "title": "Script One",
                    "year": 2010,
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "w-b",
                    "media_type": "movie",
                    "title": "Script Two",
                    "year": 2012,
                }
            )
            credit = [
                {
                    "tmdb_person_id": 900,
                    "name": "Ada Writer",
                    "department": "Writing",
                    "job": "Screenplay",
                    "billing_order": 0,
                }
            ]
            db.upsert_credits_for_item(a, credit)
            db.upsert_credits_for_item(b, credit)
            edges = build_person_centric_relations(db)
            self.assertGreaterEqual(len(edges["written_by"]), 2)
            db.replace_relations_of_types({"written_by": edges["written_by"]})
            payload = list_relations_for_item(db, a, relation="written_by", limit=5)
            self.assertEqual(payload["items"][0]["why"]["label"], "Written by Ada Writer")


class KeywordWhyAndRankedOrTests(unittest.TestCase):
    def test_shared_keywords_appear_in_relation_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = db.upsert_library_item(
                {
                    "rating_key": "seed",
                    "media_type": "movie",
                    "title": "Seed",
                    "year": 2020,
                    "genres": ["Drama"],
                    "keywords": ["heist", "found family"],
                    "tmdb_collection_id": 42,
                    "collection_name": "Capers",
                }
            )
            peer = db.upsert_library_item(
                {
                    "rating_key": "peer",
                    "media_type": "movie",
                    "title": "Peer",
                    "year": 2021,
                    "genres": ["Drama"],
                    "keywords": ["heist", "double cross"],
                    "tmdb_collection_id": 42,
                    "collection_name": "Capers",
                }
            )
            db.replace_relations_of_types(
                {
                    "collection": [
                        (seed, peer, "collection", 1.0, "tmdb_collection"),
                    ]
                }
            )
            payload = list_relations_for_item(db, seed, limit=5)
            why = payload["items"][0]["why"]
            self.assertEqual(why["shared_keywords"], ["heist"])
            self.assertIn("heist", why["explanation"]["evidence"]["shared_keywords"])

    def test_ranked_or_when_motif_and_empty_but_keywords_match(self) -> None:
        """Hybrid AND is empty; ranked OR still surfaces keyword/plot hits."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Revenge Only",
                    "year": 2010,
                    "summary": "A quiet drama.",
                    "keywords": ["revenge"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Bride Only",
                    "year": 2011,
                    "summary": "A bride walks down the aisle.",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "3",
                    "media_type": "movie",
                    "title": "Both Signals",
                    "year": 2012,
                    "summary": "The Bride seeks revenge after a coma.",
                    "keywords": ["revenge"],
                }
            )
            ids = {str(r["title"]): int(r["id"]) for r in db.all_library_items()}
            db.replace_facets_of_type(
                "keyword",
                [
                    (ids["Revenge Only"], "keyword", "revenge"),
                    (ids["Both Signals"], "keyword", "revenge"),
                ],
            )

            hybrid = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,revenge",
                        "plot_match_mode": "hybrid",
                        "limit": 20,
                    }
                ),
            )
            # Only Both Signals has both tokens via multi-signal layers.
            self.assertEqual(
                [item["title"] for item in hybrid["items"]], ["Both Signals"]
            )

            # Titles that only hit one token: hybrid AND excluding Both would be empty.
            # Ranked OR finds partial matches and ranks the two-token hit first.
            ranked = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,revenge",
                        "plot_match_mode": "any",
                        "limit": 20,
                    }
                ),
            )
            titles = [item["title"] for item in ranked["items"]]
            self.assertEqual(ranked["total_matched"], 3)
            self.assertEqual(titles[0], "Both Signals")
            self.assertIn("Revenge Only", titles)
            self.assertIn("Bride Only", titles)
            both = ranked["items"][0]
            layers = {entry["motif"]: entry["layers"] for entry in both["match_layers"]}
            self.assertIn("keyword", layers["revenge"])
            self.assertTrue(
                "plot_text" in layers["bride"] or "motif" in layers.get("bride", [])
            )


if __name__ == "__main__":
    unittest.main()
