"""Facet catalog query (full-index tag search)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.library.facets import library_facet_catalog, rebuild_library_facets


class FacetSearchTests(unittest.TestCase):
    def test_keyword_catalog_q_finds_non_top_chip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            # Make popular tags outrank a rare keyword by count so it falls off the default chip list.
            for index in range(80):
                tag = f"popular-tag-{index}"
                for copy in range(3):
                    db.upsert_library_item(
                        {
                            "rating_key": f"pop-{index}-{copy}",
                            "media_type": "movie",
                            "title": f"Popular {index}-{copy}",
                            "year": 2000 + (index % 20),
                            "tmdb_id": 1000 + index * 10 + copy,
                            "keywords": [tag],
                        }
                    )
            db.upsert_library_item(
                {
                    "rating_key": "ff-1",
                    "media_type": "movie",
                    "title": "REC",
                    "year": 2007,
                    "tmdb_id": 8329,
                    "keywords": ["found footage"],
                }
            )
            rebuild_library_facets(db)

            top = library_facet_catalog(db, "keyword", limit=60)
            top_values = {entry["value"] for entry in top["facets"]}
            self.assertNotIn("found footage", top_values)

            hits = library_facet_catalog(db, "keyword", limit=20, q="found footage")
            values = [entry["value"] for entry in hits["facets"]]
            self.assertIn("found footage", values)
            self.assertEqual(hits["q"], "found footage")


if __name__ == "__main__":
    unittest.main()
