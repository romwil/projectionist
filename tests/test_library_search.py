"""Tests for keyword-first library search."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.facets import rebuild_library_facets
from curatorx.library.search import looks_like_facet_tag_query, search_library


class LibrarySearchTests(unittest.IsolatedAsyncioTestCase):
    def _seed(self, db: Database) -> None:
        db.upsert_library_item(
            {
                "rating_key": "ff-1",
                "media_type": "movie",
                "title": "The Blair Witch Project",
                "year": 1999,
                "tmdb_id": 2667,
                "keywords": ["found footage", "horror"],
                "summary": "Three student filmmakers disappear.",
            }
        )
        db.upsert_library_item(
            {
                "rating_key": "noise-1",
                "media_type": "movie",
                "title": "Quiet Picnic",
                "year": 2012,
                "tmdb_id": 9001,
                "keywords": ["romance"],
                "summary": "A gentle afternoon.",
            }
        )
        rebuild_library_facets(db)

    def test_looks_like_facet_tag_query(self) -> None:
        self.assertTrue(looks_like_facet_tag_query("found footage"))
        self.assertFalse(
            looks_like_facet_tag_query(
                "something long and plotty about characters wandering through fog forever"
            )
        )

    async def test_search_library_prefers_keyword_over_semantic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed(db)
            with patch(
                "curatorx.library.search.query_library_async",
                new_callable=AsyncMock,
            ) as mock_semantic:
                cards = await search_library(
                    db,
                    Settings(),
                    "found footage",
                    limit=10,
                )
                mock_semantic.assert_not_called()
            titles = {card.title for card in cards}
            self.assertIn("The Blair Witch Project", titles)
            self.assertNotIn("Quiet Picnic", titles)
            self.assertTrue(any("keyword" in (card.recommendation_reason or "") for card in cards))

    async def test_search_library_falls_back_to_semantic_when_no_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed(db)

            async def fake_semantic(_db, _filters, _settings):
                return {
                    "total_matched": 1,
                    "returned": 1,
                    "offset": 0,
                    "has_more": False,
                    "search_mode": "semantic",
                    "items": [{"id": db.library_item_by_rating_key("noise-1")["id"]}],
                }

            with patch(
                "curatorx.library.search.query_library_async",
                new=AsyncMock(side_effect=fake_semantic),
            ):
                cards = await search_library(
                    db,
                    Settings(),
                    "mood for a gentle afternoon picnic",
                    limit=10,
                )
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].title, "Quiet Picnic")

    async def test_search_library_extracts_title_from_conversational_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "simpsley-1",
                    "media_type": "movie",
                    "title": "Simpsley",
                    "year": 2026,
                    "summary": "A Simpsons noir special.",
                }
            )

            cards = await search_library(
                db,
                Settings(),
                "how about simpsley? 2026?",
                media_type="movie",
            )

            self.assertEqual([(card.title, card.year) for card in cards], [("Simpsley", 2026)])


if __name__ == "__main__":
    unittest.main()
