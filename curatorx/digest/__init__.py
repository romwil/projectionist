"""Weekly in-app library digest (M4 owner tool).

Assembles a "This week in your library" snapshot from existing stats, health,
knowledge coverage, media issues, and recent additions — no email transport
required. A scheduler task snapshots it weekly; the Dashboard reads the latest.
"""

from __future__ import annotations

from curatorx.digest.service import (
    WEEK_SECONDS,
    build_weekly_digest,
    current_week_start,
    snapshot_weekly_digest,
)

__all__ = [
    "WEEK_SECONDS",
    "build_weekly_digest",
    "current_week_start",
    "snapshot_weekly_digest",
]
