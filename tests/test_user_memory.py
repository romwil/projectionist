"""v1.8.29 private-memory isolation and purge regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.memory import MemoryAccessError, UserMemoryService


class UserMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "curatorx.db")
        for user_id, name, role in (("owner", "Owner", "owner"), ("adult-a", "A", "member"), ("adult-b", "B", "member"), ("youth", "Youth", "member")):
            self.db.create_local_user(user_id=user_id, display_name=name, password_hash="x", role=role)
        self.service = UserMemoryService(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_adults_are_fail_closed_from_each_other_and_owner(self) -> None:
        self.service.remember(caller_id="adult-a", kind="self_disclosure", text="private A")
        with self.assertRaises(MemoryAccessError):
            self.service.recall(caller_id="adult-b", caller_role="member", target_id="adult-a")
        with self.assertRaises(MemoryAccessError):
            self.service.recall(caller_id="owner", caller_role="owner", target_id="adult-a")

    def test_owner_can_review_youth_only(self) -> None:
        self.db.set_user_youth("youth", True)
        self.service.remember(caller_id="youth", kind="learning_goal", text="learn animation")
        notes = self.service.recall(caller_id="owner", caller_role="owner", target_id="youth")
        self.assertEqual([note["text"] for note in notes], ["learn animation"])

    def test_purge_removes_private_notes_and_chats(self) -> None:
        self.service.remember(caller_id="adult-a", kind="preference", text="no horror")
        self.db.ensure_chat_session("a-chat", user_id="adult-a")
        self.db.save_chat_message("a-chat", "m1", "user", [{"type": "text", "content": "hello"}])
        self.db.create_saved_library_page(
            page_id="page-a",
            user_id="adult-a",
            name="Sci-fi gaps",
            content={"blocks": [{"type": "text", "content": "Watch Stalker."}]},
            searchable_text="stalker meditative sci-fi",
            source_session_id="a-chat",
            source_message_id="m1",
        )
        # add_preference with a user_id writes both a preference_facts row and a
        # mirrored user_memory_note during the compatibility window.
        self.db.add_preference("preference", "no gore", user_id="adult-a")

        result = self.db.purge_user_memory_and_chats("adult-a")
        self.assertEqual(result["notes_deleted"], 2)
        self.assertEqual(result["chat_sessions_deleted"], 1)
        self.assertEqual(result["chat_messages_deleted"], 1)
        self.assertEqual(result["saved_library_pages_deleted"], 1)
        self.assertEqual(result["preference_facts_deleted"], 1)

        self.assertEqual(self.db.list_user_memory_notes("adult-a"), [])
        self.assertIsNone(self.db.get_chat_thread("a-chat", user_id="adult-a"))

        # ZERO rows may remain across every per-user store the purge promises to clear.
        with self.db.connect() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM chat_messages WHERE session_id = ?",
                    ("a-chat",),
                ).fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM saved_library_pages WHERE user_id = ?",
                    ("adult-a",),
                ).fetchone()["c"],
                0,
            )
            if "user_id" in self.db._table_columns(conn, "preference_facts"):
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM preference_facts WHERE user_id = ?",
                        ("adult-a",),
                    ).fetchone()["c"],
                    0,
                )

    def test_export_includes_threads_pages_and_preferences(self) -> None:
        """Export mirrors exactly what purge deletes: notes, chat transcripts,
        saved library pages, and preference facts."""
        self.service.remember(caller_id="adult-a", kind="preference", text="loves noir")
        self.db.ensure_chat_session("a-chat", user_id="adult-a")
        self.db.save_chat_message("a-chat", "m1", "user", [{"type": "text", "content": "hello noir"}])
        self.db.create_saved_library_page(
            page_id="page-a",
            user_id="adult-a",
            name="Noir gaps",
            content={"blocks": [{"type": "text", "content": "Watch Chinatown."}]},
            searchable_text="chinatown noir",
        )
        self.db.add_preference("preference", "no gore", user_id="adult-a")

        export = self.db.export_user_memory("adult-a")

        self.assertTrue(any(note["text"] == "loves noir" for note in export["notes"]))

        self.assertEqual(len(export["chat_threads"]), 1)
        thread = export["chat_threads"][0]
        self.assertEqual(thread["id"], "a-chat")
        self.assertEqual([m["role"] for m in thread["messages"]], ["user"])

        self.assertEqual(len(export["saved_library_pages"]), 1)
        self.assertEqual(export["saved_library_pages"][0]["name"], "Noir gaps")

        self.assertEqual(len(export["preference_facts"]), 1)
        self.assertEqual(export["preference_facts"][0]["text"], "no gore")

    def test_legacy_null_owner_threads_are_owner_review_only(self) -> None:
        """Members (scoped user_id, include_orphans=False) never see legacy
        NULL-owner threads; only owner review (include_orphans=True) can."""
        self.db.ensure_chat_session("orphan-chat", user_id=None)
        self.db.save_chat_message("orphan-chat", "m1", "user", [{"type": "text", "content": "legacy"}])

        # Member scope cannot get/list/delete the orphan thread.
        self.assertIsNone(self.db.get_chat_thread("orphan-chat", user_id="adult-a"))
        member_ids = [t["id"] for t in self.db.list_chat_threads(user_id="adult-a")]
        self.assertNotIn("orphan-chat", member_ids)
        self.assertFalse(self.db.delete_chat_thread("orphan-chat", user_id="adult-a"))

        # Owner review can get/list the orphan thread.
        self.assertIsNotNone(
            self.db.get_chat_thread("orphan-chat", user_id="owner", include_orphans=True)
        )
        owner_ids = [
            t["id"] for t in self.db.list_chat_threads(user_id="owner", include_orphans=True)
        ]
        self.assertIn("orphan-chat", owner_ids)

        # Owner delete removes the session AND its transcript.
        self.assertTrue(
            self.db.delete_chat_thread("orphan-chat", user_id="owner", include_orphans=True)
        )
        with self.db.connect() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM chat_messages WHERE session_id = ?",
                    ("orphan-chat",),
                ).fetchone()["c"],
                0,
            )
