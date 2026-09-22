"""Owned-not-in-Radarr register-existing helpers and admin list endpoint."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from projectionist.agent.tools import resolve_radarr_search_for_movie
from projectionist.connectors.radarr import RadarrMovie
from projectionist.library.admin_execution import AdminExecutionStore
from projectionist.library.db import Database
from projectionist.library.radarr_register import _item_from_preview, _register_batch


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

    def test_register_batch_same_tmdb_is_already_without_post(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [
                    {
                        "rating_key": "rk-presence",
                        "media_type": "movie",
                        "title": "Presence",
                        "year": 2025,
                        "tmdb_id": 1388150,
                        "in_radarr": 0,
                    }
                ]
            )
            row = db.library_item_by_tmdb(1388150, "movie")
            assert row is not None
            preview = {
                "id": int(row["id"]),
                "title": "Presence",
                "year": 2025,
                "tmdb_id": 1388150,
            }
            store = AdminExecutionStore("radarr_register")
            store.begin(items=[_item_from_preview(preview)])
            client = _CatalogRadarr(
                movies=[
                    RadarrMovie(
                        id=9,
                        title="Presence",
                        year=2025,
                        tmdb_id=1388150,
                        monitored=True,
                        has_file=True,
                        folder_path="/movies/Presence (2025)",
                    )
                ]
            )
            result = _register_batch(
                store,
                threading.Event(),
                db=db,
                settings=_settings(),
                client=client,
                rows=[preview],
            )
            self.assertEqual(result["already"], 1)
            self.assertEqual(result["registered"], 0)
            self.assertEqual(result["failed"], [])
            self.assertEqual(client.added, [])
            snap = store.snapshot()
            item = snap["items"][0]
            self.assertEqual(item["status"], "skipped")
            self.assertEqual(item["outcome"], "already")
            self.assertIn("Already in Radarr", item.get("message") or item.get("error") or "")
            self.assertEqual(int(db.library_item_by_tmdb(1388150, "movie")["in_radarr"] or 0), 1)

    def test_register_batch_path_conflict_does_not_mark_in_radarr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_items(
                [
                    {
                        "rating_key": "rk-presence",
                        "media_type": "movie",
                        "title": "Presence",
                        "year": 2025,
                        "tmdb_id": 1388150,
                        "in_radarr": 0,
                    }
                ]
            )
            row = db.library_item_by_tmdb(1388150, "movie")
            assert row is not None
            preview = {
                "id": int(row["id"]),
                "title": "Presence",
                "year": 2025,
                "tmdb_id": 1388150,
            }
            store = AdminExecutionStore("radarr_register")
            store.begin(items=[_item_from_preview(preview)])
            client = _CatalogRadarr(
                movies=[
                    RadarrMovie(
                        id=9,
                        title="Presence",
                        year=2025,
                        tmdb_id=111,
                        monitored=True,
                        has_file=True,
                        folder_path="/movies/Presence (2025)",
                    )
                ]
            )
            result = _register_batch(
                store,
                threading.Event(),
                db=db,
                settings=_settings(),
                client=client,
                rows=[preview],
            )
            self.assertEqual(result["already"], 0)
            self.assertEqual(result["registered"], 0)
            self.assertEqual(len(result["failed"]), 1)
            self.assertEqual(client.added, [])
            item = store.snapshot()["items"][0]
            self.assertEqual(item["status"], "failed")
            self.assertEqual(item["outcome"], "path_conflict")
            self.assertIn("Path conflict", item["error"])
            self.assertNotIn("formattedMessagePlaceholderValues", item["error"])
            self.assertNotIn("HTTP 400", item["error"])
            self.assertEqual(int(db.library_item_by_tmdb(1388150, "movie")["in_radarr"] or 0), 0)
            self.assertEqual(store.snapshot()["execution"]["failed"], 1)
            self.assertEqual(store.snapshot()["execution"]["completed"], 0)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        radarr_url="http://radarr.test",
        radarr_api_key="secret",
        radarr_root_folder="/movies",
        movies_root="/movies",
        radarr_quality_profile_id=1,
    )


class _CatalogRadarr:
    def __init__(self, movies: Optional[List[RadarrMovie]] = None) -> None:
        self._movies = list(movies or [])
        self.added: List[int] = []

    def movies(self) -> List[RadarrMovie]:
        return list(self._movies)

    def movie_by_tmdb_id(self, tmdb_id: int) -> Optional[RadarrMovie]:
        for movie in self._movies:
            if movie.tmdb_id == int(tmdb_id):
                return movie
        return None

    def add_movie(self, tmdb_id: int, **kwargs: Any) -> Dict[str, Any]:
        del kwargs
        raise AssertionError(f"must not POST into Radarr for tmdb {tmdb_id}")

    def root_folders(self) -> List[Dict[str, Any]]:
        return [{"path": "/movies"}]
