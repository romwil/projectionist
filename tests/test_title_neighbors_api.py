"""Neighbors API for title detail More Like This carousel."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.library.db import Database


class TitleNeighborsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_neighbors_empty_when_title_missing(self) -> None:
        response = self.client.get("/api/title/movie/999/neighbors")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["total"], 0)

    def test_neighbors_returns_cached_rows(self) -> None:
        seed_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-1",
                "title": "Seed",
                "year": 1982,
                "media_type": "movie",
                "tmdb_id": 78,
                "poster_url": "https://example.com/seed.jpg",
                "genres": ["Sci-Fi"],
            }
        )
        neighbor_id = self.db.upsert_library_item(
            {
                "rating_key": "rk-2",
                "title": "Neighbor",
                "year": 1984,
                "media_type": "movie",
                "tmdb_id": 79,
                "poster_url": "https://example.com/n.jpg",
                "genres": ["Sci-Fi"],
                "summary": "Close twin",
            }
        )
        self.db.set_neighbors(seed_id, [(neighbor_id, 0.91, 0.2)])

        response = self.client.get("/api/title/movie/78/neighbors")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["title"], "Neighbor")
        self.assertEqual(item["tmdb_id"], 79)
        self.assertAlmostEqual(item["score"], 0.91, places=2)


if __name__ == "__main__":
    unittest.main()
