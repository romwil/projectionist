"""Tests for local avatar storage and validation."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.avatars import (
    detect_avatar_extension,
    find_local_avatar_file,
    local_avatar_api_path,
    resolve_avatar_url,
    safe_user_id,
    save_avatar_bytes,
)
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


# Minimal valid PNG (1x1)
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class AvatarHelpersTests(unittest.TestCase):
    def test_safe_user_id_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            safe_user_id("../etc/passwd")
        with self.assertRaises(ValueError):
            safe_user_id("foo/bar")
        self.assertEqual(safe_user_id("plex-12345"), "plex-12345")

    def test_detect_avatar_extension_rejects_bad_types(self) -> None:
        with self.assertRaises(ValueError):
            detect_avatar_extension(b"not-an-image" * 4, "text/plain")
        with self.assertRaises(ValueError):
            detect_avatar_extension(b"tiny", "image/png")
        with self.assertRaises(ValueError):
            detect_avatar_extension(b"x" * (2 * 1024 * 1024 + 1), "image/png")

    def test_save_and_resolve_local_avatar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_path = save_avatar_bytes("plex-9", _PNG, "image/png", root=root)
            self.assertEqual(api_path, local_avatar_api_path("plex-9"))
            found = find_local_avatar_file("plex-9", root=root)
            self.assertIsNotNone(found)
            self.assertTrue(found.is_file())
            self.assertEqual(
                resolve_avatar_url("plex-9", "https://plex.test/broken.jpg", root=root),
                api_path,
            )

    def test_resolve_falls_back_to_stored_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                resolve_avatar_url("plex-1", "https://plex.test/a.jpg", root=root),
                "https://plex.test/a.jpg",
            )


class AvatarUploadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-avatar-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        profile = {
            "id": 99,
            "title": "Avatar User",
            "email": "avatar@example.com",
            "thumb": "https://plex.test/broken.jpg",
        }
        with patch("curatorx.web.auth.fetch_plex_account", return_value=profile), patch(
            "curatorx.web.avatars.cache_remote_avatar",
            return_value=None,
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "tok"})
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def test_upload_avatar_rejects_non_image(self) -> None:
        resp = self.client.post(
            "/api/auth/me/avatar",
            files={"file": ("notes.txt", b"hello world " * 8, "text/plain")},
        )
        self.assertEqual(resp.status_code, 400)

    def test_upload_and_fetch_avatar(self) -> None:
        resp = self.client.post(
            "/api/auth/me/avatar",
            files={"file": ("me.png", _PNG, "image/png")},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["user"]["avatar_url"].startswith("/api/auth/avatar/"))
        avatar = self.client.get(body["user"]["avatar_url"])
        self.assertEqual(avatar.status_code, 200)
        self.assertEqual(avatar.headers.get("content-type"), "image/png")


if __name__ == "__main__":
    unittest.main()
