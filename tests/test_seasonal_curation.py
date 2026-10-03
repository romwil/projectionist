"""Agent seasonal shelf curation + curator notes on Explore feeds."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import feed_seasonal_spotlight, preview_holiday_rail
from projectionist.library.seasonal_curation import (
    apply_seasonal_shelf_proposal,
    enrich_picks,
    normalize_proposal_picks,
)


class SeasonalCurationTests(unittest.TestCase):
    def _seed_halloween_library(self, db: Database) -> dict[str, int]:
        known = db.upsert_library_item(
            {
                "rating_key": "hall1",
                "media_type": "movie",
                "title": "Classic Haunt",
                "year": 1978,
                "keywords": ["horror", "halloween"],
            }
        )
        gem = db.upsert_library_item(
            {
                "rating_key": "hall2",
                "media_type": "movie",
                "title": "Quiet Attic",
                "year": 2012,
                "keywords": ["horror", "haunted"],
            }
        )
        filler = db.upsert_library_item(
            {
                "rating_key": "hall3",
                "media_type": "movie",
                "title": "Zombie Dump",
                "year": 2024,
                "keywords": ["horror"],
            }
        )
        return {"known": known, "gem": gem, "filler": filler}

    def test_normalize_proposal_picks_filters_and_orders(self) -> None:
        picks = normalize_proposal_picks(
            [
                {"library_item_id": 2, "note": "  A gem.  "},
                {"id": 99, "note": "ignored"},
                {"library_item_id": 1, "curator_note": "Known doorway in."},
                {"library_item_id": 2, "note": "duplicate"},
            ],
            allowed_ids=[1, 2, 3],
            limit=10,
        )
        self.assertEqual(
            picks,
            [
                {"library_item_id": 2, "curator_note": "A gem."},
                {"library_item_id": 1, "curator_note": "Known doorway in."},
            ],
        )

    def test_apply_writes_notes_and_explore_feed_surfaces_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            result = apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "The doorway everyone expects — still the right opener.",
                    },
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "Quieter scare for the household that already knows the classics.",
                    },
                ],
            )
            self.assertEqual(result["applied"], 2)
            preview_ids = [int(item["id"]) for item in result["preview"]["items"]]
            self.assertEqual(preview_ids[:2], [ids["known"], ids["gem"]])
            self.assertEqual(
                result["preview"]["items"][0].get("curator_note"),
                "The doorway everyone expects — still the right opener.",
            )
            self.assertEqual(
                result["preview"]["items"][0].get("why"),
                "The doorway everyone expects — still the right opener.",
            )

            live = feed_seasonal_spotlight(
                db, today=date(2026, 10, 28), prefer_snapshot=False
            )
            self.assertEqual(live["scope_id"], "halloween")
            self.assertEqual(int(live["items"][0]["id"]), ids["known"])
            self.assertIn("doorway everyone expects", live["items"][0].get("why") or "")
            self.assertIn("Quieter scare", live["items"][1].get("curator_note") or "")

    def test_curated_pins_beat_uncurated_year_sort_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            # Without pins, newest matching title leads (year-sort dump).
            before = preview_holiday_rail(db, "halloween", limit=12)
            before_ids = [int(item["id"]) for item in before["items"]]
            self.assertEqual(before_ids[0], ids["filler"])

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {"library_item_id": ids["gem"], "curator_note": "Lead with the quiet one."},
                    {"library_item_id": ids["known"], "curator_note": "Then the classic."},
                ],
            )
            after = preview_holiday_rail(db, "halloween", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids[:2], [ids["gem"], ids["known"]])
            self.assertNotEqual(after_ids[0], ids["filler"])

    def test_enrich_picks_attaches_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            enriched = enrich_picks(
                db,
                [{"library_item_id": ids["known"], "curator_note": "Hello"}],
            )
            self.assertEqual(enriched[0]["title"], "Classic Haunt")
            self.assertEqual(enriched[0]["year"], 1978)
            self.assertEqual(enriched[0]["curator_note"], "Hello")

    def test_schema_migration_adds_curator_note_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                cols = {row["name"] for row in conn.execute("PRAGMA table_info(holiday_rail_titles)")}
            self.assertIn("curator_note", cols)


if __name__ == "__main__":
    unittest.main()
