"""Continue Watching must follow a play this process just recorded."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexOnDeckItem
from projectionist.library import explore_hub
from projectionist.library.continue_watching_progress import (
    clear_continue_watching_progress_notes,
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


if __name__ == "__main__":
    unittest.main()
