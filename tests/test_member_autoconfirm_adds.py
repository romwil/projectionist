"""BD-3: an adult member's Radarr/Sonarr adds can skip the owner confirm, and nothing else can.

These fail if a member can grant the setting to themselves, if Youth can carry
it, if it opens remove_from_arr or another owner-only tool, if an autoconfirmed
add skips the security log, or if that log row carries chat or memory text.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist import authz
from projectionist import security_audit as sa
from projectionist.agent.tools import ToolRegistry, build_tool_definitions
from projectionist.agent.tools.confirmed import execute_confirmed_action
from projectionist.config_store import FeatureFlags, Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.db.migrations import CURRENT_SCHEMA_VERSION

from tests.test_phase2_trust_core import _HouseholdApp, _multi_user_settings, _tool_names

ACQUIRE_TOOLS = {"add_to_radarr", "add_to_sonarr"}
MEMORY_TEXT = "secretly loves sad clown movies"


def _arr_settings() -> Settings:
    return Settings(
        radarr_url="http://radarr",
        radarr_api_key="secret",
        sonarr_url="http://sonarr",
        sonarr_api_key="secret",
        features=FeatureFlags(multi_user_enabled=True),
    )


def _audit_rows(db: Database, event: str) -> list[dict]:
    return list(db.list_security_events(event=event, limit=50)["items"])


class AutoconfirmPolicyTests(unittest.TestCase):
    def test_autoconfirm_opens_adds_only(self) -> None:
        for action in ("add_radarr", "add_sonarr"):
            self.assertIsNone(
                authz.pending_action_denial(
                    action, is_owner=False, is_youth=False, autoconfirm_adds=True
                )
            )
            self.assertEqual(
                authz.pending_action_denial(action, is_owner=False, is_youth=False),
                authz.ARR_ACQUIRE_MESSAGE,
            )
            self.assertEqual(
                authz.pending_action_denial(
                    action, is_owner=False, is_youth=True, autoconfirm_adds=True
                ),
                authz.YOUTH_MESSAGE,
            )
        for kind in ("remove_arr", "mark_bad_media", "create_plex_collection", "add_to_plex_collection"):
            self.assertEqual(
                authz.pending_action_denial(
                    kind, is_owner=False, is_youth=False, autoconfirm_adds=True
                ),
                authz.OWNER_ONLY_MESSAGE,
                kind,
            )
        for tool in authz.OWNER_ONLY_TOOL_NAMES - ACQUIRE_TOOLS:
            self.assertEqual(
                authz.tool_denial(tool, is_owner=False, is_youth=False, autoconfirm_adds=True),
                authz.OWNER_ONLY_MESSAGE,
                tool,
            )

    def test_tool_list_shows_adds_but_not_remove_for_autoconfirm_member(self) -> None:
        settings = _multi_user_settings()
        on = _tool_names(build_tool_definitions(settings, role="member", autoconfirm_adds=True))
        off = _tool_names(build_tool_definitions(settings, role="member"))
        youth = _tool_names(
            build_tool_definitions(settings, role="member", is_youth=True, autoconfirm_adds=True)
        )
        self.assertTrue(ACQUIRE_TOOLS <= on)
        self.assertNotIn("remove_from_arr", on)
        self.assertFalse(off & ACQUIRE_TOOLS)
        self.assertFalse(youth & ACQUIRE_TOOLS)

    def test_only_an_adult_member_row_with_the_flag_qualifies(self) -> None:
        settings = _multi_user_settings()
        member = {"role": "member", "is_youth": False, "disabled": False, "autoconfirm_adds": True}

        def check(account, *, role="member", is_youth=False, s=settings):
            return authz.autoconfirms_adds(s, role=role, is_youth=is_youth, account=account)

        self.assertTrue(check(member))
        self.assertFalse(check({**member, "autoconfirm_adds": False}))
        self.assertFalse(check({**member, "is_youth": True}))
        self.assertFalse(check(member, is_youth=True))
        self.assertFalse(check({**member, "disabled": True}))
        self.assertFalse(check({**member, "role": "owner"}, role="owner"))
        self.assertFalse(check(member, s=Settings()))
        self.assertFalse(check(None))


class AutoconfirmSchemaTests(unittest.TestCase):
    def test_migration_62_adds_column_default_off(self) -> None:
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 62)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.create_local_user(
                user_id="m1", display_name="m", password_hash="x", role="member"
            )
            with sqlite3.connect(Path(tmp) / "t.db") as conn:
                cols = {row[1]: row for row in conn.execute("PRAGMA table_info(users)")}
                versions = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
            self.assertIn("autoconfirm_adds", cols)
            self.assertIn(61, versions)
            self.assertIn(62, versions)
            self.assertFalse(dict(db.get_user("m1"))["autoconfirm_adds"])

    def test_youth_on_clears_flag_and_youth_cannot_take_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.create_local_user(user_id="m1", display_name="m", password_hash="x", role="member")
            self.assertTrue(db.set_user_autoconfirm_adds("m1", True)["autoconfirm_adds"])
            self.assertFalse(db.set_user_youth("m1", True)["autoconfirm_adds"])
            self.assertEqual(int(db.get_user("m1")["autoconfirm_adds"]), 0)
            with self.assertRaises(ValueError):
                db.set_user_autoconfirm_adds("m1", True)


class AutoconfirmToggleRouteTests(_HouseholdApp):
    def test_only_the_owner_can_toggle_autoconfirm(self) -> None:
        member = self._client_for("member")
        resp = member.patch("/api/users/local-member", json={"autoconfirm_adds": True})
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(int(self.db.get_user("local-member")["autoconfirm_adds"]), 0)

        owner = self._client_for("owner")
        resp = owner.patch("/api/users/local-member", json={"autoconfirm_adds": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["user"]["autoconfirm_adds"])
        rows = _audit_rows(self.db, sa.AUTOCONFIRM_CHANGE)
        self.assertEqual(rows[0]["actor_id"], "local-owner")
        self.assertEqual(rows[0]["target_id"], "local-member")
        self.assertIs(rows[0]["detail"]["autoconfirm_adds"], True)

        me = self._client_for("member").get("/api/auth/me").json()
        self.assertTrue(me["user"]["autoconfirm_adds"])

    def test_youth_and_owner_accounts_cannot_carry_autoconfirm(self) -> None:
        owner = self._client_for("owner")
        resp = owner.patch("/api/users/local-youth", json={"autoconfirm_adds": True})
        self.assertEqual(resp.status_code, 409, resp.text)
        resp = owner.patch(
            "/api/users/local-member",
            json={"autoconfirm_adds": True, "is_youth": True, "confirm_youth": True},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertFalse(bool(self.db.get_user("local-member")["is_youth"]))
        resp = owner.patch("/api/users/local-owner", json={"autoconfirm_adds": True})
        self.assertEqual(resp.status_code, 400, resp.text)

    def test_turning_youth_on_clears_autoconfirm(self) -> None:
        owner = self._client_for("owner")
        self.assertEqual(
            owner.patch("/api/users/local-member", json={"autoconfirm_adds": True}).status_code, 200
        )
        resp = owner.patch(
            "/api/users/local-member", json={"is_youth": True, "confirm_youth": True}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["user"]["autoconfirm_adds"])
        cleared = [
            row
            for row in _audit_rows(self.db, sa.AUTOCONFIRM_CHANGE)
            if row["detail"].get("reason") == "youth_on"
        ]
        self.assertEqual(len(cleared), 1)


class AutoconfirmRoleChangeTests(_HouseholdApp):
    def test_promotion_clears_autoconfirm_so_demotion_cannot_restore_it(self) -> None:
        owner = self._client_for("owner")
        owner.patch("/api/users/local-member", json={"autoconfirm_adds": True})
        resp = owner.patch("/api/users/local-member", json={"role": "owner"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(int(self.db.get_user("local-member")["autoconfirm_adds"]), 0)
        resp = owner.patch("/api/users/local-member", json={"role": "member"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertFalse(resp.json()["user"]["autoconfirm_adds"])
        reasons = [row["detail"].get("reason") for row in _audit_rows(self.db, sa.AUTOCONFIRM_CHANGE)]
        self.assertIn("role_change", reasons)


class AutoconfirmAddRouteTests(_HouseholdApp):
    def _enable(self) -> None:
        self.db.set_user_autoconfirm_adds("local-member", True)
        self.db.add_user_memory_note("local-member", kind="note", text=MEMORY_TEXT)

    def test_flag_off_member_still_cannot_add(self) -> None:
        token = "tok-off"
        self.db.save_pending_action(
            token, "add_radarr", {"action": "add_radarr", "tmdb_id": 603, "title": "X"},
            user_id="local-member",
        )
        with patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls:
            resp = self._client_for("member").post(
                "/api/actions/confirm", json={"token": token, "confirmed": True}
            )
        self.assertEqual(resp.status_code, 403, resp.text)
        radarr_cls.assert_not_called()
        self.assertEqual(_audit_rows(self.db, sa.AUTOCONFIRM_ADD), [])

    def test_autoconfirm_member_add_runs_and_writes_audit_without_memory(self) -> None:
        self._enable()
        member = self._client_for("member")
        with patch.object(self.app_mod, "radarr_add_configuration_error", return_value=None), patch.object(
            self.app_mod, "RadarrClient"
        ) as propose_cls, patch.object(
            self.app_mod, "validate_arr_root_folder", return_value=None
        ), patch.object(self.app_mod, "check_radarr_already_exists", return_value=None):
            resp = member.post(
                "/api/actions/propose",
                json={"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        propose_cls.assert_called()
        token = resp.json()["confirmation_token"]
        with patch(
            "projectionist.agent.tools.confirmed.radarr_add_configuration_error", return_value=None
        ), patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls, patch(
            "projectionist.agent.tools.confirmed.resolve_radarr_root_folder", return_value="/movies"
        ):
            radarr_cls.return_value.add_movie.return_value = {"id": 9, "title": "The Matrix"}
            resp = member.post("/api/actions/confirm", json={"token": token, "confirmed": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["autoconfirmed"])
        radarr_cls.return_value.add_movie.assert_called_once()
        rows = _audit_rows(self.db, sa.AUTOCONFIRM_ADD)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor_id"], "local-member")
        self.assertEqual(rows[0]["outcome"], "ok")
        self.assertEqual(rows[0]["detail"]["title"], "The Matrix")
        self.assertEqual(rows[0]["detail"]["service"], "Radarr")
        self.assertNotIn(MEMORY_TEXT, json.dumps(rows[0]))

    def test_autoconfirm_member_still_cannot_remove(self) -> None:
        self._enable()
        self.db.save_pending_action(
            "tok-rm",
            "remove_arr",
            {"action": "remove_arr", "media_type": "movie", "arr_id": 1, "delete_files": True},
            user_id="local-member",
        )
        resp = self._client_for("member").post(
            "/api/actions/confirm", json={"token": "tok-rm", "confirmed": True}
        )
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(self.db.peek_pending_action_kind("tok-rm"), "remove_arr")


class AutoconfirmAgentTests(unittest.TestCase):
    def _db(self, tmp: str, *, flag: bool, youth: bool = False) -> Database:
        db = Database(Path(tmp) / "t.db")
        db.create_local_user(user_id="m1", display_name="m", password_hash="x", role="member")
        if flag:
            db.set_user_autoconfirm_adds("m1", True)
        if youth:
            db.set_user_youth("m1", True)
        db.add_user_memory_note("m1", kind="note", text=MEMORY_TEXT)
        return db

    def _run_add(self, db: Database, *, is_youth: bool = False):
        registry = ToolRegistry(
            db, _arr_settings(), DEFAULT_LENS_ID, user_id="m1", user_role="member", is_youth=is_youth
        )

        async def run():
            with patch("projectionist.agent.tools.acquire.RadarrClient"), patch(
                "projectionist.agent.tools.acquire.validate_arr_root_folder", return_value=None
            ), patch(
                "projectionist.agent.tools.acquire.check_radarr_already_exists", return_value=None
            ), patch(
                "projectionist.agent.tools.confirmed.RadarrClient"
            ) as radarr_cls, patch(
                "projectionist.agent.tools.confirmed.resolve_radarr_root_folder", return_value="/movies"
            ):
                radarr_cls.return_value.add_movie.return_value = {"id": 9}
                raw = await registry.execute(
                    "add_to_radarr", {"tmdb_id": 603, "title": "The Matrix"}
                )
                remove = await registry.execute(
                    "remove_from_arr", {"media_type": "movie", "tmdb_id": 603}
                )
                return json.loads(raw), json.loads(remove), radarr_cls

        return registry, *asyncio.run(run())

    def test_autoconfirm_member_agent_add_happens_in_one_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp, flag=True)
            registry, added, removed, radarr_cls = self._run_add(db)
            self.assertTrue(added.get("autoconfirmed"), added)
            self.assertNotIn("confirmation_token", added)
            self.assertEqual(registry.pending_tokens, [])
            radarr_cls.return_value.add_movie.assert_called_once()
            self.assertEqual(removed.get("code"), "agent_tool_not_permitted")
            rows = _audit_rows(db, sa.AUTOCONFIRM_ADD)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["actor_id"], "m1")
            self.assertEqual(rows[0]["detail"]["title"], "The Matrix")
            self.assertNotIn(MEMORY_TEXT, json.dumps(rows))

    def test_flag_off_and_youth_agent_add_refused(self) -> None:
        for flag, youth in ((False, False), (True, True)):
            with tempfile.TemporaryDirectory() as tmp:
                db = self._db(tmp, flag=flag, youth=youth)
                _registry, added, _removed, radarr_cls = self._run_add(db, is_youth=youth)
                self.assertEqual(added.get("code"), "agent_tool_not_permitted", added)
                radarr_cls.return_value.add_movie.assert_not_called()
                self.assertEqual(_audit_rows(db, sa.AUTOCONFIRM_ADD), [])

    def test_direct_confirm_needs_the_flag(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db = Database(Path(tmp) / "t.db")
                db.save_pending_action(
                    "tok", "add_sonarr", {"action": "add_sonarr", "tvdb_id": 81189}, user_id="m1"
                )
                with self.assertRaises(PermissionError):
                    await execute_confirmed_action(
                        db, _arr_settings(), "tok", user_id="m1", actor_is_owner=False
                    )
                self.assertEqual(db.peek_pending_action_kind("tok"), "add_sonarr")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
