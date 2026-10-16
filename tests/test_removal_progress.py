"""Per-title removal progress is reported before the next delete starts."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.radarr_url = "http://radarr.test"
    settings.radarr_api_key = "key"
    settings.plex_url = ""
    settings.plex_token = ""
    settings.sonarr_url = ""
    settings.sonarr_api_key = ""
    return settings


def _row(key: str, title: str) -> dict:
    return {
        "rating_key": key,
        "title": title,
        "media_type": "movie",
        "tmdb_id": 1,
        "file_size": 2000,
    }


class RemovalProgressTests(unittest.TestCase):
    def test_removing_event_precedes_arr_delete_and_totals_follow(self) -> None:
        from projectionist.library.full_remove import RemovalProgress

        db = MagicMock()
        db.library_item_by_rating_key.side_effect = lambda key: _row(key, f"Title {key}")
        db.delete_library_items_by_rating_keys.return_value = 1

        with (
            patch(
                "projectionist.library.full_remove.resolve_arr_removal_target",
                return_value={"arr_id": 7, "title": "Title", "tmdb_id": 1},
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch("projectionist.library.full_remove.plex_configuration_error", return_value="skip"),
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            radarr = MagicMock()
            radarr.movie_by_id.return_value = {
                "path": "/movies/Title",
                "sizeOnDisk": 5000,
                "movieFile": {"path": "/movies/Title/Title.mkv", "size": 5000},
            }
            radarr_cls.return_value = radarr
            run = RemovalProgress(db, _settings(), ["rk-1", "rk-2"], mode="full")
            events = run.events()
            start = next(events)
            self.assertEqual(start["type"], "start")
            self.assertEqual(start["total"], 2)
            removing = next(events)
            self.assertEqual(removing["status"], "removing")
            self.assertEqual(removing["done"], 0)
            self.assertEqual(radarr.delete_movie.call_count, 0)
            removed = next(events)
            self.assertEqual(removed["status"], "removed")
            self.assertEqual(removed["done"], 1)
            self.assertEqual(removed["bytes_freed_so_far"], 5000)
            self.assertEqual(radarr.delete_movie.call_count, 1)
            self.assertIn("/movies/Title/Title.mkv", removed["entry"]["files"])

            rest = list(events)
            complete = rest[-1]
            self.assertEqual(complete["type"], "complete")
            self.assertEqual(complete["result"]["deleted"], 2)
            self.assertEqual(complete["result"]["totals"]["files"], 2)
            self.assertEqual(complete["result"]["totals"]["bytes_freed"], 10000)
            self.assertEqual(radarr.delete_movie.call_count, 2)

    def test_cancel_does_not_start_the_next_title(self) -> None:
        from projectionist.library.full_remove import RemovalProgress

        db = MagicMock()
        db.library_item_by_rating_key.side_effect = lambda key: _row(key, f"Title {key}")
        db.delete_library_items_by_rating_keys.return_value = 1
        cancel = threading.Event()

        def _delete_movie(*_args, **_kwargs):
            cancel.set()

        with (
            patch(
                "projectionist.library.full_remove.resolve_arr_removal_target",
                return_value={"arr_id": 7, "title": "Title", "tmdb_id": 1},
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch("projectionist.library.full_remove.plex_configuration_error", return_value="skip"),
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            radarr = MagicMock()
            radarr.movie_by_id.return_value = {
                "path": "/movies/Title",
                "sizeOnDisk": 100,
                "movieFile": {"path": "/movies/Title/Title.mkv", "size": 100},
            }
            radarr.delete_movie.side_effect = _delete_movie
            radarr_cls.return_value = radarr
            run = RemovalProgress(
                db,
                _settings(),
                ["rk-1", "rk-2"],
                mode="full",
                cancel_event=cancel,
            )
            events = list(run.events())

        self.assertEqual(radarr.delete_movie.call_count, 1)
        self.assertTrue(run.cancelled)
        self.assertEqual(run.result["deleted"], 1)
        self.assertTrue(run.result["cancelled"])
        self.assertEqual(events[-1]["type"], "complete")
        statuses = [event.get("status") for event in events if event.get("type") == "title"]
        self.assertEqual(statuses, ["removing", "removed"])


if __name__ == "__main__":
    unittest.main()
