"""Tests for saved curator library storage."""

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database


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
            self.assertEqual(len(db.list_saved_library_pages(user_id="user-a", query="stalker")), 1)
            self.assertEqual(db.get_saved_library_page("save-1", user_id="user-b"), None)
            self.assertTrue(db.delete_saved_library_page("save-1", user_id="user-a"))

