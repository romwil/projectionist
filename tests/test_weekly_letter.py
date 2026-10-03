"""Weekly household letter: composition, inbox delivery, optional email, owner API."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import MailSettings, Settings
from projectionist.library.admin_execution import reset_admin_execution_for_tests
from projectionist.library.db import Database
from projectionist.library.health import STALE_ADD_DAYS
from projectionist.notifications.weekly_letter import (
    compose_weekly_letter,
    deliver_weekly_letter,
    format_bytes,
    format_hours,
    load_letter_settings,
    save_letter_settings,
    week_bucket,
)


def _db(tmp: str) -> Database:
    return Database(Path(tmp) / "test.db")


class HouseLetterTests(unittest.TestCase):
    def test_empty_library_is_a_letter_not_tiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            letter = compose_weekly_letter(_db(tmp), now=1_700_000_000)
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
            letter = compose_weekly_letter(db, now=now)

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

    def test_closing_paragraph_names_no_removed_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.upsert_library_item({"rating_key": "k", "media_type": "movie", "title": "T"})
            text = compose_weekly_letter(db)["body"].lower()
        self.assertNotIn("gift queue", text)
        self.assertNotIn("seasonal preview", text)


def _mail_settings() -> Settings:
    return Settings(
        mail=MailSettings(
            enabled=True, provider="smtp", from_email="house@example.com", smtp_host="smtp.example.com"
        )
    )


def _seed(db: Database, *, email: str | None = "owner@example.com") -> str:
    with db.connect() as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = 'bootstrap-owner'", (email,))
    db.upsert_library_item(
        {"rating_key": "rk-a", "media_type": "movie", "title": "Heat", "year": 1995, "view_count": 0}
    )
    return "bootstrap-owner"


class WeeklyLetterDeliveryTests(unittest.TestCase):
    def test_defaults_weekly_on_email_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = load_letter_settings(_db(tmp))
        self.assertTrue(state["weekly"])
        self.assertFalse(state["email"])

    def test_lands_in_owner_inbox_once_per_week_without_mail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            owner = _seed(db)
            with patch("projectionist.mail.send_mail") as send:
                first = deliver_weekly_letter(db, Settings(), now=1_800_000_000.0)
                second = deliver_weekly_letter(db, Settings(), now=1_800_000_000.0 + 3600)
                next_week = deliver_weekly_letter(db, Settings(), now=1_800_000_000.0 + 8 * 86400)
            self.assertEqual(first["delivered"], 1)
            self.assertEqual(first["emailed"], 0)
            self.assertEqual(second["skipped"], "already_sent")
            self.assertEqual(next_week["delivered"], 1)
            send.assert_not_called()
            rows = db.list_notifications_for_user(owner)
            rows = rows["items"] if isinstance(rows, dict) else rows
            letters = [r for r in rows if (r.get("payload") or {}).get("newsletter") == "house-letter"]
            self.assertEqual(len(letters), 2)
            self.assertEqual(letters[0]["kind"], "digest")
            self.assertIn("Dear owner,", letters[0]["body"])

    def test_weekly_off_skips_but_send_now_still_delivers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            _seed(db)
            save_letter_settings(db, weekly=False)
            self.assertEqual(deliver_weekly_letter(db, Settings())["skipped"], "weekly_off")
            self.assertEqual(deliver_weekly_letter(db, Settings(), force=True)["delivered"], 1)

    def test_empty_library_is_not_sent_on_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            self.assertEqual(deliver_weekly_letter(db, Settings())["skipped"], "empty_library")

    def test_email_only_when_opted_in_and_mail_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            _seed(db)
            with patch("projectionist.mail.send_mail") as send:
                # Mail configured but owner did not opt in → inbox only.
                result = deliver_weekly_letter(db, _mail_settings(), force=True)
                self.assertEqual((result["delivered"], result["emailed"]), (1, 0))
                send.assert_not_called()
                # Opted in but mail not configured → inbox only, no failure.
                save_letter_settings(db, email=True)
                result = deliver_weekly_letter(db, Settings(), force=True)
                self.assertEqual((result["delivered"], result["emailed"]), (1, 0))
                send.assert_not_called()
                # Opted in AND configured → email too.
                result = deliver_weekly_letter(db, _mail_settings(), force=True)
                self.assertEqual((result["delivered"], result["emailed"]), (1, 1))
                self.assertEqual(send.call_count, 1)
                self.assertEqual(send.call_args.kwargs["to_email"], "owner@example.com")

    def test_week_bucket_is_iso_week(self) -> None:
        self.assertEqual(week_bucket(1_800_000_000.0)[:4], "2027")
        self.assertRegex(week_bucket(), r"^\d{4}-W\d{2}$")

    def test_scheduler_registers_weekly_letter_and_no_gift_queue(self) -> None:
        from projectionist.scheduler.engine import IdleScheduler
        from projectionist.scheduler.tasks import register_all, weekly_letter

        self.assertTrue(callable(weekly_letter.run))
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(_db(tmp), Path(tmp))
            register_all(scheduler)
            self.assertIn("weekly_letter", scheduler._definitions)
            self.assertNotIn("gift_queue", scheduler._definitions)


class WeeklyLetterRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_get_put_send_round_trip(self) -> None:
        got = self.client.get("/api/admin/weekly-letter")
        self.assertEqual(got.status_code, 200, got.text)
        payload = got.json()
        self.assertTrue(payload["weekly"])
        self.assertFalse(payload["email"])
        self.assertFalse(payload["mail_configured"])
        self.assertEqual(payload["letter"]["title"], "A letter about the house")

        # Email cannot be switched on without configured mail.
        put = self.client.put("/api/admin/weekly-letter", json={"weekly": False, "email": True})
        self.assertEqual(put.status_code, 200, put.text)
        self.assertFalse(put.json()["weekly"])
        self.assertFalse(put.json()["email"])
        self.assertFalse(self.client.get("/api/admin/weekly-letter").json()["weekly"])

        sent = self.client.post("/api/admin/weekly-letter/send")
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual(sent.json()["emailed"], 0)

    def test_old_house_routes_are_gone(self) -> None:
        for path in (
            "/api/admin/house/letter",
            "/api/admin/house/gifts",
            "/api/admin/house/seasonal-preview",
            "/api/admin/house/trust-diary",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class HolidayRailOrderTests(unittest.TestCase):
    def test_order_pins_matches_in_exact_order_and_keeps_other_pins_after(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.ensure_holiday_defaults()
            ids = [
                db.upsert_library_item(
                    {
                        "rating_key": f"rk-{n}",
                        "media_type": "movie",
                        "title": f"Haunt {n}",
                        "year": 2000 + n,
                        "keywords": ["horror", "haunted"],
                    }
                )
                for n in range(4)
            ]
            db.set_holiday_rail_title("halloween", ids[3], curation="pin")
            rows = db.set_holiday_rail_order("halloween", [ids[2], ids[0]])
            pins = sorted(
                (r for r in rows if r["curation"] == "pin"), key=lambda r: r["pin_position"]
            )
            self.assertEqual([int(r["library_item_id"]) for r in pins], [ids[2], ids[0], ids[3]])
            with self.assertRaises(ValueError):
                db.set_holiday_rail_order("halloween", [999_999])

    def test_order_endpoint_returns_preview_in_that_order(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.environ["DATA_DIR"] = tmp.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)
        db = app_mod._db()
        db.ensure_holiday_defaults()
        ids = [
            db.upsert_library_item(
                {
                    "rating_key": f"rk-{n}",
                    "media_type": "movie",
                    "title": f"Haunt {n}",
                    "year": 2000 + n,
                    "keywords": ["horror", "haunted"],
                }
            )
            for n in range(3)
        ]
        res = client.put(
            "/api/admin/holidays/halloween/rail/order",
            json={"library_item_ids": [ids[2], ids[0], ids[1]]},
        )
        self.assertEqual(res.status_code, 200, res.text)
        shown = [int(i["id"]) for i in res.json()["preview"]["items"]][:3]
        self.assertEqual(shown, [ids[2], ids[0], ids[1]])
        bad = client.put(
            "/api/admin/holidays/halloween/rail/order", json={"library_item_ids": [987654]}
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(
            client.put("/api/admin/holidays/nope/rail/order", json={"library_item_ids": []}).status_code,
            404,
        )
        jobs._manager = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
