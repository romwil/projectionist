"""Full-mode MCP tools, auth mapping, and schema allowances."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from projectionist.mcp.mode import _secret_eq, resolve_http_mcp_auth, set_mcp_mode
from projectionist.privacy import sanitize


class ConstantTimeKeyCompareTests(unittest.TestCase):
    """M11: MCP API keys must be compared in constant time."""

    def test_secret_eq_matches_and_rejects(self) -> None:
        self.assertTrue(_secret_eq("abc123", "abc123"))
        self.assertFalse(_secret_eq("abc123", "abc124"))

    def test_secret_eq_empty_is_false(self) -> None:
        self.assertFalse(_secret_eq("", ""))
        self.assertFalse(_secret_eq("abc", ""))
        self.assertFalse(_secret_eq("", "abc"))

    def test_secret_eq_length_mismatch_does_not_raise(self) -> None:
        self.assertFalse(_secret_eq("short", "a-much-longer-secret-value"))

    def test_auth_mapping_still_correct_with_constant_time_compare(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PROJECTIONIST_MCP_API_KEY": "priv-key",
                "PROJECTIONIST_MCP_FULL_API_KEY": "full-key",
            },
            clear=False,
        ) as env:
            env.pop("CURATORX_MCP_API_KEY", None)
            env.pop("CURATORX_MCP_FULL_API_KEY", None)
            self.assertEqual(resolve_http_mcp_auth("full-key")[0], "full")
            self.assertEqual(resolve_http_mcp_auth("priv-key")[0], "privacy")
            self.assertIsNone(resolve_http_mcp_auth("wrong")[0])


class FullModeAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self._tmpdir.name

    def tearDown(self) -> None:
        if self._prev_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev_data_dir
        self._tmpdir.cleanup()

    def test_wrong_key_does_not_escalate(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CURATORX_MCP_API_KEY": "priv-key",
                "CURATORX_MCP_FULL_API_KEY": "full-key",
            },
            clear=False,
        ):
            mode, _, status = resolve_http_mcp_auth("priv-key")
            self.assertEqual(mode, "privacy")
            self.assertEqual(status, 200)
            mode2, detail, status2 = resolve_http_mcp_auth("not-a-key")
            self.assertIsNone(mode2)
            self.assertEqual(status2, 401)
            self.assertEqual(detail, "Unauthorized")

    def test_disabled_http_mcp_is_generic_401(self) -> None:
        with patch("projectionist.mcp.mode.privacy_api_key", return_value=""), patch(
            "projectionist.mcp.mode.full_api_key", return_value=""
        ):
            mode, detail, status = resolve_http_mcp_auth("anything")
            self.assertIsNone(mode)
            self.assertEqual(status, 401)
            self.assertEqual(detail, "Unauthorized")
            self.assertNotIn("PROJECTIONIST_", detail or "")
            self.assertNotIn("CURATORX_", detail or "")


class FullSchemaTests(unittest.TestCase):
    def test_full_allows_rating_key_never_token(self) -> None:
        cleaned = sanitize(
            {
                "rating_key": "42",
                "view_count": 3,
                "in_sonarr": True,
                "file_size": 50,
                "poster_url": "https://image.tmdb.org/t/p/w342/x.jpg",
                "backdrop_url": "http://lan/plex?X-Plex-Token=sekrit",
            },
            audience="mcp_full",
            settings=type(
                "S",
                (),
                {"mcp_tmdb_poster_size": "w500", "mcp_tmdb_backdrop_size": "w1280"},
            )(),
        )
        self.assertEqual(cleaned["rating_key"], "42")
        self.assertEqual(cleaned["view_count"], 3)
        self.assertTrue(cleaned["in_sonarr"])
        self.assertEqual(cleaned["poster_url"], "https://image.tmdb.org/t/p/w500/x.jpg")
        self.assertEqual(cleaned.get("backdrop_url") or "", "")
        self.assertNotIn("sekrit", json.dumps(cleaned))


try:
    from projectionist.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


@skipUnless(HAS_MCP, "mcp package not installed")
class McpFullModeToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")

    def tearDown(self) -> None:
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_library_query_keeps_rating_key(self) -> None:
        from projectionist.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        db.upsert_library_item(
            {
                "rating_key": "rk-full",
                "media_type": "movie",
                "title": "Alien",
                "year": 1979,
                "file_size": 1234,
                "view_count": 1,
                "poster_url": "http://plex/thumb?X-Plex-Token=SECRET",
            }
        )
        with patch.object(mcp_server, "_database", return_value=db):
            raw = mcp_server.library_query(year_from=1970, year_to=1979)
        payload = json.loads(raw)
        item = payload["items"][0]
        self.assertEqual(item["rating_key"], "rk-full")
        self.assertEqual(item["file_size"], 1234)
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("X-Plex-Token", raw)

    def test_propose_add_radarr_returns_pending_token(self) -> None:
        mock_settings = MagicMock()
        mock_settings.radarr_url = "http://radarr"
        mock_settings.radarr_api_key = "key"
        mock_settings.radarr_root_folder = "/movies"
        mock_settings.movies_root = "/movies"
        mock_settings.radarr_quality_profile_id = 1

        db = MagicMock()
        db.save_pending_action = MagicMock()
        db.is_acquisition_excluded.return_value = False

        with (
            patch.object(mcp_server, "_database", return_value=db),
            patch.object(mcp_server, "_settings", return_value=mock_settings),
            patch("projectionist.config_store.radarr_add_configuration_error", return_value=None),
            patch("projectionist.config_store.validate_arr_root_folder", return_value=None),
            patch("projectionist.config_store.resolve_radarr_root_folder", return_value="/movies"),
            patch("projectionist.connectors.radarr.RadarrClient") as client_cls,
            patch("projectionist.agent.tools.check_radarr_already_exists", return_value=None),
        ):
            client_cls.return_value.root_folders.return_value = [{"path": "/movies"}]
            raw = mcp_server.propose_add_radarr(tmdb_id=578, title="Jaws")
        payload = json.loads(raw)
        self.assertIn("pending_token", payload)
        self.assertTrue(payload["pending_token"])
        db.save_pending_action.assert_called_once()

    def test_privacy_key_holder_blocked_from_propose(self) -> None:
        set_mcp_mode("privacy")
        payload = json.loads(mcp_server.propose_remove_arr(media_type="movie", title="X"))
        self.assertIn("error", payload)

    def test_confirm_without_scope_cannot_self_confirm(self) -> None:
        """H3: full key without active-curation scope must not execute; token survives."""
        from projectionist.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        token = "tok-h3"
        db.save_pending_action(
            token, "add_radarr", {"action": "add_radarr", "tmdb_id": 578, "title": "Jaws"}, user_id=None
        )
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("PROJECTIONIST_MCP_FULL_CONFIRM", None)
            env.pop("CURATORX_MCP_FULL_CONFIRM", None)
            with patch.object(mcp_server, "_database", return_value=db):
                payload = json.loads(mcp_server.confirm_pending_action(token, confirmed=True))

        self.assertIn("error", payload)
        self.assertTrue(payload.get("requires_human_confirmation"))
        self.assertEqual(payload.get("pending_token"), token)
        surviving = db.pop_pending_action(token, user_id="plex-owner")
        self.assertIsNotNone(surviving)
        self.assertEqual(surviving["action"], "add_radarr")

    def test_confirm_with_scope_executes(self) -> None:
        """Full key scoped via PROJECTIONIST_MCP_FULL_CONFIRM may self-confirm."""
        from unittest.mock import AsyncMock

        from projectionist.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        token = "tok-scoped"
        db.save_pending_action(token, "add_radarr", {"action": "add_radarr"}, user_id=None)

        with patch.dict(os.environ, {"PROJECTIONIST_MCP_FULL_CONFIRM": "1"}, clear=False):
            with (
                patch.object(mcp_server, "_database", return_value=db),
                patch(
                    "projectionist.agent.tools.execute_confirmed_action",
                    new=AsyncMock(return_value={"action": "add_radarr"}),
                ) as exec_mock,
            ):
                payload = json.loads(mcp_server.confirm_pending_action(token, confirmed=True))

        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("action"), "add_radarr")
        exec_mock.assert_awaited_once()
        self.assertEqual(exec_mock.await_args.args[2], token)

    def test_confirm_pending_action_can_cancel(self) -> None:
        """Cancelling over MCP is safe and consumes the token."""
        from projectionist.library.db import Database

        db = Database(Path(self._tmpdir.name) / "test.db")
        token = "tok-cancel"
        db.save_pending_action(token, "add_radarr", {"action": "add_radarr"}, user_id=None)
        with patch.object(mcp_server, "_database", return_value=db):
            payload = json.loads(mcp_server.confirm_pending_action(token, confirmed=False))

        self.assertTrue(payload.get("cancelled"))
        self.assertTrue(payload.get("found"))
        self.assertIsNone(db.pop_pending_action(token, user_id="plex-owner"))


if __name__ == "__main__":
    unittest.main()
