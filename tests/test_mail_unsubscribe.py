"""GRO-008: one-click unsubscribe turns off only that program for that person."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from projectionist import security_audit as sa
from projectionist.mail.transport import ONE_CLICK_POST
from projectionist.mail.unsubscribe import (
    UNSUBSCRIBE_PATH,
    UnsubscribeError,
    make_unsubscribe_token,
    resolve_unsubscribe_token,
)
from projectionist.web.auth import _hash_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache

PROFILE_FLAGS = ("newsletter_opt_in", "nudge_opt_in", "year_in_review_opt_in")


class MailUnsubscribeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-mail-unsubscribe-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        (Path(self._tmpdir.name) / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                    "household_domain": "https://movies.example",
                    "mail": {
                        "enabled": True,
                        "provider": "resend",
                        "from_email": "curator@example.com",
                        "resend_api_key": "re_test_key",
                    },
                }
            ),
            encoding="utf-8",
        )
        for name, role in (("owner", "owner"), ("alex", "member"), ("sam", "member")):
            self.db.create_local_user(
                user_id=f"local-{name}",
                display_name=name,
                password_hash=_hash_password("password123"),
                role=role,
            )
            self.db.update_user_profile(
                f"local-{name}",
                notification_email=f"{name}@example.com",
                notify_channel_email=True,
                newsletter_opt_in=True,
                nudge_opt_in=True,
                year_in_review_opt_in=True,
            )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _prefs(self, user_id: str) -> dict:
        user = self.db.get_user(user_id)
        return {
            **{flag: bool(user[flag]) for flag in PROFILE_FLAGS},
            "email": bool(user["notify_channel_email"]),
            "muted": json.loads(user["email_muted_kinds"] or "[]"),
        }

    def _post(self, token: str):
        return self.client.post(f"{UNSUBSCRIBE_PATH}?t={token}", data={"List-Unsubscribe": "One-Click"})

    def test_get_changes_nothing_and_post_turns_off_only_that_program(self) -> None:
        token = make_unsubscribe_token(self.db, "local-alex", "nudge")
        before_alex, before_sam = self._prefs("local-alex"), self._prefs("local-sam")

        page = self.client.get(f"{UNSUBSCRIBE_PATH}?t={token}")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("watch nudges", page.text)
        self.assertIn('method="post"', page.text)
        self.assertEqual(page.headers.get("cache-control"), "no-store")
        self.assertEqual(self._prefs("local-alex"), before_alex)

        done = self._post(token)
        self.assertEqual(done.status_code, 200, done.text)
        after = self._prefs("local-alex")
        self.assertFalse(after["nudge_opt_in"])
        self.assertEqual(after, {**before_alex, "nudge_opt_in": False})
        self.assertEqual(self._prefs("local-sam"), before_sam)

        events = self.db.list_security_events(event=sa.EMAIL_UNSUBSCRIBE)["items"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["target_id"], "local-alex")
        self.assertEqual(events[0]["detail"]["program"], "nudge")

    def test_program_without_flag_is_muted_for_email_only(self) -> None:
        from projectionist.notifications.service import _user_dict, user_wants_channel

        before = self._prefs("local-alex")
        self.assertEqual(self._post(make_unsubscribe_token(self.db, "local-alex", "arrival")).status_code, 200)
        after = self._prefs("local-alex")
        self.assertEqual(after, {**before, "muted": ["arrival"]})
        user = _user_dict(self.db, "local-alex")
        self.assertFalse(user_wants_channel(user, kind="arrival", channel="email"))
        self.assertTrue(user_wants_channel(user, kind="arrival", channel="inbox"))
        self.assertTrue(user_wants_channel(user, kind="recommendation", channel="email"))

    def test_member_can_turn_a_muted_program_back_on(self) -> None:
        self._post(make_unsubscribe_token(self.db, "local-alex", "arrival"))
        login = self.client.post("/api/auth/local/login", json={"username": "alex", "password": "password123"})
        self.assertEqual(login.status_code, 200, login.text)
        resp = self.client.patch("/api/auth/me", json={"email_muted_kinds": ["bogus"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["email_muted_kinds"], [])

    def test_forged_tampered_and_other_person_tokens_are_refused(self) -> None:
        token = make_unsubscribe_token(self.db, "local-alex", "digest")
        body, sig = token.split(".")
        forged = make_unsubscribe_token(self.db, "local-sam", "digest").split(".")[0] + "." + sig
        for bad in ("", "nope", f"{body}.AAAA", forged, token + "x"):
            with self.subTest(bad=bad[:12]):
                with self.assertRaises(UnsubscribeError):
                    resolve_unsubscribe_token(self.db, bad)
                self.assertEqual(self._post(bad).status_code, 400)
        self.assertTrue(self._prefs("local-alex")["newsletter_opt_in"])
        self.assertTrue(self._prefs("local-sam")["newsletter_opt_in"])

    def test_link_stops_working_after_delete_my_data(self) -> None:
        token = make_unsubscribe_token(self.db, "local-alex", "digest")
        self.db.erase_user_data("local-alex")
        resp = self._post(token)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("expired", resp.text)
        fresh = make_unsubscribe_token(self.db, "local-alex", "digest")
        self.assertNotEqual(fresh, token)
        self.assertEqual(self._post(fresh).status_code, 200)

    def test_email_carries_one_click_headers_for_this_person_and_program(self) -> None:
        from projectionist.notifications import service

        with mock.patch.object(service, "send_mail") as sent:
            service.deliver_notification(
                self.db,
                self._settings(),
                user_id="local-alex",
                kind="recommendation",
                title="Sam thinks you'd like Heat",
            )
        kwargs = sent.call_args.kwargs
        self.assertTrue(kwargs["one_click"])
        url = urlparse(kwargs["list_unsubscribe"])
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", f"https://movies.example{UNSUBSCRIBE_PATH}")
        self.assertIn(kwargs["list_unsubscribe"], kwargs["body_text"])
        target = resolve_unsubscribe_token(self.db, parse_qs(url.query)["t"][0])
        self.assertEqual((target.user_id, target.kind), ("local-alex", "recommendation"))

    def test_muted_program_sends_no_email(self) -> None:
        from projectionist.notifications import service

        self._post(make_unsubscribe_token(self.db, "local-alex", "recommendation"))
        with mock.patch.object(service, "send_mail") as sent:
            result = service.deliver_notification(
                self.db, self._settings(), user_id="local-alex", kind="recommendation", title="Heat"
            )
        sent.assert_not_called()
        self.assertIsNotNone(result["notification"])

    def test_smtp_message_has_list_unsubscribe_post(self) -> None:
        from projectionist.config_store import MailSettings
        from projectionist.mail import transport

        sent = []
        smtp = mock.MagicMock()
        smtp.__enter__.return_value.send_message.side_effect = sent.append
        url = "https://movies.example/api/mail/unsubscribe?t=x"
        with mock.patch.object(transport.smtplib, "SMTP", return_value=smtp):
            transport._send_smtp(
                MailSettings(enabled=True, provider="smtp", smtp_host="smtp.example", smtp_use_tls=False,
                             from_email="curator@example.com"),
                to_email="alex@example.com", subject="s", text="b", html="<p>b</p>",
                list_unsubscribe=f"<{url}>", one_click=True,
            )
        self.assertEqual(sent[0]["List-Unsubscribe"], f"<{url}>")
        self.assertEqual(sent[0]["List-Unsubscribe-Post"], ONE_CLICK_POST)

    def _settings(self):
        from projectionist.config_store import load_merged_settings

        return load_merged_settings(Path(self._tmpdir.name))


if __name__ == "__main__":
    unittest.main()
