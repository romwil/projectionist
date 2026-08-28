"""Tests for setup wizard helpers."""

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, TheaterSettings, load_merged_settings, save_settings
from projectionist.web.app import SettingsPayload
from projectionist.web.setup import merge_secret_fields, merge_theater_settings_payload, resolve_test_payload


class SetupTests(unittest.TestCase):
    def test_resolve_test_payload_backfills_llm_model(self) -> None:
        existing = Settings(llm_provider="anthropic", llm_model="claude-sonnet-4-6")
        merged = resolve_test_payload({"llm_provider": "anthropic"}, existing)
        self.assertEqual(merged["llm_model"], "claude-sonnet-4-6")

    def test_resolve_test_payload_preserves_incoming_llm_model(self) -> None:
        existing = Settings(llm_provider="anthropic", llm_model="claude-sonnet-4-6")
        merged = resolve_test_payload(
            {"llm_provider": "anthropic", "llm_model": "claude-sonnet-4-20250514"},
            existing,
        )
        self.assertEqual(merged["llm_model"], "claude-sonnet-4-20250514")

    def test_merge_secret_fields_preserves_plex_sections(self) -> None:
        existing = Settings(plex_movie_section="1", plex_tv_section="2")
        merged = merge_secret_fields(
            {"plex_movie_section": "", "plex_tv_section": ""},
            existing,
        )
        self.assertEqual(merged["plex_movie_section"], "1")
        self.assertEqual(merged["plex_tv_section"], "2")

    def test_merge_secret_fields_preserves_onboarding_complete(self) -> None:
        existing = Settings(onboarding_complete=True)
        merged = merge_secret_fields({"onboarding_complete": False}, existing)
        self.assertTrue(merged["onboarding_complete"])

    def test_merge_secret_fields_allows_onboarding_complete(self) -> None:
        existing = Settings(onboarding_complete=False)
        merged = merge_secret_fields({"onboarding_complete": True}, existing)
        self.assertTrue(merged["onboarding_complete"])

    def test_merge_theater_settings_payload_preserves_when_omitted(self) -> None:
        existing = Settings(theater=TheaterSettings(enabled=True, rotate_seconds=20))
        payload = SettingsPayload.model_validate({"features": {"multi_user_enabled": False}})
        merged = merge_secret_fields(payload.model_dump(), existing)
        merge_theater_settings_payload(payload, existing, merged)
        self.assertTrue(merged["theater"]["enabled"])
        self.assertEqual(merged["theater"]["rotate_seconds"], 20)

    def test_merge_theater_settings_payload_merges_partial_nested(self) -> None:
        existing = Settings(
            theater=TheaterSettings(
                enabled=False,
                orientation="portrait",
                rotate_seconds=20,
            )
        )
        payload = SettingsPayload.model_validate({"theater": {"enabled": True}})
        merged = merge_secret_fields(payload.model_dump(), existing)
        merge_theater_settings_payload(payload, existing, merged)
        self.assertTrue(merged["theater"]["enabled"])
        self.assertEqual(merged["theater"]["orientation"], "portrait")
        self.assertEqual(merged["theater"]["rotate_seconds"], 20)


class TheaterSettingsPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        self._tmpdir.cleanup()

    def test_theater_enabled_survives_partial_put_and_reload(self) -> None:
        data_dir = Path(self._tmpdir.name)
        save_settings(data_dir, Settings(theater=TheaterSettings(enabled=True)))

        resp = self.client.put(
            "/api/settings",
            json={"features": {"multi_user_enabled": False, "invite_only": True}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["theater"]["enabled"])

        reloaded = load_merged_settings(data_dir)
        self.assertTrue(reloaded.theater.enabled)

    def test_theater_enabled_survives_full_put_round_trip(self) -> None:
        current = self.client.get("/api/settings").json()
        current["theater"] = {
            **(current.get("theater") or {}),
            "enabled": True,
            "orientation": "landscape",
            "audience": "everyone",
            "idle_mode": "empty",
            "multi_mode": "rotator",
            "header_mode": "dynamic",
            "static_label": "",
            "rotate_seconds": 12,
        }
        resp = self.client.put("/api/settings", json=current)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["theater"]["enabled"])

        reloaded = load_merged_settings(Path(self._tmpdir.name))
        self.assertTrue(reloaded.theater.enabled)


if __name__ == "__main__":
    unittest.main()
