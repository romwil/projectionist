"""BD-4 Youth guardrails: memory off by default, local-or-none chat route,
confirmed + notified + audited Youth toggle that never opens earlier memory."""

from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from projectionist.agent.tools import ToolRegistry, build_system_prompt, build_tool_definitions
from projectionist.config_store import Settings, YouthSettings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.db.migrations import _widen_notification_kind
from projectionist.memory import MemoryAccessError, UserMemoryService
from projectionist.models.schemas import PreferenceSignal
from projectionist.preferences.store import remember_preference
from projectionist.web.auth import _hash_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from projectionist.youth.chat_route import (
    YOUTH_CHAT_LOCAL_NOT_LOCAL_NOTICE,
    YOUTH_CHAT_LOCAL_NOT_READY_NOTICE,
    YOUTH_CHAT_OFF_NOTICE,
    is_local_base_url,
    resolve_youth_chat_route,
)
from projectionist.youth.memory_policy import curator_memory_paused

SECRET_NOTE = "secret-adult-note-about-a-private-diagnosis"
MEMORY_TOOLS = {"remember_about_user", "remember_preference", "recall_user_memory"}

CLOUD_SETTINGS = dict(
    llm_provider="openai",
    llm_base_url="https://api.openai.com/v1",
    llm_api_key="sk-household-cloud",
    llm_model="gpt-4o-mini",
)


def _local_youth(**extra) -> YouthSettings:
    return YouthSettings(
        chat_route="local",
        local_base_url="http://192.168.1.20:11434/v1",
        local_model="llama3.2",
        **extra,
    )


class YouthSettingsDefaultsTests(unittest.TestCase):
    def test_defaults_are_memory_off_and_no_model(self) -> None:
        youth = Settings().youth
        self.assertFalse(youth.memory_enabled)
        self.assertEqual(youth.chat_route, "none")

    def test_legacy_settings_file_keeps_loading_with_safe_defaults(self) -> None:
        settings = Settings.from_mapping({"youth": {"max_content_rating": "PG"}})
        self.assertEqual(settings.youth.max_content_rating, "PG")
        self.assertFalse(settings.youth.memory_enabled)
        self.assertEqual(settings.youth.chat_route, "none")

    def test_memory_paused_only_for_youth_while_off(self) -> None:
        off = Settings()
        on = Settings(youth=YouthSettings(memory_enabled=True))
        self.assertTrue(curator_memory_paused(off, is_youth=True))
        self.assertFalse(curator_memory_paused(off, is_youth=False))
        self.assertFalse(curator_memory_paused(on, is_youth=True))


class YouthChatRouteTests(unittest.TestCase):
    def test_local_url_classification(self) -> None:
        for url in (
            "http://localhost:11434/v1",
            "http://127.0.0.1:1234/v1",
            "http://192.168.1.20:11434/v1",
            "http://10.10.1.202:11434/v1",
            "http://ollama:11434/v1",
            "http://nas.local:11434/v1",
            "http://llm.home.arpa/v1",
        ):
            self.assertTrue(is_local_base_url(url), url)
        for url in (
            "https://api.openai.com/v1",
            "https://api.anthropic.com",
            "http://8.8.8.8/v1",
            "ftp://192.168.1.2/",
            "",
            "not a url",
        ):
            self.assertFalse(is_local_base_url(url), url)

    def test_default_route_is_none_with_notice_even_when_household_cloud_is_set(self) -> None:
        route = resolve_youth_chat_route(Settings(**CLOUD_SETTINGS))
        self.assertIsNone(route.settings)
        self.assertEqual(route.notice, YOUTH_CHAT_OFF_NOTICE)

    def test_local_route_without_url_or_model_fails_closed(self) -> None:
        route = resolve_youth_chat_route(
            Settings(**CLOUD_SETTINGS, youth=YouthSettings(chat_route="local"))
        )
        self.assertIsNone(route.settings)
        self.assertEqual(route.notice, YOUTH_CHAT_LOCAL_NOT_READY_NOTICE)

    def test_local_route_pointing_at_cloud_fails_closed(self) -> None:
        youth = YouthSettings(
            chat_route="local", local_base_url="https://api.openai.com/v1", local_model="gpt-4o"
        )
        route = resolve_youth_chat_route(Settings(**CLOUD_SETTINGS, youth=youth))
        self.assertIsNone(route.settings)
        self.assertEqual(route.notice, YOUTH_CHAT_LOCAL_NOT_LOCAL_NOTICE)

    def test_local_route_replaces_household_model_and_drops_the_cloud_key(self) -> None:
        route = resolve_youth_chat_route(Settings(**CLOUD_SETTINGS, youth=_local_youth()))
        self.assertIsNone(route.notice)
        assert route.settings is not None
        self.assertEqual(route.settings.llm_provider, "ollama")
        self.assertEqual(route.settings.llm_base_url, "http://192.168.1.20:11434/v1")
        self.assertEqual(route.settings.llm_model, "llama3.2")
        self.assertEqual(route.settings.llm_api_key, "")
        self.assertEqual(route.settings.llm_embedding_base_url, "")


class _DbCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "projectionist.db"
        self.db = Database(self.path)
        for user_id, name, role in (("owner", "Owner", "owner"), ("adult", "Adult", "member")):
            self.db.create_local_user(user_id=user_id, display_name=name, password_hash="x", role=role)
        self.service = UserMemoryService(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class YouthMemoryReviewTests(_DbCase):
    def test_toggle_on_does_not_open_existing_adult_memory(self) -> None:
        self.service.remember(caller_id="adult", kind="self_disclosure", text=SECRET_NOTE)
        self.db.set_user_youth("adult", True)
        notes = self.service.recall(caller_id="owner", caller_role="owner", target_id="adult")
        self.assertEqual(notes, [])
        # The member still sees their own memory.
        own = self.service.recall(caller_id="adult", caller_role="member")
        self.assertEqual([n["text"] for n in own], [SECRET_NOTE])

    def test_owner_sees_only_notes_written_after_youth_started(self) -> None:
        self.service.remember(caller_id="adult", kind="note", text=SECRET_NOTE)
        self.db.set_user_youth("adult", True)
        self.service.remember(caller_id="adult", kind="note", text="likes dragons")
        notes = self.service.recall(caller_id="owner", caller_role="owner", target_id="adult")
        self.assertEqual([n["text"] for n in notes], ["likes dragons"])

    def test_off_then_on_restarts_the_review_window(self) -> None:
        self.db.set_user_youth("adult", True)
        self.service.remember(caller_id="adult", kind="note", text="first youth note")
        self.db.set_user_youth("adult", False)
        with self.assertRaises(MemoryAccessError):
            self.service.recall(caller_id="owner", caller_role="owner", target_id="adult")
        time.sleep(0.01)
        self.db.set_user_youth("adult", True)
        notes = self.service.recall(caller_id="owner", caller_role="owner", target_id="adult")
        self.assertEqual(notes, [])

    def test_setting_youth_on_twice_keeps_the_original_start(self) -> None:
        self.db.set_user_youth("adult", True)
        first = self.db.youth_since("adult")
        time.sleep(0.01)
        self.db.set_user_youth("adult", True)
        self.assertEqual(self.db.youth_since("adult"), first)

    def test_account_created_as_youth_starts_at_creation(self) -> None:
        invite = self.db.create_invite(token_hash="h" * 64, created_by="owner", is_youth=True)
        self.db.create_local_user_and_redeem_invite(
            invite_id=invite["id"],
            user_id="kid",
            display_name="Kid",
            password_hash="x",
            role="member",
            is_youth=True,
        )
        self.assertIsNotNone(self.db.youth_since("kid"))
        self.service.remember(caller_id="kid", kind="note", text="loves animation")
        notes = self.service.recall(caller_id="owner", caller_role="owner", target_id="kid")
        self.assertEqual([n["text"] for n in notes], ["loves animation"])


class YouthGuardrailMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "projectionist.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_existing_youth_fail_closed_unless_joined_as_youth(self) -> None:
        db = Database(self.path)
        db.create_local_user(user_id="owner", display_name="Owner", password_hash="x", role="owner")
        db.create_local_user(user_id="flipped", display_name="F", password_hash="x", role="member")
        invite = db.create_invite(token_hash="k" * 64, created_by="owner", is_youth=True)
        db.create_local_user_and_redeem_invite(
            invite_id=invite["id"], user_id="kid", display_name="Kid",
            password_hash="x", role="member", is_youth=True,
        )
        with db.connect() as conn:
            conn.execute("UPDATE users SET created_at = 1000.0 WHERE id IN ('kid', 'flipped')")
            conn.execute("UPDATE users SET is_youth = 1, youth_since = NULL WHERE id IN ('kid', 'flipped')")
            conn.execute("DELETE FROM schema_version WHERE version = 61")
        before = time.time()
        db = Database(self.path)
        self.assertEqual(db.youth_since("kid"), 1000.0)
        self.assertGreaterEqual(db.youth_since("flipped") or 0, before)

    def test_widen_notification_kind_keeps_rows_columns_and_indexes(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE user_notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('recommendation', 'arrival', 'year-in-review')),
                title TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            ALTER TABLE user_notifications ADD COLUMN read_at REAL;
            CREATE INDEX idx_user_notifications_user ON user_notifications(user_id, created_at DESC);
            INSERT INTO user_notifications VALUES ('n1', 'u1', 'arrival', 'Hi', 1.0, 2.0);
            """
        )
        _widen_notification_kind(conn, "account")
        _widen_notification_kind(conn, "account")
        conn.execute(
            "INSERT INTO user_notifications VALUES ('n2', 'u1', 'account', 'Youth', 3.0, NULL)"
        )
        rows = conn.execute("SELECT id, kind, read_at FROM user_notifications ORDER BY id").fetchall()
        self.assertEqual(rows, [("n1", "arrival", 2.0), ("n2", "account", None)])
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO user_notifications VALUES ('n3', 'u1', 'bogus', 'x', 1.0, NULL)")
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("idx_user_notifications_user", indexes)

    def test_fresh_database_accepts_account_notifications(self) -> None:
        db = Database(self.path)
        db.create_local_user(user_id="u1", display_name="U", password_hash="x", role="member")
        note = db.create_notification(notification_id="n1", user_id="u1", kind="account", title="t")
        self.assertEqual(note["kind"], "account")


class YouthMemoryCuratorTests(_DbCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db.set_user_youth("adult", True)
        self.service.remember(caller_id="adult", kind="self_disclosure", text=SECRET_NOTE)

    def test_prompt_leaves_out_youth_memory_when_paused(self) -> None:
        paused = build_system_prompt(
            self.db, DEFAULT_LENS_ID, user_id="adult", user_role="member",
            is_youth=True, memory_paused=True,
        )
        self.assertNotIn(SECRET_NOTE, paused)
        active = build_system_prompt(
            self.db, DEFAULT_LENS_ID, user_id="adult", user_role="member",
            is_youth=True, memory_paused=False,
        )
        self.assertIn(SECRET_NOTE, active)

    def test_memory_tools_hidden_for_youth_while_memory_off(self) -> None:
        def names(settings: Settings, *, is_youth: bool) -> set:
            return {
                str(t["function"]["name"])
                for t in build_tool_definitions(settings, role="member", is_youth=is_youth)
            }

        self.assertFalse(MEMORY_TOOLS & names(Settings(), is_youth=True))
        self.assertTrue(MEMORY_TOOLS <= names(Settings(), is_youth=False))
        on = Settings(youth=YouthSettings(memory_enabled=True))
        self.assertTrue(MEMORY_TOOLS <= names(on, is_youth=True))

    async def test_memory_tools_refuse_and_write_nothing_for_youth(self) -> None:
        registry = ToolRegistry(
            self.db, Settings(), DEFAULT_LENS_ID, user_id="adult", user_role="member", is_youth=True
        )
        before = len(self.db.list_user_memory_notes("adult"))
        out = json.loads(await registry.execute("remember_about_user", {"text": "my school is X"}))
        self.assertEqual(out.get("code"), "youth_memory_off")
        out = json.loads(await registry.execute("remember_preference", {"text": "no horror"}))
        self.assertEqual(out.get("code"), "youth_memory_off")
        recalled = json.loads(await registry.execute("recall_user_memory", {}))
        self.assertEqual(recalled["notes"], [])
        self.assertEqual(len(self.db.list_user_memory_notes("adult")), before)

    def test_remember_preference_paused_writes_no_personal_note(self) -> None:
        before = len(self.db.list_user_memory_notes("adult"))
        remember_preference(
            self.db,
            PreferenceSignal(signal_type="explicit", text="Rated Up 5/5: loved it"),
            user_id="adult",
            memory_paused=True,
        )
        self.assertEqual(len(self.db.list_user_memory_notes("adult")), before)
        with self.db.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM preference_facts WHERE user_id = 'adult'"
            ).fetchone()[0]
        self.assertEqual(count, 0)


class YouthCuratorRouteTests(_DbCase, unittest.IsolatedAsyncioTestCase):
    async def test_route_none_makes_no_model_call_and_explains(self) -> None:
        from projectionist.agent import curator

        settings = Settings(**CLOUD_SETTINGS)
        with mock.patch.object(curator, "get_chat_provider") as provider_factory, mock.patch.object(
            curator, "tracked_chat"
        ) as chat_call:
            agent = curator.CuratorAgent(
                self.db, settings, user_id="adult", user_role="member", is_youth=True
            )
            result = await agent.run("youth-s1", "what should I watch?")
        provider_factory.assert_not_called()
        chat_call.assert_not_called()
        text = result["message"]["blocks"][0]["content"]
        self.assertEqual(text, YOUTH_CHAT_OFF_NOTICE)

    async def test_stream_route_none_makes_no_model_call(self) -> None:
        from projectionist.agent import curator

        settings = Settings(**CLOUD_SETTINGS)
        with mock.patch.object(curator, "get_chat_provider") as provider_factory, mock.patch.object(
            curator, "tracked_stream"
        ) as stream_call:
            events = [
                json.loads(chunk)
                async for chunk in curator.stream_agent(
                    self.db, settings, "youth-s2", "hi", user_id="adult",
                    user_role="member", is_youth=True,
                )
            ]
        provider_factory.assert_not_called()
        stream_call.assert_not_called()
        done = next(e for e in events if e["type"] == "done")
        self.assertEqual(done["message"]["blocks"][0]["content"], YOUTH_CHAT_OFF_NOTICE)

    def test_local_route_builds_provider_from_local_settings_only(self) -> None:
        from projectionist.agent import curator

        settings = Settings(**CLOUD_SETTINGS, youth=_local_youth())
        with mock.patch.object(curator, "get_chat_provider") as provider_factory:
            agent = curator.CuratorAgent(
                self.db, settings, user_id="adult", user_role="member", is_youth=True
            )
        used = provider_factory.call_args.args[0]
        self.assertEqual(used.llm_base_url, "http://192.168.1.20:11434/v1")
        self.assertEqual(used.llm_api_key, "")
        self.assertIsNone(agent.youth_chat_notice)

    def test_adults_keep_the_household_model(self) -> None:
        from projectionist.agent import curator

        settings = Settings(**CLOUD_SETTINGS, youth=_local_youth())
        with mock.patch.object(curator, "get_chat_provider") as provider_factory:
            curator.CuratorAgent(self.db, settings, user_id="adult", user_role="member")
        used = provider_factory.call_args.args[0]
        self.assertEqual(used.llm_base_url, "https://api.openai.com/v1")


class YouthToggleApiTests(unittest.TestCase):
    """Owner PATCH /api/users/{id}: confirm, notify, audit, never reveal memory."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-youth-guardrails-session-secret"
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
        self.settings_path = Path(self._tmpdir.name) / "settings.json"
        self.settings_path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                    **CLOUD_SETTINGS,
                    "youth": {"max_content_rating": "PG"},
                }
            ),
            encoding="utf-8",
        )
        for username, role in (("owner", "owner"), ("member", "member")):
            self.db.create_local_user(
                user_id=f"local-{username}",
                display_name=username,
                password_hash=_hash_password("password123"),
                role=role,
            )
        UserMemoryService(self.db).remember(
            caller_id="local-member", kind="self_disclosure", text=SECRET_NOTE
        )
        self._login("owner")

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

    def _login(self, username: str) -> None:
        self.client.cookies.clear()
        resp = self.client.post(
            "/api/auth/local/login", json={"username": username, "password": "password123"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def _youth_events(self) -> list:
        return self.db.list_security_events(event="youth_change")["items"]

    def _account_notes(self) -> list:
        return self.db.list_notifications_for_user("local-member", kinds=["account"])

    def test_unconfirmed_youth_on_changes_nothing(self) -> None:
        resp = self.client.patch(
            "/api/users/local-member", json={"is_youth": True, "role": "owner"}
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        row = self.db.get_user("local-member")
        self.assertFalse(bool(row["is_youth"]))
        self.assertEqual(row["role"], "member")
        self.assertEqual(self._youth_events(), [])
        self.assertEqual(self._account_notes(), [])

    def test_confirmed_youth_on_notifies_audits_and_reveals_no_memory(self) -> None:
        records: list = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record.getMessage())

        root = logging.getLogger()
        handler = _Capture(level=logging.DEBUG)
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            resp = self.client.patch(
                "/api/users/local-member", json={"is_youth": True, "confirm_youth": True}
            )
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["user"]["is_youth"])
        self.assertNotIn(SECRET_NOTE, resp.text)
        self.assertFalse(any(SECRET_NOTE in line for line in records))

        notes = self._account_notes()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["title"], "Youth mode is on for your account")
        self.assertIn("owner turned on Youth mode", notes[0]["body"])
        self.assertIn("stays private", notes[0]["body"])
        self.assertNotIn(SECRET_NOTE, json.dumps(notes))

        events = self._youth_events()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["actor_id"], "local-owner")
        self.assertEqual(event["target_id"], "local-member")
        self.assertGreater(float(event["created_at"]), 0)
        self.assertTrue(event["detail"]["confirmed"])
        self.assertTrue(event["detail"]["member_notified"])
        self.assertFalse(event["detail"]["was_youth"])
        self.assertNotIn(SECRET_NOTE, json.dumps(event))

        review = self.client.get("/api/users/local-member/memory")
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["notes"], [])
        self.assertFalse(review.json()["memory_enabled"])
        self.assertNotIn(SECRET_NOTE, review.text)

    def test_turning_youth_off_needs_no_confirm(self) -> None:
        self.db.set_user_youth("local-member", True)
        resp = self.client.patch("/api/users/local-member", json={"is_youth": False})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["user"]["is_youth"])
        self.assertEqual(self._account_notes(), [])

    def test_youth_chat_uses_no_model_and_explains(self) -> None:
        self.db.set_user_youth("local-member", True)
        self._login("member")
        from projectionist.agent import curator

        with mock.patch.object(curator, "get_chat_provider") as provider_factory:
            resp = self.client.post("/api/chat", json={"message": "recommend something"})
        self.assertEqual(resp.status_code, 200, resp.text)
        provider_factory.assert_not_called()
        self.assertEqual(resp.json()["message"]["blocks"][0]["content"], YOUTH_CHAT_OFF_NOTICE)

    def test_partial_settings_put_keeps_youth_choices(self) -> None:
        saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
        saved["youth"] = {
            "max_content_rating": "PG",
            "memory_enabled": True,
            "chat_route": "local",
            "local_base_url": "http://ollama:11434/v1",
            "local_model": "llama3.2",
        }
        self.settings_path.write_text(json.dumps(saved), encoding="utf-8")
        current = self.client.get("/api/settings").json()
        current["youth"] = {"max_content_rating": "G"}
        resp = self.client.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 200, resp.text)
        youth = resp.json()["youth"]
        self.assertEqual(youth["max_content_rating"], "G")
        self.assertTrue(youth["memory_enabled"])
        self.assertEqual(youth["chat_route"], "local")
        self.assertEqual(youth["local_base_url"], "http://ollama:11434/v1")


if __name__ == "__main__":
    unittest.main()
