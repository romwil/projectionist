"""Focused tests for member-facing title relation payloads and routes."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db import Database
from projectionist.library.relations import list_relations_for_item, walk_relations


def _title(
    db: Database,
    *,
    rating_key: str,
    tmdb_id: int,
    title: str,
    genres: list[str],
    collection_name: str = "",
) -> int:
    return db.upsert_library_item(
        {
            "rating_key": rating_key,
            "media_type": "movie",
            "tmdb_id": tmdb_id,
            "title": title,
            "year": 2020,
            "genres": genres,
            "tmdb_collection_id": 10 if collection_name else None,
            "collection_name": collection_name,
        }
    )


class RelationPayloadTests(unittest.TestCase):
    def test_relations_include_peer_cards_and_plain_language_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = _title(
                db,
                rating_key="seed",
                tmdb_id=1,
                title="Seed",
                genres=["Drama", "Science Fiction"],
                collection_name="Future Stories",
            )
            collection_peer = _title(
                db,
                rating_key="collection",
                tmdb_id=2,
                title="Sequel",
                genres=["Drama"],
                collection_name="Future Stories",
            )
            crew_peer = _title(
                db,
                rating_key="crew",
                tmdb_id=3,
                title="Crew Reunion",
                genres=["Science Fiction"],
            )
            neighbor = _title(
                db,
                rating_key="neighbor",
                tmdb_id=4,
                title="Plot Cousin",
                genres=["Science Fiction", "Thriller"],
            )
            shared_credits = [
                {
                    "tmdb_person_id": 100,
                    "name": "Ava Director",
                    "department": "Directing",
                    "job": "Director",
                    "billing_order": 0,
                },
                {
                    "tmdb_person_id": 101,
                    "name": "Wes Writer",
                    "department": "Writing",
                    "job": "Writer",
                    "billing_order": 1,
                },
            ]
            db.upsert_credits_for_item(seed, shared_credits)
            db.upsert_credits_for_item(crew_peer, shared_credits)
            db.set_neighbors(seed, [(neighbor, 0.82, 0.57)])
            db.replace_relations_of_types(
                {
                    "collection": [
                        (seed, collection_peer, "collection", 1.0, "tmdb_collection")
                    ],
                    "shared_crew": [
                        (seed, crew_peer, "shared_crew", 0.4, "credits_overlap")
                    ],
                    "neighbor": [
                        (seed, neighbor, "neighbor", 0.82, "item_neighbors")
                    ],
                }
            )

            payload = list_relations_for_item(db, seed, limit=10)
            by_relation = {edge["relation"]: edge for edge in payload["items"]}

            collection = by_relation["collection"]
            self.assertEqual(collection["peer"]["title"], "Sequel")
            self.assertEqual(collection["peer"]["library_item_id"], collection_peer)
            self.assertEqual(collection["why"]["collection_name"], "Future Stories")
            self.assertEqual(collection["why"]["shared_genres"], ["Drama"])
            self.assertIn("Future Stories", collection["why"]["label"])

            crew = by_relation["shared_crew"]
            self.assertEqual(
                crew["why"]["shared_people"], ["Ava Director", "Wes Writer"]
            )
            self.assertIn("Ava Director", crew["why"]["label"])

            plot = by_relation["neighbor"]
            self.assertEqual(plot["why"]["plot_kinship"], "Strong plot kinship")
            self.assertEqual(plot["why"]["shared_genres"], ["Science Fiction"])
            self.assertTrue(plot["why"]["surprise_flavor"])
            self.assertIn("Strong plot kinship", plot["why"]["label"])

    def test_walk_caps_depth_at_two_and_keeps_enriched_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            first = _title(
                db, rating_key="first", tmdb_id=1, title="First", genres=["Drama"]
            )
            second = _title(
                db, rating_key="second", tmdb_id=2, title="Second", genres=["Drama"]
            )
            third = _title(
                db, rating_key="third", tmdb_id=3, title="Third", genres=["Drama"]
            )
            db.replace_relations_of_types(
                {
                    "collection": [
                        (first, second, "collection", 1.0, "tmdb_collection"),
                        (second, third, "collection", 1.0, "tmdb_collection"),
                    ]
                }
            )

            payload = walk_relations(db, first, depth=9, limit=10)

            self.assertEqual(payload["depth"], 2)
            self.assertEqual([edge["to_id"] for edge in payload["items"]], [second, third])
            self.assertTrue(all(edge["why"]["label"] for edge in payload["items"]))


class RelationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_title_relations_and_walk_routes_resolve_tmdb_id(self) -> None:
        seed = _title(
            self.db, rating_key="seed", tmdb_id=101, title="Seed", genres=["Drama"]
        )
        peer = _title(
            self.db, rating_key="peer", tmdb_id=202, title="Peer", genres=["Drama"]
        )
        self.db.replace_relations_of_types(
            {
                "collection": [
                    (seed, peer, "collection", 1.0, "tmdb_collection")
                ]
            }
        )

        response = self.client.get("/api/title/movie/101/relations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_id"], seed)
        self.assertEqual(response.json()["items"][0]["peer"]["tmdb_id"], 202)

        walked = self.client.get(
            "/api/title/movie/101/relations/walk",
            params={"depth": 2, "relation": "collection"},
        )
        self.assertEqual(walked.status_code, 200)
        self.assertEqual(walked.json()["depth"], 2)
        self.assertEqual(walked.json()["items"][0]["why"]["type"], "collection")

    def test_title_relations_returns_404_for_unknown_or_mismatched_title(self) -> None:
        _title(
            self.db, rating_key="show-id", tmdb_id=303, title="Movie", genres=[]
        )
        missing = self.client.get("/api/title/show/303/relations")
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
