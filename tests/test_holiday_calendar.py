"""Phase B1 / B1b / B2 — holiday calendar store + seasonal rail curation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import feed_seasonal_spotlight, preview_holiday_rail
from projectionist.library.holidays import (
    active_grounding,
    grounding_date_for,
    movable_grounding,
    resolve_seasonal_context,
)


class HolidayCalendarTests(unittest.TestCase):
    def test_asymmetric_shoulders_and_grounding(self) -> None:
        christmas = {
            "id": "christmas",
            "name": "Christmas",
            "kind": "fixed",
            "month": 12,
            "day": 25,
            "pre_shoulder_days": 21,
            "post_shoulder_days": 4,
            "enabled": True,
            "search_terms": ["christmas"],
        }
        self.assertEqual(grounding_date_for(christmas, 2026), date(2026, 12, 25))
        # Long runway before, short after.
        self.assertEqual(active_grounding(christmas, date(2026, 12, 5)), date(2026, 12, 25))
        self.assertEqual(active_grounding(christmas, date(2026, 12, 28)), date(2026, 12, 25))
        self.assertIsNone(active_grounding(christmas, date(2026, 12, 31)))
        self.assertIsNone(active_grounding(christmas, date(2026, 11, 30)))

        halloween = {
            **christmas,
            "id": "halloween",
            "month": 10,
            "day": 31,
            "pre_shoulder_days": 12,
            "post_shoulder_days": 3,
        }
        self.assertEqual(active_grounding(halloween, date(2026, 10, 20)), date(2026, 10, 31))
        self.assertIsNone(active_grounding(halloween, date(2026, 10, 18)))

    def test_disabled_observance_never_drives_rail(self) -> None:
        obs = [
            {
                "id": "halloween",
                "name": "Halloween",
                "kind": "fixed",
                "month": 10,
                "day": 31,
                "pre_shoulder_days": 12,
                "post_shoulder_days": 3,
                "enabled": False,
                "search_terms": ["horror"],
                "schedule_publish": True,
            }
        ]
        ctx = resolve_seasonal_context(obs, date(2026, 10, 28))
        self.assertEqual(ctx.mode, "season")
        self.assertNotEqual(ctx.scope_id, "halloween")

    def test_movable_thanksgiving_seed_window(self) -> None:
        # 2026-11-26 is Thanksgiving.
        self.assertEqual(movable_grounding("thanksgiving", 2026), date(2026, 11, 26))
        arbor = movable_grounding("arbor_day", 2026)
        self.assertEqual(arbor, date(2026, 4, 24))

    def test_crud_restore_and_seasonal_feed_reads_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            items = db.list_holiday_observances()
            self.assertGreaterEqual(len(items), 12)
            christmas = db.get_holiday_observance("christmas")
            assert christmas is not None
            self.assertEqual(christmas["pre_shoulder_days"], 21)
            self.assertEqual(christmas["post_shoulder_days"], 4)

            db.update_holiday_observance(
                "christmas",
                {
                    **christmas,
                    "pre_shoulder_days": 28,
                    "post_shoulder_days": 2,
                    "search_terms": ["christmas", "yule", "festive"],
                },
            )
            updated = db.get_holiday_observance("christmas")
            assert updated is not None
            self.assertEqual(updated["pre_shoulder_days"], 28)
            self.assertIn("yule", updated["search_terms"])

            custom = db.create_holiday_observance(
                {
                    "name": "Cabin Week",
                    "kind": "fixed",
                    "month": 8,
                    "day": 12,
                    "pre_shoulder_days": 3,
                    "post_shoulder_days": 3,
                    "search_terms": ["cabin", "lake", "summer"],
                    "enabled": True,
                }
            )
            self.assertTrue(custom["id"])
            self.assertFalse(custom["is_builtin"])

            db.delete_holiday_observance("halloween")
            self.assertIsNone(db.get_holiday_observance("halloween"))
            restored = db.restore_holiday_defaults()
            self.assertGreaterEqual(restored["restored"], 12)
            self.assertIsNotNone(db.get_holiday_observance("halloween"))
            # Custom family day survives restore.
            self.assertIsNotNone(db.get_holiday_observance(custom["id"]))

            forest = db.upsert_library_item(
                {
                    "rating_key": "arbor",
                    "media_type": "movie",
                    "title": "The Forest",
                    "year": 2016,
                    "keywords": ["forest"],
                }
            )
            payload = feed_seasonal_spotlight(db, today=date(2026, 4, 24))
            self.assertEqual(payload["label"], "Arbor Day")
            self.assertEqual(payload["mode"], "holiday")
            self.assertEqual(payload["scope_id"], "arbor-day")
            self.assertEqual(payload["items"][0]["title"], "The Forest")
            self.assertEqual(payload["items"][0]["id"], forest)

    def test_rail_curation_pins_includes_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            matched = db.upsert_library_item(
                {
                    "rating_key": "horror1",
                    "media_type": "movie",
                    "title": "Haunted House",
                    "year": 2010,
                    "keywords": ["horror", "haunted"],
                }
            )
            bad = db.upsert_library_item(
                {
                    "rating_key": "horror2",
                    "media_type": "movie",
                    "title": "Monster Mash Musical",
                    "year": 2018,
                    "keywords": ["monster"],
                }
            )
            favorite = db.upsert_library_item(
                {
                    "rating_key": "fav",
                    "media_type": "movie",
                    "title": "Family Favorite",
                    "year": 1999,
                    "keywords": ["drama"],
                }
            )
            # Widen Halloween window to cover the test day via store defaults (Oct 31 ±).
            # Use preview which ignores active window.
            db.set_holiday_rail_title("halloween", bad, curation="exclude")
            db.set_holiday_rail_title("halloween", favorite, curation="include")
            db.set_holiday_rail_title("halloween", favorite, curation="pin")

            preview = preview_holiday_rail(db, "halloween", limit=12)
            ids = [int(item["id"]) for item in preview["items"]]
            self.assertEqual(ids[0], favorite)
            self.assertIn(matched, ids)
            self.assertNotIn(bad, ids)
            self.assertEqual(preview["items"][0].get("rail_role"), "pin")

            # Live feed path on Halloween day applies the same curation.
            live = feed_seasonal_spotlight(db, today=date(2026, 10, 31), prefer_snapshot=False)
            self.assertEqual(live["scope_id"], "halloween")
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertEqual(live_ids[0], favorite)
            self.assertNotIn(bad, live_ids)

    def test_seasonal_snapshot_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "xmas",
                    "media_type": "movie",
                    "title": "Christmas Story",
                    "year": 1983,
                    "keywords": ["christmas"],
                }
            )
            from projectionist.library.feeds import build_seasonal_rail_snapshot

            result = build_seasonal_rail_snapshot(db, today=date(2026, 12, 24), limit=6)
            self.assertEqual(result["status"], "completed")
            snap = db.get_seasonal_rail_snapshot("2026-12-24")
            assert snap is not None
            self.assertEqual(snap["scope_id"], "christmas")
            cached = feed_seasonal_spotlight(db, today=date(2026, 12, 24), prefer_snapshot=True)
            self.assertTrue(cached.get("from_schedule"))
            self.assertEqual(cached["scope_id"], "christmas")


if __name__ == "__main__":
    unittest.main()
