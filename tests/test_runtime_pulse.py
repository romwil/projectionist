"""Ready means working (PERF-007), on-box runtime metrics (PERF-001), household pulse (GRO-018)."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web import runtime_metrics
from projectionist.web.household_pulse import WEEK_S, build_household_pulse


def _insert_event(db, event_class: str, payload: dict, *, at: float) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(at))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO system_telemetry_stream (id, event_class, payload_json, timestamp) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), event_class, json.dumps(payload), stamp),
        )
        conn.commit()


class _AppCase(unittest.TestCase):
    multi_user = True

    def setUp(self) -> None:
        from projectionist.web.auth import _hash_password, clear_pin_bindings
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-runtime-pulse-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        settings = {"llm_provider": "ollama"}
        if self.multi_user:
            settings.update(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                }
            )
        Path(self._tmp.name, "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        if self.multi_user:
            for name, role in (("owner", "owner"), ("alice", "member")):
                self.db.create_local_user(
                    user_id=f"local-{name}",
                    display_name=name,
                    password_hash=_hash_password("password123"),
                    role=role,
                )
        runtime_metrics.RESERVOIR.clear()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        self.app_mod.app.state.ready = False
        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        runtime_metrics.RESERVOIR.clear()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmp.cleanup()

    def _login(self, name: str) -> None:
        self.client.cookies.clear()
        resp = self.client.post("/api/auth/local/login", json={"username": name, "password": "password123"})
        self.assertEqual(resp.status_code, 200, resp.text)


class ReadyMeansWorkingTests(_AppCase):
    multi_user = False

    def test_ready_when_started_and_database_answers(self) -> None:
        self.app_mod.app.state.ready = True
        resp = self.client.get("/api/ready")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["database"], "ok")

    def test_ready_is_503_while_starting(self) -> None:
        self.app_mod.app.state.ready = False
        self.assertEqual(self.client.get("/api/ready").status_code, 503)

    def test_missing_database_fails_ready_but_not_health(self) -> None:
        self.app_mod.app.state.ready = True
        path = Path(self.db.path)
        path.rename(path.with_name(path.name + ".moved"))
        resp = self.client.get("/api/ready")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("missing", resp.json()["detail"])
        self.assertFalse(path.exists(), "ready must not create an empty database in place of the real one")
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

    def test_corrupt_database_fails_ready(self) -> None:
        self.app_mod.app.state.ready = True
        path = Path(self.db.path)
        path.rename(path.with_name(path.name + ".moved"))
        path.write_bytes(b"this is not a sqlite file" * 100)
        resp = self.client.get("/api/ready")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.json()["detail"])

    def test_slow_database_fails_ready(self) -> None:
        self.app_mod.app.state.ready = True
        path = Path(self.db.path)
        # An exclusive lock keeps even a read-only open from reading sqlite_master.
        import sqlite3

        holder = sqlite3.connect(str(path), isolation_level=None)
        holder.execute("PRAGMA journal_mode=DELETE")
        holder.execute("BEGIN EXCLUSIVE")
        try:
            started = time.perf_counter()
            state = runtime_metrics.probe_database(path, timeout_s=0.1)
            elapsed = time.perf_counter() - started
        finally:
            holder.execute("ROLLBACK")
            holder.close()
        self.assertIn(state, ("timeout", "error"))
        self.assertLess(elapsed, 1.0)


class RuntimeRouteTests(_AppCase):
    def test_owner_sees_queue_depth_and_latency(self) -> None:
        self._login("owner")
        self.client.get("/api/library/query", params={"q": "x"})
        for i in range(3):
            self.db.run_write(lambda i=i: i, label="test")
        gate = threading.Event()
        blocker = threading.Thread(target=lambda: self.db.run_write(gate.wait, label="block"), daemon=True)
        blocker.start()
        try:
            deadline = time.time() + 2
            while time.time() < deadline and self.db.write_queue_stats()["jobs_done"] < 3:
                time.sleep(0.01)
            waiters = [
                threading.Thread(target=lambda: self.db.run_write(lambda: None, label="queued"), daemon=True)
                for _ in range(2)
            ]
            for waiter in waiters:
                waiter.start()
            while time.time() < deadline + 2 and self.db.write_queue_stats()["queue_depth"] < 2:
                time.sleep(0.01)
            resp = self.client.get("/api/admin/runtime")
        finally:
            gate.set()
            blocker.join(timeout=5)
            for waiter in locals().get("waiters", []):
                waiter.join(timeout=5)
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertGreaterEqual(body["write_queue"]["queue_depth"], 2)
        self.assertGreaterEqual(body["write_queue"]["jobs_done"], 3)
        self.assertIn("max_wait_s", body["write_queue"])
        self.assertIn("library_query", body["latency"])
        self.assertGreater(body["latency"]["api"]["count"], 0)
        self.assertIn(body["slo"]["library_query"]["status"], ("pass", "fail"))
        self.assertGreater(body["uptime_s"], 0)

    def test_member_gets_403(self) -> None:
        self._login("alice")
        self.assertEqual(self.client.get("/api/admin/runtime").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/pulse").status_code, 403)


class HouseholdPulseTests(_AppCase):
    def _seed(self, now: float) -> None:
        for i in range(10):
            _insert_event(
                self.db,
                "chat_turn",
                {"user_id": "local-alice", "outcome": "error" if i == 0 else "completed", "duration_ms": 1000 + i},
                at=now - 3600,
            )
        _insert_event(self.db, "chat_turn", {"user_id": "local-owner", "outcome": "cancelled"}, at=now - 3600)
        _insert_event(self.db, "play_start", {"user_id": "local-alice", "rec_id": "rec-1"}, at=now - 7200)
        _insert_event(self.db, "play_start", {"user_id": "local-alice"}, at=now - 7200)
        _insert_event(self.db, "play_start", {"user_id": "local-owner", "rec_id": "r2"}, at=now - WEEK_S - 60)
        _insert_event(self.db, "play_start", {"user_id": "local-owner", "rec_id": "old"}, at=now - 5 * WEEK_S)

    def test_pulse_totals_north_star_and_guardrails(self) -> None:
        now = time.time()
        self._seed(now)
        pulse = build_household_pulse(self.db, now=now)
        self.assertEqual(pulse["source"], "on_box")
        self.assertEqual(pulse["north_star"]["this_week"], 1)
        self.assertEqual(pulse["north_star"]["last_week"], 1)
        self.assertEqual(pulse["north_star"]["weekly"], [0, 0, 1, 1])
        guards = {g["id"]: g for g in pulse["guardrails"]}
        self.assertAlmostEqual(guards["chat_failure_rate"]["value"], round(1 / 11, 3))
        self.assertEqual(guards["chat_failure_rate"]["status"], "watch")
        self.assertEqual(guards["chat_p95_ms"]["status"], "ok")
        with self.db.connect() as conn:
            members = conn.execute("SELECT COUNT(*) AS c FROM users WHERE disabled = 0").fetchone()["c"]
        self.assertEqual(guards["dormant_members"]["value"], members - 2)
        self.assertEqual(pulse["weeks"][0]["active_members"], 2)
        self.assertIn("write_queue_depth", pulse["box"])

    def test_pulse_has_no_member_breakdown(self) -> None:
        now = time.time()
        self._seed(now)
        self._login("owner")
        resp = self.client.get("/api/admin/pulse")
        self.assertEqual(resp.status_code, 200, resp.text)
        text = resp.text
        for needle in ("local-alice", "local-owner", "alice", "rec-1"):
            self.assertNotIn(needle, text)

    def test_pulse_view_is_recorded_with_user_id_only(self) -> None:
        self._login("owner")
        self.assertEqual(self.client.get("/api/admin/pulse").status_code, 200)
        deadline = time.time() + 3
        rows = []
        while time.time() < deadline and not rows:
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM system_telemetry_stream WHERE event_class = 'owner_pulse_view'"
                ).fetchall()
            time.sleep(0.02)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(json.loads(rows[0]["payload_json"])), {"user_id", "app_version"})


class ReservoirTests(unittest.TestCase):
    def test_percentiles_and_window(self) -> None:
        reservoir = runtime_metrics.LatencyReservoir(size=10)
        for value in range(1, 21):
            reservoir.record("api", float(value))
        snap = reservoir.snapshot()["api"]
        self.assertEqual(snap["count"], 20)
        self.assertEqual(snap["window"], 10)
        self.assertEqual(snap["max_ms"], 20.0)
        self.assertGreaterEqual(snap["p95_ms"], snap["p50_ms"])

    def test_request_groups(self) -> None:
        self.assertEqual(runtime_metrics.request_group("/api/library/query"), "library_query")
        self.assertEqual(runtime_metrics.request_group("/api/chat/stream"), "chat")
        self.assertEqual(runtime_metrics.request_group("/api/ready"), "probe")
        self.assertIsNone(runtime_metrics.request_group("/assets/app.js"))


if __name__ == "__main__":
    unittest.main()
