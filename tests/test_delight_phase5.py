"""Tests for Delight Phase 5: curator depth (nudge, syllabus, acquire, mood, callbacks)."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.acquire import build_acquire_path
from projectionist.config_store import FeatureFlags, SeerrSettings, Settings
from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.library.feeds import feed_seasonal_spotlight
from projectionist.memory import UserMemoryService
from projectionist.notifications.nudges import (
    build_nudge_copy,
    deliver_enthusiast_nudges,
    pick_nudge_title,
    recently_watched_context,
)
from projectionist.notifications.service import user_wants_channel
from projectionist.syllabus import build_syllabus_for_course, syllabus_chat_prompt


class NudgeUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()
        self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "year": 1995,
                "view_count": 0,
                "tmdb_id": 949,
            }
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_user_wants_nudge_requires_opt_in(self) -> None:
        user = {
            "notify_channel_inbox": True,
            "notify_channel_email": True,
            "nudge_opt_in": False,
        }
        self.assertFalse(user_wants_channel(user, kind="nudge", channel="inbox"))
        user["nudge_opt_in"] = True
        self.assertTrue(user_wants_channel(user, kind="nudge", channel="inbox"))

    def test_pick_and_deliver_opt_in_only(self) -> None:
        pick = pick_nudge_title(self.db)
        self.assertIsNotNone(pick)
        assert pick is not None
        copy = build_nudge_copy(self.db, pick=pick)
        self.assertEqual(copy["title"], pick["title"])
        self.assertIn("You have to see this", copy["subject"])
        self.assertNotIn("recently watched:", copy["body"].lower())

        self.db.update_user_profile(
            BOOTSTRAP_OWNER_ID, nudge_opt_in=True, notify_channel_inbox=True
        )
        settings = Settings()
        result = deliver_enthusiast_nudges(self.db, settings, now=1_700_000_000.0)
        self.assertGreaterEqual(result["delivered"], 1)
        notes = self.db.list_notifications_for_user(BOOTSTRAP_OWNER_ID, kinds=["nudge"])
        self.assertTrue(notes)

    def test_recently_watched_context(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-seen",
                "media_type": "movie",
                "title": "Seen Recently",
                "year": 2001,
                "view_count": 1,
                "last_viewed_at": 1_700_000_000.0,
            }
        )
        recent = recently_watched_context(self.db, now=1_700_000_100.0, limit=5)
        titles = [r["title"] for r in recent]
        self.assertIn("Seen Recently", titles)


class SyllabusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()
        list_id = uuid.uuid4().hex
        self.db.create_curated_list(
            list_id=list_id,
            user_id=None,
            name="Kurosawa Lab",
            description="Study the masters",
            list_kind="course",
        )
        for idx, title in enumerate(("Rashomon", "Seven Samurai", "Ikiru")):
            self.db.add_curated_list_item(
                item_id=uuid.uuid4().hex,
                list_id=list_id,
                user_id=None,
                tmdb_id=1000 + idx,
                tvdb_id=None,
                media_type="movie",
                title=title,
            )
            item = self.db.find_curated_list_item(list_id, title=title)
            if item:
                self.db.update_curated_list_item(
                    list_id, item["id"], note=f"Watch for craft in {title}"
                )
        self.db.set_curated_list_visibility(list_id, visibility="published")
        self.list_id = list_id
        self.user_id = BOOTSTRAP_OWNER_ID

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_build_multi_session_syllabus(self) -> None:
        payload = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        self.assertTrue(payload["created"])
        self.assertGreaterEqual(len(payload["sessions"]), 2)
        prompt = syllabus_chat_prompt(payload["sessions"][0], course_name="Kurosawa Lab")
        self.assertIn("multi-session syllabus", prompt)
        again = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        self.assertFalse(again["created"])
        self.assertEqual(len(again["sessions"]), len(payload["sessions"]))


class AcquirePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_in_library_skips_request(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-owned",
                "media_type": "movie",
                "title": "Owned Film",
                "year": 1999,
                "tmdb_id": 42,
                "view_count": 0,
            }
        )
        settings = Settings(
            features=FeatureFlags(seerr_enabled=True),
            seerr=SeerrSettings(url="http://seerr.test", api_key="x"),
        )
        path = build_acquire_path(
            self.db,
            settings,
            title="Owned Film",
            media_type="movie",
            tmdb_id=42,
        )
        self.assertEqual(path["availability"], "in_library")
        self.assertIsNone(path["confirmation_token"])
        self.assertEqual(path["steps"][2]["status"], "skipped")

    def test_requestable_creates_pending_token(self) -> None:
        settings = Settings(
            features=FeatureFlags(seerr_enabled=True),
            seerr=SeerrSettings(
                url="http://seerr.test",
                api_key="x",
                require_linked_user_for_requests=False,
            ),
        )
        path = build_acquire_path(
            self.db,
            settings,
            title="Missing Film",
            media_type="movie",
            tmdb_id=99,
            user_id=BOOTSTRAP_OWNER_ID,
        )
        self.assertEqual(path["availability"], "requestable")
        self.assertTrue(path["requires_consent"])
        self.assertTrue(path["confirmation_token"])


class SeasonalAnniversaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        # 2026-07-18 is a Saturday; seed a real month+day match so re-validation keeps it.
        self.db.upsert_library_item(
            {
                "rating_key": "rk-ann",
                "media_type": "movie",
                "title": "Anniversary Pick",
                "year": 2010,
                "release_date": "2010-07-18",
                "view_count": 0,
            }
        )
        # Year-only / wrong-day junk must not appear on the weekend anniversary rail.
        self.db.upsert_library_item(
            {
                "rating_key": "rk-year-only",
                "media_type": "movie",
                "title": "10 Cloverfield Lane",
                "year": 2016,
                "view_count": 0,
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-wrong-day",
                "media_type": "movie",
                "title": "Wrong Day Film",
                "year": 2010,
                "release_date": "2010-03-01",
                "view_count": 0,
            }
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_anniversaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    anniversary_type TEXT NOT NULL,
                    anniversary_text TEXT NOT NULL,
                    scanned_date TEXT NOT NULL
                )
                """
            )
            rows = {
                str(r["rating_key"]): int(r["id"])
                for r in conn.execute(
                    "SELECT id, rating_key FROM library_items"
                ).fetchall()
            }
            for rating_key, text in (
                ("rk-ann", "Released 16 years ago today"),
                ("rk-year-only", "Released 10 years ago today"),
                ("rk-wrong-day", "Released 16 years ago today"),
            ):
                conn.execute(
                    """
                    INSERT INTO daily_anniversaries
                        (item_id, anniversary_type, anniversary_text, scanned_date)
                    VALUES (?, 'release_anniversary', ?, ?)
                    """,
                    (rows[rating_key], text, "2026-07-18"),
                )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_weekend_uses_anniversary_rows(self) -> None:
        payload = feed_seasonal_spotlight(
            self.db, today=date(2026, 7, 18), limit=6, prefer_snapshot=False
        )
        self.assertEqual(payload["mode"], "weekend_anniversary")
        titles = [item.get("title") for item in payload["items"]]
        self.assertIn("Anniversary Pick", titles)
        self.assertNotIn("10 Cloverfield Lane", titles)
        self.assertNotIn("Wrong Day Film", titles)

    def test_stale_year_only_anniversaries_do_not_fill_rail(self) -> None:
        """Poisoned daily_anniversaries without matching release_date must not win the rail."""
        with self.db.connect() as conn:
            conn.execute("DELETE FROM daily_anniversaries")
            junk = conn.execute(
                "SELECT id FROM library_items WHERE rating_key = 'rk-year-only'"
            ).fetchone()
            assert junk is not None
            conn.execute(
                """
                INSERT INTO daily_anniversaries
                    (item_id, anniversary_type, anniversary_text, scanned_date)
                VALUES (?, 'release_anniversary', 'Released 10 years ago today', ?)
                """,
                (int(junk["id"]), "2026-07-18"),
            )
        payload = feed_seasonal_spotlight(
            self.db, today=date(2026, 7, 18), limit=6, prefer_snapshot=False
        )
        self.assertNotEqual(payload["mode"], "weekend_anniversary")
        titles = [item.get("title") for item in payload["items"]]
        self.assertNotIn("10 Cloverfield Lane", titles)

    def test_poisoned_anniversary_snapshot_falls_through(self) -> None:
        """Stale weekend_anniversary snapshot without real dates must not serve filler."""
        junk_id = None
        for row in self.db.all_library_items():
            if str(row["rating_key"]) == "rk-year-only":
                junk_id = int(row["id"])
                break
        assert junk_id is not None
        self.db.save_seasonal_rail_snapshot(
            snapshot_date="2026-07-18",
            scope_id="season:summer",
            label="Weekend anniversaries",
            mode="weekend_anniversary",
            items=[
                {
                    "id": junk_id,
                    "title": "10 Cloverfield Lane",
                    "year": 2016,
                    "media_type": "movie",
                    "anniversary_text": "Released 10 years ago today",
                }
            ],
        )
        # Clear live anniversaries so fall-through cannot rebuild from the same junk.
        with self.db.connect() as conn:
            conn.execute("DELETE FROM daily_anniversaries")
        payload = feed_seasonal_spotlight(
            self.db, today=date(2026, 7, 18), limit=6, prefer_snapshot=True
        )
        self.assertFalse(payload.get("from_schedule"))
        self.assertNotEqual(payload["mode"], "weekend_anniversary")
        titles = [item.get("title") for item in payload["items"]]
        self.assertNotIn("10 Cloverfield Lane", titles)


class MoodQuickPickApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        self.db.upsert_library_item(
            {
                "rating_key": "rk-comedy",
                "media_type": "movie",
                "title": "Funny Bone",
                "year": 2000,
                "genres": '["Comedy"]',
                "view_count": 0,
            }
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_mood_quick_pick(self) -> None:
        response = self.client.get("/api/library/quick-pick?mood=laugh")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload.get("mood"), "laugh")
        self.assertIsNotNone(payload.get("item"))
        self.assertIn("mood", (payload.get("why") or "").lower())


class CallbackMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()
        self.memory = UserMemoryService(self.db)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_callback_kind_round_trips_export(self) -> None:
        note = self.memory.remember(
            caller_id=BOOTSTRAP_OWNER_ID,
            kind="callback",
            text="Our running joke about neon noir Friday nights",
        )
        self.assertEqual(note["kind"], "callback")
        exported = self.db.export_user_memory(BOOTSTRAP_OWNER_ID)
        kinds = {n["kind"] for n in exported["notes"]}
        self.assertIn("callback", kinds)

    def test_callback_title_metadata_enriches_deep_link(self) -> None:
        from projectionist.agent.tools import (
            _callback_title_metadata,
            _enrich_memory_note_deep_link,
        )

        meta = _callback_title_metadata(
            {
                "title": "The Office",
                "media_type": "show",
                "tmdb_id": 2236,
                "year": 2001,
            }
        )
        note = self.memory.remember(
            caller_id=BOOTSTRAP_OWNER_ID,
            kind="callback",
            text="the bleak UK comedy bit",
            metadata=meta,
        )
        enriched = _enrich_memory_note_deep_link(note)
        self.assertEqual(enriched["deep_link"]["title"], "The Office")
        self.assertEqual(enriched["deep_link"]["dig_in_path"], "/title/show/2236")
        self.assertTrue(enriched["deep_link"]["chat_about"])
        self.assertEqual(enriched["title_card"]["tmdb_id"], 2236)


if __name__ == "__main__":
    unittest.main()
