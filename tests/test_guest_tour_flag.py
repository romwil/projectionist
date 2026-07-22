"""Guest tour feature flag (settings + CURATORX_GUEST_TOUR_ENABLED)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from curatorx.config_store import (
    FeatureFlags,
    Settings,
    resolve_guest_tour_enabled,
    save_settings,
)


class GuestTourFlagTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("CURATORX_GUEST_TOUR_ENABLED", None)

    def test_defaults_off(self) -> None:
        self.assertFalse(resolve_guest_tour_enabled(Settings()))

    def test_settings_toggle(self) -> None:
        settings = Settings(features=FeatureFlags(guest_tour_enabled=True))
        self.assertTrue(resolve_guest_tour_enabled(settings))

    def test_env_wins_when_set(self) -> None:
        settings = Settings(features=FeatureFlags(guest_tour_enabled=False))
        os.environ["CURATORX_GUEST_TOUR_ENABLED"] = "1"
        self.assertTrue(resolve_guest_tour_enabled(settings))
        os.environ["CURATORX_GUEST_TOUR_ENABLED"] = "0"
        self.assertFalse(resolve_guest_tour_enabled(Settings(features=FeatureFlags(guest_tour_enabled=True))))

    def test_persists_in_settings_json(self) -> None:
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(features=FeatureFlags(guest_tour_enabled=True))
            save_settings(data_dir, settings)
            raw = (data_dir / "settings.json").read_text(encoding="utf-8")
            self.assertIn("guest_tour_enabled", raw)


if __name__ == "__main__":
    unittest.main()
