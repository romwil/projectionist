"""Guest tour is permanently off."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from projectionist.config_store import (
    FeatureFlags,
    Settings,
    resolve_guest_tour_enabled,
    save_settings,
)


class GuestTourFlagTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_GUEST_TOUR_ENABLED", None)

    def test_always_false(self) -> None:
        self.assertFalse(resolve_guest_tour_enabled(Settings()))
        self.assertFalse(
            resolve_guest_tour_enabled(Settings(features=FeatureFlags(guest_tour_enabled=True)))
        )
        os.environ["PROJECTIONIST_GUEST_TOUR_ENABLED"] = "1"
        self.assertFalse(resolve_guest_tour_enabled(Settings()))

    def test_persists_legacy_key_but_does_not_enable(self) -> None:
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(features=FeatureFlags(guest_tour_enabled=True))
            save_settings(data_dir, settings)
            raw = (data_dir / "settings.json").read_text(encoding="utf-8")
            self.assertIn("guest_tour_enabled", raw)
            self.assertFalse(resolve_guest_tour_enabled(settings))


if __name__ == "__main__":
    unittest.main()
