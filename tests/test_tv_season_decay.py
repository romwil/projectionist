"""Unit tests for TV season-decay + episode sentiment taste weighting."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.preferences.tv_taste import (
    episode_sentiment,
    is_abandoned_mid_series,
    season_decay,
    show_taste_multiplier,
    summarize_episode_curve,
)
from curatorx.scheduler.tasks import taste_refresh


def _ep(season: int, *, views: int = 0, stars: float | None = None) -> dict:
    return {
        "season_number": season,
        "episode_number": 1,
        "view_count": views,
        "plex_user_rating_stars": stars,
    }


class TvTasteUnitTests(unittest.TestCase):
    def test_episode_sentiment_curves(self) -> None:
        self.assertAlmostEqual(episode_sentiment(5, 1), 1.0)
        self.assertAlmostEqual(episode_sentiment(1, 1), -1.0)
        self.assertAlmostEqual(episode_sentiment(3, 1), 0.0)
        self.assertAlmostEqual(episode_sentiment(None, 2), 0.15)
        self.assertAlmostEqual(episode_sentiment(None, 0), 0.0)

    def test_season_decay_before_anchor_is_full(self) -> None:
        self.assertEqual(season_decay(1, 3), 1.0)
        self.assertEqual(season_decay(3, 3), 1.0)
        self.assertLess(season_decay(5, 2), 0.5)

    def test_abandoned_mid_series_loved_s1(self) -> None:
        # Strong S1 ratings, then nothing in S2–S4.
        episodes = [
            *[_ep(1, views=1, stars=5) for _ in range(8)],
            *[_ep(2, views=0) for _ in range(8)],
            *[_ep(3, views=0) for _ in range(8)],
            *[_ep(4, views=0) for _ in range(8)],
        ]
        self.assertTrue(is_abandoned_mid_series(episodes))
        mult = show_taste_multiplier(episodes)
        summary = summarize_episode_curve(episodes)
        self.assertEqual(summary["last_engaged_season"], 1)
        self.assertLess(mult, 0.5)
        # Later seasons should be heavily decayed.
        self.assertLessEqual(summary["per_season"][4]["decay"], 0.25)

    def test_consistent_engagement_keeps_weight(self) -> None:
        episodes = []
        for season in (1, 2, 3):
            episodes.extend(_ep(season, views=1, stars=4) for _ in range(6))
        self.assertFalse(is_abandoned_mid_series(episodes))
        mult = show_taste_multiplier(episodes)
        self.assertGreater(mult, 0.55)

    def test_mid_series_dip_then_recovery(self) -> None:
        episodes = [
            *[_ep(1, views=1, stars=5) for _ in range(4)],
            *[_ep(2, views=1, stars=2) for _ in range(4)],
            *[_ep(3, views=1, stars=5) for _ in range(4)],
        ]
        self.assertFalse(is_abandoned_mid_series(episodes))
        mult = show_taste_multiplier(episodes)
        # Mixed but engaged through S3 — not crushed by abandon multiplier.
        self.assertGreater(mult, 0.4)


class TasteRefreshTvIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_taste_refresh_downweights_abandoned_show_genres(self) -> None:
        abandoned_id = self.db.upsert_library_item(
            {
                "rating_key": "show-abandoned",
                "media_type": "show",
                "title": "Abandoned Drama",
                "year": 2018,
                "genres": ["Drama"],
                "keywords": ["small town"],
                "view_count": 10,
            }
        )
        loved_id = self.db.upsert_library_item(
            {
                "rating_key": "show-loved",
                "media_type": "show",
                "title": "Loved Comedy",
                "year": 2019,
                "genres": ["Comedy"],
                "keywords": ["workplace"],
                "view_count": 20,
            }
        )
        # Abandoned: loved early, nothing later.
        abandoned_eps = []
        for season, views, stars in ((1, 1, 5), (2, 0, None), (3, 0, None), (4, 0, None)):
            for ep_n in range(1, 5):
                abandoned_eps.append(
                    {
                        "show_item_id": abandoned_id,
                        "rating_key": f"ep-a-{season}-{ep_n}",
                        "season_number": season,
                        "episode_number": ep_n,
                        "title": f"S{season}E{ep_n}",
                        "view_count": views,
                        "plex_user_rating_stars": stars,
                    }
                )
        # Consistently engaged comedy.
        loved_eps = []
        for season in (1, 2, 3):
            for ep_n in range(1, 5):
                loved_eps.append(
                    {
                        "show_item_id": loved_id,
                        "rating_key": f"ep-l-{season}-{ep_n}",
                        "season_number": season,
                        "episode_number": ep_n,
                        "title": f"S{season}E{ep_n}",
                        "view_count": 1,
                        "plex_user_rating_stars": 5,
                    }
                )
        self.db.upsert_library_episodes(abandoned_eps + loved_eps)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_title_reviews (
                    id, rating_key, media_type, title, stars, created_at, updated_at
                ) VALUES
                  ('rev-1', 'show-abandoned', 'show', 'Abandoned Drama', 5, 1.0, 1.0),
                  ('rev-2', 'show-loved', 'show', 'Loved Comedy', 5, 1.0, 1.0)
                """
            )

        result = asyncio.run(taste_refresh.run(self.db, Settings(), lambda: False))
        self.assertEqual(result["status"], "completed")
        self.assertGreaterEqual(result.get("tv_shows_adjusted", 0), 1)

        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT cluster_tag, weight FROM lens_taste_profile WHERE lens_id = 'general'"
            ).fetchall()
        weights = {str(r["cluster_tag"]): float(r["weight"]) for r in rows}
        self.assertIn("drama", weights)
        self.assertIn("comedy", weights)
        # Abandoned drama must weigh less than consistently engaged comedy.
        self.assertLess(weights["drama"], weights["comedy"])


if __name__ == "__main__":
    unittest.main()
