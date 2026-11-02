"""Phase 2 trust core: chat ownership, agent tool policy, youth surfaces, settings fail-closed.

Two-user and youth fixtures against a real app (local auth, multi-user on).
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from projectionist.agent.tools import (
    OWNER_ONLY_TOOL_NAMES,
    ToolRegistry,
    build_tool_definitions,
)
from projectionist.config_store import FeatureFlags, Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.web.auth import _hash_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache

_ENV_KEYS = (
    "DATA_DIR",
    "PROJECTIONIST_SKIP_DOTENV",
    "LLM_PROVIDER",
    "PROJECTIONIST_SESSION_SECRET",
    "PROJECTIONIST_SETUP_STATE",
)


def _tool_names(defs) -> set[str]:
    return {str((tool.get("function") or {}).get("name") or "") for tool in defs}


def _multi_user_settings(**features) -> Settings:
    return Settings(features=FeatureFlags(multi_user_enabled=True, **features))


class _HouseholdApp(unittest.TestCase):
    """Owner, adult member, and youth member signed in on separate clients."""

    multi_user = True

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-phase2-trust-core-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        if self.multi_user:
            (self.data_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "features": {"multi_user_enabled": True},
                        "auth": {
                            "mode": "local",
                            "plex_login_enabled": False,
                            "local_login_enabled": True,
                        },
                        "llm_provider": "ollama",
                    }
                ),
                encoding="utf-8",
            )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.db = jobs.get_job_manager().db
        if self.multi_user:
            for user_id, name, role in (
                ("local-owner", "owner", "owner"),
                ("local-member", "member", "member"),
                ("local-youth", "youth", "member"),
            ):
                self.db.create_local_user(
                    user_id=user_id,
                    display_name=name,
                    password_hash=_hash_password("password123"),
                    role=role,
                )
            self.db.set_user_youth("local-youth", True)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _client_for(self, username: str) -> TestClient:
        client = TestClient(self.app_mod.app)
        resp = client.post(
            "/api/auth/local/login", json={"username": username, "password": "password123"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        clear_rate_limits()
        return client


class ChatThreadOwnershipTests(_HouseholdApp):
    async def _fake_stream(self, *_args, **_kwargs):
        yield json.dumps({"type": "token", "content": "Hi"})
        yield json.dumps({"type": "done"})

    def test_stream_refuses_another_users_thread_before_any_event(self) -> None:
        owner = self._client_for("owner")
        thread = owner.post("/api/chat/threads", json={}).json()
        member = self._client_for("member")
        stream_agent = MagicMock(side_effect=self._fake_stream)
        with patch("projectionist.web.chat_routes.stream_agent", stream_agent):
            resp = member.post(
                "/api/chat/stream",
                json={"message": "what did they ask?", "session_id": thread["session_id"]},
            )
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["detail"], "Thread not found")
        stream_agent.assert_not_called()
        self.assertEqual(self.db.chat_history(thread["session_id"], limit=10), [])

    def test_non_stream_chat_refuses_another_users_thread(self) -> None:
        owner = self._client_for("owner")
        thread = owner.post("/api/chat/threads", json={}).json()
        youth = self._client_for("youth")
        resp = youth.post("/api/chat", json={"message": "hi", "session_id": thread["session_id"]})
        self.assertEqual(resp.status_code, 404, resp.text)

    def test_stream_allows_own_thread(self) -> None:
        member = self._client_for("member")
        thread = member.post("/api/chat/threads", json={}).json()
        with patch("projectionist.web.chat_routes.stream_agent", self._fake_stream):
            resp = member.post(
                "/api/chat/stream",
                json={"message": "hello", "session_id": thread["session_id"]},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("done", resp.text)

    def test_ensure_chat_session_refuses_foreign_thread(self) -> None:
        from projectionist.library.db._chat import ChatThreadOwnershipError

        self.db.ensure_chat_session("owned-thread", DEFAULT_LENS_ID, user_id="local-owner")
        with self.assertRaises(ChatThreadOwnershipError):
            self.db.ensure_chat_session("owned-thread", DEFAULT_LENS_ID, user_id="local-member")
        self.db.ensure_chat_session("owned-thread", DEFAULT_LENS_ID, user_id="local-owner")


class AgentToolPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_member_and_youth_tool_lists_exclude_owner_tools(self) -> None:
        settings = _multi_user_settings(seerr_enabled=True, plex_collections_enabled=True)
        owner = _tool_names(build_tool_definitions(settings, role="owner"))
        member = _tool_names(build_tool_definitions(settings, role="member"))
        youth = _tool_names(build_tool_definitions(settings, role="member", is_youth=True))
        unknown = _tool_names(build_tool_definitions(settings))
        self.assertTrue(OWNER_ONLY_TOOL_NAMES <= owner)
        for names in (member, youth, unknown):
            self.assertFalse(names & OWNER_ONLY_TOOL_NAMES, names & OWNER_ONLY_TOOL_NAMES)
        self.assertIn("approve_seerr_request", owner)
        self.assertNotIn("approve_seerr_request", member)
        self.assertIn("request_via_seerr", member)

    def test_single_owner_mode_keeps_owner_tools(self) -> None:
        names = _tool_names(build_tool_definitions(Settings()))
        self.assertIn("mark_bad_media", names)

    async def test_member_mark_bad_media_is_refused_with_no_arr_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = Settings(
                radarr_url="http://radarr",
                radarr_api_key="secret",
                features=FeatureFlags(multi_user_enabled=True),
            )
            for role, youth in (("member", False), ("member", True)):
                registry = ToolRegistry(
                    db, settings, DEFAULT_LENS_ID, user_id="m1", user_role=role, is_youth=youth
                )
                with patch("projectionist.library.bad_media.RadarrClient") as radarr_cls, patch(
                    "projectionist.library.bad_media.mark_bad_media"
                ) as mark:
                    raw = await registry.execute(
                        "mark_bad_media", {"tmdb_id": 555, "media_type": "movie"}
                    )
                payload = json.loads(raw)
                self.assertEqual(payload.get("code"), "agent_tool_not_permitted")
                mark.assert_not_called()
                radarr_cls.assert_not_called()
                self.assertEqual(registry.pending_tokens, [])

    async def test_member_cannot_approve_seerr_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = Settings(features=FeatureFlags(multi_user_enabled=True, seerr_enabled=True))
            settings.seerr.url = "http://seerr"
            settings.seerr.api_key = "k"
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="m1", user_role="member")
            with patch("projectionist.agent.tools.acquire.SeerrClient") as seerr_cls:
                raw = await registry.execute("approve_seerr_request", {"request_id": 7})
            self.assertEqual(json.loads(raw).get("code"), "agent_tool_not_permitted")
            seerr_cls.assert_not_called()

    async def test_owner_mark_bad_media_waits_for_ui_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = Settings(radarr_url="http://radarr", radarr_api_key="secret")
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="o1", user_role="owner")
            with patch("projectionist.library.bad_media.mark_bad_media") as mark:
                proposal = json.loads(
                    await registry.execute("mark_bad_media", {"tmdb_id": 555, "media_type": "movie"})
                )
                token = proposal["confirmation_token"]
                redeemed = json.loads(
                    await registry.execute("confirm_pending_action", {"confirmation_token": token})
                )
                mark.assert_not_called()
            self.assertEqual(redeemed.get("code"), "confirm_requires_user")
            self.assertEqual(db.peek_pending_action_kind(token), "mark_bad_media")

    async def test_member_and_youth_remove_from_arr_is_refused_before_any_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = Settings(
                radarr_url="http://radarr",
                radarr_api_key="secret",
                sonarr_url="http://sonarr",
                sonarr_api_key="secret",
                features=FeatureFlags(multi_user_enabled=True),
            )
            cases = (
                ("member", False, "Only the household owner can do that."),
                ("member", True, "This action is not available on Youth accounts."),
                (None, False, "Only the household owner can do that."),
            )
            for role, youth, expected in cases:
                registry = ToolRegistry(
                    db, settings, DEFAULT_LENS_ID, user_id="m1", user_role=role, is_youth=youth
                )
                for media_type in ("movie", "show"):
                    with patch(
                        "projectionist.agent.tools.acquire.resolve_arr_removal_target"
                    ) as resolve:
                        raw = await registry.execute(
                            "remove_from_arr",
                            {"media_type": media_type, "tmdb_id": 555, "delete_files": True},
                        )
                    payload = json.loads(raw)
                    self.assertEqual(payload.get("code"), "agent_tool_not_permitted")
                    self.assertEqual(payload.get("error"), expected)
                    self.assertNotIn("confirmation_token", payload)
                    resolve.assert_not_called()
                self.assertEqual(registry.pending_tokens, [])
            with db.connect() as conn:
                count = conn.execute("SELECT COUNT(*) AS c FROM pending_actions").fetchone()["c"]
            self.assertEqual(count, 0)

    async def test_owner_remove_from_arr_proposes_and_model_cannot_redeem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            settings = Settings(
                radarr_url="http://radarr",
                radarr_api_key="secret",
                features=FeatureFlags(multi_user_enabled=True),
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="o1", user_role="owner")
            resolved = {"arr_id": 42, "title": "Doomed", "tmdb_id": 555}
            with patch(
                "projectionist.agent.tools.acquire.resolve_arr_removal_target",
                return_value=resolved,
            ), patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls:
                proposal = json.loads(
                    await registry.execute(
                        "remove_from_arr",
                        {"media_type": "movie", "tmdb_id": 555, "delete_files": True},
                    )
                )
                token = proposal["confirmation_token"]
                for args in (
                    {"confirmation_token": token},
                    {"confirmation_token": token, "confirmed": True},
                    {"token": token, "confirmed": "yes"},
                ):
                    redeemed = json.loads(await registry.execute("confirm_pending_action", args))
                    self.assertEqual(redeemed.get("code"), "confirm_requires_user")
                radarr_cls.assert_not_called()
            self.assertEqual(db.peek_pending_action_kind(token), "remove_arr")
            stored = db.pop_pending_action(token, user_id="o1")
            self.assertTrue(stored["delete_files"])
            self.assertTrue(stored["add_exclusion"])

    async def test_model_can_still_cancel_a_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.save_pending_action("tok-cancel", "add_radarr", {"action": "add_radarr"}, user_id="m1")
            registry = ToolRegistry(
                db, _multi_user_settings(), DEFAULT_LENS_ID, user_id="m1", user_role="member"
            )
            out = json.loads(
                await registry.execute(
                    "confirm_pending_action", {"confirmation_token": "tok-cancel", "confirmed": False}
                )
            )
            self.assertTrue(out["cancelled"])
            self.assertIsNone(db.peek_pending_action_kind("tok-cancel"))


class ConfirmRouteTests(_HouseholdApp):
    def test_member_cannot_redeem_owner_only_token(self) -> None:
        self.db.save_pending_action(
            "tok-remove",
            "remove_arr",
            {"action": "remove_arr", "media_type": "movie", "arr_id": 1, "delete_files": True},
            user_id=None,
        )
        member = self._client_for("member")
        resp = member.post("/api/actions/confirm", json={"token": "tok-remove", "confirmed": True})
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertEqual(self.db.peek_pending_action_kind("tok-remove"), "remove_arr")

    def _save_remove_token(self, token: str, *, user_id, media_type: str = "movie") -> None:
        payload = {
            "action": "remove_arr",
            "media_type": media_type,
            "arr_id": 42,
            "title": "Doomed",
            "delete_files": True,
            "add_exclusion": True,
        }
        payload["tmdb_id" if media_type == "movie" else "tvdb_id"] = 555
        self.db.save_pending_action(token, "remove_arr", payload, user_id=user_id)

    def test_youth_and_member_crafted_remove_tokens_never_reach_arr(self) -> None:
        cases = (
            ("member", "local-member", "movie"),
            ("member", "local-owner", "show"),
            ("member", None, "show"),
            ("youth", "local-youth", "movie"),
            ("youth", "local-owner", "movie"),
        )
        with patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls, patch(
            "projectionist.agent.tools.confirmed.SonarrClient"
        ) as sonarr_cls, patch(
            "projectionist.agent.tools.confirmed.resolve_arr_removal_target"
        ) as resolve:
            for index, (username, token_owner, media_type) in enumerate(cases):
                token = f"tok-crafted-{index}"
                self._save_remove_token(token, user_id=token_owner, media_type=media_type)
                client = self._client_for(username)
                resp = client.post("/api/actions/confirm", json={"token": token, "confirmed": True})
                self.assertEqual(resp.status_code, 403, (username, resp.text))
                self.assertEqual(
                    resp.json()["detail"], "Only the household owner can confirm this action"
                )
                self.assertEqual(self.db.peek_pending_action_kind(token), "remove_arr")
            radarr_cls.assert_not_called()
            sonarr_cls.assert_not_called()
            resolve.assert_not_called()

    def test_owner_confirm_removes_with_files_and_exclusion(self) -> None:
        self._save_remove_token("tok-owner", user_id="local-owner")
        owner = self._client_for("owner")
        resolved = {"arr_id": 42, "title": "Doomed", "tmdb_id": 555}
        with patch("projectionist.agent.tools.confirmed.RadarrClient") as radarr_cls, patch(
            "projectionist.agent.tools.confirmed.resolve_arr_removal_target",
            return_value=resolved,
        ):
            resp = owner.post("/api/actions/confirm", json={"token": "tok-owner", "confirmed": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["action"], "remove_arr")
        radarr_cls.return_value.delete_movie.assert_called_once_with(
            42, delete_files=True, add_exclusion=True
        )
        self.assertTrue(self.db.is_acquisition_excluded(media_type="movie", tmdb_id=555))
        self.assertIsNone(self.db.peek_pending_action_kind("tok-owner"))


class YouthSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "t.db")
        self.settings = Settings()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _newsletter(self, user):
        from projectionist.notifications import newsletters

        rows = {
            "adult": {"id": 1, "title": "Adult Pick", "content_rating": "R", "view_count": 0},
            "kid": {"id": 2, "title": "Kid Pick", "content_rating": "PG", "view_count": 0},
        }
        watched = [
            {"id": 10, "title": "Seen R", "content_rating": "R"},
            {"id": 11, "title": "Seen G", "content_rating": "G"},
        ]
        seeds_seen = []

        def bridge(_db, row, seeds):
            seeds_seen.append([seed["title"] for seed in seeds])
            return {"kind": "watched_bridge", "sentence": f"Because of {row['title']}"}

        digest = {"new_this_week": {"titles": [{"ref": "adult"}, {"ref": "kid"}]}}
        with patch.object(newsletters, "build_weekly_digest", return_value=digest), patch.object(
            newsletters, "library_row_for_ref", side_effect=lambda _db, item: rows[item["ref"]]
        ), patch.object(newsletters, "watched_library_rows", return_value=watched), patch.object(
            newsletters, "tracker_watched_item_ids", return_value=set()
        ), patch.object(newsletters, "specific_bridge", side_effect=bridge):
            out = newsletters.build_member_newsletter(self.db, self.settings, user=user)
        return out, seeds_seen

    def test_youth_newsletter_drops_over_ceiling_titles_and_seeds(self) -> None:
        out, seeds = self._newsletter({"id": "y1", "display_name": "Kid", "is_youth": True})
        self.assertNotIn("Adult Pick", out["body"])
        self.assertIn("Kid Pick", out["body"])
        self.assertTrue(seeds)
        for seed_titles in seeds:
            self.assertNotIn("Seen R", seed_titles)

    def test_adult_newsletter_is_unchanged(self) -> None:
        out, _seeds = self._newsletter({"id": "a1", "display_name": "Adult", "is_youth": False})
        self.assertIn("Adult Pick", out["body"])
        self.assertIn("Kid Pick", out["body"])

    def test_nudges_skip_youth_accounts(self) -> None:
        from projectionist.notifications import nudges

        users = [{"id": "y1", "is_youth": True, "nudge_opt_in": True, "disabled": False}]
        with patch.object(self.db, "list_users", return_value=users), patch.object(
            nudges, "pick_nudge_title"
        ) as pick, patch.object(nudges, "deliver_notification") as deliver:
            nudges.deliver_enthusiast_nudges(self.db, self.settings)
        pick.assert_not_called()
        deliver.assert_not_called()

    def test_youth_continue_watching_is_gated_and_skips_on_deck(self) -> None:
        from projectionist.library import explore_hub

        rail = {
            "items": [
                {"title": "South Park", "content_rating": "TV-MA", "rating_key": "1"},
                {"title": "Mister Rogers", "content_rating": "TV-Y", "rating_key": "2"},
                {"title": "Unrated", "content_rating": "", "rating_key": "3"},
            ],
            "total": 3,
        }
        payload = {"rails": {"continue_watching": rail}}
        with patch(
            "projectionist.library.continue_watching_progress.apply_known_continue_watching",
            side_effect=lambda _db, r: r,
        ):
            youth = explore_hub._public_copy(
                payload, cached=True, stale=False, db=self.db, youth_settings=self.settings
            )
            adult = explore_hub._public_copy(payload, cached=True, stale=False, db=self.db)
        youth_titles = [i["title"] for i in youth["rails"]["continue_watching"]["items"]]
        self.assertEqual(youth_titles, ["Mister Rogers"])
        self.assertEqual(youth["rails"]["continue_watching"]["total"], 1)
        self.assertEqual(len(adult["rails"]["continue_watching"]["items"]), 3)

        plex = object()
        seen = []
        with patch.object(
            explore_hub,
            "feed_continue_watching",
            side_effect=lambda _db, limit, plex_client: seen.append(plex_client) or {},
        ):
            for is_youth in (True, False):
                builders = dict(
                    explore_hub._slow_rail_builders(self.db, capped=5, plex=plex, is_youth=is_youth)
                )
                builders["continue_watching"]()
        self.assertEqual(seen, [None, plex])


class SettingsFailClosedTests(_HouseholdApp):
    def test_truncated_settings_returns_503_not_owner(self) -> None:
        member = self._client_for("member")
        (self.data_dir / "settings.json").write_text("", encoding="utf-8")
        anonymous = TestClient(self.app_mod.app)
        for client in (anonymous, member):
            resp = client.get("/api/auth/me")
            self.assertEqual(resp.status_code, 503, resp.text)
            self.assertNotIn("owner", resp.text.lower().replace("restore", ""))
        self.assertEqual(anonymous.get("/api/health").status_code, 200)

    def test_non_object_settings_fail_closed(self) -> None:
        from projectionist.config_store import SettingsCorruptError, load_merged_settings

        (self.data_dir / "settings.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(SettingsCorruptError):
            load_merged_settings(self.data_dir)

    def test_failed_write_leaves_original_intact(self) -> None:
        from projectionist.config_store import load_merged_settings, save_settings

        path = self.data_dir / "settings.json"
        before = path.read_text(encoding="utf-8")
        settings = load_merged_settings(self.data_dir)
        settings.features.multi_user_enabled = False
        with patch("projectionist.config_store.os.replace", side_effect=OSError("power cut")):
            with self.assertRaises(OSError):
                save_settings(self.data_dir, settings)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual([p.name for p in self.data_dir.glob(".settings.json.*")], [])
        self.assertTrue(load_merged_settings(self.data_dir).features.multi_user_enabled)

    def test_save_is_owner_only_file(self) -> None:
        from projectionist.config_store import load_merged_settings, save_settings

        path = save_settings(self.data_dir, load_merged_settings(self.data_dir))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SessionAndExportTests(_HouseholdApp):
    def test_owner_keeps_session_after_creating_member(self) -> None:
        owner = self._client_for("owner")
        resp = owner.post(
            "/api/auth/local/register", json={"username": "newkid", "password": "password456"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["created"])
        self.assertNotIn(SESSION_COOKIE_NAME, resp.headers.get("set-cookie", ""))
        me = owner.get("/api/auth/me").json()
        self.assertEqual(me["user"]["id"], "local-owner")

    def _seed_taste(self, user_id: str, text: str) -> None:
        now = time.time()
        self.db.add_preference("explicit", text, user_id=user_id)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_title_reviews
                    (id, rating_key, media_type, title, stars, review_text, created_at, updated_at, user_id)
                VALUES (?, ?, 'movie', ?, 4, ?, ?, ?, ?)
                """,
                (f"rev-{user_id}", f"rk-{user_id}", text, text, now, now, user_id),
            )

    def test_taste_export_is_caller_only(self) -> None:
        self._seed_taste("local-owner", "owner-taste")
        self._seed_taste("local-member", "member-taste")
        for username, mine, theirs in (
            ("member", "member-taste", "owner-taste"),
            ("owner", "owner-taste", "member-taste"),
        ):
            resp = self._client_for(username).get("/api/me/taste-export")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertIn("projectionist-my-taste-", resp.headers["content-disposition"])
            self.assertIn(mine, resp.text)
            self.assertNotIn(theirs, resp.text)

    def test_household_backup_download_is_audited(self) -> None:
        from projectionist.web.backup import household_backup_log

        owner = self._client_for("owner")
        resp = owner.get("/api/admin/backup/snapshot")
        self.assertEqual(resp.status_code, 200, resp.text)
        log = household_backup_log(self.db)
        self.assertEqual([entry["actor_id"] for entry in log], ["local-owner"])
        member = self._client_for("member")
        self.assertEqual(member.get("/api/admin/backup/snapshot").status_code, 403)


class ConnectedHonestyTests(unittest.TestCase):
    def test_certified_service_without_readable_key_is_not_connected(self) -> None:
        from projectionist.web.setup import build_certifications_status

        from projectionist.secrets_crypto import encrypt_secret

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            db = Database(data_dir / "t.db")
            db.upsert_service_integration("tmdb", connection_status="verified", certified=1)
            with patch.dict(os.environ, {"PROJECTIONIST_SECRETS_KEY": "old-key"}):
                ciphertext = encrypt_secret("tmdb-secret", data_dir=data_dir)
            (data_dir / "settings.json").write_text(json.dumps({"tmdb_api_key": ciphertext}), encoding="utf-8")
            with patch.dict(os.environ, {"PROJECTIONIST_SECRETS_KEY": "old-key"}):
                readable = build_certifications_status(db, data_dir)["services"]["tmdb"]
            with patch.dict(os.environ, {"PROJECTIONIST_SECRETS_KEY": "new-key"}):
                swapped = build_certifications_status(db, data_dir)["services"]["tmdb"]
        self.assertTrue(readable["certified"])
        self.assertFalse(swapped["certified"])
        self.assertEqual(swapped["connection_status"], "needs_key")


class MoviesQueryOffLoopTests(_HouseholdApp):
    multi_user = False

    def test_health_answers_while_a_slow_library_query_runs(self) -> None:
        import httpx

        def slow_query(*_args, **_kwargs):
            time.sleep(0.8)
            return {"items": [], "total": 0}

        async def run() -> tuple[float, float]:
            transport = httpx.ASGITransport(app=self.app_mod.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                start = time.perf_counter()
                query = asyncio.create_task(client.get("/api/library/query?media_type=movie"))
                await asyncio.sleep(0.1)
                health = await client.get("/api/health")
                health_at = time.perf_counter() - start
                self.assertEqual(health.status_code, 200)
                resp = await query
                self.assertEqual(resp.status_code, 200, resp.text)
                return health_at, time.perf_counter() - start

        with patch("projectionist.web.library_routes.query_library", side_effect=slow_query):
            health_at, query_at = asyncio.run(run())
        self.assertLess(health_at, 0.5)
        self.assertGreater(query_at, 0.7)


if __name__ == "__main__":
    unittest.main()
