"""Tests for named curated lists (T9)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from curatorx.agent.tools import ToolRegistry
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.lists import PLEX_LISTS_PUBLISH_SUPPORTED


class CuratedListsDbTests(unittest.TestCase):
    def test_create_list_add_and_remove_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            created = db.create_curated_list(
                list_id="list-1",
                user_id=None,
                name="Weekend",
                description="Short picks",
            )
            self.assertEqual(created["name"], "Weekend")
            self.assertEqual(created["item_count"], 0)

            item = db.add_curated_list_item(
                item_id="item-1",
                list_id="list-1",
                user_id=None,
                tmdb_id=27205,
                tvdb_id=None,
                media_type="movie",
                title="Inception",
            )
            self.assertEqual(item["title"], "Inception")

            detail = db.get_curated_list("list-1", user_id=None, include_items=True)
            assert detail is not None
            self.assertEqual(detail["item_count"], 1)
            self.assertEqual(len(detail["items"]), 1)

            removed = db.delete_curated_list_item("list-1", "item-1", user_id=None)
            self.assertTrue(removed)
            detail = db.get_curated_list("list-1", user_id=None, include_items=True)
            assert detail is not None
            self.assertEqual(detail["item_count"], 0)

    def test_duplicate_list_name_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_curated_list(list_id="a", user_id=None, name="Favorites")
            with self.assertRaises(ValueError):
                db.create_curated_list(list_id="b", user_id=None, name="Favorites")

    def test_playlist_kind_persists_and_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            created = db.create_curated_list(
                list_id="playlist-1", user_id=None, name="Road trip", list_kind="playlist"
            )
            self.assertEqual(created["list_kind"], "playlist")
            updated = db.update_curated_list("playlist-1", user_id=None, list_kind="list")
            assert updated is not None
            self.assertEqual(updated["list_kind"], "list")

    def test_plex_lists_publish_is_deferred(self) -> None:
        self.assertFalse(PLEX_LISTS_PUBLISH_SUPPORTED)


class CuratedListsToolTests(IsolatedAsyncioTestCase):
    async def test_list_create_add_remove_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)

            created = json.loads(
                await registry.execute("create_list", {"name": "Noir night", "description": ""})
            )
            self.assertIn("list", created)
            list_id = created["list"]["id"]

            listed = json.loads(await registry.execute("list_lists", {}))
            self.assertEqual(listed["count"], 1)
            self.assertEqual(listed["items"][0]["name"], "Noir night")

            added = json.loads(
                await registry.execute(
                    "add_to_list",
                    {
                        "list_id": list_id,
                        "title": "Heat",
                        "media_type": "movie",
                        "tmdb_id": 949,
                    },
                )
            )
            self.assertEqual(added["item"]["title"], "Heat")

            removed = json.loads(
                await registry.execute(
                    "remove_from_list",
                    {"list_name": "Noir night", "tmdb_id": 949, "media_type": "movie"},
                )
            )
            self.assertTrue(removed["removed"])


if __name__ == "__main__":
    unittest.main()
