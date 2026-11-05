"""Lifecycle and invite mail carry a way back in and a way out (GRO-008, GRO-009)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.config_store import MailSettings, Settings
from projectionist.invites import POSITIONING_SENTENCE, create_household_invite, invite_email
from projectionist.library.db import Database
from projectionist.mail.links import app_base_url, lifecycle_footer
from projectionist.mail.transport import MailSendResult, send_mail
from projectionist.notifications.newsletters import NEWSLETTER_FOOTER
from projectionist.notifications.service import deliver_notification
from projectionist.notifications.weekly_letter import deliver_weekly_letter, save_letter_settings
from projectionist.web.session_tokens import clear_session_secret_cache

OWNER = "bootstrap-owner"


def _settings(*, domain: str = "", provider: str = "smtp") -> Settings:
    mail = MailSettings(
        enabled=True,
        provider=provider,
        from_email="house@example.com",
        smtp_host="smtp.example.com",
        resend_api_key="re_test",
    )
    return Settings(mail=mail, household_domain=domain)


def _db(tmp: str) -> Database:
    db = Database(Path(tmp) / "test.db")
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET email = ?, display_name = ? WHERE id = ?",
            ("owner@example.com", "Will", OWNER),
        )
    db.update_user_profile(OWNER, notify_channel_email=True, newsletter_opt_in=True)
    return db


class FooterTests(unittest.TestCase):
    def test_base_url_from_household_domain(self) -> None:
        self.assertEqual(app_base_url(Settings()), "")
        self.assertEqual(app_base_url(Settings(household_domain="movies.example.com/")), "https://movies.example.com")
        self.assertEqual(app_base_url(Settings(household_domain="http://10.0.0.5:8788")), "http://10.0.0.5:8788")

    def test_footer_links_carry_no_token(self) -> None:
        footer = lifecycle_footer(Settings(household_domain="movies.example.com"))
        self.assertIn("https://movies.example.com/inbox", footer.text)
        self.assertIn("https://movies.example.com/settings/notifications", footer.text)
        self.assertIn('href="https://movies.example.com/settings/notifications"', footer.html)
        self.assertEqual(footer.list_unsubscribe, "https://movies.example.com/settings/notifications")
        self.assertNotIn("?", footer.text)

    def test_footer_without_domain_still_says_how_to_stop(self) -> None:
        footer = lifecycle_footer(Settings())
        self.assertIn("Settings → Notifications", footer.text)
        self.assertIn("home network", footer.text)
        self.assertIsNone(footer.list_unsubscribe)


class TransportHeaderTests(unittest.TestCase):
    def test_smtp_sets_list_unsubscribe(self) -> None:
        smtp = MagicMock()
        with patch("projectionist.mail.transport.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp
            send_mail(
                _settings(),
                to_email="a@example.com",
                subject="Hi",
                body_text="Body",
                list_unsubscribe="https://movies.example.com/settings/notifications",
            )
        msg = smtp.send_message.call_args.args[0]
        self.assertEqual(msg["List-Unsubscribe"], "<https://movies.example.com/settings/notifications>")
        self.assertIsNone(msg["List-Unsubscribe-Post"])

    def test_smtp_omits_header_without_url(self) -> None:
        smtp = MagicMock()
        with patch("projectionist.mail.transport.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp
            send_mail(_settings(), to_email="a@example.com", subject="Hi", body_text="Body")
        self.assertIsNone(smtp.send_message.call_args.args[0]["List-Unsubscribe"])

    def test_resend_sets_list_unsubscribe(self) -> None:
        client = MagicMock()
        client.post.return_value = MagicMock(status_code=200, json=lambda: {"id": "m1"})
        with patch("projectionist.mail.transport.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value = client
            send_mail(
                _settings(provider="resend"),
                to_email="a@example.com",
                subject="Hi",
                body_text="Body",
                list_unsubscribe="https://movies.example.com/settings/notifications",
            )
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(
            payload["headers"], {"List-Unsubscribe": "<https://movies.example.com/settings/notifications>"}
        )


class LifecycleMailTests(unittest.TestCase):
    def test_notification_email_links_back_and_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            with patch(
                "projectionist.notifications.service.send_mail",
                return_value=MailSendResult(ok=True, provider="smtp"),
            ) as send:
                result = deliver_notification(
                    db,
                    _settings(domain="movies.example.com"),
                    user_id=OWNER,
                    kind="digest",
                    title="This week for you, Will",
                    body=f"Hi Will,\n\nPicks.\n\n{NEWSLETTER_FOOTER}\n",
                    outbound_body="Hi Will,\n\nPicks.",
                )
            inbox = db.list_notifications_for_user(OWNER)
        self.assertTrue(result["emailed"])
        kwargs = send.call_args.kwargs
        self.assertIn("https://movies.example.com/inbox", kwargs["body_text"])
        self.assertIn("Stop these emails: https://movies.example.com/settings/notifications", kwargs["body_text"])
        self.assertNotIn(NEWSLETTER_FOOTER, kwargs["body_text"])
        self.assertIn('href="https://movies.example.com/inbox"', kwargs["body_html"])
        self.assertEqual(kwargs["list_unsubscribe"], "https://movies.example.com/settings/notifications")
        rows = inbox["items"] if isinstance(inbox, dict) else inbox
        self.assertIn(NEWSLETTER_FOOTER, rows[0]["body"])

    def test_owner_letter_email_points_at_newsletters_admin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            db.upsert_library_item({"rating_key": "rk-a", "media_type": "movie", "title": "Heat", "year": 1995})
            save_letter_settings(db, email=True)
            with patch("projectionist.mail.send_mail") as send:
                result = deliver_weekly_letter(db, _settings(domain="movies.example.com"), force=True)
        self.assertEqual(result["emailed"], 1)
        kwargs = send.call_args.kwargs
        self.assertIn("Stop these emails: https://movies.example.com/admin/newsletters", kwargs["body_text"])
        self.assertEqual(kwargs["list_unsubscribe"], "https://movies.example.com/admin/newsletters")


class InviteMailTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-invite-mail-secret-value"
        clear_session_secret_cache()

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        clear_session_secret_cache()

    def test_invite_email_names_inviter_and_expiry(self) -> None:
        message = invite_email(inviter="Will", join_url="https://m.example.com/join?token=t", expires_at=1_800_000_000)
        self.assertEqual(message["subject"], "Will invited you to join Projectionist")
        self.assertIn(POSITIONING_SENTENCE, message["text"])
        self.assertIn("works once and expires on January 15, 2027", message["text"])
        self.assertIn('href="https://m.example.com/join?token=t"', message["html"])

    def test_invite_is_actually_emailed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _db(tmp)
            with patch(
                "projectionist.invites.send_mail",
                return_value=MailSendResult(ok=True, provider="smtp"),
            ) as send:
                created = create_household_invite(
                    db,
                    _settings(domain="movies.example.com"),
                    owner_id=OWNER,
                    email="cousin@example.com",
                )
        self.assertTrue(created["emailed"])
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "cousin@example.com")
        self.assertEqual(kwargs["subject"], "Will invited you to join Projectionist")
        self.assertIn(created["join_url"], kwargs["body_text"])
        self.assertTrue(created["join_url"].startswith("https://movies.example.com/join?token="))


if __name__ == "__main__":
    unittest.main()
