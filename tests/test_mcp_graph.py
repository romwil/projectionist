"""LIB-02 — privacy-sanitized MCP wraps of in-process graph tools."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from projectionist.library.db import Database
from projectionist.library.plot_kinship import KINSHIP_CACHE_NOT_READY_NOTE
from projectionist.library.relations import refresh_title_relations
from projectionist.mcp.mode import set_mcp_mode
from tests.test_household_bridges import BAKE_PLOT, SPY_PLOT, _explainable_neighbor, _title

try:
    from projectionist.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False
    mcp_server = None  # type: ignore[assignment]


@skipUnless(HAS_MCP, "mcp package not installed")
class McpGraphPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("privacy")
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("DATA_DIR", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_list_relations_named_peers_or_cache_note(self) -> None:
        heat = _title(
            self.db,
            rating_key="heat",
            title="Heat",
            year=1995,
            tmdb_collection_id=9,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="peer",
            title="Collateral",
            year=2004,
            tmdb_collection_id=9,
            summary=SPY_PLOT,
        )
        refresh_title_relations(self.db, include_neighbors=False)
        with patch.object(mcp_server, "_database", return_value=self.db):
            payload = json.loads(mcp_server.list_relations(title="Heat", year=1995))
        self.assertTrue(payload["items"])
        item = payload["items"][0]
        self.assertEqual(item["explanation"]["kind"], "collection")
        self.assertTrue(item["explanation"]["sentence"])
        dumped = json.dumps(payload)
        self.assertNotIn("rating_key", dumped)
        self.assertNotIn("heat", dumped)

        cosine_only = Database(Path(self._tmpdir.name) / "empty.db")
        seed = _title(cosine_only, rating_key="rk-seed", title="Seed", year=1999)
        other = _title(cosine_only, rating_key="rk-peer", title="Peer", year=2000)
        cosine_only.set_neighbors(seed, [(other, 0.99, 0.1)])
        with patch.object(mcp_server, "_database", return_value=cosine_only):
            empty = json.loads(mcp_server.find_similar_titles(title="Seed"))
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["note"], KINSHIP_CACHE_NOT_READY_NOTE)
        self.assertTrue(empty.get("empty"))

    def test_titles_by_person_and_walk_depth_cap(self) -> None:
        a = _title(self.db, rating_key="a", title="Alpha", year=2000)
        b = _title(self.db, rating_key="b", title="Beta", year=2001)
        credit = [
            {
                "tmdb_person_id": 525,
                "name": "Christopher Nolan",
                "department": "Directing",
                "job": "Director",
                "billing_order": 0,
            }
        ]
        self.db.upsert_credits_for_item(a, credit)
        self.db.upsert_credits_for_item(b, credit)
        with patch.object(mcp_server, "_database", return_value=self.db):
            people = json.loads(mcp_server.titles_by_person(name="Christopher Nolan"))
            walked = json.loads(mcp_server.walk_relations(title="Alpha", depth=9, limit=10))
        titles = {item["title"] for item in people["items"]}
        self.assertEqual(titles, {"Alpha", "Beta"})
        self.assertTrue(all(item.get("explanation", {}).get("sentence") for item in people["items"]))
        self.assertNotIn("rating_key", json.dumps(people))
        self.assertLessEqual(walked.get("depth") or 0, 2)

    def test_find_similar_titles_explainable_only(self) -> None:
        seed = _title(
            self.db,
            rating_key="seed",
            title="Bake Off",
            year=2010,
            summary=BAKE_PLOT,
        )
        peer = _title(
            self.db,
            rating_key="peer",
            title="Spy Bake",
            year=2011,
            summary=SPY_PLOT,
        )
        _explainable_neighbor(self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT)
        with patch.object(mcp_server, "_database", return_value=self.db):
            payload = json.loads(mcp_server.find_similar_titles(title="Bake Off", year=2010))
        self.assertEqual(payload["items"][0]["title"], "Spy Bake")
        self.assertEqual(payload["items"][0]["explanation"]["kind"], "plot_link")
        self.assertTrue(payload["items"][0]["explanation"]["sentence"])
        self.assertNotIn("rating_key", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
