"""POST /api/chat/stream, GET 410, and the 8k ChatRequest cap."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class ChatStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in ("PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_post_stream_returns_200(self) -> None:
        async def fake_stream(*_args, **_kwargs):
            yield json.dumps({"type": "token", "content": "Hi"})
            yield json.dumps({"type": "done"})

        with patch("projectionist.web.app.stream_agent", fake_stream):
            resp = self.client.post(
                "/api/chat/stream",
                json={"message": "hello", "session_id": "stream-s1"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIn("token", resp.text)
        self.assertIn("done", resp.text)

    def test_get_stream_returns_410(self) -> None:
        resp = self.client.get("/api/chat/stream", params={"message": "hello"})
        self.assertEqual(resp.status_code, 410)
        self.assertIn("POST", resp.json()["detail"])

    def test_8001_char_message_is_rejected(self) -> None:
        too_long = "x" * 8001
        stream = self.client.post("/api/chat/stream", json={"message": too_long})
        chat = self.client.post("/api/chat", json={"message": too_long})
        # Field(max_length=8000) is a FastAPI validation 422 (400-class client error).
        self.assertIn(stream.status_code, (400, 422), stream.text)
        self.assertIn(chat.status_code, (400, 422), chat.text)
