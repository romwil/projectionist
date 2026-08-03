"""Per-user watch ledger: events, sessions, completions, year rollups."""

from __future__ import annotations

ALGORITHM_VERSION = 1
COMPLETION_THRESHOLD_PCT = 90.0
SESSION_GAP_MS = 4 * 60 * 60 * 1000
CLIENT_HANDOFF_GAP_MS = 30 * 60 * 1000
RESTART_PROGRESS_PCT = 15.0
SCROBBLE_DEDUPE_WINDOW_MS = 120_000
IMPLAUSIBLE_RECOMPLETE_MS = 6 * 60 * 60 * 1000

__all__ = [
    "ALGORITHM_VERSION",
    "COMPLETION_THRESHOLD_PCT",
]
