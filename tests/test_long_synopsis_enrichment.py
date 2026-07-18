"""Tests for long-synopsis idle enrichment defaults and disable."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.config_store import Settings, load_merged_settings, save_settings
from curatorx.library.db import Database
from curatorx.scheduler.tasks import long_synopsis_enrichment


class LongSynopsisDefaultTests(unittest.TestCase):
    def test_settings_default_is_wikipedia(self) -> None:
        self.assertEqual(Settings().long_synopsis_source, "wikipedia")

    def test_missing_key_loads_as_wikipedia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "settings.json").write_text("{}", encoding="utf-8")
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.long_synopsis_source, "wikipedia")

    def test_explicit_empty_stays_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "settings.json").write_text(
                json.dumps({"long_synopsis_source": ""}),
                encoding="utf-8",
            )
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.long_synopsis_source, "")
            source, reason = long_synopsis_enrichment.resolve_synopsis_source(loaded)
            self.assertEqual(source, "")
            self.assertEqual(reason, "no_synopsis_source_configured")

    def test_off_disables_source(self) -> None:
        source, reason = long_synopsis_enrichment.resolve_synopsis_source(
            Settings(long_synopsis_source="off")
        )
        self.assertEqual(source, "")
        self.assertEqual(reason, "no_synopsis_source_configured")

    def test_default_settings_resolve_to_wikipedia(self) -> None:
        source, reason = long_synopsis_enrichment.resolve_synopsis_source(Settings())
        self.assertEqual(source, "wikipedia")
        self.assertIsNone(reason)


class LongSynopsisSkipTests(unittest.TestCase):
    def test_skips_when_source_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            result = asyncio.run(
                long_synopsis_enrichment.run(
                    db,
                    Settings(long_synopsis_source="off"),
                    should_stop=lambda: False,
                )
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

    def test_default_settings_run_wikipedia_without_explicit_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "3",
                    "media_type": "movie",
                    "title": "Default Source Film",
                    "year": 2010,
                    "summary": "Short.",
                }
            )
            with patch(
                "curatorx.scheduler.tasks.long_synopsis_enrichment.fetch_extract",
                return_value="Wikipedia default extract.",
            ):
                result = asyncio.run(
                    long_synopsis_enrichment.run(
                        db, Settings(), should_stop=lambda: False
                    )
                )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["enriched"], 1)
            self.assertEqual(result.get("source"), "wikipedia")

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

    def test_save_round_trip_preserves_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(long_synopsis_source="off"))
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.long_synopsis_source, "off")


if __name__ == "__main__":
    unittest.main()
