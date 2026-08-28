"""Tests for optional sqlite-vec ANN prefilter (graceful fallback)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from projectionist.library.db import Database
from projectionist.library.embeddings import semantic_search
from projectionist.library import neighbors as neighbors_mod
from projectionist.library.vec_index import (
    ann_candidate_ids,
    reset_vec_capability_cache,
    vec_available,
    vec_capability,
)


class VecCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_vec_capability_cache()
        self._prev = os.environ.get("PROJECTIONIST_SQLITE_VEC")

    def tearDown(self) -> None:
        reset_vec_capability_cache()
        if self._prev is None:
            os.environ.pop("PROJECTIONIST_SQLITE_VEC", None)
        else:
            os.environ["PROJECTIONIST_SQLITE_VEC"] = self._prev

    def test_env_disable_forces_unavailable(self) -> None:
        os.environ["PROJECTIONIST_SQLITE_VEC"] = "0"
        reset_vec_capability_cache()
        cap = vec_capability()
        self.assertFalse(cap["available"])
        self.assertIn("disabled", cap["reason"])
        self.assertFalse(vec_available())

    def test_ann_returns_none_when_unavailable(self) -> None:
        os.environ["PROJECTIONIST_SQLITE_VEC"] = "0"
        reset_vec_capability_cache()
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "projectionist.db")
            result = ann_candidate_ids(db, [1.0, 0.0, 0.0], limit=10)
            self.assertIsNone(result)


class SemanticSearchFallbackTests(unittest.TestCase):
    def test_semantic_search_works_without_vec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "projectionist.db")
            a = db.upsert_library_item(
                {
                    "rating_key": "a",
                    "media_type": "movie",
                    "title": "Alpha",
                    "year": 2000,
                }
            )
            b = db.upsert_library_item(
                {
                    "rating_key": "b",
                    "media_type": "movie",
                    "title": "Beta",
                    "year": 2001,
                }
            )
            db.set_embeddings(
                [
                    (a, [1.0, 0.0, 0.0]),
                    (b, [0.0, 1.0, 0.0]),
                ]
            )
            with mock.patch("projectionist.library.vec_index.vec_available", return_value=False):
                hits = semantic_search(db, [1.0, 0.0, 0.0], limit=5)
            self.assertEqual(hits[0][0], a)


class NeighborAnnPrefilterTests(unittest.TestCase):
    def test_refresh_uses_prefilter_when_ann_returns_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "projectionist.db")
            ids = []
            for i, vec in enumerate(
                ([1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]),
                start=1,
            ):
                item_id = db.upsert_library_item(
                    {
                        "rating_key": f"rk-{i}",
                        "media_type": "movie",
                        "title": f"Title {i}",
                        "year": 2000 + i,
                        "genres": ["Drama"] if i < 3 else ["Comedy"],
                    }
                )
                ids.append(item_id)
                db.set_embedding(item_id, vec)

            seed, near, far_a, far_b = ids
            # Pretend ANN only returns the near neighbor (+ noise).
            with mock.patch("projectionist.library.neighbors.vec_available", return_value=True), mock.patch(
                "projectionist.library.vec_index.ensure_vec_index", return_value=True
            ), mock.patch(
                "projectionist.library.neighbors.ann_candidate_ids",
                return_value=[near],
            ):
                processed = neighbors_mod.refresh_neighbors_for_items(db, [seed], top_k=5)
            self.assertEqual(processed, 1)
            rows = db.get_neighbors(seed, limit=10)
            neighbor_ids = {int(r["neighbor_id"]) for r in rows}
            self.assertIn(near, neighbor_ids)
            self.assertNotIn(far_a, neighbor_ids)
            self.assertNotIn(far_b, neighbor_ids)


if __name__ == "__main__":
    unittest.main()
