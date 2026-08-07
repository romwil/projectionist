"""Year in Review snapshot + delivery + admin generate."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from projectionist.year_in_review.delivery import (
    current_calendar_year,
    deliver_year_in_review,
    prior_calendar_year,
)
from projectionist.year_in_review.snapshot import build_reel_for_user, get_snapshot
from projectionist.year_in_review.chapters import (
    build_honesty,
    build_monthly_rhythm,
    build_ratings,
    build_top_movies,
)
from projectionist.year_in_review.signals import collect_social_signals
from projectionist.watch_tracker.rollups import build_year_rollup
from projectionist.reviews.store import save_review
from projectionist.watch_tracker.models import TitleRollup, YearRollup


class YearInReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir.db")
        self.settings = Settings()
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )
        self.db.update_user_profile("owner-1", year_in_review_opt_in=True, notify_channel_inbox=True)
        self.db.create_local_user(
            user_id="guest-1",
            display_name="Guest",
            password_hash="x",
            role="guest",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _seed_completions(self, *, user_id: str, plex_id: str, year: int, count: int = 4) -> None:
        start_ms, _ = year_bounds_ms(year)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"{user_id}-{i}",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key=plex_id,
                rating_key=f"movie-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(count)
        ]
        ingest_watch_events(self.db, events)
        rebuild_watch_derivations(self.db, user_id=user_id)

    def test_calendar_year_helpers(self) -> None:
        mid_2026 = datetime(2026, 8, 6, tzinfo=timezone.utc).timestamp()
        self.assertEqual(current_calendar_year(mid_2026), 2026)
        self.assertEqual(prior_calendar_year(mid_2026), 2025)

    def test_build_reel_adaptive_chapters(self) -> None:
        year = 2024
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        snap = build_reel_for_user(self.db, user_id="owner-1", year=year)
        self.assertEqual(snap["status"], "ready")
        chapters = snap["reel"]["chapters"]
        self.assertGreaterEqual(len(chapters), 3)
        kinds = {c["kind"] for c in chapters}
        self.assertIn("overture", kinds)
        self.assertIn("honesty", kinds)
        # No social signals → no ratings/shares/live chapters required
        self.assertNotIn("ratings", kinds)

    def test_guest_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_reel_for_user(self.db, user_id="guest-1", year=2024)

    def test_delivery_opt_in_and_inbox(self) -> None:
        year = 2024
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            status_hint="ready",
        )
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["path"], f"/year-in-review/{year}")
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertIn(str(year), notes[0]["title"])
        loaded = get_snapshot(self.db, user_id="owner-1", year=year)
        self.assertIsNotNone(loaded)
        self.assertIsNotNone(loaded["notified_at"])

    def test_force_delivers_inbox_without_opt_in(self) -> None:
        """Owner test-send must create the production-shaped inbox item even without opt-in."""
        year = current_calendar_year()
        self.db.update_user_profile("owner-1", year_in_review_opt_in=False)
        self._seed_completions(user_id="owner-1", plex_id="111", year=year)
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            status_hint="ready",
            force=True,
        )
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["path"], f"/year-in-review/{year}")
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["kind"], "year-in-review")
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertEqual(notes[0]["title"], f"Your {year} Year in Review is ready")

    def test_force_without_notify_gate_still_skips_empty(self) -> None:
        year = current_calendar_year()
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=year,
            user_ids=["owner-1"],
            force=True,
        )
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["delivered"], 0)
        self.assertEqual(result["status"], "empty")
        self.assertIsNone(result["path"])
        notes = self.db.list_notifications_for_user("owner-1", kinds=["year-in-review"])
        self.assertEqual(len(notes), 0)

    def test_empty_year_skips_delivery(self) -> None:
        result = deliver_year_in_review(
            self.db,
            self.settings,
            year=2020,
            user_ids=["owner-1"],
        )
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["delivered"], 0)


class YearInReviewAdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-yir-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in (
            "CURATORX_SKIP_DOTENV",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _seed_owner_completions(self, year: int) -> str:
        db = self.app_mod._db()
        me = self.client.get("/api/auth/me").json()["user"]
        user_id = str(me["id"])
        db.update_user_profile(
            user_id,
            year_in_review_opt_in=True,
            notify_channel_inbox=True,
        )

        def _map_plex() -> None:
            with db.connect() as conn:
                conn.execute(
                    "UPDATE users SET plex_user_id = ? WHERE id = ?",
                    ("111", user_id),
                )

        db.run_write(_map_plex, label="map_bootstrap_plex")
        start_ms, _ = year_bounds_ms(year)
        events = [
            WatchEventInput(
                source="plex_history",
                source_event_id=f"api-{i}",
                source_event_kind="history_played",
                server_machine_id="srv",
                source_user_key="111",
                rating_key=f"api-movie-{i}",
                media_type="movie",
                occurred_at_ms=start_ms + i * 86_400_000,
                terminal=True,
            )
            for i in range(4)
        ]
        ingest_watch_events(db, events)
        rebuild_watch_derivations(db, user_id=user_id)
        return user_id

    def test_admin_generate_defaults_to_current_year_and_is_ready(self) -> None:
        year = current_calendar_year()
        user_id = self._seed_owner_completions(year)
        with patch(
            "projectionist.year_in_review.delivery.prior_calendar_year",
            return_value=year - 1,
        ):
            resp = self.client.post(
                "/api/admin/year-in-review/generate",
                json={"scope": "self", "notify": True},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["year"], year)
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["path"], f"/year-in-review/{year}")
        self.assertEqual(body["delivered"], 1)
        self.assertEqual(body["generated"], 1)

        got = self.client.get(f"/api/year-in-review/{year}")
        self.assertEqual(got.status_code, 200, got.text)
        self.assertEqual(got.json()["status"], "ready")
        self.assertGreaterEqual(len(got.json()["reel"]["chapters"]), 3)

        notes = self.app_mod._db().list_notifications_for_user(user_id, kinds=["year-in-review"])
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["payload"].get("path"), f"/year-in-review/{year}")
        self.assertEqual(notes[0]["title"], f"Your {year} Year in Review is ready")

    def test_admin_generate_empty_year_omits_path(self) -> None:
        year = current_calendar_year()
        resp = self.client.post(
            "/api/admin/year-in-review/generate",
            json={"scope": "self", "notify": False, "year": year},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["year"], year)
        self.assertEqual(body["status"], "empty")
        self.assertIsNone(body.get("path"))
        self.assertEqual(
            self.client.get(f"/api/year-in-review/{year}").status_code,
            404,
        )


def _title(
    *,
    rating_key: str,
    title: str,
    completions: int = 1,
    distinct_days: int = 1,
    media_type: str = "movie",
    last_ms: int = 1_700_000_000_000,
) -> TitleRollup:
    return TitleRollup(
        rating_key=rating_key,
        media_type=media_type,  # type: ignore[arg-type]
        parent_rating_key=None if media_type == "movie" else rating_key,
        title=title,
        year=2020,
        poster_url=None,
        completions=completions,
        confidence={"certain": 0, "likely": 0, "plex_event_only": completions},
        last_completed_at_ms=last_ms,
        distinct_days=distinct_days,
    )


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
        confidence={"certain": 1, "likely": 2, "plex_event_only": 7},
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


class YearInReviewChapterPolishTests(unittest.TestCase):
    """Copy + signal honesty: revisits, ratings sources, busy-month titles, plain methodology."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "yir-polish.db")
        self.db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email="owner@example.com",
            plex_user_id="111",
            role="owner",
        )

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _ingest_movie(
        self,
        *,
        rating_key: str,
        occurred_at_ms: int,
        source_event_id: str,
    ) -> None:
        ingest_watch_events(
            self.db,
            [
                WatchEventInput(
                    source="plex_history",
                    source_event_id=source_event_id,
                    source_event_kind="history_played",
                    server_machine_id="srv",
                    source_user_key="111",
                    rating_key=rating_key,
                    media_type="movie",
                    occurred_at_ms=occurred_at_ms,
                    terminal=True,
                )
            ],
        )

    def test_same_day_completion_noise_is_not_a_rewatch(self) -> None:
        year = 2026
        start_ms, _ = year_bounds_ms(year)
        self.db.upsert_library_item(
            {
                "rating_key": "stuck-1",
                "media_type": "movie",
                "title": "The Autopsy of Jane Doe",
                "year": 2016,
            }
        )
        # Two finishes same UTC day, >6h apart so correlate keeps both rows —
        # still one distinct day (pause/restart / fragment noise ≠ rewatch).
        self._ingest_movie(
            rating_key="stuck-1",
            occurred_at_ms=start_ms + 1 * 3_600_000,
            source_event_id="same-a",
        )
        self._ingest_movie(
            rating_key="stuck-1",
            occurred_at_ms=start_ms + 8 * 3_600_000,
            source_event_id="same-b",
        )
        # Floor of 3 completions for YIR readiness.
        self._ingest_movie(
            rating_key="other-1",
            occurred_at_ms=start_ms + 86_400_000,
            source_event_id="other-a",
        )
        self._ingest_movie(
            rating_key="other-2",
            occurred_at_ms=start_ms + 2 * 86_400_000,
            source_event_id="other-b",
        )
        rebuild_watch_derivations(self.db, user_id="owner-1")
        rollup = build_year_rollup(self.db, user_id="owner-1", year=year)
        stuck = next(t for t in rollup.top_movies if t.rating_key == "stuck-1")
        self.assertGreaterEqual(stuck.completions, 2)
        self.assertEqual(stuck.distinct_days, 1)
        self.assertFalse(stuck.is_rewatch)

        chapter = build_top_movies(rollup, {})
        assert chapter is not None
        self.assertEqual(chapter["title"], "Movies you finished")
        self.assertNotIn("revisited", chapter["body"].lower())
        self.assertNotIn("stuck", chapter["body"].lower())

    def test_distinct_days_count_as_rewatch(self) -> None:
        year = 2026
        start_ms, _ = year_bounds_ms(year)
        self.db.upsert_library_item(
            {
                "rating_key": "rewatch-1",
                "media_type": "movie",
                "title": "Coherence",
                "year": 2013,
            }
        )
        self._ingest_movie(
            rating_key="rewatch-1",
            occurred_at_ms=start_ms + 86_400_000,
            source_event_id="day1",
        )
        self._ingest_movie(
            rating_key="rewatch-1",
            occurred_at_ms=start_ms + 10 * 86_400_000,
            source_event_id="day2",
        )
        self._ingest_movie(
            rating_key="filler-1",
            occurred_at_ms=start_ms + 20 * 86_400_000,
            source_event_id="fill",
        )
        rebuild_watch_derivations(self.db, user_id="owner-1")
        rollup = build_year_rollup(self.db, user_id="owner-1", year=year)
        chapter = build_top_movies(rollup, {})
        assert chapter is not None
        self.assertEqual(chapter["title"], "Movies that stuck")
        self.assertIn("Coherence", chapter["body"])
        self.assertIn("different days", chapter["body"])
        self.assertIn("not a pause and resume", chapter["body"])

    def test_busy_month_lists_concrete_titles(self) -> None:
        titles = [
            _title(rating_key="m1", title="High Anxiety"),
            _title(rating_key="m2", title="Tucker and Dale vs Evil"),
            _title(rating_key="s1", title="Death Note", media_type="episode", completions=12),
            _title(rating_key="m3", title="Midway"),
            _title(rating_key="m4", title="Sisu"),
        ]
        rollup = _rollup(
            monthly_counts={6: 37, 7: 10},
            peak_month_titles=titles,
        )
        chapter = build_monthly_rhythm(rollup, {})
        assert chapter is not None
        self.assertIn("June", chapter["body"])
        self.assertIn("37", chapter["body"])
        self.assertIn("High Anxiety", chapter["body"])
        self.assertIn("Tucker and Dale vs Evil", chapter["body"])
        self.assertIn("Death Note", chapter["body"])
        self.assertIn("Midway", chapter["body"])
        self.assertIn("And 1 more", chapter["body"])
        self.assertTrue(chapter["posters"])

    def test_honesty_copy_is_plain_and_short(self) -> None:
        rollup = _rollup(
            confidence={"certain": 0, "likely": 3, "plex_event_only": 97},
        )
        chapter = build_honesty(rollup, {})
        assert chapter is not None
        body = chapter["body"]
        self.assertIn("finishes attributed to you", body.lower())
        self.assertIn("3 reconstructed from progress", body)
        self.assertIn("97 marked played in Plex without progress data", body)
        for jargon in (
            "tracked completions",
            "household Plex totals",
            "uninterrupted",
            "reconstructed as likely",
            "without enough progress evidence",
            "crossing the finish line",
        ):
            self.assertNotIn(jargon, body)

    def test_ratings_include_plex_stars_on_finished_titles(self) -> None:
        year = 2026
        start_ms, _ = year_bounds_ms(year)
        self.db.upsert_library_item(
            {
                "rating_key": "plex-rated",
                "media_type": "movie",
                "title": "Arrival",
                "year": 2016,
                "plex_user_rating_stars": 5,
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "proj-rated",
                "media_type": "movie",
                "title": "Death Note",
                "year": 2017,
            }
        )
        for i, key in enumerate(("plex-rated", "proj-rated", "filler")):
            if key == "filler":
                self.db.upsert_library_item(
                    {"rating_key": "filler", "media_type": "movie", "title": "Filler", "year": 2020}
                )
            self._ingest_movie(
                rating_key=key,
                occurred_at_ms=start_ms + (i + 1) * 86_400_000,
                source_event_id=f"r-{i}",
            )
        rebuild_watch_derivations(self.db, user_id="owner-1")
        save_review(
            self.db,
            stars=5,
            title="Death Note",
            media_type="movie",
            rating_key="proj-rated",
            user_id="owner-1",
        )
        # Backdate review into the year window (save_review uses now).
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE user_title_reviews SET created_at = ? WHERE rating_key = ?",
                (start_ms / 1000.0 + 10, "proj-rated"),
            )

        signals = collect_social_signals(self.db, user_id="owner-1", year=year)
        sources = {r["source"] for r in signals["ratings"]}
        titles = {r["title"] for r in signals["ratings"]}
        self.assertIn("projectionist", sources)
        self.assertIn("plex", sources)
        self.assertIn("Death Note", titles)
        self.assertIn("Arrival", titles)

        chapter = build_ratings(_rollup(), signals)
        assert chapter is not None
        self.assertIn("Projectionist", chapter["body"])
        self.assertTrue(
            "Plex" in chapter["body"] or "plex" in chapter["body"].lower(),
            chapter["body"],
        )

    def test_projectionist_only_ratings_say_so(self) -> None:
        chapter = build_ratings(
            _rollup(),
            {
                "ratings": [
                    {
                        "title": "Death Note",
                        "stars": 5.0,
                        "source": "projectionist",
                    }
                ],
                "ratings_sources": {
                    "projectionist": True,
                    "plex": False,
                    "plex_available": False,
                },
            },
        )
        assert chapter is not None
        self.assertIn("Projectionist", chapter["body"])
        self.assertIn("no Plex library stars synced yet", chapter["body"])


if __name__ == "__main__":
    unittest.main()
