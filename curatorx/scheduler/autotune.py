"""Active auto-tune for idle trickle tasks.

After a successful productive run, adjust ``items_per_cycle`` (batch) and
optionally ``run_interval_seconds`` based on measured duration vs timeout and
backlog ETA vs a target catch-up horizon.

Safety caps are per-task so TMDB / LLM / CPU-heavy neighbor work cannot runaway.
Owner interval overrides still win on the next save; auto-tune only nudges within
bounds and records every decision in the run's metrics for audit.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Tasks that expose a tunable batch size + progress backlog.
AUTOTUNE_TASKS = frozenset(
    {
        "metadata_enrichment",
        "semantic_embeddings",
        "plot_neighbors",
        "llm_logline_enrichment",
    }
)

# Target wall-clock catch-up horizon when backlog is large (seconds).
TARGET_HORIZON_SECONDS = {
    "metadata_enrichment": 7 * 86400,
    "semantic_embeddings": 7 * 86400,
    "plot_neighbors": 7 * 86400,
    "llm_logline_enrichment": 30 * 86400,  # keep LLM spend gentle
}

# Soft interval bounds for auto-tune nudges (owner may still set outside these
# via Admin; auto-tune will not push beyond them).
INTERVAL_BOUNDS: Dict[str, Tuple[int, int]] = {
    "metadata_enrichment": (1800, 86400),  # 30m – 1d
    "semantic_embeddings": (3600, 172800),  # 1h – 2d
    "plot_neighbors": (900, 43200),  # 15m – 12h (catch-up friendly)
    "llm_logline_enrichment": (3600, 172800),  # 1h – 2d
}

BATCH_BOUNDS: Dict[str, Tuple[int, int]] = {
    "metadata_enrichment": (5, 50),
    "semantic_embeddings": (10, 100),
    "plot_neighbors": (5, 60),
    "llm_logline_enrichment": (1, 10),
}

# Raise batch when duration is under this fraction of the timeout.
RAISE_DURATION_FRACTION = 0.45
# Lower batch when duration exceeds this fraction of the timeout.
LOWER_DURATION_FRACTION = 0.85
# Batch step multipliers.
RAISE_FACTOR = 1.5
LOWER_FACTOR = 0.66
# Interval step multipliers when ETA ≫ / ≪ horizon.
INTERVAL_SHORTEN_FACTOR = 0.75
INTERVAL_LENGTHEN_FACTOR = 1.35


@dataclass
class AutotuneDecision:
    """Result of one auto-tune evaluation."""

    changed: bool
    items_per_cycle: Optional[int] = None
    run_interval_seconds: Optional[int] = None
    reasons: Optional[list[str]] = None
    metrics: Optional[Dict[str, Any]] = None

    def as_metrics(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "autotune_changed": self.changed,
            "autotune_reasons": list(self.reasons or []),
        }
        if self.items_per_cycle is not None:
            payload["autotune_items_per_cycle"] = self.items_per_cycle
        if self.run_interval_seconds is not None:
            payload["autotune_run_interval_seconds"] = self.run_interval_seconds
        if self.metrics:
            payload.update(self.metrics)
        return payload


def clamp_batch(name: str, value: int) -> int:
    lo, hi = BATCH_BOUNDS.get(name, (1, 100))
    return max(lo, min(hi, int(value)))


def clamp_interval(name: str, value: int) -> int:
    lo, hi = INTERVAL_BOUNDS.get(name, (60, 2_592_000))
    return max(lo, min(hi, max(60, int(value))))


def resolve_batch_size(db: Any, name: str, default: int) -> int:
    """Read persisted ``items_per_cycle`` for a task, falling back to *default*."""
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT items_per_cycle FROM scheduled_tasks WHERE name = ?",
                (name,),
            ).fetchone()
    except Exception:
        return clamp_batch(name, default) if name in AUTOTUNE_TASKS else max(1, int(default))
    if row is None:
        return clamp_batch(name, default) if name in AUTOTUNE_TASKS else max(1, int(default))
    keys = row.keys() if hasattr(row, "keys") else []
    if "items_per_cycle" not in keys or row["items_per_cycle"] is None:
        return clamp_batch(name, default) if name in AUTOTUNE_TASKS else max(1, int(default))
    try:
        value = int(row["items_per_cycle"])
    except (TypeError, ValueError):
        value = int(default)
    return clamp_batch(name, value) if name in AUTOTUNE_TASKS else max(1, value)


def evaluate_autotune(
    *,
    name: str,
    status: str,
    duration_ms: int,
    timeout_seconds: int,
    items_per_cycle: int,
    interval_seconds: int,
    items_processed: Optional[int],
    remaining_items: Optional[int],
    has_more: bool = False,
) -> AutotuneDecision:
    """Compute a safe batch/interval adjustment without writing it.

    Only runs for :data:`AUTOTUNE_TASKS` after a successful productive cycle.
    """
    if name not in AUTOTUNE_TASKS:
        return AutotuneDecision(changed=False, reasons=["not_autotune_task"])

    if status not in {"completed", "cycle_limit"}:
        return AutotuneDecision(changed=False, reasons=[f"status_{status}"])

    processed = int(items_processed or 0)
    backlog = int(remaining_items) if remaining_items is not None else 0
    if processed <= 0 and backlog <= 0 and not has_more:
        return AutotuneDecision(changed=False, reasons=["no_backlog"])

    timeout_ms = max(1, int(timeout_seconds) * 1000)
    duration_ms = max(0, int(duration_ms))
    current_batch = clamp_batch(name, items_per_cycle)
    current_interval = clamp_interval(name, interval_seconds)
    new_batch = current_batch
    new_interval = current_interval
    reasons: list[str] = []
    detail: Dict[str, Any] = {
        "autotune_duration_ms": duration_ms,
        "autotune_timeout_ms": timeout_ms,
        "autotune_backlog": backlog,
        "autotune_processed": processed,
        "autotune_batch_before": current_batch,
        "autotune_interval_before": current_interval,
    }

    duration_frac = duration_ms / float(timeout_ms)
    high_backlog = backlog >= max(current_batch * 2, 10) or has_more

    if duration_frac >= LOWER_DURATION_FRACTION or status == "cycle_limit" and duration_frac >= 0.7:
        lowered = clamp_batch(name, max(1, int(math.floor(current_batch * LOWER_FACTOR))))
        if lowered < current_batch:
            new_batch = lowered
            reasons.append("near_timeout_lower_batch")
    elif duration_frac <= RAISE_DURATION_FRACTION and high_backlog:
        raised = clamp_batch(name, max(current_batch + 1, int(math.ceil(current_batch * RAISE_FACTOR))))
        if raised > current_batch:
            new_batch = raised
            reasons.append("headroom_raise_batch")

    # Interval vs target horizon using the *new* batch size.
    horizon = TARGET_HORIZON_SECONDS.get(name, 7 * 86400)
    if backlog > 0 and new_batch > 0:
        cycles = int(math.ceil(backlog / float(new_batch)))
        eta_seconds = cycles * new_interval
        detail["autotune_eta_seconds"] = eta_seconds
        detail["autotune_target_horizon_seconds"] = horizon
        if eta_seconds > horizon * 1.25:
            shortened = clamp_interval(
                name, max(60, int(math.floor(new_interval * INTERVAL_SHORTEN_FACTOR)))
            )
            if shortened < new_interval:
                new_interval = shortened
                reasons.append("backlog_eta_shorten_interval")
        elif eta_seconds < horizon * 0.35 and backlog < new_batch * 3 and not has_more:
            # Small leftover backlog — no need to run so often.
            lengthened = clamp_interval(
                name, int(math.ceil(new_interval * INTERVAL_LENGTHEN_FACTOR))
            )
            if lengthened > new_interval:
                new_interval = lengthened
                reasons.append("caught_up_lengthen_interval")

    changed = new_batch != current_batch or new_interval != current_interval
    if not changed:
        reasons = reasons or ["no_change"]
    detail["autotune_batch_after"] = new_batch
    detail["autotune_interval_after"] = new_interval

    return AutotuneDecision(
        changed=changed,
        items_per_cycle=new_batch if changed else current_batch,
        run_interval_seconds=new_interval if changed else current_interval,
        reasons=reasons,
        metrics=detail,
    )
