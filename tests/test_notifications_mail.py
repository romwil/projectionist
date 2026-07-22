"""Tests for the P3b notification + mail platform."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import MailSettings, Settings
from curatorx.library.db import Database
from curatorx.mail.transport import MailSendResult, mail_configured
from curatorx.notifications.arrivals import notify_arrivals
from curatorx.notifications.newsletters import (
    build_member_newsletter,
    deliver_weekly_newsletters,
)
from curatorx.notifications.service import deliver_notification
from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


class MailTransportTests(unittest.TestCase):
    def test_mail_configured_requires_provider_and_from(self) -> None:
        self.assertFalse(mail_configured(MailSettings()))
        self.assertFalse(
            mail_configured(MailSettings(enabled=True, provider="smtp", smtp_host="smtp.example"))
        )
        self.assertTrue(
            mail_configured(
                MailSettings(
                    enabled=True,
                    provider="smtp",
                    smtp_host="smtp.example",
                    from_email="curator@example.com",
                )
            )
        )
        self.assertTrue(
            mail_configured(
                MailSettings(
                    enabled=True,
                    provider="resend",
                    resend_api_key="re_test",
                    from_email="curator@example.com",
                )
            )
        )


class NotificationPlatformTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-notif-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
            "mail": {
                "enabled": True,
                "provider": "resend",
                "from_email": "curator@example.com",
                "resend_api_key": "re_test_key",
                "subject_prefix": "[CuratorX]",
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _login(self, *, plex_id: int, title: str, email: str) -> dict:
        profile = {
            "id": plex_id,
            "title": title,
            "email": email,
            "thumb": None,
        }
        with patch("curatorx.web.auth.fetch_plex_account", return_value=profile):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"tok-{plex_id}"})
        self.assertEqual(resp.status_code, 200)
        return resp.json()["user"]

    def test_notification_prefs_round_trip(self) -> None:
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        patched = self.client.patch(
            "/api/auth/me",
            json={
                "notification_email": "alerts@example.com",
                "notify_channel_email": True,
                "newsletter_opt_in": True,
            },
        )
        self.assertEqual(patched.status_code, 200)
        user = patched.json()["user"]
        self.assertEqual(user["notification_email"], "alerts@example.com")
        self.assertTrue(user["notify_channel_email"])
        self.assertTrue(user["newsletter_opt_in"])

    def test_inbox_kinds_and_unread_badge(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=1, title="Owner", email="owner@example.com")
        member = self._login(plex_id=2, title="Member", email="member@example.com")
        del owner

        # Sign back in as member for inbox reads
        self._login(plex_id=2, title="Member", email="member@example.com")
        settings = Settings.load(Path(self._tmpdir.name) / "settings.json")
        deliver_notification(
            self.db,
            settings,
            user_id=member["id"],
            kind="arrival",
            title="Now in your library: Arrival Test (1999)",
            body="A collection gap just closed.",
            related_id="arrival-test-1",
        )
        inbox = self.client.get("/api/notifications?unread_only=true")
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertGreaterEqual(body["unread_count"], 1)
        self.assertEqual(body["items"][0]["kind"], "arrival")

        seen = self.client.post("/api/notifications/seen", json={"all_unread": True})
        self.assertEqual(seen.status_code, 200)
        again = self.client.get("/api/notifications?unread_only=true")
        self.assertEqual(again.json()["unread_count"], 0)

    def test_recommendation_also_creates_notification(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=10, title="Owner", email="o@example.com")
        member = self._login(plex_id=11, title="Member", email="m@example.com")
        # Re-auth as owner to create recommendation
        self._login(plex_id=10, title="Owner", email="o@example.com")
        created = self.client.post(
            "/api/recommendations",
            json={
                "to_user_ids": [member["id"]],
                "media_type": "movie",
                "title": "Heat",
                "tmdb_id": 949,
                "year": 1995,
                "message": "Night drive energy",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["count"], 1)

        self._login(plex_id=11, title="Member", email="m@example.com")
        inbox = self.client.get("/api/notifications?unread_only=true")
        self.assertEqual(inbox.status_code, 200)
        kinds = {item["kind"] for item in inbox.json()["items"]}
        self.assertIn("recommendation", kinds)
        del owner

    def test_mail_settings_mask_and_test_send(self) -> None:
        self._enable_multi_user()
        self._login(plex_id=20, title="Owner", email="owner@example.com")
        settings = self.client.get("/api/settings")
        self.assertEqual(settings.status_code, 200)
        mail = settings.json()["mail"]
        self.assertTrue(mail.get("resend_api_key_set"))
        self.assertEqual(mail.get("resend_api_key"), "")

        import curatorx.mail as mail_mod

        with patch.object(
            mail_mod,
            "send_mail",
            return_value=MailSendResult(ok=True, provider="resend", message_id="msg_1"),
        ) as mock_send:
            resp = self.client.post(
                "/api/admin/mail/test",
                json={"to_email": "owner@example.com"},
            )
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertTrue(resp.json()["ok"])
            mock_send.assert_called_once()

    def test_weekly_newsletter_opt_in(self) -> None:
        self._enable_multi_user()
        user = self.db.create_local_user(
            user_id="local-member-1",
            display_name="LocalMember",
            password_hash="x",
            role="member",
            email="local@example.com",
        )
        self.db.update_user_profile(
            user["id"],
            newsletter_opt_in=True,
            notify_channel_inbox=True,
            notify_channel_email=False,
        )
        settings = Settings.load(Path(self._tmpdir.name) / "settings.json")
        refreshed = self.db._row_to_user(self.db.get_user(user["id"]))
        content = build_member_newsletter(self.db, settings, user=refreshed)
        self.assertIn("This week", content["subject"])
        result = deliver_weekly_newsletters(self.db, settings)
        self.assertGreaterEqual(result["delivered"], 1)

    def test_weekly_newsletter_scoped_skips_opt_out(self) -> None:
        self._enable_multi_user()
        opted = self.db.create_local_user(
            user_id="local-opted",
            display_name="OptedIn",
            password_hash="x",
            role="member",
            email="opted@example.com",
        )
        quiet = self.db.create_local_user(
            user_id="local-quiet",
            display_name="Quiet",
            password_hash="x",
            role="member",
            email="quiet@example.com",
        )
        self.db.update_user_profile(
            opted["id"],
            newsletter_opt_in=True,
            notify_channel_inbox=True,
        )
        self.db.update_user_profile(
            quiet["id"],
            newsletter_opt_in=False,
            notify_channel_inbox=True,
        )
        settings = Settings.load(Path(self._tmpdir.name) / "settings.json")
        result = deliver_weekly_newsletters(
            self.db,
            settings,
            user_ids=[opted["id"], quiet["id"]],
        )
        self.assertEqual(result["delivered"], 1)
        self.assertEqual(result["skipped_opt_out"], 1)
        self.assertEqual(result["targeted"], 2)

    def test_admin_weekly_newsletter_generate_scopes(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=30, title="Owner", email="owner30@example.com")
        member = self.db.create_local_user(
            user_id="local-nl-member",
            display_name="NlMember",
            password_hash="x",
            role="member",
            email="nl@example.com",
        )
        self.db.update_user_profile(
            owner["id"],
            newsletter_opt_in=True,
            notify_channel_inbox=True,
        )
        self.db.update_user_profile(
            member["id"],
            newsletter_opt_in=True,
            notify_channel_inbox=True,
        )

        bad = self.client.post(
            "/api/admin/weekly-newsletter/generate",
            json={"scope": "users", "user_ids": []},
        )
        self.assertEqual(bad.status_code, 400)

        missing = self.client.post(
            "/api/admin/weekly-newsletter/generate",
            json={"scope": "users", "user_ids": ["no-such-user"]},
        )
        self.assertEqual(missing.status_code, 404)

        self_resp = self.client.post(
            "/api/admin/weekly-newsletter/generate",
            json={"scope": "self"},
        )
        self.assertEqual(self_resp.status_code, 200, self_resp.text)
        self.assertEqual(self_resp.json()["scope"], "self")
        self.assertGreaterEqual(self_resp.json()["delivered"], 1)

        users_resp = self.client.post(
            "/api/admin/weekly-newsletter/generate",
            json={"scope": "users", "user_ids": [member["id"]]},
        )
        self.assertEqual(users_resp.status_code, 200, users_resp.text)
        self.assertEqual(users_resp.json()["scope"], "users")
        self.assertGreaterEqual(users_resp.json()["delivered"], 1)

        all_resp = self.client.post(
            "/api/admin/weekly-newsletter/generate",
            json={"scope": "all"},
        )
        self.assertEqual(all_resp.status_code, 200, all_resp.text)
        self.assertEqual(all_resp.json()["scope"], "all")
        self.assertGreaterEqual(all_resp.json()["delivered"], 1)

    def test_arrival_notifications_for_gap_title(self) -> None:
        self._enable_multi_user()
        owner = self.db.create_local_user(
            user_id="local-owner-1",
            display_name="LocalOwner",
            password_hash="x",
            role="owner",
            email="owner@example.com",
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cached_gap_analysis (
                    analysis_key TEXT PRIMARY KEY,
                    results_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO cached_gap_analysis (analysis_key, results_json, generated_at)
                VALUES ('director_gaps', ?, '1')
                """,
                (json.dumps([{"missing": [{"tmdb_id": 42, "title": "Gap Movie"}]}]),),
            )
        settings = Settings()
        with patch(
            "curatorx.notifications.arrivals.feed_recently_added",
            return_value={
                "items": [
                    {
                        "title": "Gap Movie",
                        "year": 2001,
                        "tmdb_id": 42,
                        "media_type": "movie",
                        "rating_key": "rk-42",
                        "added_at": 9999999999.0,
                    }
                ]
            },
        ):
            result = notify_arrivals(self.db, settings, now=10000000000.0)
        self.assertGreaterEqual(result["created"], 1)
        unread = self.db.count_unread_notifications(owner["id"])
        self.assertGreaterEqual(unread, 1)


if __name__ == "__main__":
    unittest.main()
