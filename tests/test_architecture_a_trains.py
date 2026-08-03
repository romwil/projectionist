"""Focused tests for Architecture A Trains 2–4 (schema, secrets, gates, MCP privacy)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock, skipUnless

from projectionist.agent.tools import ToolRegistry
from projectionist.config_store import (
    FeatureFlags,
    Settings,
    load_merged_settings,
    migrate_plaintext_settings_secrets,
    save_settings,
)
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.db.migrations import CURRENT_SCHEMA_VERSION
from projectionist.secrets_crypto import decrypt_secret, encrypt_secret, is_encrypted_secret


class SchemaIntegrityTests(unittest.TestCase):
    def test_schema_version_and_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                pragma = conn.execute("PRAGMA foreign_keys").fetchone()
                self.assertEqual(int(pragma[0]), 1)
                row = conn.execute(
                    "SELECT MAX(version) AS v FROM schema_version"
                ).fetchone()
                self.assertEqual(int(row["v"]), CURRENT_SCHEMA_VERSION)
                tables = {
                    str(r["name"])
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertIn("schema_version", tables)
                self.assertNotIn("agent_blueprints", tables)
                cols = {
                    str(r["name"])
                    for r in conn.execute("PRAGMA table_info(service_integrations)").fetchall()
                }
                self.assertIn("credential_marker", cols)
                self.assertNotIn("api_token_encrypted", cols)

    def test_foreign_key_cascade_chat_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO chat_sessions (id, created_at, updated_at) VALUES ('s1', 1, 1)"
                )
                conn.execute(
                    """
                    INSERT INTO chat_messages (id, session_id, role, blocks_json, created_at)
                    VALUES ('m1', 's1', 'user', '[]', 1)
                    """
                )
                conn.execute("DELETE FROM chat_sessions WHERE id = 's1'")
                left = conn.execute(
                    "SELECT COUNT(*) AS c FROM chat_messages WHERE id = 'm1'"
                ).fetchone()
                self.assertEqual(int(left["c"]), 0)

    def test_library_graph_orphan_cleanup_migration(self) -> None:
        """Migration 37 removes item_neighbors orphans that break title_relations rebuild."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = Database(db_path)
            item_id = db.upsert_library_item(
                {
                    "rating_key": "rk1",
                    "media_type": "movie",
                    "title": "Seed",
                    "year": 2000,
                }
            )
            raw = sqlite3.connect(db_path)
            try:
                raw.execute("PRAGMA foreign_keys=OFF")
                raw.execute(
                    """
                    INSERT INTO item_neighbors (item_id, neighbor_id, score, surprise_score)
                    VALUES (?, 999999, 0.5, 0.0)
                    """,
                    (item_id,),
                )
                # Re-run migration 37 specifically (not merely the latest version).
                raw.execute("DELETE FROM schema_version WHERE version = ?", (37,))
                raw.commit()
            finally:
                raw.close()

            # Re-open applies the library-graph orphan cleanup migration.
            db2 = Database(db_path)
            with db2.connect() as conn:
                left = conn.execute(
                    "SELECT COUNT(*) AS c FROM item_neighbors WHERE neighbor_id = 999999"
                ).fetchone()
                self.assertEqual(int(left["c"]), 0)
                ver = conn.execute(
                    "SELECT MAX(version) AS v FROM schema_version"
                ).fetchone()
                self.assertEqual(int(ver["v"]), CURRENT_SCHEMA_VERSION)


class SecretsAtRestTests(unittest.TestCase):
    def test_encrypt_roundtrip_and_persist(self) -> None:
        os.environ["PROJECTIONIST_SECRETS_KEY"] = "test-secrets-key-for-unit"
        previous_tmdb = os.environ.pop("TMDB_API_KEY", None)
        try:
            cipher = encrypt_secret("super-secret-token")
            self.assertTrue(is_encrypted_secret(cipher))
            self.assertEqual(decrypt_secret(cipher), "super-secret-token")
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                save_settings(data_dir, Settings(tmdb_api_key="plain-tmdb"))
                raw = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
                self.assertTrue(is_encrypted_secret(raw["tmdb_api_key"]))
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.tmdb_api_key, "plain-tmdb")
        finally:
            del os.environ["PROJECTIONIST_SECRETS_KEY"]
            if previous_tmdb is not None:
                os.environ["TMDB_API_KEY"] = previous_tmdb

    def test_boot_migration_encrypts_plaintext(self) -> None:
        os.environ["PROJECTIONIST_SECRETS_KEY"] = "test-secrets-key-for-migrate"
        previous_tmdb = os.environ.pop("TMDB_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                path = data_dir / "settings.json"
                path.write_text(
                    json.dumps({"tmdb_api_key": "legacy-plain", "llm_model": "gpt-4o-mini"})
                    + "\n",
                    encoding="utf-8",
                )
                self.assertTrue(migrate_plaintext_settings_secrets(data_dir))
                raw = json.loads(path.read_text(encoding="utf-8"))
                self.assertTrue(is_encrypted_secret(raw["tmdb_api_key"]))
                self.assertEqual(raw["llm_model"], "gpt-4o-mini")
                self.assertFalse(migrate_plaintext_settings_secrets(data_dir))
        finally:
            del os.environ["PROJECTIONIST_SECRETS_KEY"]
            if previous_tmdb is not None:
                os.environ["TMDB_API_KEY"] = previous_tmdb

    def test_env_wins_for_secrets(self) -> None:
        os.environ["PROJECTIONIST_SECRETS_KEY"] = "test-secrets-key-env-wins"
        os.environ["TMDB_API_KEY"] = "from-env"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                save_settings(data_dir, Settings(tmdb_api_key="from-file"))
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.tmdb_api_key, "from-env")
        finally:
            del os.environ["PROJECTIONIST_SECRETS_KEY"]
            del os.environ["TMDB_API_KEY"]


class AgentWriteGateTests(unittest.TestCase):
    def test_single_owner_allows_watchlist_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = asyncio.run(
                registry._tool_add_to_watchlist(
                    {"title": "Film", "media_type": "movie", "tmdb_id": 42}
                )
            )
            payload = json.loads(result)
            self.assertIn("pin", payload)

    def test_multi_user_blocks_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                features=FeatureFlags(
                    multi_user_enabled=True,
                    agent_may_mutate_personal_data=False,
                )
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="u1")
            result = asyncio.run(
                registry._tool_add_to_watchlist(
                    {"title": "Film", "media_type": "movie", "tmdb_id": 42}
                )
            )
            payload = json.loads(result)
            self.assertEqual(payload.get("code"), "agent_personal_mutation_gated")

    def test_multi_user_allows_when_opted_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, display_name, role, created_at)
                    VALUES ('u1', 'Member', 'member', 1.0)
                    """
                )
            settings = Settings(
                features=FeatureFlags(
                    multi_user_enabled=True,
                    agent_may_mutate_personal_data=True,
                )
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, user_id="u1")
            result = asyncio.run(
                registry._tool_add_to_watchlist(
                    {"title": "Film", "media_type": "movie", "tmdb_id": 42}
                )
            )
            payload = json.loads(result)
            self.assertIn("pin", payload)


try:
    from projectionist.mcp import server as _mcp_server  # noqa: F401

    _HAS_MCP = True
except Exception:  # noqa: BLE001
    _HAS_MCP = False


@skipUnless(_HAS_MCP, "mcp package not installed")
class PrivacyMcpAffinityTests(unittest.TestCase):
    def test_affinity_tools_require_full_mode(self) -> None:
        from projectionist.mcp import server as mcp_server
        from projectionist.mcp.mode import set_mcp_mode

        set_mcp_mode("privacy")
        try:
            for fn in (
                mcp_server.analyze_watch_patterns,
                mcp_server.recommend_hidden_gems,
                mcp_server.suggest_purge_candidates_tool,
                mcp_server.list_watchlist_pins,
                mcp_server.what_to_watch_tonight,
            ):
                with mock.patch.object(mcp_server, "_database", side_effect=AssertionError("should not hit db")):
                    payload = json.loads(fn())
                self.assertIn("error", payload)
                self.assertIn("full MCP", payload["error"])
        finally:
            set_mcp_mode("full")


if __name__ == "__main__":
    unittest.main()
