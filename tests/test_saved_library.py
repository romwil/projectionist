"""Tests for saved curator library storage."""

import tempfile
import unittest
import sqlite3
import asyncio
from pathlib import Path
from unittest.mock import patch

from curatorx.library.db import Database
from curatorx.web.app import _persona_voiced_library_summary


class SavedLibraryTests(unittest.TestCase):
    def test_saved_page_is_private_and_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            saved = db.create_saved_library_page(
                page_id="save-1",
                user_id="user-a",
                name="Sci-fi gaps",
                source_session_id="thread-1",
                source_message_id="message-1",
                content={"blocks": [{"type": "text", "content": "Watch Stalker for its meditative sci-fi."}]},
                searchable_text="Sci-fi gaps Stalker meditative sci-fi",
            )
            self.assertEqual(saved["name"], "Sci-fi gaps")
            self.assertEqual(saved["summary"], "")
            self.assertIsNone(saved["persona_id"])
            self.assertEqual(len(db.list_saved_library_pages(user_id="user-a", query="stalker")), 1)
            self.assertEqual(db.get_saved_library_page("save-1", user_id="user-b"), None)
            self.assertTrue(db.delete_saved_library_page("save-1", user_id="user-a"))

    def test_saved_library_migration_adds_summary_and_persona_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.db"
            with sqlite3.connect(path) as conn:
                conn.execute(
                    """
                    CREATE TABLE saved_library_pages (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
                        source_session_id TEXT, source_message_id TEXT,
                        searchable_text TEXT NOT NULL DEFAULT '', content_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )
            db = Database(path)
            with db.connect() as conn:
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(saved_library_pages)")}
            self.assertTrue({"summary", "persona_id"}.issubset(columns))

    def test_summary_falls_back_when_llm_is_unavailable(self) -> None:
        content = {"blocks": [{"type": "text", "content": "Watch Stalker for its meditative science-fiction atmosphere."}]}
        with patch("curatorx.web.app.get_chat_provider", side_effect=RuntimeError("offline")):
            summary = asyncio.run(_persona_voiced_library_summary(content, persona={"name": "Jefferson"}))
        self.assertEqual(summary, "Watch Stalker for its meditative science-fiction atmosphere.")

