"""Year in Review recap sheet + genre/hours rollup."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import TitleRollup, WatchEventInput, YearRollup
from projectionist.watch_tracker.rollups import build_year_rollup, year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.year_in_review.chapters import assemble_chapters, build_movie_genre, build_volume
from projectionist.year_in_review.recap import (
    build_recap,
    format_catalog_hours,
    personality_line,
    ranked_names,
)
from projectionist.year_in_review.snapshot import build_reel_for_user


def _title(**overrides: object) -> TitleRollup:
    base = dict(
        rating_key="m1",
        media_type="movie",
        parent_rating_key=None,
        title="Coherence",
        year=2013,
        poster_url=None,
        completions=1,
        confidence={"plex_event_only": 1},
        last_completed_at_ms=1,
        distinct_days=1,
    )
    base.update(overrides)
    return TitleRollup(**base)  # type: ignore[arg-type]


def _rollup(**overrides: object) -> YearRollup:
    base = dict(
        user_id="owner-1",
        year=2026,
        completion_count=10,
        movie_completions=4,
        episode_completions=6,
        unique_titles=5,
        unique_episodes=6,
        sittings_observed=12,
        confidence={"certain": 1, "likely": 0, "plex_event_only": 9},
        top_movies=[],
        top_shows=[],
        monthly_counts={6: 8, 7: 2},
        peak_month_titles=[],
        first_completion_at_ms=1,
        last_completion_at_ms=2,
        has_enough_data=True,
    )
    base.update(overrides)
    return YearRollup(**base)  # type: ignore[arg-type]


class RecapBuilderTests(unittest.TestCase):
    def test_personality_and_hero_hours(self) -> None:
        recap = build_recap(
            _rollup(
                movie_genre_counts={"Horror": 12, "Thriller": 5},
                tv_genre_counts={"Drama": 40, "Comedy": 9},
                unique_shows=3,
                catalog_minutes=180,
                catalog_minutes_coverage=4,
            )
        )
        self.assertEqual(recap["headline"], "Horror movies. Drama TV. That was your year.")
        hero_ids = [item["id"] for item in recap["hero"]]
        self.assertIn("hours", hero_ids)
        self.assertEqual(recap["movie_genre"]["name"], "Horror")
        self.assertEqual(recap["movie_genre"]["runner_up"]["name"], "Thriller")
        self.assertEqual(recap["tv_genre"]["name"], "Drama")
        self.assertIn("catalog runtimes", recap["hours_note"])

    def test_omits_hours_and_genres_when_missing(self) -> None:
        recap = build_recap(_rollup())
        self.assertIsNone(recap["movie_genre"])
        self.assertIsNone(recap["tv_genre"])
        self.assertFalse(any(item["id"] == "hours" for item in recap["hero"]))
        self.assertEqual(recap["hours_note"], "")

    def test_rewatch_only_on_distinct_days(self) -> None:
        recap = build_recap(
            _rollup(
                top_movies=[
                    _title(distinct_days=1, completions=2, title="Noise"),
                    _title(rating_key="m2", title="Coherence", distinct_days=3, completions=3),
                ]
            )
        )
        assert recap["rewatch"] is not None
        self.assertEqual(recap["rewatch"]["title"], "Coherence")
        self.assertEqual(recap["rewatch"]["days"], 3)

    def test_format_hours_and_ranked_names(self) -> None:
        self.assertEqual(format_catalog_hours(60), "1")
        self.assertEqual(format_catalog_hours(90), "1.5")
        self.assertEqual(format_catalog_hours(720), "12")
        self.assertEqual(
            ranked_names({"B": 2, "A": 2, "C": 9}, limit=2),
            [{"name": "C", "count": 9}, {"name": "A", "count": 2}],
        )
        self.assertIn("Horror all the way down", personality_line(movie_genre="Horror", tv_genre="Horror", year=2026))


class RecapRollupIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir-recap.db")
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )
        self.db.update_user_profile("owner-1", year_in_review_opt_in=True)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_rollup_joins_genres_hours_and_credits(self) -> None:
        year = 2026
        start_ms, _ = year_bounds_ms(year)
        horror_id = self.db.upsert_library_item(
            {
                "rating_key": "movie-horror",
                "media_type": "movie",
                "title": "The Autopsy of Jane Doe",
                "year": 2016,
                "genres": ["Horror", "Thriller"],
                "directors": ["Andre Ovredal"],
                "cast": ["Emile Hirsch", "Brian Cox"],
                "runtime_minutes": 86,
            }
        )
        self.assertTrue(horror_id)
        show_id = self.db.upsert_library_item(
            {
                "rating_key": "show-drama",
                "media_type": "show",
                "title": "The Bear",
                "year": 2022,
                "genres": ["Drama"],
            }
        )
        self.db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "ep-1",
                "season_number": 1,
                "episode_number": 1,
                "title": "System",
                "runtime_minutes": 28,
            }
        )
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id="h1",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="111",
                rating_key="movie-horror",
                media_type="movie",
                occurred_at_ms=start_ms + 86_400_000,
                terminal=True,
            ),
            WatchEventInput(
                source="plex_history",
                source_event_id="h2",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="111",
                rating_key="ep-1",
                media_type="episode",
                parent_rating_key="show-drama",
                occurred_at_ms=start_ms + 2 * 86_400_000,
                terminal=True,
            ),
            WatchEventInput(
                source="plex_history",
                source_event_id="h3",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="111",
                rating_key="movie-horror",
                media_type="movie",
                occurred_at_ms=start_ms + 10 * 86_400_000,
                terminal=True,
            ),
        ]
        ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db, user_id="owner-1")
        rollup = build_year_rollup(self.db, user_id="owner-1", year=year)
        self.assertGreaterEqual(rollup.movie_genre_counts.get("Horror", 0), 2)
        self.assertEqual(rollup.tv_genre_counts.get("Drama"), 1)
        self.assertEqual(rollup.catalog_minutes, 86 + 86 + 28)
        self.assertEqual(rollup.catalog_minutes_coverage, 3)
        self.assertEqual(rollup.director_counts.get("Andre Ovredal"), 2)
        self.assertEqual(rollup.unique_movies, 1)
        self.assertEqual(rollup.unique_shows, 1)
        self.assertEqual(sum(rollup.weekday_counts.values()), 3)

        snap = build_reel_for_user(self.db, user_id="owner-1", year=year)
        recap = snap["reel"]["recap"]
        self.assertEqual(recap["movie_genre"]["name"], "Horror")
        self.assertEqual(recap["tv_genre"]["name"], "Drama")
        kinds = {c["kind"] for c in snap["reel"]["chapters"]}
        self.assertIn("movie_genre", kinds)
        self.assertIn("tv_genre", kinds)
        self.assertIn("volume", kinds)
        self.assertNotIn("honesty", kinds)

        genre_ch = build_movie_genre(rollup, {})
        assert genre_ch is not None
        self.assertEqual(genre_ch["title"], "Horror")
        volume = build_volume(rollup, {})
        assert volume is not None
        self.assertEqual(volume["title"], "The totals")

    def test_assemble_skips_empty_genre_chapters(self) -> None:
        chapters = assemble_chapters(_rollup(movie_genre_counts={}, tv_genre_counts={}))
        kinds = {c["kind"] for c in chapters}
        self.assertNotIn("movie_genre", kinds)
        self.assertNotIn("tv_genre", kinds)


if __name__ == "__main__":
    unittest.main()
