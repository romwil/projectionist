"""Verify that error responses never leak internal details to clients."""

from __future__ import annotations

import importlib
import logging
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class ErrorSanitizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # _safe_error_detail unit tests
    # ------------------------------------------------------------------

    def test_safe_error_detail_generic_exception(self) -> None:
        msg = self.app_mod._safe_error_detail(
            RuntimeError("/var/lib/curatorx/db.sqlite3: locked"),
            "Chat request failed",
        )
        self.assertEqual(msg, "Chat request failed")
        self.assertNotIn("/var/lib", msg)

    def test_safe_error_detail_llm_provider_error(self) -> None:
        from curatorx.agent.providers import LLMProviderError

        msg = self.app_mod._safe_error_detail(
            LLMProviderError("API key sk-proj-abc123 is invalid"),
        )
        self.assertEqual(
            msg, "LLM provider error \u2014 check your API key and provider settings"
        )
        self.assertNotIn("sk-proj", msg)

    def test_safe_error_detail_connection_error(self) -> None:
        msg = self.app_mod._safe_error_detail(
            ConnectionError("Connection refused: http://192.168.1.5:7878"),
            "Radarr",
        )
        self.assertIn("Unable to reach", msg)
        self.assertNotIn("192.168.1.5", msg)

    def test_safe_error_detail_os_error(self) -> None:
        msg = self.app_mod._safe_error_detail(
            OSError("No route to host"),
            "Plex",
        )
        self.assertIn("Unable to reach", msg)
        self.assertNotIn("No route", msg)

    def test_safe_error_detail_value_error_uses_context(self) -> None:
        msg = self.app_mod._safe_error_detail(
            ValueError("column xyz not found in table abc"),
            "Invalid request",
        )
        self.assertEqual(msg, "Invalid request")
        self.assertNotIn("column", msg)
        self.assertNotIn("table", msg)

    def test_safe_error_detail_fallback_without_context(self) -> None:
        msg = self.app_mod._safe_error_detail(RuntimeError("oops"))
        self.assertEqual(msg, "An error occurred while processing your request")

    def test_safe_error_detail_logs_full_error(self) -> None:
        with self.assertLogs("curatorx.web.app", level=logging.ERROR) as cm:
            self.app_mod._safe_error_detail(
                RuntimeError("secret-internal-detail-42"),
                "Chat request failed",
            )
        log_output = "\n".join(cm.output)
        self.assertIn("secret-internal-detail-42", log_output)

    # ------------------------------------------------------------------
    # Integration tests — error responses don't leak
    # ------------------------------------------------------------------

    def test_chat_500_does_not_leak_traceback(self) -> None:
        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(
                side_effect=RuntimeError(
                    "Traceback: File /app/curatorx/agent/curator.py line 42"
                )
            )
            agent_cls.return_value = agent
            resp = self.client.post("/api/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 500)
        detail = resp.json()["detail"]
        self.assertNotIn("Traceback", detail)
        self.assertNotIn("/app/curatorx", detail)
        self.assertNotIn("curator.py", detail)
        self.assertEqual(detail, "Chat request failed")

    def test_chat_502_llm_error_does_not_leak_api_key(self) -> None:
        from curatorx.agent.providers import LLMProviderError

        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(
                side_effect=LLMProviderError(
                    "Invalid API key: sk-proj-XXXXXXXXXX"
                )
            )
            agent_cls.return_value = agent
            resp = self.client.post("/api/chat", json={"message": "hi"})
        self.assertEqual(resp.status_code, 502)
        detail = resp.json()["detail"]
        self.assertNotIn("sk-proj", detail)
        self.assertIn("LLM provider error", detail)

    def test_seerr_error_does_not_leak_url(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "features": {"seerr_enabled": True},
                "seerr": {
                    "url": "http://internal-seerr.local:5055",
                    "api_key": "supersecret",
                },
            },
        )
        with patch(
            "curatorx.web.app.SeerrClient.list_requests",
            side_effect=RuntimeError(
                "Connection refused: http://internal-seerr.local:5055/api/v1"
            ),
        ):
            resp = self.client.get("/api/requests")
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertNotIn("internal-seerr", detail)
        self.assertNotIn("5055", detail)
        self.assertNotIn("supersecret", detail)

    def test_confirm_action_does_not_leak_arr_details(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.save_pending_action(
            "test-token-abc",
            "add_radarr",
            {"action": "add_radarr", "tmdb_id": 123, "title": "Test"},
        )
        with patch(
            "curatorx.web.app.execute_confirmed_action",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "HTTP 500 from http://192.168.1.5:7878/api/v3: internal server error"
            ),
        ):
            resp = self.client.post(
                "/api/actions/confirm",
                json={"token": "test-token-abc", "confirmed": True},
            )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertNotIn("192.168.1.5", detail)
        self.assertNotIn("HTTP 500", detail)
        self.assertEqual(detail, "Action confirmation failed")


if __name__ == "__main__":
    unittest.main()
