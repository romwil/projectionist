"""v1.36.7 house letter, seasonal veto, gift queue, and trust diary."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from projectionist.config_store import Settings
from projectionist.house.gifts import (
    deliver_due_gifts,
    deliver_gift,
    enqueue_gift,
    list_gifts,
    remove_gift,
)
from projectionist.house.letter import compose_house_letter, format_bytes, format_hours
from projectionist.house.seasonal import (
    preview_upcoming_rails,
    restore_rail_title,
    veto_rail_title,
)
from projectionist.house.trust_diary import collect_trust_diary
from projectionist.library.db import Database
from projectionist.library.health import STALE_ADD_DAYS
from projectionist.library.rematch import persist_skipped_ids


def _db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


class HouseLetterTests(unittest.TestCase):
    def test_empty_library_is_a_letter_not_tiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            letter = compose_house_letter(_db(tmp), now=1_700_000_000)
        self.assertEqual(letter["title"], "A letter about the house")
        self.assertEqual(letter["salutation"], "Dear owner,")
        kinds = [row["kind"] for row in letter["paragraphs"]]
        self.assertEqual(kinds, ["empty"])
        self.assertIn("no library index", letter["body"].lower())
        self.assertNotIn("tile", letter["body"].lower())

    def test_letter_names_hours_dead_weight_and_disk(self) -> None:
        now = 1_800_000_000.0
        stale = now - (STALE_ADD_DAYS + 5) * 86400
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.upsert_library_item(
                {
                    "rating_key": "rk-unwatched",
                    "media_type": "movie",
                    "title": "Lawrence of Arabia",
                    "year": 1962,
                    "view_count": 0,
                    "duration_ms": 12 * 3_600_000,
                    "file_size": 40 * 1024**3,
                    "added_at": stale,
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "rk-watched",
                    "media_type": "movie",
                    "title": "Arrival",
                    "year": 2016,
                    "view_count": 2,
                    "duration_ms": 2 * 3_600_000,
                    "file_size": 8 * 1024**3,
                    "added_at": now,
                }
            )
            letter = compose_house_letter(db, now=now)

        stats = letter["stats"]
        self.assertEqual(stats["unwatched_count"], 1)
        self.assertEqual(stats["unwatched_hours_label"], "12 hours")
        self.assertEqual(stats["dead_weight_count"], 1)
        self.assertIn("Lawrence of Arabia", stats["dead_weight"][0]["label"])
        kinds = [row["kind"] for row in letter["paragraphs"]]
        self.assertEqual(kinds, ["hours", "dead_weight", "disk", "close"])
        body = letter["body"]
        self.assertIn("12 hours", body)
        self.assertIn("Lawrence of Arabia", body)
        self.assertIn("I will not send a fleet", body)
        self.assertIn("disks hold", body.lower())

    def test_format_hours_and_bytes(self) -> None:
        self.assertEqual(format_hours(0), "no timed hours")
        self.assertEqual(format_hours(30 * 60 * 1000), "less than an hour")
        self.assertEqual(format_hours(12 * 3_600_000), "12 hours")
        self.assertEqual(format_bytes(0), "an unknown amount of disk")
        self.assertEqual(format_bytes(40 * 1024**3), "40 GB")


class HouseGiftQueueTests(unittest.TestCase):
    def test_enqueue_is_not_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.create_local_user(
                user_id="member-1",
                display_name="Ada",
                password_hash="x",
                role="member",
            )
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-gift",
                    "media_type": "movie",
                    "title": "After Hours",
                    "year": 1985,
                    "view_count": 0,
                }
            )
            gift = enqueue_gift(
                db,
                user_id="member-1",
                library_item_id=item_id,
                why="Because she asked for a quiet night not a franchise.",
            )
            queued = list_gifts(db)
            self.assertEqual(queued["pending_count"], 1)
            self.assertIsNone(gift["delivered_at"])
            self.assertTrue(gift["id"].startswith("gift_"))
            self.assertIn("quiet night", gift["why"])

            removed = remove_gift(db, gift["id"])
            self.assertTrue(removed)
            self.assertEqual(list_gifts(db)["pending_count"], 0)

    def test_deliver_due_skips_future_and_sends_due(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.create_local_user(
                user_id="member-1",
                display_name="Ada",
                password_hash="x",
                role="member",
            )
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-gift-2",
                    "media_type": "movie",
                    "title": "The Apartment",
                    "year": 1960,
                }
            )
            due = enqueue_gift(
                db,
                user_id="member-1",
                library_item_id=item_id,
                why="A gift.",
                scheduled_for=10.0,
            )
            later = enqueue_gift(
                db,
                user_id="member-1",
                library_item_id=item_id,
                why="Later.",
                scheduled_for=9_999_999_999.0,
            )
            result = deliver_due_gifts(db, Settings(), now=100.0)
            self.assertEqual(result["delivered"], 1)
            self.assertEqual(result["skipped_future"], 1)
            again = deliver_gift(db, Settings(), due["id"], now=200.0)
            self.assertTrue(again["already_delivered"])
            still = list_gifts(db)
            delivered_ids = {row["id"] for row in still["delivered"]}
            pending_ids = {row["id"] for row in still["pending"]}
            self.assertIn(due["id"], delivered_ids)
            self.assertIn(later["id"], pending_ids)


class HouseSeasonalPreviewTests(unittest.TestCase):
    def test_preview_and_veto_reuse_holiday_rail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.ensure_holiday_defaults()
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-xmas",
                    "media_type": "movie",
                    "title": "A Christmas Story",
                    "year": 1983,
                    "summary": "christmas holiday",
                    "genres": ["holiday", "christmas"],
                    "view_count": 0,
                }
            )
            preview = preview_upcoming_rails(
                db, horizon_days=30, today=date(2026, 12, 10)
            )
            rails = {row["scope_id"]: row for row in preview["rails"]}
            self.assertIn("christmas", rails)
            christmas = rails["christmas"]
            titles = [str(item.get("title") or "") for item in christmas["items"]]
            self.assertTrue(any("Christmas" in title for title in titles))

            veto = veto_rail_title(db, "christmas", item_id)
            self.assertEqual(veto["curation"], "exclude")
            self.assertIn(item_id, veto["vetoed_ids"])
            restored = restore_rail_title(db, "christmas", item_id)
            self.assertTrue(restored["ok"])
            self.assertNotIn(item_id, restored["vetoed_ids"])


class HouseTrustDiaryTests(unittest.TestCase):
    def test_diary_links_rematch_and_job_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk-skip",
                    "media_type": "movie",
                    "title": "Presence",
                    "year": 2025,
                }
            )
            persist_skipped_ids(db, [item_id])
            diary = collect_trust_diary(
                db,
                jobs=[
                    {
                        "id": "job-1",
                        "name": "Investigate The Night Of",
                        "status": "running",
                        "message": "Comparing stills.",
                        "started_at": 50,
                    }
                ],
                now=100,
            )
        kinds = {row["kind"] for row in diary["entries"]}
        self.assertIn("rematch", kinds)
        self.assertIn("job", kinds)
        rematch = next(row for row in diary["entries"] if row["kind"] == "rematch")
        self.assertEqual(rematch["href"], "/admin/libraries")
        job = next(row for row in diary["entries"] if row["kind"] == "job")
        self.assertEqual(job["href"], "/admin/tasks")
        self.assertIn("stills", job["why"])


class HouseSchedulerTaskTests(unittest.TestCase):
    def test_gift_queue_task_registers_weekly(self) -> None:
        from projectionist.scheduler.engine import IdleScheduler
        from projectionist.scheduler.tasks import gift_queue, register_all

        self.assertEqual(gift_queue.INTERVAL_SECONDS, 7 * 86400)
        self.assertTrue(callable(gift_queue.register))
        self.assertTrue(callable(gift_queue.run))
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            scheduler = IdleScheduler(db, Path(tmp))
            register_all(scheduler)
            self.assertIn("gift_queue", scheduler._definitions)
            self.assertEqual(
                scheduler._definitions["gift_queue"].run_interval_seconds,
                7 * 86400,
            )


class HouseRoutesExportTests(unittest.TestCase):
    def test_router_exposes_owner_paths(self) -> None:
        from projectionist.web.house_routes import register_house_routes, router

        self.assertTrue(callable(register_house_routes))
        paths = {getattr(route, "path", None) for route in router.routes}
        self.assertIn("/api/admin/house/letter", paths)
        self.assertIn("/api/admin/house/seasonal-preview", paths)
        self.assertIn("/api/admin/house/gifts", paths)
        self.assertIn("/api/admin/house/trust-diary", paths)
