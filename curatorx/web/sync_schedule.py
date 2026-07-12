"""Pure decision helpers for library sync scheduling."""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def should_run_scheduled_library_sync(
    *,
    now: datetime,
    last_sync_ts: Optional[float],
    interval_hours: int,
    preferred_hour: Optional[int],
) -> bool:
    """Return whether the background sync scheduler should start a job.

    ``library_sync_interval_hours`` is the minimum gap between syncs (1–168).

    When ``preferred_hour`` is unset, fire as soon as that gap has elapsed
    (including “never synced”).

    When ``preferred_hour`` is set (0–23, container-local time via ``TZ``):
    wait until that clock hour each day instead of firing purely on elapsed
    time after startup. Still respect the interval gate so a restart shortly
    after a sync does not double-run. If the library is already stale beyond
    the interval and local time is at/past the preferred hour, catch up.
    """
    interval = max(1, int(interval_hours))
    now_ts = now.timestamp()

    if last_sync_ts is not None:
        try:
            age_seconds = now_ts - float(last_sync_ts)
        except (TypeError, ValueError):
            age_seconds = float("inf")
        if age_seconds < interval * 3600:
            return False

    if preferred_hour is None:
        return True

    try:
        hour = int(preferred_hour)
    except (TypeError, ValueError):
        return True
    if hour < 0 or hour > 23:
        return True

    if now.hour < hour:
        return False

    if last_sync_ts is not None:
        try:
            last_dt = datetime.fromtimestamp(float(last_sync_ts), tz=now.tzinfo)
        except (TypeError, ValueError, OSError, OverflowError):
            return True
        if last_dt.date() == now.date() and last_dt.hour >= hour:
            return False

    return True
