"""Inbox first page must not open SQLite twice or return the whole unread set."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.library.db import Database


class InboxFirstPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _seed_unread(self, count: int) -> None:
        self.db.upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email="member@example.com",
            plex_user_id="plex-member-1",
            role="member",
        )
        clock = iter(float(1_000 - index) for index in range(count))
        with patch(
            "projectionist.library.db._notifications.time.time",
            side_effect=lambda: next(clock),
        ):
            for index in range(count):
                self.db.create_notification(
                    notification_id=f"note-{index}",
                    user_id="member-1",
                    kind="arrival",
                    title=f"Arrival {index}",
                    body="Now in the library",
                )

    def test_first_page_uses_one_connection_and_leaves_older_rows(self) -> None:
        self._seed_unread(30)
        opens = {"n": 0}
        original = self.db.connect

        def counting():
            opens["n"] += 1
            return original()

        self.db.connect = counting  # type: ignore[method-assign]
        page = self.db.notification_inbox_page("member-1", unread_only=True, limit=12)
        self.assertEqual(opens["n"], 1)
        self.assertEqual(len(page["items"]), 12)
        self.assertEqual(page["unread_count"], 30)
        self.assertEqual(page["items"][0]["id"], "note-0")
        self.assertEqual(page["items"][-1]["id"], "note-11")

        rest = self.db.notification_inbox_page(
            "member-1", unread_only=True, limit=38, offset=12
        )
        self.assertEqual(len(rest["items"]), 18)
        self.assertEqual(rest["items"][0]["id"], "note-12")
        ids = [row["id"] for row in page["items"] + rest["items"]]
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(set(ids)), 30)

    def test_read_keeps_the_row_and_dismiss_removes_it(self) -> None:
        self._seed_unread(3)
        updated = self.db.mark_notifications_read("member-1", ["note-0"])
        self.assertEqual(updated, 1)
        kept = self.db.notification_inbox_page("member-1", status="all", limit=12)
        self.assertEqual(kept["total"], 3)
        self.assertEqual(kept["unread_count"], 2)
        row = next(item for item in kept["items"] if item["id"] == "note-0")
        self.assertIsNone(row["seen_at"])
        self.assertIsNotNone(row["read_at"])
        unread = self.db.notification_inbox_page("member-1", status="unread", sort="oldest", limit=12)
        self.assertEqual([item["id"] for item in unread["items"]], ["note-2", "note-1"])
        self.db.mark_notifications_seen("member-1", notification_ids=["note-0"])
        after = self.db.notification_inbox_page("member-1", status="all", limit=12)
        self.assertEqual(after["total"], 2)
        self.assertNotIn("note-0", [item["id"] for item in after["items"]])

    def test_dismiss_all_leaves_mail_you_already_read(self) -> None:
        self._seed_unread(2)
        self.db.mark_notifications_read("member-1", ["note-0"])
        self.db.mark_notifications_seen("member-1", all_unread=True)
        kept = self.db.notification_inbox_page("member-1", status="all", limit=12)
        self.assertEqual([item["id"] for item in kept["items"]], ["note-0"])
