"""Tests for library embedding rebuild progress and batching."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.embeddings import rebuild_embeddings
from curatorx.models.recommendation import sanitize_recommendation_reason


class RecommendationReasonTests(unittest.TestCase):
    def test_sanitize_keeps_human_text(self) -> None:
        self.assertEqual(
            sanitize_recommendation_reason("British Quatermass energy"),
            "British Quatermass energy",
        )

    def test_sanitize_drops_pipeline_labels(self) -> None:
        self.assertEqual(sanitize_recommendation_reason("TMDB title match"), "")
        self.assertEqual(sanitize_recommendation_reason("tmdb search"), "")
        self.assertEqual(sanitize_recommendation_reason("Missing from your collection"), "")
        self.assertEqual(sanitize_recommendation_reason(""), "")


class RebuildEmbeddingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_rebuild_embeddings_reports_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for index in range(5):
                db.upsert_library_item(
                    {
                        "rating_key": f"rk-{index}",
                        "media_type": "movie",
                        "title": f"Title {index}",
                        "year": 1980 + index,
                        "summary": "A film.",
                        "genres": ["Sci-Fi"],
                    }
                )

            events: list[tuple[str, int, int, str]] = []

            def progress(phase: str, current: int, total: int, message: str) -> None:
                events.append((phase, current, total, message))

            with patch(
                "curatorx.library.embeddings.embed_texts",
                new=AsyncMock(side_effect=lambda texts, settings: [[0.1] * 8 for _ in texts]),
            ):
                count = await rebuild_embeddings(
                    db,
                    Settings(),
                    progress=progress,
                    batch_size=2,
                )

            self.assertEqual(count, 5)
            self.assertGreaterEqual(len(events), 3)
            self.assertEqual(events[0][0], "finishing")
            self.assertEqual(events[-1][1], 5)
            self.assertEqual(events[-1][2], 5)
            self.assertTrue(any("of ~5" in message for _, _, _, message in events))
            self.assertEqual(len(db.get_embeddings()), 5)

    async def test_rebuild_embeddings_empty_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            events: list[tuple[str, int, int, str]] = []

            def progress(phase: str, current: int, total: int, message: str) -> None:
                events.append((phase, current, total, message))

            count = await rebuild_embeddings(db, Settings(), progress=progress)
            self.assertEqual(count, 0)
            self.assertEqual(events, [("finishing", 1, 1, "Building recommendations…")])


if __name__ == "__main__":
    unittest.main()
