"""Week-long Live guide horizon and refill-before-expiry."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from projectionist.live_channels.guide_horizon import (
    GUIDE_HORIZON_HOURS,
    PLEX_RELOAD_STATE_KEY,
    REFILL_LEAD_HOURS,
    hours_until,
    lineup_needs_week,
    maintain_guide_week,
    plex_reload_due,
    programming_hours_to_set,
    soonest_guide_hours,
    window_is_short,
    window_needs_roll,
)


# Measured on Automat prod, 2026-10-04. XMLTV programmingHours was 12.
_MEASURED_NOW = datetime(2026, 10, 4, 21, 4, 39, tzinfo=timezone.utc)
_MEASURED_END = datetime(2026, 10, 5, 9, 0, 0, tzinfo=timezone.utc)
# Sci-Fi channel duration that evening (ms) — about 7.9 days of lineup.
_MEASURED_CYCLE_MS = 684_600_000


def _settings(*, live: bool = True, url: str = "http://tunarr.test") -> SimpleNamespace:
    return SimpleNamespace(
        features=SimpleNamespace(live_channels_enabled=live),
        tunarr=SimpleNamespace(url=url),
        plex_url="http://plex.test",
        plex_token="token",
    )


class _MemoryDb:
    def __init__(self) -> None:
        self.state: dict[str, str] = {}

    def get_sync_state(self, key: str) -> str | None:
        return self.state.get(key)

    def set_sync_state(self, key: str, value: str) -> None:
        self.state[key] = value


class _Engine:
    def __init__(self, *, hours: int, end: datetime, channels: list[dict]) -> None:
        self.hours = hours
        self.end = end
        self.channels = channels
        self.force_puts = 0

    def get_guide_status(self) -> dict:
        return {
            "guideTimes": {
                "station": {
                    "start": (self.end - timedelta(hours=12)).isoformat(),
                    "end": self.end.isoformat(),
                }
            }
        }

    def ensure_xmltv_programming_hours(self, hours: int) -> dict:
        if self.hours >= int(hours):
            return {"ok": True, "changed": False, "programmingHours": self.hours}
        previous = self.hours
        self.hours = int(hours)
        return {"ok": True, "changed": True, "programmingHours": self.hours, "previous": previous}

    def put_xmltv_settings(self, body: dict) -> dict:
        self.force_puts += 1
        self.hours = int(body["programmingHours"])
        return {"programmingHours": self.hours}

    def list_channels(self) -> list[dict]:
        return list(self.channels)


class GuideHorizonTests(unittest.TestCase):
    def test_measured_evening_window_ends_before_a_week(self) -> None:
        ahead = hours_until(_MEASURED_END, _MEASURED_NOW)
        self.assertGreater(ahead, 11.5)
        self.assertLess(ahead, 12.5)
        self.assertTrue(window_is_short(ahead))
        self.assertTrue(window_needs_roll(ahead))
        self.assertEqual(programming_hours_to_set(12), GUIDE_HORIZON_HOURS)
        self.assertEqual(GUIDE_HORIZON_HOURS, 24 * 7)
        # The lineup was already about a week; the published slice was the short part.
        self.assertFalse(lineup_needs_week(_MEASURED_CYCLE_MS))

    def test_week_ahead_does_not_roll_or_refill(self) -> None:
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        end = now + timedelta(hours=GUIDE_HORIZON_HOURS - 2)
        ahead = soonest_guide_hours({"a": {"end": end.isoformat()}}, now)
        assert ahead is not None
        self.assertFalse(window_is_short(ahead))
        self.assertFalse(window_needs_roll(ahead))
        self.assertIsNone(programming_hours_to_set(GUIDE_HORIZON_HOURS))
        self.assertGreater(REFILL_LEAD_HOURS, 24)

    def test_lead_window_rolls_before_the_week_expires(self) -> None:
        self.assertTrue(window_needs_roll(REFILL_LEAD_HOURS - 1))
        self.assertFalse(window_needs_roll(REFILL_LEAD_HOURS + 1))
        self.assertTrue(window_needs_roll(None))
        self.assertTrue(lineup_needs_week(3 * 3_600_000))
        self.assertTrue(plex_reload_due(None, 1_000.0))
        self.assertFalse(plex_reload_due(1_000.0, 1_000.0 + 3600))

    def test_maintain_extends_short_window_without_reshuffling_a_week_cycle(self) -> None:
        engine = _Engine(
            hours=12,
            end=_MEASURED_END,
            channels=[{"id": "sci-fi", "duration": _MEASURED_CYCLE_MS, "name": "Sci-Fi"}],
        )
        db = _MemoryDb()
        reloads: list[str] = []
        refills: list[str] = []
        result = maintain_guide_week(
            _settings(),
            db,
            client=engine,
            now=_MEASURED_NOW,
            reload_plex=lambda: reloads.append("plex") or {"ok": True, "reloaded": True},
            refill_lineup=lambda cid: refills.append(cid) or {"ok": True},
        )
        self.assertTrue(result["extended"])
        self.assertTrue(result["rolled"])
        self.assertEqual(engine.hours, GUIDE_HORIZON_HOURS)
        self.assertEqual(engine.force_puts, 0)
        self.assertEqual(refills, [])
        self.assertEqual(reloads, ["plex"])
        self.assertIn(PLEX_RELOAD_STATE_KEY, db.state)

    def test_maintain_refills_a_short_cycle_when_the_week_is_nearly_gone(self) -> None:
        now = _MEASURED_NOW
        engine = _Engine(
            hours=GUIDE_HORIZON_HOURS,
            end=now + timedelta(hours=12),
            channels=[{"id": "creature", "duration": 2 * 3_600_000, "name": "Creature"}],
        )
        db = _MemoryDb()
        refills: list[str] = []
        with patch(
            "projectionist.live_channels.publish.recipe_from_station_meta",
            return_value=object(),
        ):
            result = maintain_guide_week(
                _settings(),
                db,
                client=engine,
                now=now,
                reload_plex=lambda: {"ok": True, "reloaded": True},
                refill_lineup=lambda cid: refills.append(cid) or {"ok": True},
            )
        self.assertFalse(result["extended"])
        self.assertTrue(result["rolled"])
        self.assertEqual(engine.force_puts, 1)
        self.assertEqual(refills, ["creature"])

    def test_healthy_week_skips_rebuild_when_plex_was_just_reloaded(self) -> None:
        now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        engine = _Engine(
            hours=GUIDE_HORIZON_HOURS,
            end=now + timedelta(hours=GUIDE_HORIZON_HOURS - 1),
            channels=[{"id": "sci-fi", "duration": _MEASURED_CYCLE_MS}],
        )
        db = _MemoryDb()
        db.set_sync_state(PLEX_RELOAD_STATE_KEY, str(now.timestamp()))
        reloads: list[str] = []
        result = maintain_guide_week(
            _settings(),
            db,
            client=engine,
            now=now,
            reload_plex=lambda: reloads.append("plex") or {"reloaded": True},
        )
        self.assertFalse(result["extended"])
        self.assertFalse(result["rolled"])
        self.assertEqual(engine.force_puts, 0)
        self.assertEqual(reloads, [])
        self.assertEqual(result["refilled"], [])

    def test_live_off_skips(self) -> None:
        result = maintain_guide_week(_settings(live=False), client=object())
        self.assertEqual(result["skipped"], "live_off")


class SchedulerRegistrationTests(unittest.TestCase):
    def test_live_guide_week_is_registered_off_loop(self) -> None:
        import tempfile
        from pathlib import Path

        from projectionist.library.db import Database
        from projectionist.scheduler.engine import IdleScheduler
        from projectionist.scheduler.tasks import register_all

        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(Database(Path(tmp) / "t.db"), Path(tmp))
            register_all(scheduler)
            defn = scheduler._definitions["live_guide_week"]
            self.assertTrue(defn.off_loop)
            self.assertGreaterEqual(defn.run_interval_seconds, 3600)


if __name__ == "__main__":
    unittest.main()
