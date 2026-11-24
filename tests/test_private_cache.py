"""SEC-021: household responses are not stored in a shared cache."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from projectionist.web.private_cache import PRIVATE_NO_STORE, apply_private_api_cache
from projectionist.web.static_assets import IMMUTABLE_ASSET_CACHE_CONTROL


class _Headers:
    def __init__(self, current: str = "") -> None:
        self.value = current

    def get(self, name: str) -> str:
        if name.lower() == "cache-control":
            return self.value
        return ""

    def __setitem__(self, name: str, value: str) -> None:
        if name.lower() == "cache-control":
            self.value = value


class PrivateCachePolicyTests(unittest.TestCase):
    def test_api_without_a_header_becomes_private(self) -> None:
        headers = _Headers()
        apply_private_api_cache("/api/health", headers)
        self.assertEqual(headers.value, PRIVATE_NO_STORE)

    def test_a_private_max_age_is_kept(self) -> None:
        headers = _Headers("private, max-age=86400")
        apply_private_api_cache("/api/library/art/movie/1", headers)
        self.assertEqual(headers.value, "private, max-age=86400")

    def test_a_public_api_header_is_replaced(self) -> None:
        headers = _Headers("public, max-age=60")
        apply_private_api_cache("/api/features", headers)
        self.assertEqual(headers.value, PRIVATE_NO_STORE)

    def test_hashed_frontend_files_are_not_api(self) -> None:
        headers = _Headers(IMMUTABLE_ASSET_CACHE_CONTROL)
        apply_private_api_cache("/assets/app-abc12345.js", headers)
        self.assertEqual(headers.value, IMMUTABLE_ASSET_CACHE_CONTROL)


class PrivateCacheRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "PROJECTIONIST_SETUP_STATE",
            "LLM_PROVIDER",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _assert_private(self, path: str) -> None:
        response = self.client.get(path)
        header = response.headers.get("cache-control", "")
        self.assertIn("private", header, path)
        self.assertTrue("no-store" in header or "max-age=" in header, path)
        self.assertNotIn("public", header, path)

    def test_each_private_group_sends_a_private_cache_header(self) -> None:
        groups = {
            "api": "/api/health",
            "art": "/api/library/art/movie/1",
            "engine-playlist": "/api/playback/sessions/sess/tok/index.m3u8",
            "engine-segment": "/api/playback/sessions/sess/tok/seg.m4s",
            "library-playlist": "/api/library/playback/sess/index.m3u8",
            "library-segment": "/api/library/playback/sess/seg.ts",
            "subtitle": "/api/library/items/1/subtitles/2/file",
            "avatar": "/api/auth/avatar/someone",
        }
        for name, path in groups.items():
            with self.subTest(group=name):
                self._assert_private(path)
