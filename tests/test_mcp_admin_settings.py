"""Admin Advanced: dual-mode MCP keys + TMDB image size settings."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.config_store import Settings, save_settings
from curatorx.mcp.mode import resolve_http_mcp_auth


class McpAdminSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ.pop("CURATORX_MCP_API_KEY", None)
        os.environ.pop("CURATORX_MCP_FULL_API_KEY", None)
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("CURATORX_MCP_API_KEY", None)
        os.environ.pop("CURATORX_MCP_FULL_API_KEY", None)
        self._tmpdir.cleanup()

    def test_get_settings_masks_mcp_keys_with_hint(self) -> None:
        save_settings(
            Path(self._tmpdir.name),
            Settings(mcp_api_key="privacy-secret-abcd", mcp_full_api_key="full-secret-efgh"),
        )
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mcp_api_key"], "")
        self.assertEqual(body["mcp_full_api_key"], "")
        self.assertTrue(body["mcp_api_key_set"])
        self.assertTrue(body["mcp_full_api_key_set"])
        self.assertEqual(body["mcp_api_key_hint"], "…abcd")
        self.assertEqual(body["mcp_full_api_key_hint"], "…efgh")
        self.assertEqual(body["mcp_api_key_source"], "file")
        self.assertIn("mcp_tmdb_poster_size", body)
        self.assertIn("mcp_tmdb_backdrop_size", body)

    def test_put_settings_persists_tmdb_sizes(self) -> None:
        current = self.client.get("/api/settings").json()
        current["mcp_tmdb_poster_size"] = "w780"
        current["mcp_tmdb_backdrop_size"] = "w780"
        resp = self.client.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mcp_tmdb_poster_size"], "w780")
        self.assertEqual(body["mcp_tmdb_backdrop_size"], "w780")
        loaded = Settings.load(Path(self._tmpdir.name) / "settings.json")
        self.assertEqual(loaded.mcp_tmdb_poster_size, "w780")
        self.assertEqual(loaded.mcp_tmdb_backdrop_size, "w780")

    def test_put_settings_normalizes_invalid_tmdb_sizes(self) -> None:
        current = self.client.get("/api/settings").json()
        current["mcp_tmdb_poster_size"] = "not-a-size"
        current["mcp_tmdb_backdrop_size"] = "also-bad"
        resp = self.client.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["mcp_tmdb_poster_size"], "w500")
        self.assertEqual(body["mcp_tmdb_backdrop_size"], "w1280")

    def test_put_settings_rejects_identical_mcp_keys(self) -> None:
        current = self.client.get("/api/settings").json()
        current["mcp_api_key"] = "same-key-value"
        current["mcp_full_api_key"] = "same-key-value"
        resp = self.client.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("differ", resp.json()["detail"].lower())

    def test_rotate_privacy_key_returns_plaintext_once(self) -> None:
        resp = self.client.post("/api/settings/mcp-keys/rotate", json={"which": "privacy"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["which"], "privacy")
        self.assertTrue(body["key"])
        self.assertEqual(body["settings"]["mcp_api_key"], "")
        self.assertTrue(body["settings"]["mcp_api_key_set"])
        self.assertTrue(body["settings"]["mcp_api_key_hint"].endswith(body["key"][-4:]))

        listed = self.client.get("/api/settings").json()
        self.assertEqual(listed["mcp_api_key"], "")
        self.assertTrue(listed["mcp_api_key_set"])

        mode, _, status = resolve_http_mcp_auth(body["key"])
        self.assertEqual(mode, "privacy")
        self.assertEqual(status, 200)

    def test_rotate_full_key_distinct_and_auth(self) -> None:
        priv = self.client.post("/api/settings/mcp-keys/rotate", json={"which": "privacy"}).json()
        full = self.client.post("/api/settings/mcp-keys/rotate", json={"which": "full"}).json()
        self.assertNotEqual(priv["key"], full["key"])
        mode, _, status = resolve_http_mcp_auth(full["key"])
        self.assertEqual(mode, "full")
        self.assertEqual(status, 200)

    def test_clear_file_key(self) -> None:
        self.client.post("/api/settings/mcp-keys/rotate", json={"which": "privacy"})
        resp = self.client.post("/api/settings/mcp-keys/clear", json={"which": "privacy"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["settings"]["mcp_api_key_set"])

    def test_clear_env_key_rejected(self) -> None:
        os.environ["CURATORX_MCP_API_KEY"] = "from-env-xxxx"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        importlib.reload(self.app_mod)
        client = TestClient(self.app_mod.app)
        resp = client.post("/api/settings/mcp-keys/clear", json={"which": "privacy"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("CURATORX_MCP_API_KEY", resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
