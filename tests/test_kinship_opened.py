"""CA-01 / CA-02 — opened-title Named kinship and kinship_miss list."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless

from projectionist.library.db import Database
from projectionist.library.query import compute_knowledge_coverage
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync
from projectionist.telemetry.kinship_miss import EVENT_KINSHIP_MISS, list_kinship_miss


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 1995,
        "genres": ["Crime"],
        "keywords": [],
        "summary": "A crew plans one last score in Los Angeles.",
        "tmdb_overview": "Professionals collide on a downtown job.",
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


def _miss(db: Database, item_id: int, *, reason: str = "more_like_this_empty", hits: int = 1) -> None:
    for _ in range(hits):
        upsert_closed_loop_event_sync(
            db,
            event_type=EVENT_KINSHIP_MISS,
            priority_tier="P2",
            entity_type="title",
            entity_key=str(item_id),
            payload={"item_id": item_id, "reason": reason},
        )


class OpenedKinshipCoverageTests(unittest.TestCase):
    def test_opened_pct_moves_when_heat_is_annotated(self) -> None:
        """CA-01 success: Sunday empty More Like This on Heat → Monday % moves."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "heat.db")
            heat = _title(db, rating_key="heat", tmdb_id=949, title="Heat", year=1995)
            peer = _title(
                db,
                rating_key="heat-peer",
                tmdb_id=950,
                title="Collateral",
                year=2004,
                summary="A cab driver is forced into one night with a contract killer.",
            )
            cold = _title(
                db,
                rating_key="cold",
                tmdb_id=951,
                title="Gravity",
                year=2013,
                summary="Astronauts fight debris in orbit.",
            )
            # Whole-library Similar cache can look full: cosine neighbors on Heat + Gravity.
            db.set_neighbors(heat, [(peer, 0.91, 0.2)])
            db.set_neighbors(cold, [(peer, 0.88, 0.1)])
            _miss(db, heat, reason="more_like_this_empty")

            coverage = compute_knowledge_coverage(db)
            self.assertIn("with_explainable_neighbors_opened_pct", coverage)
            self.assertEqual(coverage["opened_title_count"], 1)
            self.assertEqual(coverage["opened_with_explainable_count"], 0)
            self.assertEqual(coverage["with_explainable_neighbors_opened_pct"], 0.0)
            # Similar cache stays high while opened Named kinship is the number to quote.
            self.assertGreater(coverage["with_neighbors_pct"], coverage["with_explainable_neighbors_opened_pct"])
            self.assertEqual(coverage["with_explainable_neighbors_pct"], 0.0)

            db.set_neighbors(heat, [(peer, 0.91, 0.2, 1, '{"sentence":"Both chase a downtown score."}')])
            after = compute_knowledge_coverage(db)
            self.assertEqual(after["opened_title_count"], 1)
            self.assertEqual(after["opened_with_explainable_count"], 1)
            self.assertEqual(after["with_explainable_neighbors_opened_pct"], 100.0)
            self.assertGreater(after["with_neighbors_pct"], 50.0)


class KinshipMissListTests(unittest.TestCase):
    def test_list_names_three_empty_more_like_this_titles(self) -> None:
        """CA-02 success: owner can name three titles without querying SQLite by hand."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "miss.db")
            heat = _title(db, rating_key="heat", tmdb_id=949, title="Heat", year=1995)
            bake = _title(db, rating_key="bake", tmdb_id=1, title="Bake Show", year=2010)
            house = _title(
                db,
                rating_key="house",
                tmdb_id=1408,
                title="House",
                year=2004,
                media_type="show",
            )
            _miss(db, heat, reason="more_like_this_empty", hits=3)
            _miss(db, bake, reason="more_like_this_empty", hits=2)
            _miss(db, house, reason="more_like_this_empty", hits=1)

            payload = list_kinship_miss(db, limit=50)
            self.assertEqual(payload["count"], 3)
            self.assertIn("auto-repaired", payload["note"].lower())
            titles = [item["title"] for item in payload["items"]]
            self.assertEqual(titles[:3], ["Heat", "Bake Show", "House"])
            by_title = {item["title"]: item for item in payload["items"]}
            self.assertEqual(by_title["Heat"]["why_queued"], "more_like_this_empty")
            self.assertEqual(by_title["Heat"]["hit_count"], 3)
            self.assertTrue(by_title["Heat"]["last_miss"])
            self.assertEqual(by_title["Heat"]["href"], "/title/movie/949")
            self.assertEqual(by_title["House"]["href"], "/title/show/1408")

    def test_relations_empty_maps_to_related_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "rel.db")
            seed = _title(db, rating_key="rel", tmdb_id=2, title="Related Miss")
            _miss(db, seed, reason="relations_empty")
            payload = list_kinship_miss(db, limit=10)
            self.assertEqual(payload["items"][0]["why_queued"], "related_empty")
            self.assertEqual(payload["items"][0]["reason"], "relations_empty")


try:
    from projectionist.mcp import server as mcp_server
    from projectionist.mcp.mode import set_mcp_mode

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


@skipUnless(HAS_MCP, "mcp package not installed")
class KinshipMcpWrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")
        self.db = Database(Path(self._tmpdir.name) / "mcp.db")

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("DATA_DIR", None)
        set_mcp_mode("privacy")
        self._tmpdir.cleanup()

    def test_full_mcp_quotes_opened_pct_and_three_titles(self) -> None:
        """OP-01 success: agent JSON names opened % and three empty More Like This titles."""
        heat = _title(self.db, rating_key="heat", tmdb_id=949, title="Heat")
        bake = _title(self.db, rating_key="bake", tmdb_id=1, title="Bake Show")
        house = _title(self.db, rating_key="house", tmdb_id=1408, title="House", media_type="show")
        peer = _title(self.db, rating_key="peer", tmdb_id=9, title="Peer")
        _miss(self.db, heat, reason="more_like_this_empty")
        _miss(self.db, bake, reason="more_like_this_empty")
        _miss(self.db, house, reason="more_like_this_empty")
        self.db.set_neighbors(heat, [(peer, 0.9, 0.2, 1)])

        from unittest.mock import patch

        with patch.object(mcp_server, "_database", return_value=self.db):
            coverage = json.loads(mcp_server.knowledge_coverage_tool())
            misses = json.loads(mcp_server.kinship_miss_list(limit=50))

        self.assertEqual(coverage["with_explainable_neighbors_opened_pct"], 33.3)
        self.assertEqual(coverage["opened_title_count"], 3)
        self.assertTrue(coverage.get("embedding_is_hash_fallback") in (True, False))
        titles = [item["title"] for item in misses["items"]]
        self.assertEqual(len(titles), 3)
        self.assertIn("Heat", titles)
        self.assertIn("Bake Show", titles)
        self.assertIn("House", titles)
        self.assertTrue(all(item["why_queued"] == "more_like_this_empty" for item in misses["items"]))

    def test_privacy_mode_blocked(self) -> None:
        set_mcp_mode("privacy")
        self.assertIn("error", json.loads(mcp_server.knowledge_coverage_tool()))
        self.assertIn("error", json.loads(mcp_server.kinship_miss_list()))


if __name__ == "__main__":
    unittest.main()
