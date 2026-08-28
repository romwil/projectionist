"""P1c — LLM usage instrumentation, pricing, and owner BI API."""

from __future__ import annotations

import importlib
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from projectionist.library.db import Database
from projectionist.telemetry.ingestion import TelemetryIngester
from projectionist.telemetry.llm_usage import (
    PURPOSE_CHAT,
    PURPOSE_LOGLINE,
    cheaper_tier_hint,
    estimate_usd,
    job_cache_get,
    job_cache_set,
    parse_token_usage,
)
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class LlmUsageHelpersTests(unittest.TestCase):
    def test_parse_openai_and_anthropic_usage(self) -> None:
        openai = parse_token_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
        self.assertEqual(openai["prompt_tokens"], 10)
        self.assertEqual(openai["completion_tokens"], 5)
        self.assertEqual(openai["total_tokens"], 15)

        anthropic = parse_token_usage({"usage": {"input_tokens": 20, "output_tokens": 7}})
        self.assertEqual(anthropic["prompt_tokens"], 20)
        self.assertEqual(anthropic["completion_tokens"], 7)
        self.assertEqual(anthropic["total_tokens"], 27)

    def test_estimate_usd_known_and_unknown(self) -> None:
        cost = estimate_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=0)
        self.assertAlmostEqual(cost or 0, 0.15, places=4)
        self.assertIsNone(estimate_usd("my-local-llama", prompt_tokens=100, completion_tokens=50))

    def test_cheaper_tier_hint(self) -> None:
        self.assertEqual(cheaper_tier_hint("claude-3-5-haiku-20241022"), "cheaper-tier")
        self.assertEqual(cheaper_tier_hint("gpt-4o-mini"), "cheaper-tier")


class LlmUsageStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        self.ingester = TelemetryIngester(self.db)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _wait_for_writes(self, timeout: float = 2.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            alive = [t for t in threading.enumerate() if t.name.startswith("telemetry-")]
            if not alive:
                return
            time.sleep(0.05)

    def test_record_llm_usage_persists_and_summarizes(self) -> None:
        self.ingester.record_llm_usage(
            purpose=PURPOSE_CHAT,
            model="gpt-4o-mini",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=42,
            persona_id="persona-1",
            session_id="sess-1",
        )
        self._wait_for_writes()
        summary = self.db.llm_usage_summary(days=7)
        self.assertEqual(summary["totals"]["call_count"], 1)
        self.assertEqual(summary["totals"]["total_tokens"], 150)
        self.assertGreater(summary["totals"]["estimated_usd"], 0)
        self.assertEqual(summary["by_purpose"][0]["purpose"], PURPOSE_CHAT)
        self.assertIn("gpt-4o-mini", summary["filters"]["models"])

    def test_record_even_when_interaction_telemetry_disabled(self) -> None:
        self.db.set_config("telemetry_enabled", "false")
        self.ingester.record_llm_usage(
            purpose=PURPOSE_LOGLINE,
            model="gpt-4o-mini",
            prompt_tokens=40,
            completion_tokens=10,
            total_tokens=50,
        )
        self._wait_for_writes()
        summary = self.db.llm_usage_summary(days=7)
        self.assertEqual(summary["totals"]["call_count"], 1)
        # Interaction stream should stay empty when telemetry is muted.
        self.assertEqual(self.db.telemetry_events(event_class="llm_usage"), [])

    def test_prune_llm_usage(self) -> None:
        self.db.insert_llm_usage(
            usage_id="old",
            purpose="chat",
            model="gpt-4o-mini",
            total_tokens=10,
            created_at=time.time() - (120 * 86400),
        )
        self.db.insert_llm_usage(
            usage_id="new",
            purpose="chat",
            model="gpt-4o-mini",
            total_tokens=20,
            created_at=time.time(),
        )
        deleted = self.db.prune_llm_usage(90)
        self.assertEqual(deleted, 1)
        summary = self.db.llm_usage_summary(days=7)
        self.assertEqual(summary["totals"]["call_count"], 1)


class LlmUsageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "anthropic"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-llm-usage-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = app_mod._db()

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def test_admin_llm_usage_endpoint(self) -> None:
        self.db.insert_llm_usage(
            usage_id="u1",
            purpose="chat",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            estimated_usd=0.001,
            persona_id="p1",
        )
        response = self.client.get("/api/admin/llm/usage?days=7")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["totals"]["call_count"], 1)
        self.assertEqual(payload["totals"]["total_tokens"], 120)
        self.assertTrue(any(row["purpose"] == "chat" for row in payload["by_purpose"]))

    def test_admin_llm_models_anthropic_fail_soft(self) -> None:
        response = self.client.get("/api/admin/llm/models")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["provider"], "anthropic")
        self.assertEqual(payload["source"], "pinned")
        self.assertGreaterEqual(len(payload["models"]), 1)
        self.assertTrue(any(row.get("hint") == "cheaper-tier" for row in payload["models"]))


class LibrarySummaryCoalesceTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_deterministic_summary_skips_llm(self) -> None:
        import projectionist.web.app as app_mod

        content = {
            "blocks": [
                {"type": "text", "content": "A short curator note about two cozy comedies."},
            ]
        }
        # Patch chat provider — must not be called for short sources.
        provider = MagicMock()
        provider.chat = AsyncMock(side_effect=AssertionError("LLM should be skipped"))
        original = app_mod.get_chat_provider
        app_mod.get_chat_provider = lambda _settings: provider  # type: ignore[assignment]
        try:
            summary = await app_mod._persona_voiced_library_summary(content, persona={"name": "Test"})
        finally:
            app_mod.get_chat_provider = original  # type: ignore[assignment]
        self.assertIn("cozy comedies", summary)
        provider.chat.assert_not_called()


class JobCacheTtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_job_cache_hit_within_ttl(self) -> None:
        job_cache_set(self.db, kind="logline", key_hash="abc", value="A vivid one-liner.")
        self.assertEqual(job_cache_get(self.db, kind="logline", key_hash="abc"), "A vivid one-liner.")

    def test_job_cache_miss_after_ttl(self) -> None:
        # Store with an expired timestamp prefix (same wire format as job_cache_set).
        self.db.set_sync_state("llm_cache:logline:old", f"{time.time() - 7 * 3600:.3f}|stale")
        self.assertIsNone(job_cache_get(self.db, kind="logline", key_hash="old"))


if __name__ == "__main__":
    unittest.main()
