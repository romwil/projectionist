"""Value-based tests for Wave 2: layered embeddings, neighbors, motifs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.embeddings import build_item_embedding_text, embedding_model_label
from curatorx.library.facets import library_facet_catalog, rebuild_library_facets
from curatorx.library.neighbors import compute_neighbors_for_seed, surprise_score
from curatorx.library.query import LibraryFilters, query_library
from curatorx.library.sync import _apply_tmdb_enrichment
from curatorx.scheduler.tasks import llm_logline_enrichment, plot_neighbors, summary_motifs


class PlotTextMigrationTests(unittest.TestCase):
    def test_plot_columns_and_neighbors_table_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(library_items)")}
                self.assertTrue({"tmdb_overview", "tagline", "llm_logline"}.issubset(cols))
                emb_cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(embeddings)")}
                self.assertIn("embedding_model", emb_cols)
                tables = {
                    str(r["name"])
                    for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                self.assertIn("item_neighbors", tables)


class LayeredEmbeddingTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_item_embedding_text_includes_overview_and_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-br",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "summary": "A blade runner hunts replicants.",
                    "tmdb_overview": "In a dystopian future, Deckard hunts synthetic humans.",
                    "tagline": "Man has made his match... now it's his problem.",
                    "llm_logline": "A weary hunter confronts what it means to be human.",
                    "genres": ["Sci-Fi", "Thriller"],
                    "keywords": ["dystopia", "android"],
                }
            )
            row = db.library_item_by_id(item_id)
            assert row is not None
            text = await build_item_embedding_text(row)
            self.assertIn("PLOT:", text)
            self.assertIn("METADATA:", text)
            self.assertIn("In a dystopian future, Deckard hunts synthetic humans.", text)
            self.assertIn("Man has made his match", text)
            self.assertIn("A weary hunter confronts what it means to be human.", text)
            self.assertIn("Blade Runner", text)
            self.assertIn("Sci-Fi", text)

    def test_tmdb_enrichment_populates_overview_and_tagline(self) -> None:
        row = {
            "rating_key": "rk-1",
            "media_type": "movie",
            "title": "Blade Runner",
            "genres": [],
            "cast": [],
            "directors": [],
            "keywords": [],
        }
        _apply_tmdb_enrichment(
            row,
            {
                "overview": "Deckard hunts replicants in Los Angeles.",
                "tagline": "More human than human.",
                "release_date": "1982-06-25",
                "vote_average": 8.1,
                "production_companies": [],
                "keywords": {"keywords": []},
                "credits": {"cast": [], "crew": []},
            },
            media_type="movie",
        )
        self.assertEqual(row["tmdb_overview"], "Deckard hunts replicants in Los Angeles.")
        self.assertEqual(row["tagline"], "More human than human.")
        self.assertEqual(row["release_date"], "1982-06-25")

    def test_embedding_model_label(self) -> None:
        self.assertEqual(embedding_model_label(Settings()), "hash-fallback")
        self.assertEqual(
            embedding_model_label(Settings(llm_api_key="sk-test", llm_embedding_model="text-embedding-3-large")),
            "text-embedding-3-large",
        )


class NeighborSurpriseTests(unittest.TestCase):
    def test_surprise_prefers_high_cosine_low_overlap(self) -> None:
        # Same cosine: lower genre overlap → higher surprise.
        high = surprise_score(0.9, 0.1)
        low = surprise_score(0.9, 0.8)
        self.assertGreater(high, low)

    def test_neighbors_surprise_ranking_differs_from_cosine(self) -> None:
        seed_tokens = {"sci-fi", "dystopia", "person:1"}
        candidates = [
            # Near-clone metadata: high cosine, low surprise
            (2, [1.0, 0.0, 0.0], {"sci-fi", "dystopia", "person:1"}),
            # Distant metadata, still high cosine: surprising
            (3, [0.95, 0.1, 0.0], {"romance", "musical"}),
            # Medium cosine, medium overlap
            (4, [0.7, 0.3, 0.0], {"sci-fi", "romance"}),
        ]
        neighbors = compute_neighbors_for_seed(
            1,
            [1.0, 0.0, 0.0],
            seed_tokens,
            candidates,
            top_k=3,
        )
        by_id = {nid: (score, surprise) for nid, score, surprise in neighbors}
        self.assertIn(2, by_id)
        self.assertIn(3, by_id)
        # Cosine ranking: 2 > 3
        self.assertGreater(by_id[2][0], by_id[3][0])
        # Surprise ranking flips: 3 beats near-clone 2
        self.assertGreater(by_id[3][1], by_id[2][1])

    def test_set_and_get_neighbors_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = db.upsert_library_item(
                {
                    "rating_key": "seed",
                    "media_type": "movie",
                    "title": "Seed",
                    "year": 2000,
                    "genres": ["Sci-Fi"],
                }
            )
            twin = db.upsert_library_item(
                {
                    "rating_key": "twin",
                    "media_type": "movie",
                    "title": "Twin",
                    "year": 2001,
                    "genres": ["Sci-Fi"],
                }
            )
            odd = db.upsert_library_item(
                {
                    "rating_key": "odd",
                    "media_type": "movie",
                    "title": "Oddball",
                    "year": 2002,
                    "genres": ["Romance"],
                }
            )
            db.set_neighbors(
                seed,
                [
                    (twin, 0.99, 0.10),
                    (odd, 0.90, 0.85),
                ],
            )
            similar = db.get_neighbors(seed, mode="similar", limit=5)
            surprising = db.get_neighbors(seed, mode="surprising", limit=5)
            self.assertEqual(int(similar[0]["neighbor_id"]), twin)
            self.assertEqual(int(surprising[0]["neighbor_id"]), odd)


class MotifFacetTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_motifs_write_motif_facets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            # Shared uncommon tokens across multiple docs (not hapax, not ubiquitous).
            plots = [
                ("rk-a", "A neon detective hunts replicants through rainy alleys."),
                ("rk-b", "The neon city hides replicants among the alleys."),
                ("rk-c", "Rainy alleys conceal a detective chasing shadows."),
                ("rk-d", "An ordinary farm story about cows and barns."),
            ]
            for key, summary in plots:
                db.upsert_library_item(
                    {
                        "rating_key": key,
                        "media_type": "movie",
                        "title": key,
                        "year": 1980,
                        "summary": summary,
                        "genres": ["Drama"],
                    }
                )

            result = await summary_motifs.run(db, Settings(), should_stop=lambda: False)
            self.assertEqual(result["status"], "completed")
            self.assertGreater(result["motifs"], 0)

            catalog = library_facet_catalog(db, "motif", limit=50)
            values = {entry["value"] for entry in catalog["facets"]}
            self.assertTrue(
                {"neon", "replicant", "replicants", "alleys", "detective"} & values,
                f"expected motif tokens in {values}",
            )

            # Motifs survive a sync-style facet rebuild.
            rebuild_library_facets(db)
            catalog_after = library_facet_catalog(db, "motif", limit=50)
            self.assertGreater(len(catalog_after["facets"]), 0)

            # query_library can filter by motif.
            motif = next(iter(catalog_after["facets"]))["value"]
            filtered = query_library(db, LibraryFilters(motifs=[motif]))
            self.assertGreater(filtered["returned"], 0)


class PlotNeighborsTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_plot_neighbors_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = []
            for index in range(4):
                item_id = db.upsert_library_item(
                    {
                        "rating_key": f"rk-{index}",
                        "media_type": "movie",
                        "title": f"Title {index}",
                        "year": 1990 + index,
                        "summary": f"Plot about theme {index % 2}",
                        "genres": ["Sci-Fi"] if index < 2 else ["Romance"],
                        "keywords": ["neon"] if index < 2 else ["wedding"],
                    }
                )
                ids.append(item_id)
                # Simple orthogonal-ish vectors with some overlap.
                vector = [0.0] * 4
                vector[index % 2] = 1.0
                vector[(index + 1) % 4] = 0.2
                db.set_embeddings([(item_id, vector, f"hash-{index}")], embedding_model="hash-fallback")

            result = await plot_neighbors.run(db, Settings(), should_stop=lambda: False)
            self.assertEqual(result["status"], "completed")
            self.assertGreater(result["processed"], 0)
            neighbors = db.get_neighbors(ids[0], mode="similar", limit=5)
            self.assertGreater(len(neighbors), 0)


class LlmLoglineTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_without_llm_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "summary": "A blade runner hunts replicants.",
                }
            )
            result = await llm_logline_enrichment.run(db, Settings(), should_stop=lambda: False)
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_llm_api_key")

    async def test_enriches_when_llm_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-1",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "summary": "A blade runner hunts replicants.",
                    "tmdb_overview": "Deckard is forced to hunt four replicants.",
                }
            )
            fake_provider = AsyncMock()
            fake_provider.chat = AsyncMock(
                return_value={"choices": [{"message": {"content": "A hunter questions his humanity."}}]}
            )
            with patch(
                "curatorx.agent.providers.get_chat_provider",
                return_value=fake_provider,
            ):
                result = await llm_logline_enrichment.run(
                    db,
                    Settings(llm_api_key="sk-test", llm_provider="openai"),
                    should_stop=lambda: False,
                )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 1)
            row = db.library_item_by_id(item_id)
            assert row is not None
            self.assertEqual(row["llm_logline"], "A hunter questions his humanity.")


if __name__ == "__main__":
    unittest.main()
