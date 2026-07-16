"""Opt-in live integration tests against real Plex / Radarr / Sonarr / Seerr.

Skipped by default so normal ``unittest discover`` never needs live services.

Enable for a hoster or CI with secrets:

.. code-block:: bash

    CURATORX_LIVE_INTEGRATION=1 \\
      PLEX_URL=... PLEX_TOKEN=... \\
      RADARR_URL=... RADARR_API_KEY=... \\
      SONARR_URL=... SONARR_API_KEY=... \\
      SEERR_URL=... SEERR_API_KEY=... \\
      .venv/bin/python -m unittest tests.test_live_integrations -v

Credentials are read from the environment (and ``.env`` unless
``CURATORX_SKIP_DOTENV=1``). When a field is empty, values from
``$DATA_DIR/settings.json`` (default ``./config``) fill the gap.

Each service test skips individually when that service is not configured.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from curatorx.config_store import load_dotenv_file, load_merged_settings
# Alias so pytest does not collect setup helpers as tests (names start with test_).
from curatorx.web.setup import (
    test_plex as check_plex,
    test_radarr as check_radarr,
    test_seerr as check_seerr,
    test_sonarr as check_sonarr,
)

_LIVE_FLAG = os.environ.get("CURATORX_LIVE_INTEGRATION", "").strip().lower()
_LIVE_ENABLED = _LIVE_FLAG in {"1", "true", "yes"}


def _env_or(*candidates: str) -> str:
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


@unittest.skipUnless(
    _LIVE_ENABLED,
    "Set CURATORX_LIVE_INTEGRATION=1 (plus service URL/API keys) to run live integrations",
)
class LiveIntegrationTests(unittest.TestCase):
    """Ping each configured *arr / Plex / Seerr instance when credentials exist."""

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("CURATORX_SKIP_DOTENV", "").strip() != "1":
            load_dotenv_file()
        data_dir = Path(os.environ.get("DATA_DIR", "config"))
        settings = load_merged_settings(data_dir)

        cls.plex_url = _env_or(os.environ.get("PLEX_URL"), settings.plex_url)
        cls.plex_token = _env_or(os.environ.get("PLEX_TOKEN"), settings.plex_token)
        cls.radarr_url = _env_or(os.environ.get("RADARR_URL"), settings.radarr_url)
        cls.radarr_api_key = _env_or(os.environ.get("RADARR_API_KEY"), settings.radarr_api_key)
        cls.sonarr_url = _env_or(os.environ.get("SONARR_URL"), settings.sonarr_url)
        cls.sonarr_api_key = _env_or(os.environ.get("SONARR_API_KEY"), settings.sonarr_api_key)
        cls.seerr_url = _env_or(os.environ.get("SEERR_URL"), settings.seerr.url)
        cls.seerr_api_key = _env_or(os.environ.get("SEERR_API_KEY"), settings.seerr.api_key)

    def test_plex_lists_sections(self) -> None:
        if not self.plex_url or not self.plex_token:
            self.skipTest("Plex not configured (need PLEX_URL + PLEX_TOKEN)")
        result = check_plex(self.plex_url, self.plex_token)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertIsInstance(result.get("sections"), list)
        self.assertGreaterEqual(len(result["sections"]), 1, result.get("message"))

    def test_radarr_reports_movies_or_root_folders(self) -> None:
        if not self.radarr_url or not self.radarr_api_key:
            self.skipTest("Radarr not configured (need RADARR_URL + RADARR_API_KEY)")
        result = check_radarr(self.radarr_url, self.radarr_api_key)
        self.assertTrue(result["ok"], result.get("message"))
        movie_count = result.get("movie_count")
        root_folders = result.get("root_folders") or []
        self.assertTrue(
            (isinstance(movie_count, int) and movie_count >= 0) or len(root_folders) >= 1,
            result.get("message"),
        )

    def test_sonarr_lists_series(self) -> None:
        if not self.sonarr_url or not self.sonarr_api_key:
            self.skipTest("Sonarr not configured (need SONARR_URL + SONARR_API_KEY)")
        result = check_sonarr(self.sonarr_url, self.sonarr_api_key)
        self.assertTrue(result["ok"], result.get("message"))
        series_count = result.get("series_count")
        self.assertIsInstance(series_count, int)
        self.assertGreaterEqual(series_count, 0, result.get("message"))

    def test_seerr_auth_me(self) -> None:
        if not self.seerr_url or not self.seerr_api_key:
            self.skipTest("Seerr not configured (need SEERR_URL + SEERR_API_KEY)")
        result = check_seerr(self.seerr_url, self.seerr_api_key)
        self.assertTrue(result["ok"], result.get("message"))
        self.assertIn("user_id", result)


class LiveIntegrationGateTests(unittest.TestCase):
    """Always runs — proves the live suite stays skipped without the env flag."""

    def test_live_class_is_skipped_when_flag_off(self) -> None:
        if _LIVE_ENABLED:
            self.skipTest("CURATORX_LIVE_INTEGRATION is enabled in this environment")
        self.assertTrue(
            getattr(LiveIntegrationTests, "__unittest_skip__", False),
            "LiveIntegrationTests must be skipped unless CURATORX_LIVE_INTEGRATION=1",
        )


if __name__ == "__main__":
    unittest.main()
