"""Durable scheduled-task run history (SQLite).

The in-memory :class:`~curatorx.scheduler.run_log.TaskRunLogStore` still feeds the
live Admin monitor.  This module is the source of truth for historical rates,
ETAs, and auto-tune decisions across restarts.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from typing import Any, Dict, List, Optional, Sequence

from curatorx.library.db import Database

DEFAULT_RETENTION_DAYS = 60
DEFAULT_HISTORY_LIMIT = 50
DEFAULT_RATE_LOOKBACK_HOURS = 72

# Preferred result keys that count as "items processed" for rate / auto-tune.
_ITEMS_KEYS: Sequence[str] = (
    "enriched",
    "embedded",
    "seeds",
    "processed",
    "tagged",
    "motifs",
    "caches_built",
    "count",
    "found",
    "total_pruned",
)


def ensure_run_history_table(conn: Any) -> None:
    """Create ``scheduled_task_runs`` (+ indexes) if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL,
            duration_ms INTEGER,
            status TEXT NOT NULL,
            trigger TEXT,
            outcome_reason TEXT,
            metrics_json TEXT,
            items_processed INTEGER,
            error TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_runs_name_finished
        ON scheduled_task_runs(name, finished_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_task_runs_finished
        ON scheduled_task_runs(finished_at)
        """
    )


def extract_items_processed(result: Optional[Dict[str, Any]]) -> Optional[int]:
    """Best-effort item count from a task result dict."""
    if not isinstance(result, dict):
        return None
    for key in _ITEMS_KEYS:
        value = result.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, float) and value >= 0 and value.is_integer():
            return int(value)
    return None


def append_task_run(
    db: Database,
    *,
    name: str,
    started_at: float,
    finished_at: float,
    duration_ms: int,
    status: str,
    trigger: str,
    outcome_reason: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    items_processed: Optional[int] = None,
    error: Optional[str] = None,
) -> int:
    """Insert one durable run row. Returns the new row id."""
    payload = json.dumps(metrics or {}, separators=(",", ":"), sort_keys=True)
    with db.connect() as conn:
        ensure_run_history_table(conn)
        cursor = conn.execute(
            """
            INSERT INTO scheduled_task_runs (
                name, started_at, finished_at, duration_ms, status, trigger,
                outcome_reason, metrics_json, items_processed, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                float(started_at),
                float(finished_at),
                int(duration_ms),
                str(status or "")[:200],
                str(trigger or "schedule")[:40],
                (str(outcome_reason)[:500] if outcome_reason else None),
                payload,
                int(items_processed) if items_processed is not None else None,
                (str(error)[:1000] if error else None),
            ),
        )
        return int(cursor.lastrowid or 0)


def prune_scheduled_task_runs(db: Database, retention_days: int) -> int:
    """Delete run-history rows older than *retention_days*. Returns rows deleted."""
    days = max(1, int(retention_days))
    cutoff = time.time() - (days * 86400)
    with db.connect() as conn:
        ensure_run_history_table(conn)
        cursor = conn.execute(
            "DELETE FROM scheduled_task_runs WHERE finished_at < ? OR "
            "(finished_at IS NULL AND started_at < ?)",
            (cutoff, cutoff),
        )
        return int(cursor.rowcount or 0)


def _row_to_dict(row: Any) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}
    raw = row["metrics_json"] if "metrics_json" in row.keys() else None
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                metrics = parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            metrics = {}
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "started_at": float(row["started_at"]) if row["started_at"] is not None else None,
        "finished_at": float(row["finished_at"]) if row["finished_at"] is not None else None,
        "duration_ms": int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        "status": str(row["status"] or ""),
        "trigger": str(row["trigger"] or ""),
        "outcome_reason": (
            str(row["outcome_reason"]) if row["outcome_reason"] is not None else None
        ),
        "metrics": metrics,
        "items_processed": (
            int(row["items_processed"]) if row["items_processed"] is not None else None
        ),
        "error": str(row["error"]) if row["error"] is not None else None,
    }


def list_task_runs(
    db: Database,
    name: str,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> List[Dict[str, Any]]:
    """Return newest-first durable runs for one task."""
    capped = max(1, min(int(limit or DEFAULT_HISTORY_LIMIT), 500))
    with db.connect() as conn:
        ensure_run_history_table(conn)
        rows = conn.execute(
            """
            SELECT * FROM scheduled_task_runs
            WHERE name = ?
            ORDER BY finished_at DESC, id DESC
            LIMIT ?
            """,
            (name, capped),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _percentile(sorted_values: List[float], pct: float) -> Optional[float]:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (pct / 100.0)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(sorted_values[low])
    weight = rank - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def aggregate_task_rate(
    db: Database,
    name: str,
    *,
    lookback_hours: int = DEFAULT_RATE_LOOKBACK_HOURS,
    interval_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate measured throughput and duration percentiles for a task.

    ``items_per_hour`` prefers wall-clock span of successful productive runs
    (items finished over the observed window).  When only one such run exists,
    falls back to items ÷ cycle interval (or duration) so ETAs still work.
    """
    hours = max(1, int(lookback_hours or DEFAULT_RATE_LOOKBACK_HOURS))
    cutoff = time.time() - (hours * 3600)
    with db.connect() as conn:
        ensure_run_history_table(conn)
        rows = conn.execute(
            """
            SELECT * FROM scheduled_task_runs
            WHERE name = ? AND finished_at IS NOT NULL AND finished_at >= ?
            ORDER BY finished_at ASC
            """,
            (name, cutoff),
        ).fetchall()

    runs = [_row_to_dict(row) for row in rows]
    total = len(runs)
    completed_like = [
        run
        for run in runs
        if str(run.get("status") or "") in {"completed", "cycle_limit"}
    ]
    errors = [
        run for run in runs if str(run.get("status") or "").startswith("error")
    ]
    skipped = [run for run in runs if str(run.get("status") or "") == "skipped"]

    durations = [
        float(run["duration_ms"])
        for run in completed_like
        if run.get("duration_ms") is not None and float(run["duration_ms"]) >= 0
    ]
    durations.sort()

    productive = [
        run
        for run in completed_like
        if run.get("items_processed") is not None and int(run["items_processed"]) > 0
    ]
    total_items = sum(int(run["items_processed"] or 0) for run in productive)

    items_per_hour: Optional[float] = None
    if productive and total_items > 0:
        first_start = min(float(run["started_at"] or 0) for run in productive)
        last_finish = max(float(run["finished_at"] or 0) for run in productive)
        span_hours = max(0.0, (last_finish - first_start) / 3600.0)
        if span_hours >= (1.0 / 60.0) and len(productive) >= 2:
            items_per_hour = total_items / span_hours
        else:
            # Single run (or near-instant span): extrapolate from cadence or duration.
            avg_items = total_items / len(productive)
            if interval_seconds and interval_seconds > 0:
                items_per_hour = avg_items / (float(interval_seconds) / 3600.0)
            else:
                avg_duration_h = (
                    statistics.mean(durations) / 3_600_000.0 if durations else 0.0
                )
                if avg_duration_h > 0:
                    items_per_hour = avg_items / avg_duration_h

    success_rate: Optional[float] = None
    if total > 0:
        # Treat completed + skipped as non-failures for "success rate" display.
        non_error = total - len(errors)
        success_rate = non_error / total

    return {
        "name": name,
        "lookback_hours": hours,
        "run_count": total,
        "completed_count": len(completed_like),
        "error_count": len(errors),
        "skipped_count": len(skipped),
        "success_rate": success_rate,
        "items_processed_total": total_items,
        "items_per_hour": items_per_hour,
        "duration_p50_ms": _percentile(durations, 50),
        "duration_p95_ms": _percentile(durations, 95),
        "avg_duration_ms": statistics.mean(durations) if durations else None,
        "avg_items_per_run": (
            (total_items / len(productive)) if productive else None
        ),
    }
