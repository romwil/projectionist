"""Continue Watching must follow a play this process just recorded."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexOnDeckItem
from projectionist.library import explore_hub
from projectionist.library.continue_watching_progress import (
    apply_known_continue_watching,
    clear_continue_watching_progress_notes,
    note_playback_progress,
    notes_for_db,
)
from projectionist.library.db import Database
from projectionist.library.explore_hub import get_explore_hub, invalidate_explore_hub_cache
from projectionist.library.playback import update_local_view_offset


class ContinueWatchingAfterPlayTests(unittest.TestCase):
    def setUp(self) -> None:
        invalidate_explore_hub_cache()
        clear_continue_watching_progress_notes()
        self._refreshers = list(
            __import__(
                "projectionist.library.continue_watching_progress",
                fromlist=["_REFRESHERS"],
            )._REFRESHERS
        )
        from projectionist.library import continue_watching_progress as notes

        self._notes = notes
        notes._REFRESHERS.clear()

    def tearDown(self) -> None:
        from projectionist.library import continue_watching_progress as notes

        notes._REFRESHERS[:] = self._refreshers
        clear_continue_watching_progress_notes()
        invalidate_explore_hub_cache()

    def test_progress_write_replaces_cached_continue_watching_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "cw-movie",
                    "media_type": "movie",
                    "title": "Half Watched",
                    "year": 2020,
                    "view_count": 0,
                    "view_offset_ms": 60_000,
                    "duration_ms": 6_000_000,
                }
            )
            settings = Settings()
            previous = get_explore_hub(db, settings, rail_limit=8, bypass_cache=True)
            previous_rail = previous["rails"]["continue_watching"]
            self.assertEqual(previous_rail["items"][0]["view_offset_ms"], 60_000)
            self.assertFalse(previous["warming"])

            update_local_view_offset(db, "cw-movie", 1_800_000, 6_000_000)

            current = get_explore_hub(db, settings, rail_limit=8)
            rail = current["rails"]["continue_watching"]
            self.assertTrue(current["cached"])
            self.assertFalse(current["warming"])
            self.assertEqual(rail["items"][0]["title"], "Half Watched")
            self.assertEqual(rail["items"][0]["view_offset_ms"], 1_800_000)
            self.assertNotEqual(rail["items"][0]["view_offset_ms"], previous_rail["items"][0]["view_offset_ms"])
            self.assertNotEqual(rail, previous_rail)
            self.assertIn("recently_added", current["rails"])

    def test_stale_on_deck_refresh_keeps_the_offset_just_played(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "cw-movie",
                    "media_type": "movie",
                    "title": "Half Watched",
                    "year": 2020,
                    "view_count": 0,
                    "view_offset_ms": 60_000,
                    "duration_ms": 6_000_000,
                }
            )

            class StaleOnDeck:
                def __init__(self, *_args, **_kwargs) -> None:
                    return None

                def on_deck(self, *, limit: int = 20):
                    del limit
                    return [
                        PlexOnDeckItem(
                            rating_key="cw-movie",
                            media_type="movie",
                            title="Half Watched",
                            view_offset_ms=60_000,
                            duration_ms=6_000_000,
                        )
                    ]

            settings = Settings(plex_url="http://plex.test:32400", plex_token="token")
            from unittest.mock import patch

            with patch.object(explore_hub, "PlexClient", StaleOnDeck):
                previous = get_explore_hub(db, settings, rail_limit=8, bypass_cache=True)
                self.assertEqual(previous["rails"]["continue_watching"]["source"], "plex_on_deck")
                self.assertEqual(previous["rails"]["continue_watching"]["items"][0]["view_offset_ms"], 60_000)

                update_local_view_offset(db, "cw-movie", 1_800_000, 6_000_000)
                painted = get_explore_hub(db, settings, rail_limit=8)
                self.assertEqual(painted["rails"]["continue_watching"]["items"][0]["view_offset_ms"], 1_800_000)
                self.assertNotEqual(
                    painted["rails"]["continue_watching"]["items"][0]["view_offset_ms"],
                    previous["rails"]["continue_watching"]["items"][0]["view_offset_ms"],
                )
                self.assertFalse(painted["warming"])

                cache_key = "youth=0|uid=|limit=8"
                explore_hub._refresh_continue_watching_cache(
                    cache_key,
                    db,
                    explore_hub._CONTEXTS[cache_key],
                )

            clear_continue_watching_progress_notes()
            self.assertEqual(notes_for_db(db), [])
            stored = get_explore_hub(db, settings, rail_limit=8)
            self.assertEqual(stored["rails"]["continue_watching"]["items"][0]["view_offset_ms"], 1_800_000)
            self.assertNotEqual(stored["rails"]["continue_watching"], previous["rails"]["continue_watching"])
            self.assertFalse(stored["warming"])

    def test_e1_then_e2_keeps_one_armstrong_and_miller_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-am",
                    "media_type": "show",
                    "title": "The Armstrong & Miller Show",
                    "year": 2007,
                    "total_episode_count": 2,
                    "unwatched_episode_count": 1,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "am-s1e1",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Episode 1",
                    "duration_ms": 1_800_000,
                    "view_offset_ms": 18_000,
                    "view_count": 0,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "am-s1e2",
                    "season_number": 1,
                    "episode_number": 2,
                    "title": "Episode 2",
                    "duration_ms": 1_800_000,
                    "view_offset_ms": 36_000,
                    "view_count": 0,
                }
            )
            on_deck = {
                "feed": "continue-watching",
                "source": "plex_on_deck",
                "items": [
                    {
                        "title": "The Armstrong & Miller Show",
                        "rating_key": "show-am",
                        "play_rating_key": "am-s1e1",
                        "media_type": "show",
                        "view_offset_ms": 18_000,
                        "duration_ms": 1_800_000,
                        "continue_season": 1,
                        "continue_episode": 1,
                        "resume_label": "S1E1 · 1% watched",
                    }
                ],
                "total": 1,
            }
            note_playback_progress(db, "am-s1e1", 0, 1_800_000, finished=True)
            note_playback_progress(db, "am-s1e2", 36_000, 1_800_000, finished=False)
            rail = apply_known_continue_watching(db, on_deck)
            self.assertEqual(len(rail["items"]), 1)
            self.assertEqual(rail["items"][0]["title"], "The Armstrong & Miller Show")
            self.assertEqual(rail["items"][0]["rating_key"], "show-am")
            self.assertEqual(rail["items"][0]["play_rating_key"], "am-s1e2")
            self.assertEqual(rail["items"][0]["continue_episode"], 2)
            self.assertIn("S1E2", rail["items"][0]["resume_label"])

    def test_finished_episode_keeps_later_on_deck_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-am",
                    "media_type": "show",
                    "title": "The Armstrong & Miller Show",
                    "year": 2007,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "am-s1e1",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Episode 1",
                    "duration_ms": 1_800_000,
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "am-s1e2",
                    "season_number": 1,
                    "episode_number": 2,
                    "title": "Episode 2",
                    "duration_ms": 1_800_000,
                    "view_offset_ms": 36_000,
                }
            )
            on_deck = {
                "items": [
                    {
                        "title": "The Armstrong & Miller Show",
                        "rating_key": "show-am",
                        "play_rating_key": "am-s1e2",
                        "media_type": "show",
                        "view_offset_ms": 36_000,
                        "continue_season": 1,
                        "continue_episode": 2,
                    }
                ],
                "total": 1,
            }
            note_playback_progress(db, "am-s1e1", 0, 1_800_000, finished=True)
            rail = apply_known_continue_watching(db, on_deck)
            self.assertEqual(len(rail["items"]), 1)
            self.assertEqual(rail["items"][0]["play_rating_key"], "am-s1e2")

    def test_duplicate_show_cards_collapse_without_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            rail = apply_known_continue_watching(
                db,
                {
                    "items": [
                        {
                            "title": "The Armstrong & Miller Show",
                            "rating_key": "show-am",
                            "play_rating_key": "am-s1e2",
                            "media_type": "show",
                            "continue_episode": 2,
                        },
                        {
                            "title": "The Armstrong & Miller Show",
                            "rating_key": "show-am",
                            "play_rating_key": "am-s1e1",
                            "media_type": "show",
                            "continue_episode": 1,
                        },
                    ],
                    "total": 2,
                },
            )
            self.assertEqual(len(rail["items"]), 1)
            self.assertEqual(rail["items"][0]["play_rating_key"], "am-s1e2")


if __name__ == "__main__":
    unittest.main()
