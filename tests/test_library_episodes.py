"""Tests for TV episode sync and queries."""

from __future__ import annotations

import logging
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

from curatorx.connectors.plex import PlexEpisode, PlexLibraryItem, PlexSeason
from curatorx.library.db import Database
from curatorx.library.episodes import query_episodes, summarize_tv_progress, sync_tv_episodes


@dataclass
class MockPlexClient:
    seasons_by_show: dict[str, List[PlexSeason]]
    episodes_by_season: dict[str, List[PlexEpisode]]
    episodes_by_show: dict[str, List[PlexEpisode]] = field(default_factory=dict)
    calls: List[tuple[str, str]] = field(default_factory=list)
    plex_shows: Optional[List[PlexLibraryItem]] = None

    def show_items(self) -> List[PlexLibraryItem]:
        self.calls.append(("show_items", ""))
        return list(self.plex_shows or [])

    def show_seasons(self, show_rating_key: str) -> List[PlexSeason]:
        self.calls.append(("show_seasons", show_rating_key))
        if not str(show_rating_key or "").strip():
            raise ValueError("show_rating_key is required")
        return list(self.seasons_by_show.get(show_rating_key, []))

    def show_all_episodes(self, show_rating_key: str) -> List[PlexEpisode]:
        self.calls.append(("show_all_episodes", show_rating_key))
        if not str(show_rating_key or "").strip():
            raise ValueError("show_rating_key is required")
        return list(self.episodes_by_show.get(show_rating_key, []))

    def season_episodes(self, season_rating_key: str) -> List[PlexEpisode]:
        self.calls.append(("season_episodes", season_rating_key))
        if not str(season_rating_key or "").strip():
            raise ValueError("season_rating_key is required")
        return list(self.episodes_by_season.get(season_rating_key, []))


class LibraryEpisodeTests(unittest.TestCase):
    def _seed_show_with_episodes(self, db: Database) -> int:
        show_id = db.upsert_library_item(
            {
                "rating_key": "show-wire",
                "media_type": "show",
                "title": "The Wire",
                "year": 2002,
                "genres": ["Crime"],
            }
        )
        db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-1",
                "season_number": 1,
                "episode_number": 1,
                "title": "The Target",
                "view_count": 1,
            }
        )
        db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-2",
                "season_number": 1,
                "episode_number": 2,
                "title": "The Detail",
                "view_count": 0,
            }
        )
        db.update_show_episode_rollups(show_id)
        return show_id

    def test_query_unwatched_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_show_with_episodes(db)
            result = query_episodes(db, show="Wire", unwatched_only=True)
            self.assertEqual(result["total_matched"], 1)
            self.assertEqual(result["items"][0]["title"], "The Detail")

    def test_summarize_tv_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self._seed_show_with_episodes(db)
            summary = summarize_tv_progress(db, group_by="show", in_progress_only=True)
            self.assertEqual(summary["group_by"], "show")
            self.assertEqual(len(summary["buckets"]), 1)
            self.assertEqual(summary["buckets"][0]["completion_percent"], 50.0)

    def test_backfill_from_plex_restores_rating_key_and_syncs_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "The Wire",
                    "year": 2002,
                    "tmdb_id": 1438,
                }
            )
            plex = MockPlexClient(
                plex_shows=[
                    PlexLibraryItem(
                        rating_key="plex-wire",
                        media_type="show",
                        title="The Wire",
                        year=2002,
                        tmdb_id="1438",
                    )
                ],
                seasons_by_show={
                    "plex-wire": [PlexSeason(rating_key="season-1", season_number=1, title="Season 1")]
                },
                episodes_by_season={
                    "season-1": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="The Target",
                            season_number=1,
                            episode_number=1,
                        )
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex)

            show = db.library_item_by_id(show_id)
            self.assertEqual(show["rating_key"], "plex-wire")
            self.assertEqual(stats["backfilled_rating_key"], 1)
            self.assertEqual(stats["shows_synced"], 1)
            self.assertEqual(stats["episodes_synced"], 1)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_seasons"],
                [("show_seasons", "plex-wire")],
            )

    def test_backfill_resolves_by_title_year_when_tmdb_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "Breaking Bad",
                    "year": 2008,
                }
            )
            plex = MockPlexClient(
                plex_shows=[
                    PlexLibraryItem(
                        rating_key="plex-bb",
                        media_type="show",
                        title="Breaking Bad",
                        year=2008,
                    )
                ],
                seasons_by_show={"plex-bb": []},
                episodes_by_season={},
            )

            stats = sync_tv_episodes(db, plex)

            show = db.library_item_by_id(show_id)
            self.assertEqual(show["rating_key"], "plex-bb")
            self.assertEqual(stats["backfilled_rating_key"], 1)
            self.assertEqual(stats["unmatchable_shows"], 0)

    def test_backfill_resolves_by_tvdb_when_tmdb_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "Mystery Show",
                    "tvdb_id": 999001,
                }
            )
            plex = MockPlexClient(
                plex_shows=[
                    PlexLibraryItem(
                        rating_key="plex-tvdb",
                        media_type="show",
                        title="Mystery Show",
                        year=2010,
                        tvdb_id="999001",
                    )
                ],
                seasons_by_show={"plex-tvdb": []},
                episodes_by_season={},
            )

            stats = sync_tv_episodes(db, plex)

            show = db.library_item_by_id(show_id)
            self.assertEqual(show["rating_key"], "plex-tvdb")
            self.assertEqual(stats["backfilled_rating_key"], 1)

    def test_sync_uses_all_leaves_when_seasons_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-flat",
                    "media_type": "show",
                    "title": "Flattened Show",
                    "leaf_count": 2,
                }
            )
            plex = MockPlexClient(
                seasons_by_show={"show-flat": []},
                episodes_by_season={},
                episodes_by_show={
                    "show-flat": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                        ),
                        PlexEpisode(
                            rating_key="ep-2",
                            title="Second",
                            season_number=1,
                            episode_number=2,
                        ),
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex)

            self.assertEqual(stats["shows_synced"], 1)
            self.assertEqual(stats["episodes_synced"], 2)
            self.assertEqual(stats["all_leaves_fallbacks"], 1)
            show = db.library_item_by_id(show_id)
            self.assertEqual(int(show["total_episode_count"]), 2)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_all_episodes"],
                [("show_all_episodes", "show-flat")],
            )
            # allLeaves-first: seasons are not needed when leaves succeed
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_seasons"],
                [],
            )

    def test_sync_logs_sample_shows_at_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "show-a",
                    "media_type": "show",
                    "title": "Alpha",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "Beta",
                }
            )
            plex = MockPlexClient(
                plex_shows=[],
                seasons_by_show={"show-a": []},
                episodes_by_season={},
            )

            with self.assertLogs("curatorx.library.episodes", level="INFO") as logs:
                sync_tv_episodes(db, plex)

            self.assertTrue(
                any("Episode sync sample" in message and "with_rating_key=" in message for message in logs.output)
            )

    def test_sync_skips_only_unmatchable_shows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "Missing Key Show",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "show-valid",
                    "media_type": "show",
                    "title": "Valid Show",
                }
            )
            plex = MockPlexClient(
                plex_shows=[],
                seasons_by_show={"show-valid": []},
                episodes_by_season={},
            )

            with self.assertLogs("curatorx.library.episodes", level="INFO") as logs:
                stats = sync_tv_episodes(db, plex)

            self.assertEqual(stats["unmatchable_shows"], 1)
            self.assertEqual(stats["shows_synced"], 1)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_seasons"],
                [("show_seasons", "show-valid")],
            )
            self.assertTrue(
                any("Skipped episode sync for 1 unmatchable shows" in message for message in logs.output)
            )

    def test_sync_skips_seasons_without_rating_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "show-mixed",
                    "media_type": "show",
                    "title": "Mixed Seasons",
                }
            )
            plex = MockPlexClient(
                seasons_by_show={
                    "show-mixed": [
                        PlexSeason(rating_key="", season_number=None, title="Bad Season"),
                        PlexSeason(rating_key="season-1", season_number=1, title="Season 1"),
                    ]
                },
                episodes_by_season={
                    "season-1": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                        )
                    ]
                },
            )

            with self.assertLogs("curatorx.library.episodes", level="INFO") as logs:
                stats = sync_tv_episodes(db, plex)

            self.assertEqual(stats["skipped_empty_seasons"], 1)
            self.assertEqual(stats["episodes_synced"], 1)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "season_episodes"],
                [("season_episodes", "season-1")],
            )
            self.assertTrue(
                any("Skipped 1 seasons without Plex rating_key" in message for message in logs.output)
            )

    def test_sync_valid_rating_key_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-good",
                    "media_type": "show",
                    "title": "Good Show",
                }
            )
            plex = MockPlexClient(
                seasons_by_show={
                    "show-good": [PlexSeason(rating_key="season-1", season_number=1, title="Season 1")]
                },
                episodes_by_season={
                    "season-1": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                            view_count=0,
                        ),
                        PlexEpisode(
                            rating_key="ep-2",
                            title="Second",
                            season_number=1,
                            episode_number=2,
                            view_count=1,
                        ),
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex)

            self.assertEqual(stats["shows_synced"], 1)
            self.assertEqual(stats["episodes_synced"], 2)
            show = db.library_item_by_id(show_id)
            self.assertEqual(int(show["total_episode_count"]), 2)
            self.assertEqual(int(show["unwatched_episode_count"]), 1)

    def test_sync_does_not_call_plex_seasons_with_empty_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "",
                    "media_type": "show",
                    "title": "No Key",
                }
            )
            plex = MockPlexClient(
                plex_shows=[],
                seasons_by_show={},
                episodes_by_season={},
            )

            sync_tv_episodes(db, plex)

            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_seasons"],
                [],
            )
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_items"],
                [("show_items", "")],
            )

    def test_sync_logging_does_not_spam_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for index in range(3):
                db.upsert_library_item(
                    {
                        "media_type": "show",
                        "title": f"Missing {index}",
                    }
                )
            plex = MockPlexClient(
                plex_shows=[],
                seasons_by_show={},
                episodes_by_season={},
            )

            with patch.object(logging.getLogger("curatorx.library.episodes"), "warning") as warning:
                stats = sync_tv_episodes(db, plex)

            self.assertEqual(stats["unmatchable_shows"], 3)
            warning.assert_not_called()

    def test_sync_prefers_all_leaves_then_falls_back_to_seasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "show-season",
                    "media_type": "show",
                    "title": "Season Path",
                }
            )
            plex = MockPlexClient(
                seasons_by_show={
                    "show-season": [PlexSeason(rating_key="season-1", season_number=1, title="Season 1")]
                },
                episodes_by_season={
                    "season-1": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                        )
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex, workers=1)

            self.assertEqual(stats["episodes_synced"], 1)
            self.assertEqual(stats["all_leaves_fallbacks"], 0)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_all_episodes"],
                [("show_all_episodes", "show-season")],
            )
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_seasons"],
                [("show_seasons", "show-season")],
            )

    def test_sync_skips_unchanged_shows_using_leaf_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-stable",
                    "media_type": "show",
                    "title": "Stable Show",
                    "leaf_count": 2,
                    "viewed_leaf_count": 1,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "ep-1",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "One",
                    "view_count": 1,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "ep-2",
                    "season_number": 1,
                    "episode_number": 2,
                    "title": "Two",
                    "view_count": 0,
                }
            )
            plex = MockPlexClient(
                seasons_by_show={"show-stable": []},
                episodes_by_season={},
                episodes_by_show={
                    "show-stable": [
                        PlexEpisode(rating_key="ep-1", title="One", season_number=1, episode_number=1),
                        PlexEpisode(rating_key="ep-2", title="Two", season_number=1, episode_number=2),
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex, workers=2)

            self.assertEqual(stats["shows_skipped_unchanged"], 1)
            self.assertEqual(stats["shows_synced"], 1)
            self.assertEqual(stats["episodes_synced"], 0)
            self.assertEqual(
                [call for call in plex.calls if call[0] == "show_all_episodes"],
                [],
            )

    def test_sync_refetches_when_viewed_leaf_count_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-watched",
                    "media_type": "show",
                    "title": "Watched Show",
                    "leaf_count": 1,
                    "viewed_leaf_count": 1,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "ep-1",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Pilot",
                    "view_count": 0,
                }
            )
            plex = MockPlexClient(
                seasons_by_show={},
                episodes_by_season={},
                episodes_by_show={
                    "show-watched": [
                        PlexEpisode(
                            rating_key="ep-1",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                            view_count=1,
                        )
                    ]
                },
            )

            stats = sync_tv_episodes(db, plex, workers=2)

            self.assertEqual(stats["shows_skipped_unchanged"], 0)
            self.assertEqual(stats["episodes_synced"], 1)
            show = db.library_item_by_id(show_id)
            self.assertEqual(int(show["unwatched_episode_count"]), 0)

    def test_parallel_fetch_serial_batched_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for index in range(8):
                db.upsert_library_item(
                    {
                        "rating_key": f"show-{index}",
                        "media_type": "show",
                        "title": f"Show {index}",
                        "leaf_count": 1,
                        "viewed_leaf_count": 0,
                    }
                )
            plex = MockPlexClient(
                seasons_by_show={},
                episodes_by_season={},
                episodes_by_show={
                    f"show-{index}": [
                        PlexEpisode(
                            rating_key=f"ep-{index}",
                            title="Pilot",
                            season_number=1,
                            episode_number=1,
                        )
                    ]
                    for index in range(8)
                },
            )

            replace_calls: List[tuple[int, int]] = []
            real_replace = db.replace_library_episodes_for_show

            def tracking_replace(show_item_id: int, episodes):
                replace_calls.append((show_item_id, len(list(episodes))))
                return real_replace(show_item_id, episodes)

            db.replace_library_episodes_for_show = tracking_replace  # type: ignore[method-assign]

            stats = sync_tv_episodes(db, plex, workers=4)

            self.assertEqual(stats["shows_synced"], 8)
            self.assertEqual(stats["episodes_synced"], 8)
            self.assertEqual(len(replace_calls), 8)
            self.assertEqual(sum(count for _, count in replace_calls), 8)
            self.assertEqual(
                len([call for call in plex.calls if call[0] == "show_all_episodes"]),
                8,
            )


if __name__ == "__main__":
    unittest.main()
