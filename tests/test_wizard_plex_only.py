"""Phase 3 (UX-009, UX-013): admin first-run wizard finishes on Plex alone.

The owner must not be blocked from finishing setup just because they have
not also wired up a language model, Radarr, and Sonarr. Those stay optional
connections the owner can add later from Admin -> Connections.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class WizardPlexOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-wizard-plex-only-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _seed_plex_only(self) -> None:
        """Curator name set, Plex certified + sections chosen; LLM/Radarr/Sonarr untouched."""
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
        db.upsert_persona(curator_name="Ada")
        db.upsert_service_integration(
            "plex",
            base_url="http://plex.local:32400",
            credential_marker="***configured***",
            connection_status="verified",
            last_tested_at="2026-10-31 00:00:00",
            certified=1,
        )
        settings_path = Path(self._tmpdir.name) / "settings.json"
        settings_path.write_text(
            json.dumps({"plex_movie_section": "1", "plex_tv_section": "2"}),
            encoding="utf-8",
        )

    def test_onboarding_complete_with_plex_only(self) -> None:
        self._seed_plex_only()
        resp = self.client.get("/api/setup/wizard")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["onboarding_complete"], body)
        self.assertTrue(body["steps"]["infrastructure"]["complete"])
        self.assertTrue(body["steps"]["infrastructure"]["plex_verified"])
        self.assertFalse(body["steps"]["infrastructure"]["llm_verified"])
        self.assertFalse(body["steps"]["infrastructure"]["radarr_verified"])
        self.assertFalse(body["steps"]["infrastructure"]["sonarr_verified"])

    def test_onboarding_incomplete_without_plex(self) -> None:
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.upsert_persona(curator_name="Ada")
        resp = self.client.get("/api/setup/wizard")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["onboarding_complete"])
        self.assertFalse(body["steps"]["infrastructure"]["complete"])


if __name__ == "__main__":
    unittest.main()
