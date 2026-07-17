"""Tests for Plot Lab motif intersection “why” explanations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.library.query import (
    attach_motif_why,
    build_motif_why,
    filters_from_mapping,
    query_library,
)


class MotifWhyTests(unittest.TestCase):
    def test_build_motif_why_all_matched_with_excerpts(self) -> None:
        why = build_motif_why(
            ["extinction", "pennsylvania"],
            ["extinction", "pennsylvania", "haunted"],
            plot_text="A story of extinction set in rural Pennsylvania after the collapse.",
        )
        self.assertEqual(why["matched_motifs"], ["extinction", "pennsylvania"])
        self.assertEqual(why["missed_motifs"], [])
        self.assertEqual(len(why["excerpts"]), 2)
        self.assertIn("all of", why["summary"])

    def test_query_library_attaches_motif_why_and_requires_all_motifs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Both Motifs",
                    "year": 2020,
                    "summary": "An extinction event hits pennsylvania hard.",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "One Motif",
                    "year": 2021,
                    "summary": "Only extinction is mentioned here.",
                }
            )
            rows = list(db.all_library_items())
            by_title = {str(r["title"]): int(r["id"]) for r in rows}
            db.replace_facets_of_type(
                "motif",
                [
                    (by_title["Both Motifs"], "motif", "extinction"),
                    (by_title["Both Motifs"], "motif", "pennsylvania"),
                    (by_title["One Motif"], "motif", "extinction"),
                ],
            )

            result = query_library(
                db,
                filters_from_mapping(
                    {"motifs": "extinction,pennsylvania", "limit": 20}
                ),
            )
            titles = [item["title"] for item in result["items"]]
            self.assertEqual(titles, ["Both Motifs"])
            item = result["items"][0]
            self.assertEqual(item["matched_motifs"], ["extinction", "pennsylvania"])
            self.assertTrue(item["motif_why"])
            self.assertTrue(item["motif_excerpts"])

    def test_attach_motif_why_noop_without_selection(self) -> None:
        items = [{"id": 1, "title": "X"}]
        # selected empty → early return; db is unused.
        attach_motif_why(None, items, [])  # type: ignore[arg-type]
        self.assertNotIn("motif_why", items[0])


if __name__ == "__main__":
    unittest.main()
