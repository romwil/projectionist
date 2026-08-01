"""Tests for season/episode scoped TV remove."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.library.db import Database
from projectionist.library.tv_remove import remove_tv_scope


class TvRemoveTests(unittest.TestCase):
    def _seed(self, db: Database) -> int:
        show_id = db.upsert_library_item(
            {
                "rating_key": "show-1",
                "media_type": "show",
                "title": "The Expanse",
                "year": 2015,
                "tvdb_id": 280619,
                "file_size": 9000,
            }
        )
        db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-1",
                "season_number": 1,
                "episode_number": 1,
                "title": "Dulcinea",
                "file_size": 4000,
                "view_count": 0,
            }
        )
        db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-2",
                "season_number": 1,
                "episode_number": 2,
                "title": "The Big Empty",
                "file_size": 5000,
                "view_count": 0,
            }
        )
        db.update_show_episode_rollups(show_id)
        return show_id

    def test_remove_episode_deletes_sonarr_plex_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = self._seed(db)
            settings = MagicMock()
            settings.sonarr_url = "http://sonarr.test"
            settings.sonarr_api_key = "key"
            settings.plex_url = "http://plex.test"
            settings.plex_token = "tok"

            with (
                patch(
                    "projectionist.library.tv_remove.resolve_arr_removal_target",
                    return_value={"arr_id": 7, "title": "The Expanse", "tvdb_id": 280619},
                ),
                patch("projectionist.library.tv_remove.SonarrClient") as sonarr_cls,
                patch("projectionist.library.tv_remove.PlexClient") as plex_cls,
                patch(
                    "projectionist.library.tv_remove.plex_configuration_error",
                    return_value=None,
                ),
            ):
                sonarr = MagicMock()
                sonarr.series_by_id.return_value = {"path": "/tv/The Expanse"}
                sonarr.episodes.return_value = [
                    {
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "episodeFileId": 11,
                        "hasFile": True,
                    },
                    {
                        "seasonNumber": 1,
                        "episodeNumber": 2,
                        "episodeFileId": 12,
                        "hasFile": True,
                    },
                ]
                sonarr.episode_files.return_value = [
                    {
                        "id": 11,
                        "path": "/tv/The Expanse/Season 01/S01E01.mkv",
                        "size": 4000,
                        "seasonNumber": 1,
                    },
                    {
                        "id": 12,
                        "path": "/tv/The Expanse/Season 01/S01E02.mkv",
                        "size": 5000,
                        "seasonNumber": 1,
                    },
                ]
                sonarr_cls.return_value = sonarr
                plex = MagicMock()
                plex_cls.return_value = plex

                payload = remove_tv_scope(
                    db,
                    settings,
                    scope="episode",
                    show_id=show_id,
                    episode_rating_key="ep-1",
                )

            self.assertEqual(payload["deleted"], 1)
            self.assertEqual(payload["totals"]["files"], 1)
            self.assertEqual(payload["totals"]["bytes_freed"], 4000)
            sonarr.delete_episode_files.assert_called_once_with([11])
            plex.delete_metadata.assert_called_once_with("ep-1")
            remaining = db.library_episodes_for_show(show_id)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(str(remaining[0]["rating_key"]), "ep-2")

    def test_remove_season_uses_library_estimate_when_arr_sparse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = self._seed(db)
            settings = MagicMock()
            settings.sonarr_url = "http://sonarr.test"
            settings.sonarr_api_key = "key"
            settings.plex_url = ""
            settings.plex_token = ""

            with (
                patch(
                    "projectionist.library.tv_remove.resolve_arr_removal_target",
                    return_value={"arr_id": 7, "title": "The Expanse", "tvdb_id": 280619},
                ),
                patch("projectionist.library.tv_remove.SonarrClient") as sonarr_cls,
                patch(
                    "projectionist.library.tv_remove.plex_configuration_error",
                    return_value="skip",
                ),
            ):
                sonarr = MagicMock()
                sonarr.series_by_id.return_value = {"path": "/tv/The Expanse"}
                sonarr.episodes.return_value = []
                sonarr.episode_files.return_value = []
                sonarr_cls.return_value = sonarr

                payload = remove_tv_scope(
                    db,
                    settings,
                    scope="season",
                    show_id=show_id,
                    season_number=1,
                )

            entry = payload["results"][0]
            self.assertEqual(entry["bytes_source"], "library_estimate")
            self.assertEqual(entry["bytes_freed"], 9000)
            self.assertIn("folder", entry["note"].lower())
            self.assertEqual(len(db.library_episodes_for_show(show_id)), 0)


if __name__ == "__main__":
    unittest.main()
