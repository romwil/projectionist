"""Tests for telemetry ingestion (Item 29).

Covers event recording, query API, feature flag disable behaviour,
and privacy (no raw message text stored).
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.library.db import Database
from curatorx.telemetry.ingestion import TelemetryIngester
from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache


class TelemetryIngesterTests(unittest.TestCase):
    """Unit tests for TelemetryIngester writes to system_telemetry_stream."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        self.ingester = TelemetryIngester(self.db)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _wait_for_writes(self, timeout: float = 2.0) -> None:
        """Block until all daemon telemetry threads finish."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("telemetry-")]
            if not alive:
                return
            time.sleep(0.05)

    # -- Recording events --

    def test_record_chat_message(self) -> None:
        self.ingester.record_chat_message(
            session_id="s1",
            lens_id="default",
            message_length=42,
            persona_id=None,
            user_id="u1",
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="chat_message")
        self.assertEqual(len(events), 1)
        payload = json.loads(events[0]["payload_json"])
        self.assertEqual(payload["session_id"], "s1")
        self.assertEqual(payload["message_length"], 42)

    def test_record_chat_feedback(self) -> None:
        self.ingester.record_chat_feedback(
            message_id="m1",
            feedback_type="helpful",
            session_id="s1",
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="chat_feedback")
        self.assertEqual(len(events), 1)

    def test_record_preference_signal(self) -> None:
        self.ingester.record_preference_signal(
            signal_type="positive",
            media_references=["a", "b"],
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="preference_signal")
        self.assertEqual(len(events), 1)
        payload = json.loads(events[0]["payload_json"])
        self.assertEqual(payload["media_reference_count"], 2)

    def test_record_review_saved(self) -> None:
        self.ingester.record_review_saved(
            rating_key="rk1",
            stars=4,
            prompted_by="near_complete",
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="review_saved")
        self.assertEqual(len(events), 1)

    def test_record_playback_event(self) -> None:
        self.ingester.record_playback_event(
            event="media.stop",
            rating_key="rk2",
            completion_pct=85.5,
            media_type="movie",
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="playback_event")
        self.assertEqual(len(events), 1)

    def test_record_tool_invocation(self) -> None:
        self.ingester.record_tool_invocation(
            tool_name="search_library",
            duration_ms=120,
            result_count=5,
            session_id="s2",
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="tool_invocation")
        self.assertEqual(len(events), 1)

    # -- Feature flag --

    def test_disabled_flag_drops_events(self) -> None:
        self.db.set_config("telemetry_enabled", "false")
        self.ingester.record_chat_message(
            session_id="s1",
            lens_id="default",
            message_length=10,
        )
        self._wait_for_writes()
        events = self.db.telemetry_events()
        self.assertEqual(len(events), 0)

    def test_enabled_flag_allows_events(self) -> None:
        self.db.set_config("telemetry_enabled", "true")
        self.ingester.record_chat_message(
            session_id="s1",
            lens_id="default",
            message_length=10,
        )
        self._wait_for_writes()
        events = self.db.telemetry_events()
        self.assertEqual(len(events), 1)

    # -- Privacy: no raw text stored --

    def test_chat_message_never_stores_text(self) -> None:
        """The ingester accepts message_length, not the actual message."""
        self.ingester.record_chat_message(
            session_id="s1",
            lens_id="default",
            message_length=100,
        )
        self._wait_for_writes()
        events = self.db.telemetry_events(event_class="chat_message")
        raw = events[0]["payload_json"]
        self.assertNotIn("message_text", raw)
        self.assertNotIn("content", raw)

    # -- Query API --

    def test_summary_groups_by_event_class(self) -> None:
        self.ingester.record_chat_message(session_id="a", message_length=1)
        self.ingester.record_chat_message(session_id="b", message_length=2)
        self.ingester.record_review_saved(stars=5, rating_key="r1")
        self._wait_for_writes()
        summary = self.db.telemetry_summary(hours=24)
        self.assertEqual(summary.get("chat_message"), 2)
        self.assertEqual(summary.get("review_saved"), 1)

    def test_events_pagination(self) -> None:
        for i in range(5):
            self.ingester.record_chat_message(session_id=f"s{i}", message_length=i)
        self._wait_for_writes()
        page = self.db.telemetry_events(limit=3, offset=0)
        self.assertEqual(len(page), 3)
        page2 = self.db.telemetry_events(limit=3, offset=3)
        self.assertEqual(len(page2), 2)


class TelemetryAdminAPITests(unittest.TestCase):
    """Integration tests for the owner-only /api/admin/telemetry/* endpoints."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-telemetry-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

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

    def test_summary_endpoint(self) -> None:
        resp = self.client.get("/api/admin/telemetry/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("windows", body)
        self.assertIn("24h", body["windows"])

    def test_events_endpoint(self) -> None:
        resp = self.client.get("/api/admin/telemetry/events")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("items", body)

    def test_events_endpoint_filters_by_type(self) -> None:
        resp = self.client.get("/api/admin/telemetry/events?type=chat_message")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
