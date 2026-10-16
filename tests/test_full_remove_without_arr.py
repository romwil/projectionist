"""Full remove continues when Radarr or Sonarr does not have the title."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _settings(**overrides: str) -> MagicMock:
    settings = MagicMock()
    settings.radarr_url = "http://radarr.test"
    settings.radarr_api_key = "radarr-key"
    settings.sonarr_url = ""
    settings.sonarr_api_key = ""
    settings.plex_url = ""
    settings.plex_token = ""
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _row(path: str = "", *, media_type: str = "movie", title: str = "The Sacrifice") -> dict:
    row = {
        "rating_key": "rk-sacrifice",
        "title": title,
        "media_type": media_type,
        "tmdb_id": 4242,
        "tvdb_id": 77 if media_type != "movie" else None,
        "file_size": 120,
    }
    if path:
        row["file_path"] = path
    return row


class FullRemoveWithoutArrTests(unittest.TestCase):
    def test_absent_radarr_deletes_known_file_and_drops_index(self) -> None:
        from projectionist.library.full_remove import RemovalProgress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "The Sacrifice (2026)"
            folder.mkdir()
            media = folder / "The Sacrifice.mkv"
            media.write_bytes(b"x" * 120)
            db = MagicMock()
            db.library_item_by_rating_key.return_value = _row(str(media))
            db.delete_library_items_by_rating_keys.return_value = 1

            with (
                patch("projectionist.agent.tools.RadarrClient") as lookup_cls,
                patch("projectionist.library.full_remove.RadarrClient") as delete_cls,
                patch("projectionist.library.full_remove.drop_cached_purge_keys"),
            ):
                lookup = MagicMock()
                lookup.movie_by_tmdb_id.return_value = None
                lookup_cls.return_value = lookup
                run = RemovalProgress(db, _settings(), ["rk-sacrifice"], mode="full")
                events = list(run.events())

            self.assertFalse(media.exists())
            self.assertFalse(folder.exists())
            delete_cls.return_value.delete_movie.assert_not_called()
            db.record_acquisition_exclusion.assert_not_called()
            db.delete_library_items_by_rating_keys.assert_called_once_with(["rk-sacrifice"])

        statuses = [event.get("status") for event in events if event.get("type") == "title"]
        self.assertEqual(statuses, ["removing", "removed"])
        removed = next(event for event in events if event.get("status") == "removed")
        entry = removed["entry"]
        self.assertIn("not in Radarr", entry["note"])
        self.assertEqual(entry["files"], [str(media)])
        self.assertEqual(entry["bytes_freed"], 120)
        self.assertTrue(entry["index_deleted"])
        self.assertFalse(entry["arr"]["add_exclusion"])
        self.assertEqual(run.result["errors"], [])
        self.assertEqual(run.result["deleted"], 1)
        self.assertEqual(run.result["totals"]["files"], 1)
        self.assertEqual(run.result["totals"]["bytes_freed"], 120)

    def test_file_delete_permission_error_fails_the_title(self) -> None:
        from projectionist.library.full_remove import RemovalProgress

        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "locked.mkv"
            media.write_bytes(b"keep")
            db = MagicMock()
            db.library_item_by_rating_key.return_value = _row(str(media))
            db.delete_library_items_by_rating_keys.return_value = 1

            with (
                patch("projectionist.agent.tools.RadarrClient") as lookup_cls,
                patch("projectionist.library.full_remove.RadarrClient"),
                patch(
                    "projectionist.library.full_remove.Path.unlink",
                    side_effect=PermissionError("Permission denied"),
                ),
                patch("projectionist.library.full_remove.drop_cached_purge_keys"),
            ):
                lookup = MagicMock()
                lookup.movie_by_tmdb_id.return_value = None
                lookup_cls.return_value = lookup
                run = RemovalProgress(db, _settings(), ["rk-sacrifice"], mode="full")
                events = list(run.events())

            self.assertTrue(media.exists())

        db.delete_library_items_by_rating_keys.assert_not_called()
        db.record_acquisition_exclusion.assert_not_called()
        statuses = [event.get("status") for event in events if event.get("type") == "title"]
        self.assertEqual(statuses, ["removing", "failed"])
        failed = next(event for event in events if event.get("status") == "failed")
        self.assertIn("Permission denied", failed["error"])
        self.assertEqual(run.result["deleted"], 0)
        self.assertEqual(len(run.result["errors"]), 1)
        self.assertFalse(run.result["errors"][0]["index_deleted"])

    def test_plex_reject_still_fails_the_title(self) -> None:
        from projectionist.library.full_remove import RemovalProgress

        db = MagicMock()
        db.library_item_by_rating_key.return_value = _row()
        db.delete_library_items_by_rating_keys.return_value = 1
        with (
            patch("projectionist.agent.tools.RadarrClient") as lookup_cls,
            patch("projectionist.library.full_remove.PlexClient") as plex_cls,
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            lookup = MagicMock()
            lookup.movie_by_tmdb_id.return_value = None
            lookup_cls.return_value = lookup
            plex = MagicMock()
            plex.media_file_paths.return_value = []
            plex.delete_metadata.side_effect = RuntimeError("Plex rejected the delete")
            plex_cls.return_value = plex
            run = RemovalProgress(
                db,
                _settings(plex_url="http://plex.test", plex_token="token"),
                ["rk-sacrifice"],
                mode="full",
            )
            events = list(run.events())

        db.delete_library_items_by_rating_keys.assert_not_called()
        db.record_acquisition_exclusion.assert_not_called()
        failed = next(event for event in events if event.get("status") == "failed")
        self.assertIn("Plex rejected", failed["error"])
        self.assertEqual(run.result["deleted"], 0)

    def test_absent_sonarr_drops_index_without_exclusion(self) -> None:
        from projectionist.library.full_remove import full_remove_library_items

        db = MagicMock()
        db.library_item_by_rating_key.return_value = _row(media_type="show", title="The Show")
        db.delete_library_items_by_rating_keys.return_value = 1
        with (
            patch("projectionist.agent.tools.SonarrClient") as lookup_cls,
            patch("projectionist.library.full_remove.SonarrClient") as delete_cls,
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            lookup = MagicMock()
            lookup.series_by_tvdb_id.return_value = None
            lookup_cls.return_value = lookup
            result = full_remove_library_items(
                db,
                _settings(sonarr_url="http://sonarr.test", sonarr_api_key="sonarr-key"),
                ["rk-sacrifice"],
            )

        delete_cls.return_value.delete_series.assert_not_called()
        db.record_acquisition_exclusion.assert_not_called()
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["errors"], [])
        self.assertIn("not in Sonarr", result["results"][0]["note"])
        self.assertFalse(result["results"][0]["arr"]["add_exclusion"])


if __name__ == "__main__":
    unittest.main()
