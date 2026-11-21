"""Track 1 rebrand compat: PROJECTIONIST env, DB path fallback."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, load_merged_settings, save_settings
from projectionist.dbfiles import AmbiguousDatabaseError, open_existing_database
from projectionist.envcompat import branded_env, resolve_env
from projectionist.web.jobs import _resolve_db_path

# 100-byte SQLite header. Opening sqlite3.connect on a missing path creates a
# 0-byte file, which is not this.
SQLITE_FILE = b"SQLite format 3\x00" + b"\x00" * 84


class EnvCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._keys = (
            "PROJECTIONIST_WEBHOOK_SECRET",
            "CURATORX_WEBHOOK_SECRET",
            "PROJECTIONIST_GUEST_TOUR_ENABLED",
            "CURATORX_GUEST_TOUR_ENABLED",
            "PROJECTIONIST_SESSION_SECRET",
            "CURATORX_SESSION_SECRET",
        )
        self._saved = {k: os.environ.get(k) for k in self._keys}
        for key in self._keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_reads_projectionist_prefix(self) -> None:
        os.environ["PROJECTIONIST_WEBHOOK_SECRET"] = "new-secret"
        self.assertEqual(resolve_env("PROJECTIONIST_WEBHOOK_SECRET"), "new-secret")
        self.assertEqual(branded_env("WEBHOOK_SECRET"), "new-secret")

    def test_ignores_legacy_curatorx_prefix(self) -> None:
        os.environ["CURATORX_WEBHOOK_SECRET"] = "legacy-secret"
        self.assertIsNone(resolve_env("PROJECTIONIST_WEBHOOK_SECRET"))
        self.assertIsNone(branded_env("WEBHOOK_SECRET"))

    def test_settings_file_with_retired_guest_tour_flag_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.json").write_text(
                '{"features": {"guest_tour_enabled": true, "multi_user_enabled": true}}',
                encoding="utf-8",
            )
            settings = load_merged_settings(root)
            self.assertTrue(settings.features.multi_user_enabled)
            self.assertFalse(hasattr(settings.features, "guest_tour_enabled"))

    def test_load_merged_settings_uses_projectionist_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PROJECTIONIST_WEBHOOK_SECRET"] = "from-projectionist"
            settings = load_merged_settings(Path(tmp))
            self.assertEqual(settings.webhook_secret, "from-projectionist")


class DbPathCompatTests(unittest.TestCase):
    def test_uses_projectionist_db_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projectionist.db").write_bytes(SQLITE_FILE)
            (root / "curatorx.db").write_bytes(b"")
            with self.assertLogs("projectionist.dbfiles", level="WARNING") as logs:
                resolved = _resolve_db_path(root)
            self.assertEqual(resolved, root / "projectionist.db")
            self.assertIn("curatorx.db", logs.output[0])
            self.assertEqual((root / "curatorx.db").read_bytes(), b"")

    def test_opens_curatorx_db_without_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "curatorx.db"
            legacy.write_bytes(SQLITE_FILE)
            resolved = _resolve_db_path(root)
            self.assertEqual(resolved, legacy)
            self.assertTrue(legacy.exists())
            self.assertFalse((root / "projectionist.db").exists())

    def test_skips_empty_projectionist_db_and_uses_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "projectionist.db"
            legacy = root / "curatorx.db"
            empty.write_bytes(b"")
            legacy.write_bytes(SQLITE_FILE)
            with self.assertLogs("projectionist.dbfiles", level="WARNING") as logs:
                resolved = _resolve_db_path(root)
            self.assertEqual(resolved, legacy)
            self.assertEqual(empty.read_bytes(), b"")
            self.assertEqual(legacy.read_bytes(), SQLITE_FILE)
            self.assertIn("projectionist.db", logs.output[0])
            self.assertIn("empty or not a SQLite database", logs.output[0])

    def test_skips_invalid_projectionist_db_and_uses_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "projectionist.db"
            legacy = root / "curatorx.db"
            invalid.write_bytes(b"not a database")
            legacy.write_bytes(SQLITE_FILE)
            with self.assertLogs("projectionist.dbfiles", level="WARNING") as logs:
                resolved = _resolve_db_path(root)
            self.assertEqual(resolved, legacy)
            self.assertEqual(invalid.read_bytes(), b"not a database")
            self.assertIn("projectionist.db", logs.output[0])

    def test_refuses_to_start_when_two_real_databases_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "projectionist.db"
            legacy = root / "curatorx.db"
            canonical.write_bytes(SQLITE_FILE)
            legacy.write_bytes(SQLITE_FILE)
            with self.assertRaises(AmbiguousDatabaseError) as raised:
                _resolve_db_path(root)
            message = str(raised.exception)
            self.assertIn("Refusing to start", message)
            self.assertIn("projectionist.db", message)
            self.assertIn("curatorx.db", message)
            self.assertEqual(canonical.read_bytes(), SQLITE_FILE)
            self.assertEqual(legacy.read_bytes(), SQLITE_FILE)

    def test_defaults_to_projectionist_db_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_resolve_db_path(root), root / "projectionist.db")
            self.assertFalse((root / "projectionist.db").exists())

    def test_adopts_mediacurator_db_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ancient = root / "mediacurator.db"
            ancient.write_bytes(SQLITE_FILE)
            resolved = _resolve_db_path(root)
            self.assertEqual(resolved, root / "projectionist.db")
            self.assertEqual(resolved.read_bytes(), SQLITE_FILE)
            self.assertFalse(ancient.exists())

    def test_open_existing_database_does_not_create_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "projectionist.db"
            with self.assertRaises(FileNotFoundError):
                open_existing_database(missing, timeout=1.0)
            self.assertFalse(missing.exists())

    def test_open_existing_database_can_write_a_file_that_is_already_there(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "curatorx.db"
            import sqlite3

            seed = sqlite3.connect(path)
            seed.execute("CREATE TABLE seed (id INTEGER)")
            seed.commit()
            seed.close()
            self.assertGreater(path.stat().st_size, 0)
            conn = open_existing_database(path, timeout=1.0)
            try:
                conn.execute("CREATE TABLE diagnostic (id INTEGER)")
                conn.commit()
            finally:
                conn.close()
            again = open_existing_database(path, timeout=1.0)
            try:
                row = again.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='diagnostic'"
                ).fetchone()
            finally:
                again.close()
            self.assertIsNotNone(row)


class WebhookHeaderCompatTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        self._secret = "compat-webhook-secret"
        save_settings(Path(self._tmpdir.name), Settings(webhook_secret=self._secret))
        import projectionist.web.app as app_mod
        import projectionist.web.jobs as jobs_mod

        jobs_mod.reset_job_manager_for_tests()
        importlib.reload(app_mod)
        self._client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        self._client.close()
        self._tmpdir.cleanup()
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)

    def test_accepts_projectionist_header(self) -> None:
        response = self._client.post(
            "/api/webhooks/plex",
            json={"event": "media.play", "Metadata": {"type": "movie", "ratingKey": "1"}},
            headers={"X-Projectionist-Webhook-Secret": self._secret},
        )
        self.assertEqual(response.status_code, 200)

    def test_rejects_legacy_curatorx_header(self) -> None:
        response = self._client.post(
            "/api/webhooks/plex",
            json={"event": "media.play", "Metadata": {"type": "movie", "ratingKey": "1"}},
            headers={"X-CuratorX-Webhook-Secret": self._secret},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
