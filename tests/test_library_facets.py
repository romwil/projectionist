"""Tests for library facet index."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.library.db import Database
from curatorx.library.facets import library_facet_catalog, rebuild_library_facets, rebuild_library_fts
from curatorx.library.query import LibraryFilters, query_library


class LibraryFacetTests(unittest.TestCase):
    def test_rebuild_and_filter_by_director(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "nolan-1",
                    "media_type": "movie",
                    "title": "Inception",
                    "year": 2010,
                    "genres": ["Sci-Fi"],
                    "directors": ["Christopher Nolan"],
                    "cast": ["Leonardo DiCaprio"],
                    "keywords": ["dream"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "other-1",
                    "media_type": "movie",
                    "title": "Jaws",
                    "year": 1975,
                    "genres": ["Thriller"],
                    "directors": ["Steven Spielberg"],
                }
            )
            count = rebuild_library_facets(db)
            self.assertGreaterEqual(count, 3)

            catalog = library_facet_catalog(db, "director", limit=10)
            self.assertEqual(catalog["facet_type"], "director")
            values = {entry["value"] for entry in catalog["facets"]}
            self.assertIn("Christopher Nolan", values)

            result = query_library(db, LibraryFilters(directors=["Nolan"], media_type="movie"))
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "Inception")

    def test_country_and_language_catalog_from_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "intl",
                    "media_type": "movie",
                    "title": "Amelie",
                    "countries": ["France"],
                    "original_language": "fr",
                }
            )
            country_catalog = library_facet_catalog(db, "country", limit=10)
            language_catalog = library_facet_catalog(db, "language", limit=10)
            self.assertEqual(country_catalog["facets"][0]["value"], "France")
            self.assertEqual(language_catalog["facets"][0]["value"], "fr")

    def test_ensure_library_facet_index_backfills_country_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "intl",
                    "media_type": "movie",
                    "title": "Amelie",
                    "countries": ["France"],
                    "original_language": "fr",
                }
            )
            from curatorx.library.facets import ensure_library_facet_index

            rebuilt = ensure_library_facet_index(db)
            self.assertGreater(rebuilt, 0)
            catalog = library_facet_catalog(db, "country", limit=10)
            self.assertEqual(catalog["facets"][0]["value"], "France")

    def test_rebuild_batches_commits_emits_progress_and_is_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(120):
                db.upsert_library_item(
                    {
                        "rating_key": f"rk-{i}",
                        "media_type": "movie",
                        "title": f"Title {i}",
                        "year": 2000 + (i % 20),
                        "directors": [f"Director {i % 10}", f"Co-Director {i % 7}"],
                        "cast": [f"Actor {j}" for j in range(12)],
                        "keywords": [f"kw-{j}" for j in range(8)],
                        "countries": ["USA", "Canada"],
                        "original_language": "en",
                    }
                )

            replace_calls: list[int] = []
            real_replace = db.replace_library_facets

            def tracking_replace(rows):
                replace_calls.append(len(rows))
                return real_replace(rows)

            progress_events: list[tuple[str, int, int, str]] = []

            def on_progress(phase: str, current: int, total: int, message: str) -> None:
                progress_events.append((phase, current, total, message))

            db.replace_library_facets = tracking_replace  # type: ignore[method-assign]
            started = time.perf_counter()
            with patch.object(db, "add_library_facet") as mock_add, patch.object(
                db, "clear_library_facets"
            ) as mock_clear:
                count = rebuild_library_facets(db, progress=on_progress)
            elapsed = time.perf_counter() - started

            self.assertGreater(count, 1000)
            self.assertEqual(len(replace_calls), 1)
            self.assertEqual(replace_calls[0], count)
            mock_add.assert_not_called()
            mock_clear.assert_not_called()
            self.assertLess(elapsed, 2.0)
            self.assertTrue(progress_events)
            self.assertTrue(all(phase == "indexing" for phase, *_ in progress_events))
            self.assertTrue(any("Building search facets" in msg for *_, msg in progress_events))
            self.assertTrue(any("rows" in msg for *_, msg in progress_events))

            with db.connect() as conn:
                stored = conn.execute("SELECT COUNT(*) AS cnt FROM library_facets").fetchone()["cnt"]
            self.assertEqual(stored, count)

            catalog = library_facet_catalog(db, "director", limit=5)
            self.assertGreaterEqual(catalog["returned"], 1)

    def test_rebuild_fts_batches_and_emits_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for i in range(40):
                db.upsert_library_item(
                    {
                        "rating_key": f"fts-{i}",
                        "media_type": "movie",
                        "title": f"FTS Title {i}",
                        "summary": f"Summary {i}",
                        "cast": [f"Actor {i}"],
                        "directors": [f"Director {i}"],
                        "keywords": [f"kw-{i}"],
                    }
                )

            replace_calls: list[int] = []
            real_replace = db.replace_library_fts

            def tracking_replace(rows):
                replace_calls.append(len(rows))
                return real_replace(rows)

            progress_events: list[str] = []
            db.replace_library_fts = tracking_replace  # type: ignore[method-assign]
            count = rebuild_library_fts(
                db,
                progress=lambda _phase, _c, _t, message: progress_events.append(message),
            )
            self.assertEqual(count, 40)
            self.assertEqual(replace_calls, [40])
            self.assertTrue(any("Building search index" in msg for msg in progress_events))


if __name__ == "__main__":
    unittest.main()
