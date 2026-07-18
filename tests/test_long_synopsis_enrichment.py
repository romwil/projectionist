"""Tests for optional long-synopsis idle enrichment."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.tasks import long_synopsis_enrichment


class LongSynopsisSkipTests(unittest.TestCase):
    def test_skips_when_source_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            result = asyncio.run(
                long_synopsis_enrichment.run(db, Settings(), should_stop=lambda: False)
            )
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_synopsis_source_configured")
            self.assertEqual(result["enriched"], 0)

    def test_skips_omdb_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            settings = Settings(long_synopsis_source="omdb", omdb_api_key="")
            result = asyncio.run(
                long_synopsis_enrichment.run(db, settings, should_stop=lambda: False)
            )
            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "no_omdb_api_key")


class LongSynopsisEnrichTests(unittest.TestCase):
    def test_writes_long_synopsis_without_touching_plex_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Example Film",
                    "year": 2001,
                    "summary": "Plex summary stays put.",
                    "tmdb_overview": "TMDB overview stays put.",
                }
            )
            settings = Settings(long_synopsis_source="wikipedia")

            with patch(
                "curatorx.scheduler.tasks.long_synopsis_enrichment.fetch_extract",
                return_value="A longer Wikipedia extract about the film.",
            ):
                result = asyncio.run(
                    long_synopsis_enrichment.run(db, settings, should_stop=lambda: False)
                )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 1)
            row = db.library_item_by_id(item_id)
            self.assertEqual(row["summary"], "Plex summary stays put.")
            self.assertEqual(row["tmdb_overview"], "TMDB overview stays put.")
            self.assertEqual(
                row["long_synopsis"], "A longer Wikipedia extract about the film."
            )
            self.assertEqual(row["synopsis_source"], "wikipedia")

    def test_does_not_overwrite_existing_synopsis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Kept Film",
                    "year": 1999,
                    "summary": "Short.",
                }
            )
            db.set_long_synopsis(item_id, "Existing long text.", "wikipedia")
            settings = Settings(long_synopsis_source="wikipedia")
            with patch(
                "curatorx.scheduler.tasks.long_synopsis_enrichment.fetch_extract",
                return_value="Should not replace.",
            ):
                result = asyncio.run(
                    long_synopsis_enrichment.run(db, settings, should_stop=lambda: False)
                )
            # Backlog excludes titles that already have a synopsis.
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 0)
            row = db.library_item_by_id(item_id)
            self.assertEqual(row["long_synopsis"], "Existing long text.")
            self.assertEqual(row["synopsis_source"], "wikipedia")


if __name__ == "__main__":
    unittest.main()
