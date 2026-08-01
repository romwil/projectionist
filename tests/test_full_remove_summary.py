"""Unit tests for full-remove path snapshotting and totals aggregation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from projectionist.library.full_remove import (
    aggregate_removal_totals,
    apply_library_bytes_fallback,
    infer_removed_folders,
    snapshot_radarr_movie,
    snapshot_sonarr_series,
)


class InferRemovedFoldersTests(unittest.TestCase):
    def test_includes_root_and_file_parents(self) -> None:
        folders = infer_removed_folders(
            [
                "/media/movies/Inception (2010)/Inception.mkv",
                "/media/movies/Inception (2010)/subs/en.srt",
            ],
            root_path="/media/movies/Inception (2010)",
        )
        self.assertEqual(
            folders,
            [
                "/media/movies/Inception (2010)",
                "/media/movies/Inception (2010)/subs",
            ],
        )

    def test_windows_paths(self) -> None:
        folders = infer_removed_folders(
            [r"D:\media\Shows\Breaking Bad\Season 01\S01E01.mkv"],
            root_path=r"D:\media\Shows\Breaking Bad",
        )
        self.assertIn(r"D:\media\Shows\Breaking Bad", folders)
        self.assertIn(r"D:\media\Shows\Breaking Bad\Season 01", folders)

    def test_no_invented_paths_without_inputs(self) -> None:
        self.assertEqual(infer_removed_folders([]), [])
        self.assertEqual(infer_removed_folders(["", None]), [])  # type: ignore[list-item]


class SnapshotTests(unittest.TestCase):
    def test_radarr_movie_uses_movie_file_and_size_on_disk(self) -> None:
        snap = snapshot_radarr_movie(
            {
                "path": "/movies/Dune (2021)",
                "sizeOnDisk": 50_000_000_000,
                "movieFile": {
                    "path": "/movies/Dune (2021)/Dune.mkv",
                    "size": 49_000_000_000,
                },
            }
        )
        self.assertEqual(snap["files"], ["/movies/Dune (2021)/Dune.mkv"])
        self.assertEqual(snap["folders"], ["/movies/Dune (2021)"])
        self.assertEqual(snap["bytes_freed"], 50_000_000_000)

    def test_radarr_falls_back_to_file_size(self) -> None:
        snap = snapshot_radarr_movie(
            {
                "path": "/movies/Dune (2021)",
                "movieFile": {
                    "path": "/movies/Dune (2021)/Dune.mkv",
                    "size": 1_234,
                },
            }
        )
        self.assertEqual(snap["bytes_freed"], 1_234)

    def test_sonarr_series_lists_episode_files(self) -> None:
        snap = snapshot_sonarr_series(
            {
                "path": "/tv/The Expanse",
                "statistics": {"sizeOnDisk": 9_000},
            },
            [
                {"path": "/tv/The Expanse/Season 01/S01E01.mkv", "size": 4_000},
                {"path": "/tv/The Expanse/Season 01/S01E02.mkv", "size": 5_000},
            ],
        )
        self.assertEqual(len(snap["files"]), 2)
        self.assertIn("/tv/The Expanse", snap["folders"])
        self.assertIn("/tv/The Expanse/Season 01", snap["folders"])
        self.assertEqual(snap["bytes_freed"], 9_000)

    def test_sonarr_uses_relative_path_when_absolute_missing(self) -> None:
        snap = snapshot_sonarr_series(
            {"path": "/tv/Hollywood Squares (2025)", "statistics": {"sizeOnDisk": 0}},
            [
                {
                    "relativePath": "Season 01/S01E01.mkv",
                    "size": 1_000,
                }
            ],
        )
        self.assertEqual(
            snap["files"],
            ["/tv/Hollywood Squares (2025)/Season 01/S01E01.mkv"],
        )
        self.assertEqual(snap["bytes_freed"], 1_000)

    def test_sonarr_folder_only_gets_library_estimate(self) -> None:
        snap = snapshot_sonarr_series(
            {"path": "/tv/Hollywood Squares (2025)", "statistics": {"sizeOnDisk": 0}},
            [],
        )
        enriched = apply_library_bytes_fallback(snap, library_bytes=24_100_000_000)
        self.assertEqual(enriched["folders"], ["/tv/Hollywood Squares (2025)"])
        self.assertEqual(enriched["files"], [])
        self.assertEqual(enriched["bytes_freed"], 24_100_000_000)
        self.assertEqual(enriched["bytes_source"], "library_estimate")
        self.assertIn("no episode", enriched["note"].lower())


class AggregateTotalsTests(unittest.TestCase):
    def test_sums_per_title_fields(self) -> None:
        totals = aggregate_removal_totals(
            [
                {
                    "files": ["a.mkv", "b.mkv"],
                    "folders": ["/a"],
                    "bytes_freed": 100,
                },
                {
                    "files": ["c.mkv"],
                    "folders": ["/c", "/c/Season 01"],
                    "bytes_freed": 50,
                },
            ]
        )
        self.assertEqual(
            totals,
            {"files": 3, "folders": 3, "bytes_freed": 150},
        )

    def test_empty_results(self) -> None:
        self.assertEqual(
            aggregate_removal_totals([]),
            {"files": 0, "folders": 0, "bytes_freed": 0},
        )


class FullRemoveApiShapeTests(unittest.TestCase):
    def test_full_remove_includes_totals_and_per_item_summary(self) -> None:
        from projectionist.library.full_remove import full_remove_library_items

        db = MagicMock()
        db.library_item_by_rating_key.return_value = {
            "rating_key": "rk-1",
            "title": "Dune",
            "media_type": "movie",
            "tmdb_id": 438631,
            "file_size": 2000,
        }
        db.delete_library_items_by_rating_keys.return_value = 1
        settings = MagicMock()
        settings.radarr_url = "http://radarr.test"
        settings.radarr_api_key = "key"
        settings.plex_url = ""
        settings.plex_token = ""
        settings.sonarr_url = ""
        settings.sonarr_api_key = ""

        with (
            patch(
                "projectionist.library.full_remove.resolve_arr_removal_target",
                return_value={"arr_id": 7, "title": "Dune", "tmdb_id": 438631},
            ),
            patch("projectionist.library.full_remove.RadarrClient") as radarr_cls,
            patch("projectionist.library.full_remove.plex_configuration_error", return_value="skip"),
            patch("projectionist.library.full_remove.drop_cached_purge_keys"),
        ):
            radarr = MagicMock()
            radarr.movie_by_id.return_value = {
                "path": "/movies/Dune (2021)",
                "sizeOnDisk": 2000,
                "movieFile": {"path": "/movies/Dune (2021)/Dune.mkv", "size": 2000},
            }
            radarr_cls.return_value = radarr
            payload = full_remove_library_items(db, settings, ["rk-1"])

        self.assertEqual(payload["mode"], "full")
        self.assertEqual(payload["deleted"], 1)
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["totals"]["files"], 1)
        self.assertEqual(payload["totals"]["folders"], 1)
        self.assertEqual(payload["totals"]["bytes_freed"], 2000)
        entry = payload["results"][0]
        self.assertEqual(entry["files"], ["/movies/Dune (2021)/Dune.mkv"])
        self.assertEqual(entry["folders"], ["/movies/Dune (2021)"])
        self.assertEqual(entry["bytes_freed"], 2000)
        radarr.movie_by_id.assert_called_once_with(7)
        radarr.delete_movie.assert_called_once_with(7, delete_files=True, add_exclusion=True)


if __name__ == "__main__":
    unittest.main()
