"""Trust release regressions: one authz policy, owner claim, own-evidence, backups.

Each class names the finding it guards. They fail if a member or youth can
confirm an acquisition (SEC-006), reach Apprise SSRF (SEC-007), read another
member's reviews through the agent (SEC-009), take an ownerless server
(SEC-008), or get a "You watched" line from someone else's history (PRIV-001).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist import authz
from projectionist.agent.tools import ToolRegistry, build_tool_definitions
from projectionist.agent.tools.confirmed import execute_confirmed_action
from projectionist.backups import (
    DEFAULT_KEEP,
    RestoreError,
    create_snapshot_file,
    list_snapshots,
    prune_snapshots,
    restore_snapshot,
)
from projectionist.config_store import FeatureFlags, Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.notifications.recommendation_reasons import watched_library_rows
from projectionist.notifications.service import deliver_notification
from projectionist.reviews.store import save_review
from projectionist.web.owner_claim import OWNER_CLAIM_COOKIE
from projectionist.web.owner_ops import build_needs_attention, people_waiting
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache

from tests.test_household_bridges import _insert_completion, _title
from tests.test_phase2_trust_core import _HouseholdApp, _multi_user_settings, _tool_names

ACQUIRE_TOOLS = {"add_to_radarr", "add_to_sonarr"}


class AcquisitionConfirmPolicyTests(unittest.TestCase):
    """SEC-006: members propose; only the owner confirms; youth never see a confirm."""

    def test_policy_table(self) -> None:
        for action in ("add_radarr", "add_sonarr"):
            self.assertIsNone(authz.pending_action_denial(action, is_owner=True, is_youth=False))
            self.assertEqual(
                authz.pending_action_denial(action, is_owner=False, is_youth=False),
                authz.ARR_ACQUIRE_MESSAGE,
            )
            self.assertEqual(
                authz.pending_action_denial(action, is_owner=False, is_youth=True),
                authz.YOUTH_MESSAGE,
            )
        self.assertIsNone(authz.pending_action_denial("request_seerr", is_owner=False, is_youth=False))
        self.assertEqual(
            authz.pending_action_denial("request_seerr", is_owner=False, is_youth=True),
            authz.YOUTH_MESSAGE,
        )
        self.assertIsNotNone(authz.pending_action_denial("remove_arr", is_owner=False, is_youth=False))
        self.assertIsNone(authz.pending_action_denial("remove_arr", is_owner=True, is_youth=False))

    def test_tool_lists_hide_acquisition_from_members_and_youth(self) -> None:
        settings = _multi_user_settings(seerr_enabled=True)
        owner = _tool_names(build_tool_definitions(settings, role="owner"))
        member = _tool_names(build_tool_definitions(settings, role="member"))
        youth = _tool_names(build_tool_definitions(settings, role="member", is_youth=True))
        self.assertTrue(ACQUIRE_TOOLS <= owner)
        self.assertFalse(member & ACQUIRE_TOOLS)
        self.assertFalse(youth & ACQUIRE_TOOLS)
        self.assertIn("request_via_seerr", member)
        self.assertNotIn("request_via_seerr", youth)
        self.assertNotIn("propose_acquire_path", youth)

    def test_agent_refuses_member_and_youth_add_with_no_arr_call(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db = Database(Path(tmp) / "t.db")
                settings = Settings(
                    radarr_url="http://radarr",
                    radarr_api_key="secret",
                    sonarr_url="http://sonarr",
                    sonarr_api_key="secret",
                    features=FeatureFlags(multi_user_enabled=True),
                )
                for youth in (False, True):
                    registry = ToolRegistry(
                        db, settings, DEFAULT_LENS_ID, user_id="m1", user_role="member", is_youth=youth
                    )
                    with patch("projectionist.agent.tools.acquire.RadarrClient") as radarr_cls, patch(
                        "projectionist.agent.tools.acquire.SonarrClient"
                    ) as sonarr_cls:
                        for tool in sorted(ACQUIRE_TOOLS):
                            raw = await registry.execute(tool, {"tmdb_id": 603, "tvdb_id": 81189, "title": "X"})
                            self.assertEqual(json.loads(raw).get("code"), "agent_tool_not_permitted", raw)
                    radarr_cls.assert_not_called()
                    sonarr_cls.assert_not_called()
                    self.assertEqual(registry.pending_tokens, [])

        asyncio.run(run())

    def test_confirm_path_refuses_non_owner_and_keeps_token(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db = Database(Path(tmp) / "t.db")
                settings = Settings(radarr_url="http://radarr", radarr_api_key="secret")
                payload = {"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"}
                db.save_pending_action("tok-add", "add_radarr", payload, user_id="m1")
                with patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls:
                    for youth in (False, True):
                        with self.assertRaises(PermissionError):
                            await execute_confirmed_action(
                                db,
                                settings,
                                "tok-add",
                                user_id="m1",
                                actor_is_owner=False,
                                actor_is_youth=youth,
                            )
                radarr_cls.assert_not_called()
                self.assertEqual(db.peek_pending_action_kind("tok-add"), "add_radarr")

        asyncio.run(run())


class AcquisitionRouteTests(_HouseholdApp):
    """SEC-006 at the REST boundary (propose + confirm)."""

    def test_member_and_youth_cannot_propose_radarr_or_sonarr(self) -> None:
        for username in ("member", "youth"):
            client = self._client_for(username)
            with patch.object(self.app_mod, "RadarrClient") as radarr_cls, patch.object(
                self.app_mod, "SonarrClient"
            ) as sonarr_cls:
                for action in ("add_radarr", "add_sonarr"):
                    resp = client.post(
                        "/api/actions/propose",
                        json={"action": action, "tmdb_id": 603, "tvdb_id": 81189, "title": "X"},
                    )
                    self.assertEqual(resp.status_code, 403, resp.text)
            radarr_cls.assert_not_called()
            sonarr_cls.assert_not_called()

    def test_youth_cannot_propose_seerr_request(self) -> None:
        resp = self._client_for("youth").post(
            "/api/actions/propose", json={"action": "request_seerr", "tmdb_id": 603, "media_type": "movie"}
        )
        self.assertEqual(resp.status_code, 403, resp.text)

    def test_owner_propose_reaches_radarr(self) -> None:
        owner = self._client_for("owner")
        with patch.object(self.app_mod, "radarr_add_configuration_error", return_value=None), patch.object(
            self.app_mod, "RadarrClient"
        ) as radarr_cls:
            radarr_cls.return_value.root_folders.return_value = []
            resp = owner.post("/api/actions/propose", json={"action": "add_radarr", "tmdb_id": 603, "title": "X"})
        self.assertNotEqual(resp.status_code, 403, resp.text)
        radarr_cls.assert_called()

    def test_member_and_youth_cannot_confirm_their_own_add_token(self) -> None:
        for username, user_id in (("member", "local-member"), ("youth", "local-youth")):
            token = f"tok-{username}"
            self.db.save_pending_action(
                token, "add_radarr", {"action": "add_radarr", "tmdb_id": 603, "title": "X"}, user_id=user_id
            )
            client = self._client_for(username)
            with patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls:
                resp = client.post("/api/actions/confirm", json={"token": token, "confirmed": True})
            self.assertEqual(resp.status_code, 403, resp.text)
            radarr_cls.assert_not_called()
            self.assertEqual(self.db.peek_pending_action_kind(token), "add_radarr")

    def test_owner_delete_stays_owner_only(self) -> None:
        self.db.save_pending_action(
            "tok-rm",
            "remove_arr",
            {"action": "remove_arr", "media_type": "movie", "arr_id": 1, "delete_files": True},
            user_id="local-member",
        )
        resp = self._client_for("member").post("/api/actions/confirm", json={"token": "tok-rm", "confirmed": True})
        self.assertEqual(resp.status_code, 403, resp.text)


class AppriseOwnerOnlyTests(_HouseholdApp):
    """SEC-007: members cannot make the server call a URL they chose."""

    def test_member_cannot_set_or_test_apprise_urls(self) -> None:
        member = self._client_for("member")
        resp = member.patch("/api/auth/me", json={"apprise_urls": "json://169.254.169.254/latest"})
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertFalse(str(self.db.get_user("local-member")["apprise_urls"] or "").strip())
        with patch("projectionist.notifications.apprise_transport.send_apprise") as send:
            resp = member.post("/api/auth/me/apprise/test", json={"url": "json://10.0.0.1:9/"})
        self.assertEqual(resp.status_code, 403, resp.text)
        send.assert_not_called()
        self.assertEqual(member.patch("/api/auth/me", json={"apprise_urls": ""}).status_code, 200)

    def test_owner_can_still_set_apprise_urls(self) -> None:
        resp = self._client_for("owner").patch("/api/auth/me", json={"apprise_urls": "json://owner.example/hook"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_delivery_ignores_stored_member_urls(self) -> None:
        settings = _multi_user_settings()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE users SET apprise_urls = ? WHERE id IN ('local-member', 'local-owner')",
                ("json://169.254.169.254/latest",),
            )
        with patch("projectionist.notifications.service.send_apprise") as send:
            deliver_notification(
                self.db, settings, user_id="local-member", kind="nudge", title="Hi", force_apprise=True
            )
            send.assert_not_called()
            deliver_notification(
                self.db, settings, user_id="local-owner", kind="nudge", title="Hi", force_apprise=True
            )
            send.assert_called_once()


class AgentReviewScopeTests(unittest.TestCase):
    """SEC-009: the agent review lookup returns only the caller's reviews."""

    def test_member_does_not_see_another_members_review(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db = Database(Path(tmp) / "t.db")
                for uid in ("member-a", "member-b"):
                    db.upsert_plex_user(user_id=uid, display_name=uid, email=None,
                                        plex_user_id=f"plex-{uid}", role="member")
                save_review(db, stars=2, title="Heat", media_type="movie", tmdb_id=949,
                            review_text="B's private take", user_id="member-b")
                save_review(db, stars=5, title="Heat", media_type="movie", tmdb_id=949,
                            review_text="A's take", user_id="member-a")
                registry = ToolRegistry(
                    db, _multi_user_settings(), DEFAULT_LENS_ID, user_id="member-a", user_role="member"
                )
                out = json.loads(await registry.execute("get_user_reviews", {"tmdb_id": 949}))
                texts = [item.get("review_text") for item in out["items"]]
                self.assertIn("A's take", texts)
                self.assertNotIn("B's private take", texts)
                anon = ToolRegistry(db, _multi_user_settings(), DEFAULT_LENS_ID, user_id=None)
                self.assertEqual(json.loads(await anon.execute("get_user_reviews", {}))["items"], [])

        asyncio.run(run())


class OwnEvidenceTests(unittest.TestCase):
    """PRIV-001 / PRIV-009: "You watched" seeds are only the reader's own viewing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "t.db")
        now_ms = int(time.time() * 1000)
        _title(self.db, rating_key="rk-b", tmdb_id=1, title="Bs Secret Show")
        _title(self.db, rating_key="rk-guest", tmdb_id=2, title="Guest Pick")
        _title(self.db, rating_key="rk-tv", tmdb_id=3, title="Server Played", view_count=3,
               last_viewed_at=time.time())
        _insert_completion(self.db, user_id="member-b", rating_key="rk-b", completed_at_ms=now_ms)
        _insert_completion(self.db, user_id=None, rating_key="rk-guest", completed_at_ms=now_ms)
        self.db.upsert_plex_user(user_id="member-a", display_name="A", email=None,
                                 plex_user_id="plex-a", role="member")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_member_without_history_gets_no_seeds(self) -> None:
        seeds = watched_library_rows(self.db, user_id="member-a", multi_user_enabled=True)
        self.assertEqual([row.get("title") for row in seeds], [])

    def test_member_only_sees_own_seed(self) -> None:
        seeds = watched_library_rows(self.db, user_id="member-b", multi_user_enabled=True)
        self.assertEqual([row.get("title") for row in seeds], ["Bs Secret Show"])

    def test_household_caller_without_reader_gets_nothing(self) -> None:
        self.assertEqual(watched_library_rows(self.db, user_id=None, multi_user_enabled=True), [])

    def test_single_owner_mode_still_uses_household_evidence(self) -> None:
        titles = {row.get("title") for row in watched_library_rows(self.db)}
        self.assertIn("Bs Secret Show", titles)

    def test_nudge_payload_never_carries_recently_watched(self) -> None:
        from projectionist.notifications.nudges import deliver_enthusiast_nudges

        with self.db.connect() as conn:
            conn.execute("UPDATE users SET nudge_opt_in = 1 WHERE id = 'member-a'")
        with patch("projectionist.notifications.nudges.pick_nudge_title",
                   return_value={"title": "Thief", "why": "w"}), patch(
            "projectionist.notifications.nudges.deliver_notification"
        ) as deliver:
            deliver_enthusiast_nudges(self.db, _multi_user_settings())
        self.assertTrue(deliver.called)
        for call in deliver.call_args_list:
            self.assertNotIn("recently_watched", call.kwargs.get("payload") or {})

    def test_stored_recently_watched_is_scrubbed_on_read(self) -> None:
        self.db.create_notification(
            notification_id="n-old",
            user_id="member-a",
            kind="nudge",
            title="Hi",
            payload={"recently_watched": [{"title": "Bs Secret Show"}], "pick_why": "w"},
        )
        rows = self.db.list_notifications_for_user("member-a")
        self.assertTrue(rows)
        self.assertNotIn("recently_watched", rows[0]["payload"])
        self.assertEqual(rows[0]["payload"]["pick_why"], "w")


class OwnerClaimTests(unittest.TestCase):
    """SEC-008: with no owner, the first sign-in needs proof; the default stays open."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(
            os.environ,
            {
                "DATA_DIR": self._tmp.name,
                "PROJECTIONIST_SKIP_DOTENV": "1",
                "LLM_PROVIDER": "ollama",
                "PROJECTIONIST_SESSION_SECRET": "owner-claim-test-secret-value",
            },
            clear=False,
        )
        self._env.start()
        os.environ.pop("PROJECTIONIST_OWNER_PASSWORD", None)
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        self._env.stop()
        self._tmp.cleanup()

    def _enable(self, client: TestClient):
        return client.put(
            "/api/settings",
            json={
                "features": {"multi_user_enabled": True, "seerr_enabled": False},
                "auth": {"mode": "plex", "plex_login_enabled": True},
            },
        )

    def _plex_login(self, client: TestClient, plex_id: int):
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": plex_id, "title": f"P{plex_id}", "email": f"p{plex_id}@example.com"},
        ):
            resp = client.post("/api/auth/plex", json={"auth_token": f"tok-{plex_id}"})
        clear_rate_limits()
        return resp

    def test_first_plex_sign_in_without_claim_is_refused(self) -> None:
        operator = TestClient(self.app_mod.app)
        self.assertEqual(self._enable(operator).status_code, 200)
        stranger = TestClient(self.app_mod.app)
        resp = self._plex_login(stranger, 41)
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIsNone(self.db.get_user_by_plex_id("41"))

    def test_claim_holder_becomes_owner_once(self) -> None:
        operator = TestClient(self.app_mod.app)
        resp = self._enable(operator)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(operator.cookies.get(OWNER_CLAIM_COOKIE))
        stolen = operator.cookies.get(OWNER_CLAIM_COOKIE)
        first = self._plex_login(operator, 42)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["user"]["role"], "owner")
        replay = TestClient(self.app_mod.app)
        replay.cookies.set(OWNER_CLAIM_COOKIE, stolen)
        second = self._plex_login(replay, 43)
        if second.status_code == 200:
            self.assertEqual(second.json()["user"]["role"], "member")
        else:
            self.assertEqual(second.status_code, 403, second.text)

    def test_default_install_stays_open_single_owner(self) -> None:
        resp = TestClient(self.app_mod.app).get("/api/auth/me")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["user"]["role"], "owner")


class BackupRoundTripTests(unittest.TestCase):
    """PERF-002 / OPS-009: the restore drill, against a temp data dir only."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        (self.data_dir / "settings.json").write_text(json.dumps({"llm_provider": "ollama"}), encoding="utf-8")
        self.db = Database(self.data_dir / "projectionist.db")
        self.db.set_config("drill", "before")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _value(self) -> str:
        with sqlite3.connect(self.data_dir / "projectionist.db") as conn:
            row = conn.execute("SELECT config_value FROM curator_system_config WHERE config_key = 'drill'").fetchone()
        return row[0] if row else ""

    def test_snapshot_restore_round_trip(self) -> None:
        snapshot = create_snapshot_file(self.data_dir)
        self.assertEqual(oct(snapshot.stat().st_mode & 0o777), "0o600")
        with zipfile.ZipFile(snapshot) as zf:
            self.assertIn("projectionist.db", zf.namelist())
            self.assertIn("settings.json", zf.namelist())
        self.db.set_config("drill", "after")
        (self.data_dir / "settings.json").write_text(json.dumps({"llm_provider": "openai"}), encoding="utf-8")
        self.assertEqual(self._value(), "after")

        result = restore_snapshot(snapshot, self.data_dir)

        self.assertEqual(self._value(), "before")
        settings = json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["llm_provider"], "ollama")
        aside = Path(result["previous_files_dir"])
        self.assertIn("projectionist.db", result["previous_files"])
        with sqlite3.connect(aside / "projectionist.db") as conn:
            kept = conn.execute("SELECT config_value FROM curator_system_config WHERE config_key = 'drill'").fetchone()
        self.assertEqual(kept[0], "after")

    def test_corrupt_snapshot_is_refused_and_data_untouched(self) -> None:
        bad = self.data_dir / "backups" / "bad.zip"
        bad.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("projectionist.db", b"not a database")
            zf.writestr("settings.json", "{}")
        with self.assertRaises(RestoreError):
            restore_snapshot(bad, self.data_dir)
        not_zip = self.data_dir / "backups" / "junk.zip"
        not_zip.write_bytes(b"junk")
        with self.assertRaises(RestoreError):
            restore_snapshot(not_zip, self.data_dir)
        self.assertEqual(self._value(), "before")

    def test_prune_keeps_newest_seven(self) -> None:
        for offset in range(DEFAULT_KEEP + 3):
            create_snapshot_file(self.data_dir, now=1_700_000_000 + offset * 86400)
        removed = prune_snapshots(self.data_dir)
        self.assertEqual(len(removed), 3)
        self.assertEqual(len(list_snapshots(self.data_dir)), DEFAULT_KEEP)

    def test_scheduled_task_writes_and_prunes(self) -> None:
        from projectionist.scheduler.tasks import household_backup

        out = asyncio.run(household_backup.run(self.db, Settings(), lambda: False))
        self.assertEqual(out["status"], "completed")
        self.assertEqual(len(list_snapshots(self.data_dir)), 1)


class NeedsAttentionPeopleTests(unittest.TestCase):
    """OPS-006 / OPS-009 / OPS-007 rows in the existing Needs attention list."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "t.db")
        self.db.upsert_plex_user(user_id="owner-1", display_name="O", email=None,
                                 plex_user_id="plex-o", role="owner")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _items(self, **kwargs):
        base = {
            "secrets": {"services": []},
            "setup": {"items": []},
            "monday": {"completed_at": 1},
            "failed": [],
        }
        base.update(kwargs)
        return {item["id"]: item for item in build_needs_attention(**base)}

    def test_people_waiting_and_expired_invites_appear(self) -> None:
        now = time.time()
        req = self.db.create_access_request(display_name="Cousin Sam", email="sam@example.com")
        with self.db.connect() as conn:
            conn.execute("UPDATE access_requests SET created_at = ? WHERE id = ?", (now - 3 * 86400, req["id"]))
        self.db.create_invite(token_hash="h1", created_by="owner-1", expires_at=now - 60)
        people = people_waiting(self.db, now=now)
        self.assertEqual(people["requests"], 1)
        self.assertEqual(people["invites_expired"], 1)
        items = self._items(people=people)
        self.assertEqual(items["access-requests"]["severity"], "high")
        self.assertEqual(items["access-requests"]["to"], "/admin/access")
        self.assertIn("invites-expiring", items)

    def test_backup_and_env_owner_rows(self) -> None:
        items = self._items(backup={"task_enabled": True, "age_days": 4}, env_owner="skipped")
        self.assertIn("backup-stale", items)
        self.assertEqual(items["env-owner-skipped"]["to"], "/help#owner-recovery")
        self.assertIn("backup-off", self._items(backup={"task_enabled": False}))

    def test_failed_tasks_still_listed(self) -> None:
        items = self._items(failed=[{"name": "library_sync", "label": "Library sync", "error": "boom"}])
        self.assertIn("tasks-failed", items)


if __name__ == "__main__":
    unittest.main()
