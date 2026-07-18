"""Unit tests for shared watch-progress classification."""

from __future__ import annotations

import unittest

from curatorx.library.watch_progress import watch_progress_state


class WatchProgressStateTests(unittest.TestCase):
    def test_movie_watched(self) -> None:
        self.assertEqual(
            watch_progress_state({"media_type": "movie", "view_count": 1}),
            "watched",
        )

    def test_movie_partial_from_view_offset(self) -> None:
        self.assertEqual(
            watch_progress_state(
                {"media_type": "movie", "view_count": 0, "view_offset_ms": 12_000}
            ),
            "partial",
        )

    def test_movie_unwatched(self) -> None:
        self.assertEqual(
            watch_progress_state({"media_type": "movie", "view_count": 0}),
            "unwatched",
        )
        self.assertEqual(watch_progress_state(None), "unwatched")

    def test_show_watched_all_episodes(self) -> None:
        self.assertEqual(
            watch_progress_state(
                {
                    "media_type": "show",
                    "total_episode_count": 10,
                    "unwatched_episode_count": 0,
                }
            ),
            "watched",
        )

    def test_show_partial(self) -> None:
        self.assertEqual(
            watch_progress_state(
                {
                    "media_type": "show",
                    "total_episode_count": 10,
                    "unwatched_episode_count": 3,
                }
            ),
            "partial",
        )

    def test_show_unwatched(self) -> None:
        self.assertEqual(
            watch_progress_state(
                {
                    "media_type": "show",
                    "total_episode_count": 8,
                    "unwatched_episode_count": 8,
                }
            ),
            "unwatched",
        )

    def test_show_falls_back_to_view_count(self) -> None:
        self.assertEqual(
            watch_progress_state({"media_type": "show", "view_count": 1}),
            "watched",
        )


if __name__ == "__main__":
    unittest.main()
