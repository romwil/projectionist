"""When is a scheduled task next due?

The configured ``run_interval_seconds`` is the *steady-state* cadence. A few
situations make the honest "next run" sooner or later than ``last_run + interval``
without changing what the owner configured:

* **Interrupted** — a chat request stopped the run early. Waiting a full interval
  (up to a week for the weekly mail tasks) would silently drop the work, so retry
  at the next idle window instead.
* **Catching up** — a trickle task (metadata, embeddings, neighbors, synopses)
  processed a full batch and still has backlog. On any library size the backlog
  drains in paced batches instead of one batch per interval; small libraries
  finish in minutes, huge ones stay bounded by the per-task gap and batch caps.
* **Backing off** — repeated ``degraded`` / ``error`` runs (e.g. Plex unreachable)
  double the wait up to a cap so a dead dependency is not hammered.
* **Skipped** — nothing to do (integration not configured). Fast tasks wait at
  least :data:`SKIPPED_MIN_INTERVAL_SECONDS` instead of logging an empty run
  every few minutes.

Pure functions, no I/O — see ``tests/test_scheduler_cadence.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

# After an interrupted run, retry at the next idle poll window rather than a full interval.
INTERRUPTED_RETRY_SECONDS = 300
# Failure backoff: double per consecutive failure, never past the cap (or the
# configured interval when that is already longer).
BACKOFF_CAP_SECONDS = 6 * 3600
BACKOFF_MAX_MULTIPLIER = 8
# Skipped runs (integration not configured) do not need a fast cadence.
SKIPPED_MIN_INTERVAL_SECONDS = 3600

REASON_INTERRUPTED = "retry_after_interrupt"
REASON_CATCH_UP = "catching_up"
REASON_BACKOFF = "backoff"
REASON_SKIPPED = "skipped_idle"


@dataclass(frozen=True)
class Cadence:
    """Effective schedule for one task."""

    interval_seconds: int
    reason: Optional[str] = None


def is_failure_status(status: Optional[str]) -> bool:
    text = str(status or "")
    return text == "degraded" or text.startswith("error")


def catch_up_threshold(batch_size: Optional[int]) -> int:
    """Minimum processed items for a run to count as productive catch-up.

    A run that only handled a sliver of its batch is usually re-hitting the same
    unresolvable titles; it must *not* trigger a fast follow-up.
    """
    return max(1, int(batch_size or 1) // 2)


def is_productive_catch_up(
    *,
    has_more: bool,
    items_processed: Optional[int],
    batch_size: Optional[int],
    catchup_gap_seconds: Optional[int],
) -> bool:
    if not has_more or not catchup_gap_seconds:
        return False
    return int(items_processed or 0) >= catch_up_threshold(batch_size)


def effective_cadence(
    *,
    interval_seconds: int,
    last_status: Optional[str],
    last_run_summary: Optional[Mapping[str, Any]] = None,
    catchup_gap_seconds: Optional[int] = None,
    failure_streak: int = 0,
) -> Cadence:
    """Return how long after ``last_run_at`` the task is due again."""
    interval = max(60, int(interval_seconds))
    status = str(last_status or "")
    base_status = status.split(":", 1)[0].strip()

    if base_status == "interrupted":
        retry = min(interval, INTERRUPTED_RETRY_SECONDS)
        return Cadence(max(60, retry), REASON_INTERRUPTED if retry < interval else None)

    if is_failure_status(status):
        streak = max(1, int(failure_streak or 1))
        multiplier = min(2**streak, BACKOFF_MAX_MULTIPLIER)
        cap = max(interval, BACKOFF_CAP_SECONDS)
        backed = min(interval * multiplier, cap)
        return Cadence(backed, REASON_BACKOFF if backed > interval else None)

    if base_status == "skipped":
        waited = max(interval, SKIPPED_MIN_INTERVAL_SECONDS)
        return Cadence(waited, REASON_SKIPPED if waited > interval else None)

    if catchup_gap_seconds and base_status in {"completed", "cycle_limit"}:
        metrics = (last_run_summary or {}).get("metrics") if last_run_summary else None
        if isinstance(metrics, Mapping) and metrics.get("catching_up"):
            gap = max(60, int(catchup_gap_seconds))
            if gap < interval:
                return Cadence(gap, REASON_CATCH_UP)

    return Cadence(interval, None)
