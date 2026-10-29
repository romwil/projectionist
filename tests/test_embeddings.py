"""Tests for library embedding rebuild progress and batching."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.embeddings import (
    embed_texts,
    embedding_model_label,
    rebuild_embeddings,
    remote_embedding_provider_available,
    semantic_search,
)
from projectionist.library.query import filters_from_mapping, query_library_async
from projectionist.models.recommendation import sanitize_recommendation_reason


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
        self.assertEqual(sanitize_recommendation_reason("Double feature — first half"), "")
        self.assertEqual(sanitize_recommendation_reason("Double feature — second half"), "")
        self.assertEqual(sanitize_recommendation_reason("Unwatched pick for you"), "")
        self.assertEqual(sanitize_recommendation_reason("Good pick for tonight"), "")
        self.assertEqual(sanitize_recommendation_reason(""), "")


class RebuildEmbeddingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_anthropic_without_embedding_endpoint_uses_hash_without_request(self) -> None:
        settings = Settings(
            llm_provider="anthropic",
            llm_api_key="not-a-real-secret",
            llm_base_url="https://api.anthropic.com",
        )

        with patch("projectionist.agent.providers.get_embedding_provider") as get_provider:
            vectors = await embed_texts(["A pilgrimage through grief."], settings)

        self.assertFalse(remote_embedding_provider_available(settings))
        self.assertEqual(embedding_model_label(settings), "hash-fallback")
        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(vectors[0]), 384)
        get_provider.assert_not_called()

    async def test_semantic_query_reports_missing_embedding_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "harold",
                    "media_type": "movie",
                    "title": "The Unlikely Pilgrimage of Harold Fry",
                    "summary": "A man walks across England to visit a dying friend.",
                }
            )
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="not-a-real-secret",
                llm_base_url="https://api.anthropic.com",
            )

            result = await query_library_async(
                db,
                filters_from_mapping({"semantic_query": "a walking pilgrimage", "limit": 5}),
                settings,
            )

            self.assertEqual(result["search_mode"], "semantic_unavailable")
            self.assertEqual(result["items"], [])
            self.assertIn("llm_embedding_base_url", result["error"])

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
                "projectionist.library.embeddings.embed_texts",
                new=AsyncMock(side_effect=lambda texts, settings, **_kw: [[0.1] * 8 for _ in texts]),
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

    async def test_rebuild_embeddings_skips_unchanged_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for index in range(4):
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

            embed_calls: list[int] = []

            async def tracking_embed(texts, settings, **_kw):
                embed_calls.append(len(texts))
                return [[0.1] * 8 for _ in texts]

            with patch(
                "projectionist.library.embeddings.embed_texts",
                new=AsyncMock(side_effect=tracking_embed),
            ):
                first = await rebuild_embeddings(db, Settings(), batch_size=2)
                self.assertEqual(first, 4)
                self.assertEqual(sum(embed_calls), 4)
                self.assertEqual(len(db.embedding_content_hashes()), 4)

                embed_calls.clear()
                second = await rebuild_embeddings(db, Settings(), batch_size=2)
                self.assertEqual(second, 4)
                self.assertEqual(sum(embed_calls), 0)

                # Change one title so only that item re-embeds.
                item = db.all_library_items()[0]
                db.upsert_library_item(
                    {
                        "rating_key": item["rating_key"],
                        "media_type": item["media_type"],
                        "title": "Changed Title",
                        "year": item["year"],
                        "summary": item["summary"],
                        "genres": ["Sci-Fi"],
                    }
                )
                third = await rebuild_embeddings(db, Settings(), batch_size=2)
                self.assertEqual(third, 4)
                self.assertEqual(sum(embed_calls), 1)


class EmbeddingIdLookupTests(unittest.TestCase):
    """Id-only callers must not full-table ``json.loads`` the TEXT vectors."""

    def test_embedding_item_ids_does_not_json_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = []
            for index in range(3):
                item_id = db.upsert_library_item(
                    {
                        "rating_key": f"rk-{index}",
                        "media_type": "movie",
                        "title": f"Title {index}",
                        "year": 1980 + index,
                        "summary": "A film.",
                    }
                )
                ids.append(item_id)
            db.set_embeddings([(item_id, [0.1, 0.2, 0.3]) for item_id in ids])

            with patch(
                "projectionist.library.db._library_lookup.json.loads",
                side_effect=AssertionError("decoded every vector"),
            ):
                got = db.embedding_item_ids()
            self.assertEqual(got, sorted(ids))

    def test_get_embeddings_still_decodes_json_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-0",
                    "media_type": "movie",
                    "title": "Title 0",
                    "year": 1980,
                    "summary": "A film.",
                }
            )
            vector = [0.25, 0.5, 0.75]
            db.set_embeddings([(item_id, vector)])
            got = db.get_embeddings()
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0][0], item_id)
            for stored, original in zip(got[0][1], vector):
                self.assertAlmostEqual(stored, original, places=10)
            # Storage is still JSON TEXT — not BLOBs.
            with db.connect() as conn:
                raw = conn.execute(
                    "SELECT vector FROM embeddings WHERE item_id = ?", (item_id,)
                ).fetchone()
            self.assertIsInstance(raw["vector"], str)
            self.assertEqual(json.loads(raw["vector"]), vector)

    def test_semantic_search_reads_json_text_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            a = db.upsert_library_item(
                {"rating_key": "a", "media_type": "movie", "title": "Alpha", "year": 2000}
            )
            b = db.upsert_library_item(
                {"rating_key": "b", "media_type": "movie", "title": "Beta", "year": 2001}
            )
            db.set_embeddings([(a, [1.0, 0.0, 0.0]), (b, [0.0, 1.0, 0.0])])
            hits = semantic_search(db, [1.0, 0.0, 0.0], limit=5)
            self.assertEqual(hits[0][0], a)


if __name__ == "__main__":
    unittest.main()
