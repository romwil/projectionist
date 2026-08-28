"""Track 1 rebrand compat: PROJECTIONIST env, DB path fallback."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, load_merged_settings, resolve_guest_tour_enabled, save_settings
from projectionist.envcompat import branded_env, resolve_env
from projectionist.web.jobs import _resolve_db_path


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

    def test_guest_tour_env_does_not_enable(self) -> None:
        os.environ["PROJECTIONIST_GUEST_TOUR_ENABLED"] = "1"
        self.assertFalse(resolve_guest_tour_enabled(Settings()))
        os.environ["CURATORX_GUEST_TOUR_ENABLED"] = "1"
        self.assertFalse(resolve_guest_tour_enabled(Settings()))

    def test_load_merged_settings_uses_projectionist_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PROJECTIONIST_WEBHOOK_SECRET"] = "from-projectionist"
            settings = load_merged_settings(Path(tmp))
            self.assertEqual(settings.webhook_secret, "from-projectionist")


class DbPathCompatTests(unittest.TestCase):
    def test_uses_projectionist_db_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projectionist.db").write_bytes(b"")
            (root / "curatorx.db").write_bytes(b"")
            self.assertEqual(_resolve_db_path(root), root / "projectionist.db")

    def test_opens_curatorx_db_without_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "curatorx.db"
            legacy.write_bytes(b"legacy")
            resolved = _resolve_db_path(root)
            self.assertEqual(resolved, legacy)
            self.assertTrue(legacy.exists())
            self.assertFalse((root / "projectionist.db").exists())

    def test_defaults_to_projectionist_db_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_resolve_db_path(root), root / "projectionist.db")

    def test_adopts_mediacurator_db_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ancient = root / "mediacurator.db"
            ancient.write_bytes(b"ancient")
            resolved = _resolve_db_path(root)
            self.assertEqual(resolved, root / "projectionist.db")
            self.assertTrue(resolved.exists())
            self.assertFalse(ancient.exists())


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
