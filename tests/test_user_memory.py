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
        result = self.db.purge_user_memory_and_chats("adult-a")
        self.assertEqual(result["notes_deleted"], 1)
        self.assertEqual(result["chat_sessions_deleted"], 1)
        self.assertEqual(self.db.list_user_memory_notes("adult-a"), [])
        self.assertIsNone(self.db.get_chat_thread("a-chat", user_id="adult-a"))
