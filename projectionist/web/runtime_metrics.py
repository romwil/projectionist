"""On-box runtime signals for the owner (PERF-001, PERF-007).

* A fixed-size, in-memory latency reservoir per request group. No database,
  no exporter, nothing leaves the process.
* ``probe_database``: what ``/api/ready`` uses to say the database answers,
  not merely that the process started.
* One JSON log line per minute (while requests arrive) with write-queue depth
  and request p95, so the numbers exist before someone opens Admin.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)

RESERVOIR_SIZE = 512
LOG_INTERVAL_S = 60.0
READY_DB_TIMEOUT_S = 0.1

# Latency SLOs from the 2026-11-01 performance review (PERF-014), checked from local samples.
SLO_P95_MS = {"library_query": 800.0, "chat": 8000.0}

_STARTED_AT = time.time()


def request_group(path: str) -> Optional[str]:
    """Bucket an API path; ``None`` for paths we do not sample."""
    if not path.startswith("/api/"):
        return None
    if path == "/api/library/query":
        return "library_query"
    if path.startswith("/api/chat"):
        return "chat"
    if path in ("/api/health", "/api/ready"):
        return "probe"
    return "api"


def _percentile(sorted_values: list, pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(round(pct / 100.0 * (len(sorted_values) - 1)))))
    return float(sorted_values[index])


class LatencyReservoir:
    """Most recent ``size`` request durations per group, in milliseconds."""

    def __init__(self, size: int = RESERVOIR_SIZE) -> None:
        self._size = size
        self._lock = threading.Lock()
        self._samples: Dict[str, Deque[float]] = {}
        self._counts: Dict[str, int] = {}
        self._last_log = 0.0

    def record(self, group: str, duration_ms: float) -> None:
        with self._lock:
            bucket = self._samples.setdefault(group, deque(maxlen=self._size))
            bucket.append(float(duration_ms))
            self._counts[group] = self._counts.get(group, 0) + 1

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            copies = {g: sorted(s) for g, s in self._samples.items()}
            counts = dict(self._counts)
        out: Dict[str, Dict[str, float]] = {}
        for group, values in copies.items():
            out[group] = {
                "count": counts.get(group, 0),
                "window": len(values),
                "p50_ms": round(_percentile(values, 50), 1),
                "p95_ms": round(_percentile(values, 95), 1),
                "max_ms": round(values[-1], 1) if values else 0.0,
            }
        return out

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
            self._counts.clear()
            self._last_log = 0.0

    def due_for_log(self, now: float) -> bool:
        with self._lock:
            if now - self._last_log < LOG_INTERVAL_S:
                return False
            self._last_log = now
            return True


RESERVOIR = LatencyReservoir()


def slo_status(latency: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for group, target in SLO_P95_MS.items():
        sample = latency.get(group)
        if not sample or not sample.get("window"):
            out[group] = {"target_p95_ms": target, "status": "no_data"}
            continue
        out[group] = {
            "target_p95_ms": target,
            "p95_ms": sample["p95_ms"],
            "status": "pass" if sample["p95_ms"] <= target else "fail",
        }
    return out


def runtime_snapshot(db: Any) -> Dict[str, Any]:
    latency = RESERVOIR.snapshot()
    try:
        queue = dict(db.write_queue_stats())
    except Exception:  # noqa: BLE001
        queue = {}
    return {
        "uptime_s": round(time.time() - _STARTED_AT, 1),
        "write_queue": queue,
        "latency": latency,
        "slo": slo_status(latency),
    }


def maybe_log_runtime(db_factory: Any) -> None:
    """Emit the once-a-minute runtime line (never raises)."""
    now = time.time()
    if not RESERVOIR.due_for_log(now):
        return
    try:
        snap = runtime_snapshot(db_factory())
        latency = snap["latency"]
        logger.info(
            "runtime %s",
            json.dumps(
                {
                    "write_queue_depth": snap["write_queue"].get("queue_depth"),
                    "write_max_wait_s": snap["write_queue"].get("max_wait_s"),
                    "api_p95_ms": latency.get("api", {}).get("p95_ms"),
                    "library_query_p95_ms": latency.get("library_query", {}).get("p95_ms"),
                    "chat_p95_ms": latency.get("chat", {}).get("p95_ms"),
                },
                sort_keys=True,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.debug("runtime log line skipped", exc_info=True)


def probe_database(path: Path, *, timeout_s: float = READY_DB_TIMEOUT_S) -> str:
    """``ok`` when the database file opens read-only and answers within ``timeout_s``.

    Opens with ``mode=ro`` so a missing or renamed file is reported instead of
    silently created. Reads only ``sqlite_master``; never the library tables.
    Returns ``ok``, ``missing``, ``empty``, ``timeout``, or ``error``.
    """
    path = Path(path)
    if not path.is_file():
        return "missing"
    result: Dict[str, str] = {}

    def _run() -> None:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout_s)
            try:
                row = conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
            finally:
                conn.close()
            result["state"] = "ok" if row else "empty"
        except sqlite3.Error:
            result["state"] = "error"

    worker = threading.Thread(target=_run, name="ready-db-probe", daemon=True)
    worker.start()
    worker.join(timeout_s)
    return result.get("state", "timeout")
