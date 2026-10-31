"""Phase 6 owner operations: checklist persistence, event spine, attribution, audit authz."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.web.auth import _hash_password, clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache

_ENV_KEYS = (
    "DATA_DIR",
    "PROJECTIONIST_SKIP_DOTENV",
    "LLM_PROVIDER",
    "PROJECTIONIST_SESSION_SECRET",
    "PROJECTIONIST_SETUP_STATE",
    "PROJECTIONIST_SECRETS_KEY",
)


def _wait_for(predicate, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return predicate()


def _stream_rows(db: Database, event_class: str):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT payload_json, media_node_id FROM system_telemetry_stream WHERE event_class = ?",
            (event_class,),
        ).fetchall()
    return [(json.loads(r["payload_json"]), r["media_node_id"]) for r in rows]


class _Household(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-phase6-owner-ops-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
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

    def _events(self, event: str):
        return self.db.list_security_events(event=event, limit=200)["items"]


class OwnerOpsAuthzTests(_Household):
    def test_member_and_youth_cannot_read_audit_or_ops(self) -> None:
        for name in ("member", "youth"):
            client = self._client_for(name)
            for path in ("/api/admin/security-audit", "/api/admin/ops/overview"):
                resp = client.get(path)
                self.assertEqual(resp.status_code, 403, f"{name} {path}: {resp.text}")
            resp = client.put("/api/admin/ops/checklist/setup/backup", json={"status": "skipped"})
            self.assertEqual(resp.status_code, 403)
            resp = client.post("/api/admin/ops/monday-pass/complete")
            self.assertEqual(resp.status_code, 403)

    def test_anonymous_cannot_read_audit(self) -> None:
        resp = TestClient(self.app_mod.app).get("/api/admin/security-audit")
        self.assertIn(resp.status_code, (401, 403))

    def test_owner_reads_audit_with_filters(self) -> None:
        owner = self._client_for("owner")
        resp = owner.get("/api/admin/security-audit")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertIn("sign_in", body["events"])
        self.assertEqual(body["user_names"].get("local-owner"), "owner")
        filtered = owner.get("/api/admin/security-audit", params={"event": "sign_in", "user_id": "local-owner"})
        self.assertTrue(all(i["event"] == "sign_in" for i in filtered.json()["items"]))
        self.assertTrue(all("local-owner" in (i["actor_id"], i["target_id"]) for i in filtered.json()["items"]))
        paged = owner.get("/api/admin/security-audit", params={"limit": 1, "offset": 0}).json()
        self.assertEqual(len(paged["items"]), 1)


class SecurityAuditEventTests(_Household):
    def test_sign_in_success_and_failure_write_one_row_each(self) -> None:
        self._client_for("member")
        rows = [r for r in self._events("sign_in") if r["actor_id"] == "local-member"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["detail"], {"method": "local"})
        resp = TestClient(self.app_mod.app).post(
            "/api/auth/local/login", json={"username": "member", "password": "wrong-password-x"}
        )
        self.assertEqual(resp.status_code, 401)
        failed = self._events("sign_in_failed")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["outcome"], "denied")
        self.assertNotIn("wrong-password-x", json.dumps(failed))

    def test_password_change_and_reset(self) -> None:
        member = self._client_for("member")
        resp = member.post(
            "/api/auth/password",
            json={"current_password": "password123", "new_password": "a-new-password-1"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        changes = self._events("password_change")
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["target_id"], "local-member")
        owner = self._client_for("owner")
        resp = owner.post(
            "/api/users/local-youth/reset-password", json={"new_password": "reset-password-2"}
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        resets = self._events("password_reset")
        self.assertEqual(len(resets), 1)
        self.assertEqual((resets[0]["actor_id"], resets[0]["target_id"]), ("local-owner", "local-youth"))
        dumped = json.dumps(self.db.list_security_events(limit=200))
        for secret in ("a-new-password-1", "reset-password-2", "password123"):
            self.assertNotIn(secret, dumped)

    def test_role_youth_and_invite_events(self) -> None:
        owner = self._client_for("owner")
        resp = owner.patch("/api/users/local-member", json={"role": "owner"})
        self.assertEqual(resp.status_code, 200, resp.text)
        roles = self._events("role_change")
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0]["detail"], {"before": "member", "after": "owner"})
        owner.patch("/api/users/local-youth", json={"is_youth": False})
        self.assertEqual(len(self._events("youth_change")), 1)
        resp = owner.post("/api/admin/invites", json={"role": "member"})
        self.assertEqual(resp.status_code, 200, resp.text)
        invite_id = resp.json()["invite"]["id"]
        created = self._events("invite_create")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["target_id"], invite_id)
        raw_token = resp.json().get("token") or ""
        if raw_token:
            self.assertNotIn(raw_token, json.dumps(created))
        owner.post(f"/api/admin/invites/{invite_id}/revoke")
        self.assertEqual(len(self._events("invite_revoke")), 1)

    def test_settings_save_records_field_names_not_values(self) -> None:
        owner = self._client_for("owner")
        current = owner.get("/api/settings").json()
        current["tmdb_api_key"] = "tmdb-secret-value-xyz"
        current["plex_url"] = "http://plex.example.lan:32400"
        resp = owner.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 200, resp.text)
        saves = self._events("settings_save")
        self.assertEqual(len(saves), 1)
        fields = saves[0]["detail"]["fields"]
        self.assertIn("tmdb_api_key", fields)
        self.assertIn("plex_url", fields)
        self.assertNotIn("tmdb-secret-value-xyz", json.dumps(saves))


class ChecklistPersistenceTests(_Household):
    def test_setup_skip_persists_and_restores(self) -> None:
        owner = self._client_for("owner")
        overview = owner.get("/api/admin/ops/overview").json()
        backup = next(i for i in overview["setup"]["items"] if i["id"] == "backup")
        self.assertEqual(backup["status"], "pending")
        resp = owner.put("/api/admin/ops/checklist/setup/backup", json={"status": "skipped"})
        self.assertEqual(resp.status_code, 200, resp.text)
        # A fresh Database on the same file sees the mark: it is on disk, not in memory.
        fresh = Database(self.db.path)
        self.assertEqual(fresh.list_checklist_marks("setup")["backup"]["status"], "skipped")
        again = owner.get("/api/admin/ops/overview").json()
        self.assertEqual(
            next(i for i in again["setup"]["items"] if i["id"] == "backup")["status"], "skipped"
        )
        self.assertNotIn("setup-backup", [i["id"] for i in again["needs_attention"]])
        owner.put("/api/admin/ops/checklist/setup/backup", json={"status": "pending"})
        restored = owner.get("/api/admin/ops/overview").json()
        self.assertEqual(
            next(i for i in restored["setup"]["items"] if i["id"] == "backup")["status"], "pending"
        )

    def test_setup_item_verified_by_server(self) -> None:
        owner = self._client_for("owner")
        self.assertEqual(owner.get("/api/admin/backup/snapshot").status_code, 200)
        resp = owner.get("/api/admin/ops/overview").json()
        statuses = {i["id"]: i["status"] for i in resp["setup"]["items"]}
        self.assertEqual(statuses["backup"], "done")
        self.assertEqual(statuses["invite"], "done")  # three accounts exist
        self.assertEqual(len(self._events("household_backup")), 1)

    def test_unknown_items_rejected(self) -> None:
        owner = self._client_for("owner")
        self.assertEqual(
            owner.put("/api/admin/ops/checklist/setup/nope", json={"status": "skipped"}).status_code, 404
        )
        self.assertEqual(
            owner.put("/api/admin/ops/checklist/monday/nope", json={"status": "reviewed"}).status_code, 404
        )
        self.assertEqual(
            owner.put("/api/admin/ops/checklist/other/x", json={"status": "reviewed"}).status_code, 404
        )

    def test_monday_pass_review_complete_and_timestamp(self) -> None:
        owner = self._client_for("owner")
        early = owner.post("/api/admin/ops/monday-pass/complete")
        self.assertEqual(early.status_code, 409)
        for step in ("kinship", "issues", "purge", "catchup"):
            resp = owner.put(f"/api/admin/ops/checklist/monday/{step}", json={"status": "reviewed"})
            self.assertEqual(resp.status_code, 200, resp.text)
        monday = owner.get("/api/admin/ops/overview").json()["monday"]
        self.assertTrue(monday["ready"])
        self.assertIsNone(monday["completed_at"])
        done = owner.post("/api/admin/ops/monday-pass/complete")
        self.assertEqual(done.status_code, 200, done.text)
        self.assertIsNotNone(done.json()["completed_at"])
        self.assertEqual(done.json()["last_completed_period"], done.json()["period"])
        overview = owner.get("/api/admin/ops/overview").json()
        self.assertNotIn("monday-pass", [i["id"] for i in overview["needs_attention"]])
        # Un-reviewing a step reopens the week's pass.
        owner.put("/api/admin/ops/checklist/monday/kinship", json={"status": "pending"})
        reopened = owner.get("/api/admin/ops/overview").json()["monday"]
        self.assertIsNone(reopened["completed_at"])
        self.assertIsNotNone(reopened["last_completed_at"])

    def test_monday_period_is_per_week(self) -> None:
        from projectionist.web.owner_ops import build_monday_pass

        now = time.time()
        self.db.set_checklist_mark("monday", "kinship", "reviewed", period="2000-W01")
        monday = build_monday_pass(self.db, now=now)
        kinship = next(s for s in monday["steps"] if s["id"] == "kinship")
        self.assertNotEqual(kinship["status"], "reviewed")

    def test_catch_up_queues_warm_explore_and_marks_step(self) -> None:
        owner = self._client_for("owner")

        class _FakeScheduler:
            def __init__(self) -> None:
                self.ran: list[str] = []

            def get_task_states(self):
                return [{"name": n, "enabled": True} for n in ("metadata_enrichment", "plot_neighbors")]

            async def trigger_task(self, name):
                self.ran.append(name)
                return {"status": "completed"}

        fake = _FakeScheduler()
        with TestClient(self.app_mod.app) as client:
            client.cookies.update(owner.cookies)
            self.app_mod.app.state.idle_scheduler = fake
            resp = client.post("/api/admin/ops/monday-pass/catch-up")
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["queued"], ["metadata_enrichment", "plot_neighbors"])
            catchup = next(s for s in resp.json()["monday"]["steps"] if s["id"] == "catchup")
            self.assertEqual(catchup["status"], "done")
            _wait_for(lambda: len(fake.ran) == 2)
        self.assertEqual(fake.ran, ["metadata_enrichment", "plot_neighbors"])


class SecretsCardTests(_Household):
    def test_undecryptable_secret_is_needs_key_and_needs_attention(self) -> None:
        from projectionist.secrets_crypto import encrypt_secret

        os.environ["PROJECTIONIST_SECRETS_KEY"] = "first-key-for-phase6"
        settings_path = self.data_dir / "settings.json"
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
        raw["tmdb_api_key"] = encrypt_secret("tmdb-real", data_dir=self.data_dir)
        settings_path.write_text(json.dumps(raw), encoding="utf-8")
        self.db.upsert_service_integration("tmdb", connection_status="verified", certified=1)
        os.environ["PROJECTIONIST_SECRETS_KEY"] = "a-different-key-now"
        owner = self._client_for("owner")
        body = owner.get("/api/admin/ops/overview").json()
        tmdb = next(s for s in body["secrets"]["services"] if s["id"] == "tmdb")
        self.assertEqual(tmdb["state"], "needs_key")
        self.assertFalse(tmdb["certified"])
        self.assertIsNotNone(tmdb["last_tested_at"])
        self.assertEqual(body["secrets"]["status"], "fail")
        self.assertIn("tmdb_api_key", body["secrets"]["unreadable_fields"])
        self.assertEqual(body["needs_attention"][0]["id"], "secrets-unreadable")
        self.assertNotIn("tmdb-real", json.dumps(body))

    def test_certified_without_key_is_a_disagreement(self) -> None:
        self.db.upsert_service_integration("radarr", connection_status="verified", certified=1)
        owner = self._client_for("owner")
        env = {k: v for k, v in os.environ.items() if not k.startswith("RADARR_")}
        with patch.dict(os.environ, env, clear=True):
            body = owner.get("/api/admin/ops/overview").json()
        radarr = next(s for s in body["secrets"]["services"] if s["id"] == "radarr")
        self.assertEqual(radarr["state"], "stale")
        self.assertIn("radarr", body["secrets"]["disagreements"])
        self.assertIn("secrets-radarr", [i["id"] for i in body["needs_attention"]])

    def test_failed_tasks_roll_up(self) -> None:
        owner = self._client_for("owner")

        class _Sched:
            def get_task_states(self):
                return [
                    {"name": "plot_neighbors", "enabled": True, "last_status": "error: boom"},
                    {"name": "taste_refresh", "enabled": True, "last_status": "completed"},
                    {"name": "gap_analysis", "enabled": False, "last_status": "error: off"},
                ]

        self.app_mod.app.state.idle_scheduler = _Sched()
        try:
            body = owner.get("/api/admin/ops/overview").json()
        finally:
            self.app_mod.app.state.idle_scheduler = None
        self.assertEqual([t["name"] for t in body["failed_tasks"]], ["plot_neighbors"])
        tasks = next(i for i in body["needs_attention"] if i["id"] == "tasks-failed")
        self.assertIn("Plot neighbors", tasks["detail"])


class ChatTurnEventTests(_Household):
    def _fake_stream(self, *_args, **_kwargs):
        async def _gen():
            yield json.dumps({"type": "tool_start", "name": "search_library"}) + "\n"
            yield json.dumps({"type": "tool_result", "name": "search_library"}) + "\n"
            yield json.dumps({"type": "token", "content": "secret household words"}) + "\n"
            yield json.dumps(
                {
                    "type": "done",
                    "message": {
                        "id": "m1",
                        "role": "assistant",
                        "blocks": [
                            {"type": "text", "content": "secret household words"},
                            {"type": "title_cards", "items": [{"rating_key": "1"}, {"rating_key": "2"}]},
                        ],
                    },
                }
            ) + "\n"

        return _gen()

    def test_streaming_turn_emits_one_chat_turn_without_text(self) -> None:
        member = self._client_for("member")
        with patch("projectionist.web.chat_routes.stream_agent", side_effect=self._fake_stream):
            resp = member.post("/api/chat/stream", json={"message": "a private question"})
            self.assertEqual(resp.status_code, 200)
            _ = resp.text
        rows = _wait_for(lambda: _stream_rows(self.db, "chat_turn"))
        self.assertEqual(len(rows), 1)
        payload = rows[0][0]
        self.assertEqual(payload["surface"], "stream")
        self.assertEqual(payload["outcome"], "completed")
        self.assertEqual(payload["card_count"], 2)
        self.assertEqual(payload["tool_count"], 1)
        self.assertEqual(payload["user_id"], "local-member")
        self.assertIn("app_version", payload)
        dumped = json.dumps(rows)
        self.assertNotIn("secret household words", dumped)
        self.assertNotIn("a private question", dumped)

    def test_stream_error_records_error_outcome(self) -> None:
        def _boom(*_args, **_kwargs):
            async def _gen():
                raise RuntimeError("provider down")
                yield ""  # pragma: no cover

            return _gen()

        member = self._client_for("member")
        with patch("projectionist.web.chat_routes.stream_agent", side_effect=_boom):
            _ = member.post("/api/chat/stream", json={"message": "hi"}).text
        rows = _wait_for(lambda: _stream_rows(self.db, "chat_turn"))
        self.assertEqual(rows[0][0]["outcome"], "error")

    def test_account_export_and_purge_cover_own_chat_turns(self) -> None:
        member = self._client_for("member")
        with patch("projectionist.web.chat_routes.stream_agent", side_effect=self._fake_stream):
            _ = member.post("/api/chat/stream", json={"message": "hi"}).text
        owner = self._client_for("owner")
        with patch("projectionist.web.chat_routes.stream_agent", side_effect=self._fake_stream):
            _ = owner.post("/api/chat/stream", json={"message": "hi"}).text
        _wait_for(lambda: len(_stream_rows(self.db, "chat_turn")) >= 2)
        exported = self.db.export_user_memory("local-member")
        self.assertEqual(
            [e["event_class"] for e in exported["interaction_events"]], ["chat_turn"]
        )
        result = self.db.purge_user_memory_and_chats("local-member")
        self.assertEqual(result["interaction_events_deleted"], 1)
        remaining = [p["user_id"] for p, _ in _stream_rows(self.db, "chat_turn")]
        self.assertEqual(remaining, ["local-owner"])

    def test_telemetry_switch_off_stops_chat_turn(self) -> None:
        self.db.set_config("telemetry_enabled", "false")
        member = self._client_for("member")
        with patch("projectionist.web.chat_routes.stream_agent", side_effect=self._fake_stream):
            _ = member.post("/api/chat/stream", json={"message": "hi"}).text
        time.sleep(0.3)
        self.assertEqual(_stream_rows(self.db, "chat_turn"), [])


class PlayAttributionTests(_Household):
    def _seed_chat_card(self, user_id: str, rating_key: str) -> str:
        session_id = uuid.uuid4().hex
        self.db.ensure_chat_session(session_id, DEFAULT_LENS_ID, user_id=user_id)
        message_id = uuid.uuid4().hex
        self.db.save_chat_message(
            session_id,
            message_id,
            "assistant",
            [{"type": "title_cards", "items": [{"rating_key": rating_key, "title": "Heat"}]}],
            lens_id=DEFAULT_LENS_ID,
        )
        return message_id

    def _play(self, client: TestClient, rating_key: str, rec=None):
        body = {"rating_key": rating_key}
        if rec is not None:
            body["rec"] = rec
        with patch(
            "projectionist.web.playback_routes.start_playback",
            return_value={"session_id": "s1", "duration_ms": 1},
        ):
            resp = client.post("/api/library/playback/start", json=body)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_verified_chat_pick_is_attributed(self) -> None:
        message_id = self._seed_chat_card("local-member", "555")
        self._play(self._client_for("member"), "555", rec=f"chat:{message_id}")
        rows = _wait_for(lambda: _stream_rows(self.db, "play_start"))
        payload, media = rows[0]
        self.assertEqual(media, "555")
        self.assertEqual((payload["rec_source"], payload["rec_id"]), ("chat", message_id))
        self.assertNotIn("Heat", json.dumps(rows))
        self.assertEqual(self.db.local_event_counts(days=7)["plays_from_picks"], 1)

    def test_other_members_pick_or_wrong_title_is_not_attributed(self) -> None:
        theirs = self._seed_chat_card("local-owner", "555")
        mine = self._seed_chat_card("local-member", "555")
        member = self._client_for("member")
        self._play(member, "555", rec=f"chat:{theirs}")
        self._play(member, "999", rec=f"chat:{mine}")
        self._play(member, "555", rec="plex:history")
        self._play(member, "555")
        rows = _wait_for(lambda: len(_stream_rows(self.db, "play_start")) == 4 and _stream_rows(self.db, "play_start"))
        self.assertEqual(len(rows), 4)
        for payload, _media in rows:
            self.assertIsNone(payload["rec_id"])
            self.assertIsNone(payload["rec_source"])
        counts = self.db.local_event_counts(days=7)
        self.assertEqual((counts["plays"], counts["plays_from_picks"]), (4, 0))

    def test_member_share_is_attributed(self) -> None:
        rec_id = uuid.uuid4().hex
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_recommendations
                    (id, from_user_id, to_user_id, media_type, rating_key, title, created_at)
                VALUES (?, 'local-owner', 'local-member', 'movie', '777', 'Ran', ?)
                """,
                (rec_id, time.time()),
            )
        self._play(self._client_for("member"), "777", rec=f"share:{rec_id}")
        rows = _wait_for(lambda: _stream_rows(self.db, "play_start"))
        self.assertEqual(rows[0][0]["rec_source"], "share")
        self.assertEqual(rows[0][0]["rec_id"], rec_id)


class AttributionParseTests(unittest.TestCase):
    def test_parse_rec_claim(self) -> None:
        from projectionist.telemetry.attribution import parse_rec_claim

        self.assertEqual(parse_rec_claim("chat:abc"), ("chat", "abc"))
        self.assertEqual(parse_rec_claim(" SHARE:x1 "), ("share", "x1"))
        for bad in (None, "", "chat:", "plex:1", "nocolon", "chat:" + "x" * 200):
            self.assertIsNone(parse_rec_claim(bad))


class AuditScrubTests(unittest.TestCase):
    def test_secret_named_detail_keys_are_dropped(self) -> None:
        from projectionist.security_audit import _scrub, changed_setting_names

        clean = _scrub({"api_key": "x", "new_password": "y", "token": "z", "field": "plex_token"})
        self.assertEqual(clean, {"field": "plex_token"})
        self.assertEqual(
            changed_setting_names({"a": 1, "m": {"x": 1, "y": 2}}, {"a": 1, "m": {"x": 2, "y": 2}}),
            ["m.x"],
        )


if __name__ == "__main__":
    unittest.main()
