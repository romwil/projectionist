"""Rate limiter tests — sliding window, IP extraction, and chat endpoint."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import Request
from fastapi.testclient import TestClient

from curatorx.web.rate_limit import (
    SlidingWindowRateLimiter,
    clear_rate_limits,
    client_ip,
    enforce_rate_limit,
)


class SlidingWindowRateLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limiter = SlidingWindowRateLimiter()

    def test_requests_within_limit_succeed(self) -> None:
        for _ in range(5):
            self.limiter.check(key="10.0.0.1", bucket="test", limit=5, window_seconds=60)

    def test_requests_exceeding_limit_raise_429(self) -> None:
        from fastapi import HTTPException

        for _ in range(3):
            self.limiter.check(key="10.0.0.1", bucket="test", limit=3, window_seconds=60)
        with self.assertRaises(HTTPException) as ctx:
            self.limiter.check(key="10.0.0.1", bucket="test", limit=3, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers or {})

    def test_different_keys_are_independent(self) -> None:
        for _ in range(3):
            self.limiter.check(key="10.0.0.1", bucket="test", limit=3, window_seconds=60)
        self.limiter.check(key="10.0.0.2", bucket="test", limit=3, window_seconds=60)

    def test_different_buckets_are_independent(self) -> None:
        for _ in range(3):
            self.limiter.check(key="10.0.0.1", bucket="alpha", limit=3, window_seconds=60)
        self.limiter.check(key="10.0.0.1", bucket="beta", limit=3, window_seconds=60)

    def test_sliding_window_resets(self) -> None:
        from fastapi import HTTPException

        for _ in range(2):
            self.limiter.check(key="10.0.0.1", bucket="fast", limit=2, window_seconds=0.1)
        with self.assertRaises(HTTPException):
            self.limiter.check(key="10.0.0.1", bucket="fast", limit=2, window_seconds=0.1)
        time.sleep(0.15)
        self.limiter.check(key="10.0.0.1", bucket="fast", limit=2, window_seconds=0.1)

    def test_clear_resets_all_buckets(self) -> None:
        for _ in range(3):
            self.limiter.check(key="10.0.0.1", bucket="test", limit=3, window_seconds=60)
        self.limiter.clear()
        self.limiter.check(key="10.0.0.1", bucket="test", limit=3, window_seconds=60)


class ClientIpExtractionTests(unittest.TestCase):
    def _make_request(
        self,
        *,
        forwarded_for: str | None = None,
        client_host: str | None = "127.0.0.1",
    ) -> Request:
        scope: dict = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
        if forwarded_for is not None:
            scope["headers"].append(
                (b"x-forwarded-for", forwarded_for.encode())
            )
        if client_host:
            scope["client"] = (client_host, 12345)
        else:
            scope["client"] = None
        return Request(scope)

    def test_prefers_x_forwarded_for(self) -> None:
        os.environ["CURATORX_TRUST_PROXY_HEADERS"] = "1"
        req = self._make_request(forwarded_for="203.0.113.50, 10.0.0.1")
        self.assertEqual(client_ip(req), "203.0.113.50")

    def test_ignores_x_forwarded_for_without_trust_flag(self) -> None:
        os.environ.pop("CURATORX_TRUST_PROXY_HEADERS", None)
        req = self._make_request(forwarded_for="203.0.113.50", client_host="127.0.0.1")
        self.assertEqual(client_ip(req), "127.0.0.1")

    def test_falls_back_to_client_host(self) -> None:
        req = self._make_request(client_host="192.168.1.100")
        self.assertEqual(client_ip(req), "192.168.1.100")

    def test_returns_unknown_when_no_client(self) -> None:
        req = self._make_request(forwarded_for=None, client_host=None)
        self.assertEqual(client_ip(req), "unknown")

    def test_single_forwarded_for_value(self) -> None:
        os.environ["CURATORX_TRUST_PROXY_HEADERS"] = "1"
        req = self._make_request(forwarded_for="198.51.100.5")
        self.assertEqual(client_ip(req), "198.51.100.5")

    def tearDown(self) -> None:
        os.environ.pop("CURATORX_TRUST_PROXY_HEADERS", None)


class ChatRateLimitIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        clear_rate_limits()

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_rate_limits()
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_chat_rate_limit_blocks_excess_requests(self) -> None:
        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(return_value={"reply": "ok", "blocks": []})
            agent_cls.return_value = agent

            for i in range(30):
                resp = self.client.post(
                    "/api/chat",
                    json={"message": f"msg-{i}"},
                )
                self.assertIn(
                    resp.status_code,
                    (200, 400),
                    f"Request {i} got unexpected {resp.status_code}",
                )

            resp = self.client.post(
                "/api/chat",
                json={"message": "one too many"},
            )
            self.assertEqual(resp.status_code, 429)

    def test_chat_within_limit_succeeds(self) -> None:
        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(return_value={"reply": "ok", "blocks": []})
            agent_cls.return_value = agent

            resp = self.client.post(
                "/api/chat",
                json={"message": "hello"},
            )
            self.assertIn(resp.status_code, (200, 400))

    def test_rate_limit_returns_retry_after_header(self) -> None:
        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(return_value={"reply": "ok", "blocks": []})
            agent_cls.return_value = agent

            for i in range(30):
                self.client.post(
                    "/api/chat",
                    json={"message": f"msg-{i}"},
                )
            resp = self.client.post(
                "/api/chat",
                json={"message": "blocked"},
            )
            self.assertEqual(resp.status_code, 429)
            self.assertIn("retry-after", resp.headers)


class LocalAuthRateLimitXffTests(unittest.TestCase):
    """Regression for S14 / TC-AUTH-RL-01."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-xff-rate-limit-session-secret"
        os.environ.pop("CURATORX_TRUST_PROXY_HEADERS", None)
        from curatorx.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        clear_rate_limits()
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
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

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_rate_limits()
        from curatorx.web.session_tokens import clear_session_secret_cache

        clear_session_secret_cache()
        os.environ.pop("CURATORX_TRUST_PROXY_HEADERS", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_spoofed_xff_cannot_bypass_local_login_limit(self) -> None:
        for i in range(11):
            self.client.post(
                "/api/auth/local/login",
                json={"username": "nobody", "password": f"wrong-{i}"},
                headers={"X-Forwarded-For": f"198.51.100.{i}"},
            )
        blocked = self.client.post(
            "/api/auth/local/login",
            json={"username": "nobody", "password": "wrong-final"},
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        self.assertEqual(blocked.status_code, 429)


if __name__ == "__main__":
    unittest.main()
