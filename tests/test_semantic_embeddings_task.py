"""Tests for the semantic_embeddings idle scheduler task.

Validates trickle ingestion: per-cycle cap (MAX_ITEMS_PER_CYCLE),
batched API calls (BATCH_SIZE), and cooperative interruption via
should_stop().
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.tasks import semantic_embeddings


def _make_db(tmp: str, n_items: int) -> Database:
    db = Database(Path(tmp) / "test.db")
    for i in range(n_items):
        db.upsert_library_item(
            {
                "rating_key": f"rk-{i}",
                "media_type": "movie",
                "title": f"Title {i}",
                "year": 2000 + i,
                "summary": f"Plot summary for title {i}.",
                "genres": ["Drama"],
            }
        )
    return db


def _fake_embed(texts, _settings):
    return [[0.1] * 8 for _ in texts]


class TrickleIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_cycle_cap_limits_embedded_count(self) -> None:
        """When more items need embedding than MAX_ITEMS_PER_CYCLE, the task
        stops after the cap and reports 'cycle_limit' status."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp, 80)

            with patch.object(semantic_embeddings, "MAX_ITEMS_PER_CYCLE", 20), \
                 patch(
                     "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                     new=AsyncMock(side_effect=_fake_embed),
                 ):
                result = await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )

            self.assertEqual(result["status"], "cycle_limit")
            self.assertEqual(result["embedded"], 20)
            self.assertGreater(result["remaining"], 0)

    async def test_small_library_completes_in_one_cycle(self) -> None:
        """A library smaller than MAX_ITEMS_PER_CYCLE finishes in one pass."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp, 5)

            with patch(
                "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                new=AsyncMock(side_effect=_fake_embed),
            ):
                result = await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["embedded"], 5)

    async def test_should_stop_interrupts_mid_cycle(self) -> None:
        """should_stop() returning True between batches causes early exit."""
        call_count = 0

        def stop_after_one_batch() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > 1

        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp, 30)

            with patch.object(semantic_embeddings, "BATCH_SIZE", 5), \
                 patch(
                     "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                     new=AsyncMock(side_effect=_fake_embed),
                 ):
                result = await semantic_embeddings.run(
                    db, Settings(), should_stop=stop_after_one_batch
                )

            self.assertEqual(result["status"], "interrupted")
            self.assertLessEqual(result["embedded"], 10)

    async def test_subsequent_cycle_picks_up_remaining(self) -> None:
        """After a cycle_limit run, a second invocation embeds the rest."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp, 30)

            with patch.object(semantic_embeddings, "MAX_ITEMS_PER_CYCLE", 20), \
                 patch(
                     "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                     new=AsyncMock(side_effect=_fake_embed),
                 ):
                r1 = await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )
                self.assertEqual(r1["status"], "cycle_limit")
                self.assertEqual(r1["embedded"], 20)

                r2 = await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )
            self.assertEqual(r2["status"], "completed")
            self.assertEqual(r2["embedded"], 10)

    async def test_skips_items_without_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "No Summary",
                    "year": 2020,
                    "summary": "",
                    "genres": ["Drama"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "rk-2",
                    "media_type": "movie",
                    "title": "Has Summary",
                    "year": 2021,
                    "summary": "A real plot.",
                    "genres": ["Drama"],
                }
            )

            with patch(
                "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                new=AsyncMock(side_effect=_fake_embed),
            ):
                result = await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )

            self.assertEqual(result["embedded"], 1)
            self.assertEqual(result["skipped"], 1)

    async def test_batch_size_controls_api_call_grouping(self) -> None:
        """embed_texts is called with at most BATCH_SIZE texts per invocation."""
        call_sizes: list[int] = []

        async def tracking_embed(texts, _settings):
            call_sizes.append(len(texts))
            return [[0.1] * 8 for _ in texts]

        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp, 12)

            with patch.object(semantic_embeddings, "BATCH_SIZE", 5), \
                 patch.object(semantic_embeddings, "MAX_ITEMS_PER_CYCLE", 100), \
                 patch(
                     "curatorx.scheduler.tasks.semantic_embeddings.embed_texts",
                     new=AsyncMock(side_effect=tracking_embed),
                 ):
                await semantic_embeddings.run(
                    db, Settings(), should_stop=lambda: False
                )

            self.assertTrue(all(size <= 5 for size in call_sizes))
            self.assertEqual(sum(call_sizes), 12)


if __name__ == "__main__":
    unittest.main()
