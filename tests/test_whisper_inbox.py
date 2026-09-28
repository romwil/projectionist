"""Named-member whisper inbox: 12-word why, not Good News, not a grab ping."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.good_news import format_good_news
from projectionist.notifications.service import deliver_notification
from projectionist.notifications.whisper import (
    WHY_WORD_LIMIT,
    clip_why,
    deliver_member_whispers,
    format_whisper_why,
    list_whispers_for_user,
    mark_whispers_seen,
    member_display_name,
    pick_whisper_title,
    word_count,
)
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from tests.admin_job_helpers import reset_admin_jobs


def _movie(
    *,
    rating_key: str,
    title: str,
    year: int,
    tmdb_id: int,
    genres: list[str] | None = None,
    view_count: int = 0,
    last_viewed_at: float | None = None,
    vote_average: float = 7.0,
) -> dict:
    return {
        "rating_key": rating_key,
        "media_type": "movie",
        "title": title,
        "year": year,
        "tmdb_id": tmdb_id,
        "genres": genres or [],
        "view_count": view_count,
        "last_viewed_at": last_viewed_at,
        "vote_average": vote_average,
        "in_radarr": 0,
    }


class WhisperCopyTests(unittest.TestCase):
    def test_why_is_named_and_twelve_words(self) -> None:
        why = format_whisper_why(
            member_name="Ada",
            title="Heat",
            seed_title="Thief",
            preset_id="classic-curator",
        )
        self.assertLessEqual(word_count(why), WHY_WORD_LIMIT)
        self.assertIn("Ada", why)
        self.assertNotIn("download complete", why.lower())
        self.assertNotIn("grabbed", why.lower())

    def test_clip_why_hard_caps_words(self) -> None:
        clipped = clip_why("one two three four five six seven eight nine ten eleven twelve thirteen")
        self.assertEqual(word_count(clipped), 12)
        self.assertTrue(clipped.startswith("one"))
        self.assertNotIn("thirteen", clipped)

    def test_forbidden_copy_is_scrubbed(self) -> None:
        why = format_whisper_why(member_name="Ada", title="Heat")
        self.assertNotIn("download complete", why.lower())
        scrubbed = clip_why("Ada, download complete for Heat tonight on the shelf now extra")
        self.assertIn("download complete", scrubbed.lower())
        # The public formatter never emits grab-client language even if a seed is messy.
        messy = format_whisper_why(
            member_name="Ada",
            title="download complete",
            seed_title="download complete",
        )
        self.assertNotIn("download complete", messy.lower())
        self.assertLessEqual(word_count(messy), WHY_WORD_LIMIT)

    def test_whisper_is_not_good_news_copy(self) -> None:
        headline, body = format_good_news(
            title="Gap Movie",
            year=2001,
            source="gap",
            curator_name="Ada",
            preset_id="classic-curator",
        )
        why = format_whisper_why(member_name="Will", title="Gap Movie", preset_id="classic-curator")
        self.assertIn("good news", headline.lower())
        self.assertNotIn("good news", why.lower())
        self.assertIn("Will", why)
        self.assertNotEqual(body.lower(), why.lower())

    def test_member_display_name_prefers_preferred(self) -> None:
        self.assertEqual(
            member_display_name({"preferred_name": "Will", "display_name": "wrompala"}),
            "Will",
        )


class WhisperDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "whisper.db")
        self.settings = Settings()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_delivers_to_named_member_not_just_owner(self) -> None:
        owner = self.db.create_local_user(
            user_id="owner-1",
            display_name="Owner",
            password_hash="x",
            role="owner",
        )
        member = self.db.create_local_user(
            user_id="member-1",
            display_name="wrompala",
            password_hash="x",
            role="member",
        )
        self.db.update_user_profile(member["id"], preferred_name="Will")
        self.db.upsert_library_items(
            [
                _movie(
                    rating_key="rk-heat",
                    title="Heat",
                    year=1995,
                    tmdb_id=949,
                    genres=["Crime", "Drama"],
                    view_count=1,
                    last_viewed_at=1_700_000_000.0,
                ),
                _movie(
                    rating_key="rk-thief",
                    title="Thief",
                    year=1981,
                    tmdb_id=11334,
                    genres=["Crime", "Thriller"],
                    vote_average=8.2,
                ),
            ]
        )
        result = deliver_member_whispers(self.db, self.settings, now=1_710_000_000.0)
        self.assertGreaterEqual(result["created"], 2)
        owner_rows = list_whispers_for_user(self.db, owner["id"])
        member_rows = list_whispers_for_user(self.db, member["id"])
        self.assertEqual(len(owner_rows), 1)
        self.assertEqual(len(member_rows), 1)
        self.assertEqual(member_rows[0]["kind"], "whisper")
        self.assertEqual(member_rows[0]["member_name"], "Will")
        self.assertLessEqual(word_count(member_rows[0]["why"]), WHY_WORD_LIMIT)
        self.assertIn("Will", member_rows[0]["why"])
        self.assertNotIn("download complete", member_rows[0]["why"].lower())
        self.assertNotEqual(member_rows[0]["id"], owner_rows[0]["id"])

    def test_skips_youth_and_does_not_repeat_the_week(self) -> None:
        member = self.db.create_local_user(
            user_id="member-2",
            display_name="Ada",
            password_hash="x",
            role="member",
        )
        youth = self.db.create_local_user(
            user_id="youth-1",
            display_name="Kid",
            password_hash="x",
            role="member",
        )
        with self.db.connect() as conn:
            conn.execute("UPDATE users SET is_youth = 1 WHERE id = ?", (youth["id"],))
        self.db.upsert_library_items(
            [_movie(rating_key="rk-1", title="Heat", year=1995, tmdb_id=949)]
        )
        first = deliver_member_whispers(self.db, self.settings, now=1_710_000_000.0)
        second = deliver_member_whispers(self.db, self.settings, now=1_710_000_100.0)
        self.assertGreaterEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(list_whispers_for_user(self.db, youth["id"]), [])
        self.assertEqual(len(list_whispers_for_user(self.db, member["id"])), 1)

    def test_pick_prefers_member_taste_cluster(self) -> None:
        member = self.db.create_local_user(
            user_id="member-3",
            display_name="Ada",
            password_hash="x",
            role="member",
        )
        self.db.set_user_taste_weight(member["id"], "noir", 0.9)
        self.db.upsert_library_items(
            [
                _movie(
                    rating_key="rk-rom",
                    title="Pretty Woman",
                    year=1990,
                    tmdb_id=114,
                    genres=["Romance", "Comedy"],
                    vote_average=9.0,
                ),
                _movie(
                    rating_key="rk-noir",
                    title="The Killers",
                    year=1946,
                    tmdb_id=981,
                    genres=["Noir", "Crime"],
                    vote_average=7.1,
                ),
            ]
        )
        pick = pick_whisper_title(self.db, user_id=member["id"])
        self.assertIsNotNone(pick)
        self.assertEqual(pick["title"], "The Killers")
        self.assertEqual(pick["cluster"], "noir")

    def test_clear_all_whispers_leaves_good_news(self) -> None:
        member = self.db.create_local_user(
            user_id="member-4",
            display_name="Ada",
            password_hash="x",
            role="member",
        )
        self.db.upsert_library_items(
            [_movie(rating_key="rk-1", title="Heat", year=1995, tmdb_id=949)]
        )
        deliver_member_whispers(self.db, self.settings, now=1_710_000_000.0)
        deliver_notification(
            self.db,
            self.settings,
            user_id=member["id"],
            kind="arrival",
            title="Good news from Curator — Heat (1995) is on the shelf.",
            body="A collection gap just closed — this is not a download ping.",
            related_id="arrival-heat-member-4",
            force_inbox=True,
        )
        updated = mark_whispers_seen(self.db, member["id"], all_unread=True)
        self.assertGreaterEqual(updated, 1)
        self.assertEqual(list_whispers_for_user(self.db, member["id"], unread_only=True), [])
        arrivals = self.db.list_notifications_for_user(
            member["id"], unread_only=True, kinds=["arrival"]
        )
        self.assertEqual(len(arrivals), 1)


class WhisperApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-whisper-session-secret-value"
        os.environ["PROJECTIONIST_ALLOW_OPEN_JOIN"] = "1"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_jobs()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_ALLOW_OPEN_JOIN", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True, "open_auto_provision": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )

    def _login(self, *, plex_id: int, title: str, email: str) -> dict:
        profile = {"id": plex_id, "title": title, "email": email, "thumb": None}
        with patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"tok-{plex_id}"})
        self.assertEqual(resp.status_code, 200)
        return resp.json()["user"]

    def test_member_inbox_is_isolated_and_named(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=11, title="Owner", email="owner@example.com")
        member = self._login(plex_id=12, title="Member", email="member@example.com")
        self.db.update_user_profile(member["id"], preferred_name="Will")
        self.db.upsert_library_items(
            [
                _movie(
                    rating_key="rk-heat",
                    title="Heat",
                    year=1995,
                    tmdb_id=949,
                    genres=["Crime"],
                    view_count=1,
                    last_viewed_at=1_700_000_000.0,
                ),
                _movie(
                    rating_key="rk-thief",
                    title="Thief",
                    year=1981,
                    tmdb_id=11334,
                    genres=["Crime"],
                ),
            ]
        )
        deliver_notification(
            self.db,
            Settings.load(Path(self._tmpdir.name) / "settings.json"),
            user_id=owner["id"],
            kind="arrival",
            title="Good news from Curator — Heat (1995) is on the shelf.",
            body="A collection gap just closed.",
            related_id="arrival-owner-only",
            force_inbox=True,
        )

        self._login(plex_id=12, title="Member", email="member@example.com")
        inbox = self.client.get("/api/whispers?unread_only=true")
        self.assertEqual(inbox.status_code, 200, inbox.text)
        body = inbox.json()
        self.assertEqual(body["member_name"], "Will")
        self.assertGreaterEqual(body["count"], 1)
        item = body["items"][0]
        self.assertEqual(item["kind"], "whisper")
        self.assertLessEqual(word_count(item["why"]), WHY_WORD_LIMIT)
        self.assertIn("Will", item["why"])
        self.assertNotIn("download complete", json.dumps(body).lower())
        self.assertNotIn("good news", json.dumps(body).lower())

        self._login(plex_id=11, title="Owner", email="owner@example.com")
        owner_inbox = self.client.get("/api/whispers?unread_only=true")
        self.assertEqual(owner_inbox.status_code, 200)
        owner_ids = {row["id"] for row in owner_inbox.json()["items"]}
        self.assertNotIn(item["id"], owner_ids)
        owner_kinds = {row["kind"] for row in owner_inbox.json()["items"]}
        self.assertNotIn("arrival", owner_kinds)

        self._login(plex_id=12, title="Member", email="member@example.com")
        seen = self.client.post("/api/whispers/seen", json={"all_unread": True})
        self.assertEqual(seen.status_code, 200)
        self.assertGreaterEqual(seen.json()["updated"], 1)
        empty = self.client.get("/api/whispers?unread_only=true")
        self.assertEqual(empty.json()["unread_count"], 0)

        still_arrival = self.db.list_notifications_for_user(
            owner["id"], unread_only=True, kinds=["arrival"]
        )
        self.assertEqual(len(still_arrival), 1)


if __name__ == "__main__":
    unittest.main()
