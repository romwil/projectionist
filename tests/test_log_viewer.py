"""Tests for application log parsing, filters, and owner API."""

from __future__ import annotations

import importlib
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.logging_config import configure_logging, resolve_log_file_path
from projectionist.web.log_viewer import (
    line_matches_filters,
    normalize_min_level,
    parse_log_line,
    read_log_tail,
    read_new_lines,
)
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class LogParseFilterTests(unittest.TestCase):
    def test_parse_text_line(self) -> None:
        line = parse_log_line(
            "2026-07-27 22:00:00 INFO projectionist.web.app: hello world",
            line_id=10,
        )
        self.assertEqual(line.id, 10)
        self.assertEqual(line.level, "INFO")
        self.assertEqual(line.logger, "projectionist.web.app")
        self.assertEqual(line.message, "hello world")
        self.assertEqual(line.timestamp, "2026-07-27 22:00:00")

    def test_parse_json_line_redacts_secrets(self) -> None:
        payload = {
            "timestamp": "2026-07-27T22:00:00+00:00",
            "level": "WARNING",
            "logger": "projectionist.connectors.http",
            "message": "GET https://x.test?api_key=secret123",
        }
        line = parse_log_line(json.dumps(payload), line_id=1)
        self.assertEqual(line.level, "WARNING")
        self.assertNotIn("secret123", line.message)
        self.assertIn("api_key=***", line.message)

    def test_min_level_filter(self) -> None:
        info = parse_log_line("2026-07-27 22:00:00 INFO demo: ok")
        error = parse_log_line("2026-07-27 22:00:00 ERROR demo: bad")
        self.assertFalse(line_matches_filters(info, min_level="WARNING"))
        self.assertTrue(line_matches_filters(error, min_level="WARNING"))

    def test_logger_and_q_filters(self) -> None:
        line = parse_log_line("2026-07-27 22:00:00 INFO projectionist.web.app: sync done")
        self.assertTrue(line_matches_filters(line, logger_prefix="projectionist.web"))
        self.assertFalse(line_matches_filters(line, logger_prefix="uvicorn"))
        self.assertTrue(line_matches_filters(line, q="sync"))
        self.assertFalse(line_matches_filters(line, q="missing"))

    def test_normalize_min_level_rejects_unknown(self) -> None:
        self.assertIsNone(normalize_min_level("ALL"))
        with self.assertRaises(ValueError):
            normalize_min_level("TRACE")

    def test_read_tail_and_new_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "projectionist.log"
            path.write_text(
                "2026-07-27 22:00:00 DEBUG projectionist.x: noise\n"
                "2026-07-27 22:00:01 INFO projectionist.web.app: kept\n"
                "2026-07-27 22:00:02 ERROR uvicorn.error: boom\n",
                encoding="utf-8",
            )
            payload = read_log_tail(path, limit=10, min_level="INFO", logger_prefix="projectionist")
            self.assertTrue(payload["exists"])
            self.assertEqual(len(payload["lines"]), 1)
            self.assertEqual(payload["lines"][0]["message"], "kept")

            offset = payload["next_offset"]
            with path.open("a", encoding="utf-8") as handle:
                handle.write("2026-07-27 22:00:03 INFO projectionist.web.app: appended\n")
            lines, new_offset = read_new_lines(path, after_offset=offset, min_level="INFO")
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].message, "appended")
            self.assertGreater(new_offset, offset)


class LogFileConfigTests(unittest.TestCase):
    def test_configure_logging_writes_rotating_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "DATA_DIR": tmp,
                "CURATORX_SKIP_DOTENV": "1",
                "PROJECTIONIST_SKIP_DOTENV": "1",
                "LOG_LEVEL": "INFO",
            }
            with patch.dict(os.environ, env, clear=False):
                configure_logging(force=True)
                path = resolve_log_file_path()
                logging.getLogger("projectionist.tests.log_viewer").info("file-handler-check")
                for handler in logging.getLogger().handlers:
                    handler.flush()
                self.assertTrue(path.is_file(), path)
                content = path.read_text(encoding="utf-8")
                self.assertIn("file-handler-check", content)


class AdminLogsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-admin-logs-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        log_path = Path(self._tmpdir.name) / "logs" / "projectionist.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "2026-07-27 22:00:00 INFO projectionist.web.app: boot\n"
            "2026-07-27 22:00:01 WARNING projectionist.web.app: slow\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "CURATORX_SKIP_DOTENV",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "CURATORX_SESSION_SECRET",
            "DATA_DIR",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        resp = self.client.put(
            "/api/settings",
            json={
                "features": {
                    "multi_user_enabled": True,
                    "open_auto_provision": True,
                    "seerr_enabled": False,
                },
                "auth": {"mode": "plex", "plex_login_enabled": True},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def _login_as(self, plex_id: int, title: str) -> None:
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={
                "id": plex_id,
                "title": title,
                "email": f"{title}@example.com",
            },
        ):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"token-{plex_id}"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_owner_can_read_logs(self) -> None:
        # Single-owner mode (no multi-user) — bootstrap owner.
        resp = self.client.get("/api/admin/logs?limit=50&level=INFO")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertTrue(payload["exists"])
        self.assertIn("sensitive_warning", payload)
        messages = [row["message"] for row in payload["lines"]]
        self.assertIn("boot", messages)
        self.assertIn("slow", messages)

    def test_member_cannot_read_logs(self) -> None:
        self._enable_multi_user()
        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(2, "Member")
        resp = self.client.get("/api/admin/logs")
        self.assertEqual(resp.status_code, 403)

    def test_guest_cannot_read_logs(self) -> None:
        self._enable_multi_user()
        self._login_as(1, "Owner")
        self.client.post("/api/auth/logout")
        self._login_as(9, "GuestCandidate")
        user_id = self.client.get("/api/auth/me").json()["user"]["id"]
        self.client.post("/api/auth/logout")
        self._login_as(1, "Owner")
        patch_resp = self.client.patch(f"/api/users/{user_id}", json={"role": "guest"})
        self.assertEqual(patch_resp.status_code, 200, patch_resp.text)
        self.client.post("/api/auth/logout")
        self._login_as(9, "GuestCandidate")
        denied = self.client.get("/api/admin/logs")
        self.assertEqual(denied.status_code, 403)

    def test_invalid_level_returns_400(self) -> None:
        resp = self.client.get("/api/admin/logs?level=TRACE")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
