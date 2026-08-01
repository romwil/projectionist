"""Tests for saved curator library storage."""

import tempfile
import unittest
import sqlite3
import asyncio
from pathlib import Path
from unittest.mock import patch

from projectionist.library.db import Database
from projectionist.web.app import _persona_voiced_library_summary
from projectionist.web.library_privacy import (
    SAVED_LIBRARY_RAIL_LIMIT,
    normalize_saved_library_content,
    sanitize_saved_rail_items,
)


class SavedLibraryTests(unittest.TestCase):
    def test_saved_page_is_private_and_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_local_user(user_id="user-a", display_name="A", password_hash="x")
            db.create_local_user(user_id="user-b", display_name="B", password_hash="x")
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
        with patch("projectionist.web.app.get_chat_provider", side_effect=RuntimeError("offline")):
            summary = asyncio.run(_persona_voiced_library_summary(content, persona={"name": "Jefferson"}))
        self.assertEqual(summary, "Watch Stalker for its meditative science-fiction atmosphere.")

    def test_sanitize_saved_rail_items_dedupes_and_drops_idless(self) -> None:
        items = [
            {"media_type": "show", "title": "Chernobyl", "tmdb_id": 87108},
            {"media_type": "show", "title": "Chernobyl again", "tmdb_id": 87108},
            {"media_type": "show", "title": "Invented", "tmdb_id": 0},
            {"media_type": "show", "title": "", "tmdb_id": 12},
            *[{"media_type": "show", "title": f"Extra {i}", "tmdb_id": 2000 + i} for i in range(20)],
        ]
        cleaned = sanitize_saved_rail_items(items)
        self.assertEqual(len(cleaned), SAVED_LIBRARY_RAIL_LIMIT)
        self.assertEqual(cleaned[0]["title"], "Chernobyl")
        self.assertEqual(sum(1 for c in cleaned if c["tmdb_id"] == 87108), 1)

    def test_normalize_saved_library_content_bounds_crazy_gap_rails(self) -> None:
        crazy = [
            {
                "media_type": "show",
                "title": "" if i % 3 == 0 else f"Gap {i}",
                "tmdb_id": 0 if i % 5 == 0 else 5000 + (i % 7),
            }
            for i in range(40)
        ]
        content = normalize_saved_library_content(
            {
                "blocks": [
                    {"type": "text", "content": "Mixed bag"},
                    {"type": "title_cards", "items": crazy},
                ]
            }
        )
        cards = [b for b in content["blocks"] if b.get("type") == "title_cards"]
        self.assertEqual(len(cards), 1)
        self.assertLessEqual(len(cards[0]["items"]), SAVED_LIBRARY_RAIL_LIMIT)
        self.assertTrue(all(c.get("tmdb_id") and c.get("title") for c in cards[0]["items"]))

