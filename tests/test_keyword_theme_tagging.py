"""Tests for local keyword → theme mapping and facet writes."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.theme_map import themes_from_keywords
from curatorx.scheduler.tasks import keyword_theme_tagging


class ThemeMapTests(unittest.TestCase):
    def test_maps_frequent_keywords_to_controlled_themes(self) -> None:
        themes = themes_from_keywords(
            ["revenge", "martial arts", "bank robbery", "unknown noise"]
        )
        self.assertIn("revenge", themes)
        self.assertIn("martial arts", themes)
        self.assertIn("heist", themes)
        self.assertNotIn("unknown noise", themes)

    def test_ignores_unmapped_keywords(self) -> None:
        self.assertEqual(themes_from_keywords(["completely-made-up-tag"]), [])


class KeywordThemeTaskTests(unittest.TestCase):
    def test_writes_theme_facets_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "kb1",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 1",
                    "year": 2003,
                    "summary": "The Bride awakens.",
                    "keywords": ["revenge", "martial arts", "assassin"],
                }
            )
            result = asyncio.run(
                keyword_theme_tagging.run(db, Settings(), should_stop=lambda: False)
            )
            self.assertEqual(result["status"], "completed")
            self.assertGreaterEqual(result["themes"], 2)
            themes = db.facet_values_for_items([item_id], "theme").get(item_id) or []
            self.assertIn("revenge", [t.lower() for t in themes])
            self.assertIn("martial arts", [t.lower() for t in themes])

    def test_replace_does_not_wipe_motifs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Example",
                    "year": 2000,
                    "keywords": ["time travel"],
                }
            )
            db.replace_facets_of_type("motif", [(item_id, "motif", "loop")])
            asyncio.run(
                keyword_theme_tagging.run(db, Settings(), should_stop=lambda: False)
            )
            motifs = db.facet_values_for_items([item_id], "motif").get(item_id) or []
            themes = db.facet_values_for_items([item_id], "theme").get(item_id) or []
            self.assertEqual(motifs, ["loop"])
            self.assertIn("time travel", [t.lower() for t in themes])


if __name__ == "__main__":
    unittest.main()
