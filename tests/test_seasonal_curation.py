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

    def _seed_muertos_library(self, db: Database) -> dict[str, int]:
        known = db.upsert_library_item(
            {
                "rating_key": "muertos1",
                "media_type": "movie",
                "title": "Familiar Altar",
                "year": 2017,
                "keywords": ["family", "mexico"],
            }
        )
        gem = db.upsert_library_item(
            {
                "rating_key": "muertos2",
                "media_type": "movie",
                "title": "Quiet Ofrenda",
                "year": 1999,
                "keywords": ["afterlife", "spirit"],
            }
        )
        dump = db.upsert_library_item(
            {
                "rating_key": "muertos3",
                "media_type": "movie",
                "title": "Family Reunion Dump",
                "year": 2024,
                "keywords": ["family"],
            }
        )
        return {"known": known, "gem": gem, "dump": dump}

    def test_apply_replaces_existing_pins_and_keyword_dump(self) -> None:
        """A confirmed curate replaces the shelf. Old pins and the year-sort tail must go."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            db.set_holiday_rail_title(
                "halloween",
                ids["filler"],
                curation="pin",
                pin_position=0,
                curator_note="Last year's leftover.",
            )
            # One veto must not be required for curate, and must not be the only change.
            db.set_holiday_rail_title("halloween", ids["known"], curation="exclude")

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "The quieter scare that belongs on the shelf this year.",
                    },
                ],
            )
            after = preview_holiday_rail(db, "halloween", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids, [ids["gem"]])
            self.assertNotIn(ids["filler"], after_ids)
            self.assertNotIn(ids["known"], after_ids)
            self.assertEqual(
                after["items"][0].get("curator_note"),
                "The quieter scare that belongs on the shelf this year.",
            )
            self.assertTrue(after.get("replaces_matches"))

    def test_apply_replaces_dia_de_los_muertos_the_same_way(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_muertos_library(db)
            before = preview_holiday_rail(db, "dia-de-los-muertos", limit=12)
            before_ids = [int(item["id"]) for item in before["items"]]
            self.assertEqual(before_ids[0], ids["dump"])

            apply_seasonal_shelf_proposal(
                db,
                "dia-de-los-muertos",
                [
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "The doorway everyone already knows for this night.",
                    },
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "A quieter ofrenda for the household that wants the smaller film.",
                    },
                ],
            )
            after = preview_holiday_rail(db, "dia-de-los-muertos", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids, [ids["known"], ids["gem"]])
            self.assertNotIn(ids["dump"], after_ids)
            self.assertIn("doorway everyone already knows", after["items"][0].get("why") or "")

            live = feed_seasonal_spotlight(
                db, today=date(2026, 11, 2), prefer_snapshot=False
            )
            self.assertEqual(live["scope_id"], "dia-de-los-muertos")
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertEqual(live_ids, [ids["known"], ids["gem"]])
            self.assertNotIn(ids["dump"], live_ids)

    def test_curated_shelf_replaces_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            from projectionist.library.feeds import build_seasonal_rail_snapshot

            built = build_seasonal_rail_snapshot(db, today=date(2026, 10, 31), limit=12)
            self.assertEqual(built["status"], "completed")
            stale_ids = [int(item["id"]) for item in built["payload"]["items"]]
            self.assertIn(ids["filler"], stale_ids)

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "Lead with the quiet one this year.",
                    },
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "Then the classic doorway.",
                    },
                ],
            )
            live = feed_seasonal_spotlight(
                db, today=date(2026, 10, 31), prefer_snapshot=True
            )
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertEqual(live_ids, [ids["gem"], ids["known"]])
            self.assertFalse(live.get("from_schedule"))
            self.assertNotIn(ids["filler"], live_ids)

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
