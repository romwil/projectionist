"""Owned-not-in-Radarr register-existing helpers and admin list endpoint."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.agent.tools import resolve_radarr_search_for_movie
from projectionist.library.db import Database


class RadarrRegisterExistingTests(unittest.TestCase):
    def test_resolve_search_defaults_false_for_owned_not_in_radarr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [
                    {
                        "rating_key": "rk-1",
                        "media_type": "movie",
                        "title": "Moon",
                        "tmdb_id": 17431,
                        "in_radarr": 0,
                    }
                ]
            )
            self.assertFalse(resolve_radarr_search_for_movie(db, 17431))
            self.assertTrue(resolve_radarr_search_for_movie(db, 17431, explicit=True))
            self.assertTrue(resolve_radarr_search_for_movie(db, 999001))

    def test_list_tool_descriptions_say_projectionist_not_curatorx(self) -> None:
        from projectionist.agent.tools._definitions import TOOL_DEFINITIONS

        blob = " ".join(
            str(tool.get("function", {}).get("description") or "")
            for tool in TOOL_DEFINITIONS
            if tool.get("function", {}).get("name")
            in {"list_lists", "create_list", "add_to_list", "remove_from_list", "recall_repo_memory"}
        )
        self.assertIn("Projectionist", blob)
        self.assertNotIn("CuratorX", blob)
