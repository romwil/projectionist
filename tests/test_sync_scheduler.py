"""Unit tests for library sync scheduler decision logic."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from curatorx.config_store import Settings
from curatorx.web.sync_schedule import should_run_scheduled_library_sync


def _local(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    # Fixed offset so tests do not depend on the host TZ.
    return datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=-4)))


class ShouldRunScheduledLibrarySyncTests(unittest.TestCase):
    def test_interval_only_runs_when_never_synced(self) -> None:
        self.assertTrue(
            should_run_scheduled_library_sync(
                now=_local(2026, 7, 12, 10),
                last_sync_ts=None,
                interval_hours=24,
                preferred_hour=None,
            )
        )

    def test_interval_only_skips_recent_sync(self) -> None:
        now = _local(2026, 7, 12, 10)
        last = (now - timedelta(hours=10)).timestamp()
        self.assertFalse(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=24,
                preferred_hour=None,
            )
        )

    def test_interval_only_runs_after_interval(self) -> None:
        now = _local(2026, 7, 12, 10)
        last = (now - timedelta(hours=25)).timestamp()
        self.assertTrue(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=24,
                preferred_hour=None,
            )
        )

    def test_preferred_hour_waits_until_hour(self) -> None:
        now = _local(2026, 7, 12, 2)  # before 03:00
        self.assertFalse(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=None,
                interval_hours=24,
                preferred_hour=3,
            )
        )

    def test_preferred_hour_runs_at_hour_when_due(self) -> None:
        now = _local(2026, 7, 12, 3)
        last = (now - timedelta(hours=25)).timestamp()
        self.assertTrue(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=24,
                preferred_hour=3,
            )
        )

    def test_preferred_hour_catchup_after_hour_when_stale(self) -> None:
        # Restart at 10:00 with stale library — past preferred hour → catch up.
        now = _local(2026, 7, 12, 10)
        last = (now - timedelta(hours=30)).timestamp()
        self.assertTrue(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=24,
                preferred_hour=3,
            )
        )

    def test_preferred_hour_blocks_startup_when_recent(self) -> None:
        now = _local(2026, 7, 12, 10)
        last = (now - timedelta(hours=2)).timestamp()
        self.assertFalse(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=24,
                preferred_hour=3,
            )
        )

    def test_preferred_hour_blocks_second_run_same_day(self) -> None:
        now = _local(2026, 7, 12, 15)
        # Synced today at 03:10 — interval would allow a short cadence, but daily window is done.
        last = _local(2026, 7, 12, 3, 10).timestamp()
        self.assertFalse(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=last,
                interval_hours=1,
                preferred_hour=3,
            )
        )

    def test_preferred_hour_never_synced_past_hour_runs(self) -> None:
        now = _local(2026, 7, 12, 10)
        self.assertTrue(
            should_run_scheduled_library_sync(
                now=now,
                last_sync_ts=None,
                interval_hours=24,
                preferred_hour=3,
            )
        )

    def test_settings_round_trip_null_hour(self) -> None:
        settings = Settings.from_mapping(
            {"library_sync_interval_hours": 24, "library_sync_hour": None}
        )
        self.assertIsNone(settings.library_sync_hour)
        settings = Settings.from_mapping({"library_sync_hour": 3})
        self.assertEqual(settings.library_sync_hour, 3)
        settings = Settings.from_mapping({"library_sync_hour": ""})
        self.assertIsNone(settings.library_sync_hour)
        settings = Settings.from_mapping({"library_sync_hour": 99})
        self.assertIsNone(settings.library_sync_hour)


if __name__ == "__main__":
    unittest.main()
