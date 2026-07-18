"""Lightweight background task scheduler that runs during idle periods.

Idle = no active chat requests for N minutes (configurable, default 15).
Tasks run sequentially to avoid SQLite write contention, ordered by staleness.
Each task is interruptible — if a chat request arrives, the current task yields.

Architecture
~~~~~~~~~~~~
The scheduler lives entirely in-process as an asyncio background task started
from the FastAPI lifespan.  It maintains its own SQLite table
(``scheduled_tasks``) for persistence across restarts, and emits progress to
``jobs_state.json`` so the status dock shows activity.

Circuit Breaker / Watchdog
~~~~~~~~~~~~~~~~~~~~~~~~~~
Each task runs with a configurable timeout (default 5 minutes).  The timeout
is enforced via a deadline loop: the scheduler waits up to *timeout* seconds
for the task to finish.  If it hasn't finished, the scheduler checks whether
the task called ``heartbeat()`` since the last wait began.  If a heartbeat
arrived, the deadline resets and the scheduler waits another full timeout
window.  If no heartbeat arrived, the task is cancelled and logged as a
timeout failure.

Tasks receive a ``should_stop`` callback which doubles as a heartbeat — each
call to ``should_stop()`` records a heartbeat, so tasks that poll for
cooperative interruption automatically extend their timeout window.

A per-task failure counter tracks consecutive failures.  After
``QUARANTINE_THRESHOLD`` consecutive failures (default 3), the task is
**quarantined** — skipped on subsequent scheduler cycles until either:

- The configurable cooldown period (default 1 hour) elapses, or
- An admin manually resets the quarantine via the API.

Quarantine state is held in-memory and does not persist across restarts,
which is intentional: a restart is itself a recovery action.

No external dependencies — pure asyncio + SQLite.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from curatorx.config_store import Settings, load_merged_settings
from curatorx.library.db import Database
from curatorx.scheduler.autotune import (
    AUTOTUNE_TASKS,
    evaluate_autotune,
    resolve_batch_size,
)
from curatorx.scheduler.progress import progress_for_definition
from curatorx.scheduler.run_history import (
    aggregate_task_rate,
    append_task_run,
    ensure_run_history_table,
    extract_items_processed,
    list_task_runs,
)
from curatorx.scheduler.run_log import TaskRunLogStore
from curatorx.scheduler.run_outcome import build_run_summary

logger = logging.getLogger(__name__)

DEFAULT_IDLE_THRESHOLD_MINUTES = 15
SCHEDULER_POLL_SECONDS = 30
SCHEDULER_INITIAL_DELAY_SECONDS = 60
DEFAULT_TASK_TIMEOUT_SECONDS = 300  # 5 minutes
QUARANTINE_THRESHOLD = 3
DEFAULT_QUARANTINE_COOLDOWN_SECONDS = 3600  # 1 hour


@dataclass
class TaskDefinition:
    """Blueprint for a schedulable background task."""

    name: str
    run_interval_seconds: int
    enabled: bool = True
    timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS
    run_fn: Optional[
        Callable[[Database, Settings, Callable[[], bool]], Awaitable[Dict[str, Any]]]
    ] = None
    # Owner-facing copy shown when the task is selected in Admin → Scheduled Tasks.
    description: str = ""
    # When set, this task trickles through a backlog/library at ``items_per_cycle``
    # items per run. Used with ``progress_scope`` to estimate wall-clock catch-up.
    items_per_cycle: Optional[int] = None
    # How to count remaining work for ETA:
    #   metadata_backlog | llm_logline_backlog | embeddings_pending | embeddings_pass
    progress_scope: Optional[str] = None


@dataclass
class TaskState:
    """Runtime state of a registered task, persisted in SQLite."""

    name: str
    last_run_at: Optional[float] = None
    enabled: bool = True
    run_interval_seconds: int = 3600
    last_duration_ms: Optional[int] = None
    last_status: Optional[str] = None
    last_outcome_reason: Optional[str] = None
    last_run_summary: Optional[Dict[str, Any]] = None
    items_per_cycle: Optional[int] = None


@dataclass
class QuarantineInfo:
    """In-memory quarantine state for a task that has failed repeatedly."""

    consecutive_failures: int = 0
    last_error: str = ""
    quarantined_at: Optional[float] = None
    cooldown_seconds: int = DEFAULT_QUARANTINE_COOLDOWN_SECONDS

    @property
    def is_quarantined(self) -> bool:
        if self.quarantined_at is None:
            return False
        elapsed = time.time() - self.quarantined_at
        if elapsed >= self.cooldown_seconds:
            self.release()
            return False
        return True

    @property
    def remaining_seconds(self) -> Optional[float]:
        if self.quarantined_at is None:
            return None
        remaining = self.cooldown_seconds - (time.time() - self.quarantined_at)
        return max(0.0, remaining)

    def record_failure(self, error: str) -> bool:
        """Record a failure. Returns True if the task is now quarantined."""
        self.consecutive_failures += 1
        self.last_error = error
        if self.consecutive_failures >= QUARANTINE_THRESHOLD and self.quarantined_at is None:
            self.quarantined_at = time.time()
            return True
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_error = ""
        self.quarantined_at = None

    def release(self) -> None:
        """Manually clear quarantine (admin reset or cooldown expiry)."""
        self.consecutive_failures = 0
        self.last_error = ""
        self.quarantined_at = None


class _HeartbeatHandle:
    """Liveness signal that tasks use to extend the timeout deadline.

    The scheduler enforces a per-task timeout via a deadline loop.  Each
    iteration of the loop snapshots ``last_heartbeat`` before waiting.  If the
    wait expires and ``last_heartbeat`` has advanced, the deadline resets for
    another full timeout window.  If it hasn't advanced, the task is cancelled.

    Long-running tasks (e.g. batch embedding) should call ``heartbeat()``
    between batches.  The ``should_stop`` callback passed to tasks also calls
    ``heartbeat()`` automatically, so tasks that poll ``should_stop()``
    regularly will keep the deadline alive without extra effort.
    """

    def __init__(self) -> None:
        self.last_heartbeat: float = time.time()

    def heartbeat(self) -> None:
        self.last_heartbeat = time.time()


class IdleScheduler:
    """Runs registered background tasks during idle periods.

    Idle is defined as "no chat request in the last *idle_threshold_minutes*
    minutes."  When idle, tasks are executed sequentially in staleness order
    (most overdue first).  Each task receives a *should_stop* callback that
    returns ``True`` when a chat request arrives or the app is shutting down,
    allowing cooperative interruption between batches.

    A circuit-breaker quarantines tasks that fail repeatedly, and a per-task
    timeout watchdog cancels tasks that hang.
    """

    def __init__(
        self,
        db: Database,
        data_dir: Path,
        *,
        idle_threshold_minutes: int = DEFAULT_IDLE_THRESHOLD_MINUTES,
    ) -> None:
        self._db = db
        self._data_dir = data_dir
        self._idle_threshold = idle_threshold_minutes * 60
        self._last_activity: float = time.time()
        self._definitions: Dict[str, TaskDefinition] = {}
        self._quarantine: Dict[str, QuarantineInfo] = {}
        self._shutdown = False
        self._running_task: Optional[str] = None
        self._running_started_at: Optional[float] = None
        self._pending_trigger: Optional[str] = None
        self._manual_tasks: set[asyncio.Task[Any]] = set()
        self._run_log = TaskRunLogStore()
        self._task: Optional[asyncio.Task[None]] = None
        self._ensure_table()

    def _busy_task_name(self) -> Optional[str]:
        return self._running_task or self._pending_trigger

    @property
    def run_log(self) -> TaskRunLogStore:
        return self._run_log

    # -- Public API ----------------------------------------------------------

    def register(self, defn: TaskDefinition) -> None:
        """Register a task definition and upsert its persistent state row."""
        self._definitions[defn.name] = defn
        if defn.name not in self._quarantine:
            self._quarantine[defn.name] = QuarantineInfo()
        self._upsert_task_state(defn)

    def record_activity(self) -> None:
        """Called on every chat request to reset the idle timer."""
        self._last_activity = time.time()

    def is_idle(self) -> bool:
        return (time.time() - self._last_activity) >= self._idle_threshold

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the scheduler background loop as an asyncio task."""
        if self._task is not None:
            return
        _loop = loop or asyncio.get_event_loop()
        self._task = _loop.create_task(self._run_loop(), name="idle-scheduler")
        logger.info(
            "IdleScheduler started (idle_threshold=%dm, tasks=%d)",
            self._idle_threshold // 60,
            len(self._definitions),
        )

    def stop(self) -> None:
        """Signal the scheduler to shut down gracefully."""
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("IdleScheduler shutdown requested")

    def should_stop(self) -> bool:
        """Cooperative stop signal for running tasks."""
        return self._shutdown or not self.is_idle()

    def get_task_states(self) -> List[Dict[str, Any]]:
        """Return all task states for the admin API, including quarantine status."""
        states = self._load_all_states()
        result: List[Dict[str, Any]] = []
        now = time.time()
        for state in states:
            defn = self._definitions.get(state.name)
            interval = state.run_interval_seconds
            next_run: Optional[float] = None
            if state.last_run_at is not None:
                next_run = state.last_run_at + interval
            qinfo = self._quarantine.get(state.name)
            quarantine_dict: Dict[str, Any] = {
                "is_quarantined": False,
                "consecutive_failures": 0,
                "last_error": "",
                "remaining_seconds": None,
            }
            if qinfo is not None:
                quarantine_dict = {
                    "is_quarantined": qinfo.is_quarantined,
                    "consecutive_failures": qinfo.consecutive_failures,
                    "last_error": qinfo.last_error,
                    "remaining_seconds": qinfo.remaining_seconds,
                }
            running = self._running_task == state.name
            last_meta = self._run_log.last_run(state.name) or {}
            last_status = state.last_status
            last_duration_ms = state.last_duration_ms
            last_run_at = state.last_run_at
            last_outcome_reason = state.last_outcome_reason
            last_run_summary = state.last_run_summary
            last_started_at = last_meta.get("started_at")
            finished_at = last_meta.get("finished_at")
            if finished_at is not None and (
                last_run_at is None or float(finished_at) >= float(last_run_at)
            ):
                meta_status = last_meta.get("status")
                if meta_status and not (
                    last_status
                    and last_status != meta_status
                    and last_status.startswith(meta_status)
                ):
                    # Keep a more detailed persisted status (e.g. "error: <detail>")
                    # instead of clobbering it with the run-log's canonical code.
                    last_status = meta_status
                if last_meta.get("duration_ms") is not None:
                    last_duration_ms = last_meta.get("duration_ms")
                last_run_at = float(finished_at)
                last_outcome_reason = last_meta.get("outcome_reason") or last_outcome_reason
                if last_meta.get("summary_line") or last_meta.get("metrics"):
                    last_run_summary = {
                        "summary_line": last_meta.get("summary_line"),
                        "metrics": last_meta.get("metrics") or {},
                        "outcome_reason": last_meta.get("outcome_reason"),
                        "status": last_meta.get("status"),
                    }
            if last_started_at is None and last_run_at is not None and last_duration_ms is not None:
                last_started_at = last_run_at - (last_duration_ms / 1000.0)
            if running and self._running_started_at is not None:
                last_started_at = self._running_started_at
            if last_run_summary is None and state.last_run_summary:
                last_run_summary = state.last_run_summary
            effective_batch = state.items_per_cycle
            if effective_batch is None and defn is not None:
                effective_batch = defn.items_per_cycle
            rate = None
            measured_iph: Optional[float] = None
            if defn is not None and defn.items_per_cycle is not None:
                rate = aggregate_task_rate(
                    self._db,
                    state.name,
                    interval_seconds=interval,
                )
                raw_iph = rate.get("items_per_hour")
                if raw_iph is not None:
                    try:
                        measured_iph = float(raw_iph)
                    except (TypeError, ValueError):
                        measured_iph = None
            progress = progress_for_definition(
                self._db,
                defn,
                interval_seconds=interval,
                items_per_cycle=effective_batch,
                items_per_hour=measured_iph,
            )
            result.append(
                {
                    "name": state.name,
                    "id": state.name,
                    "enabled": state.enabled,
                    "run_interval_seconds": interval,
                    "default_run_interval_seconds": (
                        defn.run_interval_seconds if defn is not None else interval
                    ),
                    "description": (defn.description if defn is not None else "") or "",
                    "items_per_cycle": effective_batch,
                    "default_items_per_cycle": (
                        defn.items_per_cycle if defn is not None else None
                    ),
                    "autotune_enabled": (
                        defn is not None and defn.name in AUTOTUNE_TASKS
                    ),
                    "progress_scope": defn.progress_scope if defn is not None else None,
                    "progress": progress,
                    "rate": rate,
                    "last_run_at": last_run_at,
                    "last_started_at": last_started_at,
                    "last_finished_at": last_run_at,
                    "next_run_at": next_run,
                    "last_duration_ms": last_duration_ms,
                    "last_status": last_status,
                    "last_outcome_reason": last_outcome_reason,
                    "last_run_summary": last_run_summary,
                    "last_run_summary_line": (
                        (last_run_summary or {}).get("summary_line") if last_run_summary else None
                    ),
                    "registered": defn is not None,
                    "running": running,
                    "current_run": self._run_log.current_run(state.name) if running else None,
                    "overdue": (
                        state.enabled
                        and (
                            state.last_run_at is None
                            or (now - state.last_run_at) >= interval
                        )
                    ),
                    "quarantine": quarantine_dict,
                }
            )
        return result

    def update_task(
        self,
        name: str,
        *,
        enabled: Optional[bool] = None,
        run_interval_seconds: Optional[int] = None,
        items_per_cycle: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Enable/disable a task or adjust its interval/batch. Returns updated state."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            updates: List[str] = []
            params: List[Any] = []
            if enabled is not None:
                updates.append("enabled = ?")
                params.append(1 if enabled else 0)
            if run_interval_seconds is not None:
                updates.append("run_interval_seconds = ?")
                params.append(max(60, run_interval_seconds))
            if items_per_cycle is not None:
                updates.append("items_per_cycle = ?")
                params.append(max(1, int(items_per_cycle)))
            if updates:
                params.append(name)
                conn.execute(
                    f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE name = ?",
                    params,
                )
        for item in self.get_task_states():
            if item["name"] == name:
                return item
        return None

    def get_task_history(
        self,
        name: str,
        *,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return durable run history for a task (DB source of truth)."""
        if name not in self._definitions and name not in {
            s.name for s in self._load_all_states()
        }:
            return {"error": f"Task '{name}' not found"}
        runs = list_task_runs(self._db, name, limit=limit)
        return {"name": name, "runs": runs, "count": len(runs)}

    def get_task_rate(
        self,
        name: str,
        *,
        lookback_hours: int = 72,
    ) -> Dict[str, Any]:
        """Return aggregate measured rate for a task."""
        if name not in self._definitions and name not in {
            s.name for s in self._load_all_states()
        }:
            return {"error": f"Task '{name}' not found"}
        interval = None
        for state in self._load_all_states():
            if state.name == name:
                interval = state.run_interval_seconds
                break
        return aggregate_task_rate(
            self._db,
            name,
            lookback_hours=lookback_hours,
            interval_seconds=interval,
        )

    async def trigger_task(self, name: str) -> Dict[str, Any]:
        """Manually trigger a task regardless of idle state or schedule."""
        defn = self._definitions.get(name)
        if defn is None or defn.run_fn is None:
            return {"error": f"Task '{name}' not found or has no run function"}
        busy = self._busy_task_name()
        if busy is not None:
            return {
                "error": f"Task '{busy}' is already running",
                "status": "busy",
                "running": busy,
            }
        return await self._execute_task(defn, force=True)

    def trigger_task_background(self, name: str) -> Dict[str, Any]:
        """Start a manual task run without awaiting completion (for live monitoring)."""
        defn = self._definitions.get(name)
        if defn is None or defn.run_fn is None:
            return {"error": f"Task '{name}' not found or has no run function"}
        busy = self._busy_task_name()
        if busy is not None:
            return {
                "error": f"Task '{busy}' is already running",
                "status": "busy",
                "running": busy,
            }

        self._pending_trigger = name

        async def _runner() -> None:
            try:
                await self._execute_task(defn, force=True)
            except Exception:
                logger.exception("Background trigger for task '%s' crashed", name)
            finally:
                if self._pending_trigger == name:
                    self._pending_trigger = None

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._pending_trigger = None
            return {"error": "No event loop available to start background task"}

        task = loop.create_task(_runner(), name=f"manual-task-{name}")
        self._manual_tasks.add(task)
        task.add_done_callback(self._manual_tasks.discard)
        return {
            "name": name,
            "status": "started",
            "accepted": True,
            "running": name,
        }

    def get_task_run_log(
        self,
        name: Optional[str] = None,
        *,
        after_seq: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """Return buffered run events for a task (or all tasks when name is None)."""
        if name is not None and name not in self._definitions and name not in {
            s.name for s in self._load_all_states()
        }:
            return {"error": f"Task '{name}' not found"}
        payload = self._run_log.get_events(task=name, after_seq=after_seq, limit=limit)
        payload["running"] = self._running_task
        payload["idle"] = self.is_idle()
        return payload

    def reset_quarantine(self, name: str) -> Optional[Dict[str, Any]]:
        """Clear quarantine state for a task, allowing it to run again.

        Returns the updated quarantine info dict, or None if the task doesn't exist.
        """
        if name not in self._definitions:
            return None
        qinfo = self._quarantine.get(name)
        if qinfo is None:
            qinfo = QuarantineInfo()
            self._quarantine[name] = qinfo
        else:
            qinfo.release()
        logger.info("Quarantine reset for task '%s'", name)
        return {
            "name": name,
            "is_quarantined": qinfo.is_quarantined,
            "consecutive_failures": qinfo.consecutive_failures,
            "last_error": qinfo.last_error,
        }

    # -- Internal ------------------------------------------------------------

    def _ensure_table(self) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    name TEXT PRIMARY KEY,
                    last_run_at TEXT,
                    enabled INTEGER DEFAULT 1,
                    run_interval_seconds INTEGER NOT NULL,
                    last_duration_ms INTEGER,
                    last_status TEXT,
                    last_outcome_reason TEXT,
                    last_run_summary TEXT,
                    items_per_cycle INTEGER
                )
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(scheduled_tasks)").fetchall()
            }
            if "last_outcome_reason" not in columns:
                conn.execute(
                    "ALTER TABLE scheduled_tasks ADD COLUMN last_outcome_reason TEXT"
                )
            if "last_run_summary" not in columns:
                conn.execute(
                    "ALTER TABLE scheduled_tasks ADD COLUMN last_run_summary TEXT"
                )
            if "items_per_cycle" not in columns:
                conn.execute(
                    "ALTER TABLE scheduled_tasks ADD COLUMN items_per_cycle INTEGER"
                )
            ensure_run_history_table(conn)

    def _upsert_task_state(self, defn: TaskDefinition) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_tasks (name, enabled, run_interval_seconds, items_per_cycle)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    run_interval_seconds = CASE
                        WHEN scheduled_tasks.run_interval_seconds != excluded.run_interval_seconds
                             AND scheduled_tasks.last_run_at IS NULL
                        THEN excluded.run_interval_seconds
                        ELSE scheduled_tasks.run_interval_seconds
                    END,
                    items_per_cycle = CASE
                        WHEN scheduled_tasks.items_per_cycle IS NULL
                             AND excluded.items_per_cycle IS NOT NULL
                        THEN excluded.items_per_cycle
                        ELSE scheduled_tasks.items_per_cycle
                    END
                """,
                (
                    defn.name,
                    1 if defn.enabled else 0,
                    defn.run_interval_seconds,
                    defn.items_per_cycle,
                ),
            )

    def _load_all_states(self) -> List[TaskState]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY name"
            ).fetchall()
            return [self._row_to_state(row) for row in rows]

    def _row_to_state(self, row: Any) -> TaskState:
        last_run_at: Optional[float] = None
        raw = row["last_run_at"]
        if raw is not None:
            try:
                last_run_at = float(raw)
            except (ValueError, TypeError):
                pass
        last_run_summary: Optional[Dict[str, Any]] = None
        raw_summary = row["last_run_summary"] if "last_run_summary" in row.keys() else None
        if raw_summary:
            try:
                parsed = json.loads(str(raw_summary))
                if isinstance(parsed, dict):
                    last_run_summary = parsed
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        items_per_cycle: Optional[int] = None
        raw_batch = row["items_per_cycle"] if "items_per_cycle" in row.keys() else None
        if raw_batch is not None:
            try:
                items_per_cycle = int(raw_batch)
            except (TypeError, ValueError):
                items_per_cycle = None
        return TaskState(
            name=str(row["name"]),
            last_run_at=last_run_at,
            enabled=bool(row["enabled"]),
            run_interval_seconds=int(row["run_interval_seconds"]),
            last_duration_ms=int(row["last_duration_ms"]) if row["last_duration_ms"] is not None else None,
            last_status=str(row["last_status"]) if row["last_status"] is not None else None,
            last_outcome_reason=(
                str(row["last_outcome_reason"]) if row["last_outcome_reason"] is not None else None
            ),
            last_run_summary=last_run_summary,
            items_per_cycle=items_per_cycle,
        )

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        state = self._row_to_state(row)
        now = time.time()
        next_run = (state.last_run_at + state.run_interval_seconds) if state.last_run_at else None
        return {
            "name": state.name,
            "enabled": state.enabled,
            "run_interval_seconds": state.run_interval_seconds,
            "last_run_at": state.last_run_at,
            "next_run_at": next_run,
            "last_duration_ms": state.last_duration_ms,
            "last_status": state.last_status,
            "running": self._running_task == state.name,
            "overdue": (
                state.enabled
                and (state.last_run_at is None or (now - state.last_run_at) >= state.run_interval_seconds)
            ),
        }

    def _stale_tasks(self) -> List[TaskDefinition]:
        """Return enabled, non-quarantined tasks overdue for execution, sorted most-overdue first."""
        now = time.time()
        states = {s.name: s for s in self._load_all_states()}
        candidates: List[tuple[float, TaskDefinition]] = []

        for defn in self._definitions.values():
            if defn.run_fn is None:
                continue
            state = states.get(defn.name)
            if state is None or not state.enabled:
                continue
            qinfo = self._quarantine.get(defn.name)
            if qinfo is not None and qinfo.is_quarantined:
                continue
            if state.last_run_at is None:
                staleness = float("inf")
            else:
                elapsed = now - state.last_run_at
                if elapsed < state.run_interval_seconds:
                    continue
                staleness = elapsed - state.run_interval_seconds
            candidates.append((staleness, defn))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [defn for _, defn in candidates]

    async def _run_with_deadline(
        self,
        defn: TaskDefinition,
        hb: _HeartbeatHandle,
        run_coro: Awaitable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run a task with a deadline that resets on each heartbeat.

        Instead of a single ``asyncio.wait_for`` (whose timeout is fixed once
        set), this loops: each iteration snapshots ``hb.last_heartbeat``, then
        waits up to *timeout* seconds for the shielded task.  On timeout, if a
        heartbeat arrived since the snapshot, the loop continues with a fresh
        deadline.  Otherwise the task is cancelled for real.

        ``asyncio.shield`` prevents ``wait_for`` from cancelling the underlying
        task when only the timeout fires — we need the task alive so we can
        re-enter the wait if a heartbeat arrived.
        """
        task = asyncio.ensure_future(run_coro)
        timeout = defn.timeout_seconds

        while not task.done():
            last_hb = hb.last_heartbeat
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                return task.result()
            except asyncio.TimeoutError:
                if hb.last_heartbeat > last_hb:
                    continue
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                raise asyncio.TimeoutError()

        return task.result()

    async def _execute_task(
        self,
        defn: TaskDefinition,
        *,
        force: bool = False,
        trigger: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a single task with timeout watchdog and failure tracking.

        The task runs inside :meth:`_run_with_deadline` which enforces a
        per-heartbeat sliding timeout.  A :class:`_HeartbeatHandle` is threaded
        through the ``should_stop`` callback: every call to ``should_stop()``
        records a heartbeat, so tasks that poll for cooperative interruption
        automatically extend their deadline.

        On success the failure counter resets.  On failure the counter increments;
        after ``QUARANTINE_THRESHOLD`` consecutive failures the task is quarantined.
        """
        assert defn.run_fn is not None
        if self._running_task is not None and self._running_task != defn.name:
            return {
                "name": defn.name,
                "status": "busy",
                "error": f"Task '{self._running_task}' is already running",
                "running": self._running_task,
            }

        self._running_task = defn.name
        self._running_started_at = time.time()
        if trigger is None:
            trigger = "manual" if force else "schedule"
        run_id = self._run_log.start_run(defn.name, trigger=trigger)
        emitter_token = self._run_log.bind_emitter(defn.name)
        trigger_label = f" ({trigger})" if trigger != "schedule" else ""
        logger.info("Scheduler: starting task '%s'%s", defn.name, trigger_label)
        self._emit_progress(defn.name, "running")

        hb = _HeartbeatHandle()
        qinfo = self._quarantine.setdefault(defn.name, QuarantineInfo())
        start = time.time()
        try:
            settings = load_merged_settings(self._data_dir)

            def stop_check() -> bool:
                if self._shutdown:
                    return True
                if not force and not self.is_idle():
                    return True
                return False

            async def _run_with_heartbeat() -> Dict[str, Any]:
                assert defn.run_fn is not None

                def stop_with_heartbeat() -> bool:
                    """Check whether the task should stop, and record a heartbeat.

                    Calling ``should_stop()`` is proof of liveness — the task is
                    still actively executing and checking for interruption — so
                    each call extends the timeout deadline automatically.
                    """
                    hb.heartbeat()
                    return stop_check()

                return await defn.run_fn(self._db, settings, stop_with_heartbeat)

            result = await self._run_with_deadline(defn, hb, _run_with_heartbeat())
            elapsed_ms = int((time.time() - start) * 1000)

            status = result.get("status", "completed") if isinstance(result, dict) else "completed"
            result_dict = result if isinstance(result, dict) else None
            run_summary = build_run_summary(status, result=result_dict)
            outcome_reason = run_summary.get("outcome_reason")
            qinfo.record_success()
            self._finalize_run(
                defn,
                started_at=start,
                duration_ms=elapsed_ms,
                status=status,
                trigger=trigger,
                outcome_reason=outcome_reason,
                run_summary=run_summary,
                result=result_dict,
            )
            self._run_log.end_run(
                defn.name,
                status=status,
                duration_ms=elapsed_ms,
                result=result_dict,
            )
            self._emit_progress(defn.name, status)
            logger.info(
                "Scheduler: task '%s' finished in %dms — %s",
                defn.name,
                elapsed_ms,
                status,
            )
            return {
                "name": defn.name,
                "status": status,
                "duration_ms": elapsed_ms,
                "run_id": run_id,
                **(result or {}),
            }

        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() - start) * 1000)
            error_msg = f"timed out after {defn.timeout_seconds}s"
            logger.error(
                "Scheduler: task '%s' %s (elapsed %dms)",
                defn.name,
                error_msg,
                elapsed_ms,
            )
            now_quarantined = qinfo.record_failure(error_msg)
            if now_quarantined:
                logger.warning(
                    "Task '%s' quarantined after %d consecutive failures: %s",
                    defn.name,
                    qinfo.consecutive_failures,
                    error_msg,
                )
            error_summary = build_run_summary("error", error=error_msg)
            self._finalize_run(
                defn,
                started_at=start,
                duration_ms=elapsed_ms,
                status=f"error: {error_msg}",
                trigger=trigger,
                outcome_reason=error_msg,
                run_summary=error_summary,
                error=error_msg,
                apply_autotune=False,
            )
            self._run_log.end_run(
                defn.name,
                status="error",
                duration_ms=elapsed_ms,
                error=error_msg,
            )
            self._emit_progress(defn.name, "error")
            return {
                "name": defn.name,
                "status": "error",
                "duration_ms": elapsed_ms,
                "error": error_msg,
                "run_id": run_id,
            }

        except Exception as exc:
            elapsed_ms = int((time.time() - start) * 1000)
            error_msg = str(exc)
            logger.exception("Scheduler: task '%s' failed after %dms", defn.name, elapsed_ms)
            now_quarantined = qinfo.record_failure(error_msg)
            if now_quarantined:
                logger.warning(
                    "Task '%s' quarantined after %d consecutive failures: %s",
                    defn.name,
                    qinfo.consecutive_failures,
                    error_msg,
                )
            error_summary = build_run_summary("error", error=error_msg)
            self._finalize_run(
                defn,
                started_at=start,
                duration_ms=elapsed_ms,
                status=f"error: {exc}",
                trigger=trigger,
                outcome_reason=error_msg,
                run_summary=error_summary,
                error=error_msg,
                apply_autotune=False,
            )
            self._run_log.end_run(
                defn.name,
                status="error",
                duration_ms=elapsed_ms,
                error=error_msg,
            )
            self._emit_progress(defn.name, "error")
            return {
                "name": defn.name,
                "status": "error",
                "duration_ms": elapsed_ms,
                "error": error_msg,
                "run_id": run_id,
            }
        finally:
            self._run_log.reset_emitter(emitter_token)
            self._running_task = None
            self._running_started_at = None

    def _finalize_run(
        self,
        defn: TaskDefinition,
        *,
        started_at: float,
        duration_ms: int,
        status: str,
        trigger: str,
        outcome_reason: Optional[str] = None,
        run_summary: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        apply_autotune: bool = True,
    ) -> None:
        """Persist last-run fields, append durable history, optionally auto-tune."""
        finished_at = time.time()
        metrics = dict((run_summary or {}).get("metrics") or {})
        items_processed = extract_items_processed(result)
        if items_processed is None and "items_processed" in metrics:
            try:
                items_processed = int(metrics["items_processed"])
            except (TypeError, ValueError):
                pass

        # Auto-tune before writing history so the decision is included in metrics.
        if apply_autotune and defn.name in AUTOTUNE_TASKS:
            states = {s.name: s for s in self._load_all_states()}
            state = states.get(defn.name)
            current_batch = resolve_batch_size(
                self._db,
                defn.name,
                defn.items_per_cycle or 1,
            )
            current_interval = (
                state.run_interval_seconds if state is not None else defn.run_interval_seconds
            )
            remaining = None
            has_more = bool(result.get("has_more")) if isinstance(result, dict) else False
            if defn.progress_scope:
                from curatorx.scheduler.progress import count_remaining

                remaining = count_remaining(self._db, defn.progress_scope)
            decision = evaluate_autotune(
                name=defn.name,
                status=str(result.get("status") if isinstance(result, dict) else status),
                duration_ms=duration_ms,
                timeout_seconds=defn.timeout_seconds,
                items_per_cycle=current_batch,
                interval_seconds=current_interval,
                items_processed=items_processed,
                remaining_items=remaining,
                has_more=has_more,
            )
            metrics.update(decision.as_metrics())
            if decision.changed:
                updates: Dict[str, Any] = {}
                if decision.items_per_cycle is not None:
                    updates["items_per_cycle"] = decision.items_per_cycle
                if decision.run_interval_seconds is not None:
                    updates["run_interval_seconds"] = decision.run_interval_seconds
                if updates:
                    self.update_task(defn.name, **updates)
                    logger.info(
                        "Scheduler auto-tune '%s': batch %s→%s interval %s→%s (%s)",
                        defn.name,
                        current_batch,
                        decision.items_per_cycle,
                        current_interval,
                        decision.run_interval_seconds,
                        ", ".join(decision.reasons or []),
                    )

        if run_summary is not None:
            run_summary = {**run_summary, "metrics": metrics}

        self._record_run(
            defn.name,
            duration_ms,
            status,
            outcome_reason=outcome_reason,
            run_summary=run_summary,
        )
        try:
            append_task_run(
                self._db,
                name=defn.name,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                status=status,
                trigger=trigger,
                outcome_reason=outcome_reason,
                metrics=metrics,
                items_processed=items_processed,
                error=error,
            )
        except Exception:
            logger.exception("Failed to persist scheduled_task_runs for '%s'", defn.name)

    def _record_run(
        self,
        name: str,
        duration_ms: int,
        status: str,
        *,
        outcome_reason: Optional[str] = None,
        run_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        summary_payload: Optional[str] = None
        if isinstance(run_summary, dict) and run_summary.get("summary_line"):
            summary_payload = json.dumps(
                {
                    "summary_line": run_summary.get("summary_line"),
                    "metrics": run_summary.get("metrics") or {},
                    "outcome_reason": run_summary.get("outcome_reason"),
                    "status": run_summary.get("status") or status,
                }
            )
        with self._db.connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = ?, last_duration_ms = ?, last_status = ?,
                    last_outcome_reason = ?, last_run_summary = ?
                WHERE name = ?
                """,
                (
                    str(time.time()),
                    duration_ms,
                    status[:200],
                    outcome_reason[:500] if outcome_reason else None,
                    summary_payload,
                    name,
                ),
            )

    def _emit_progress(self, task_name: str, status: str) -> None:
        """Write scheduler activity into jobs_state.json so the UI status dock shows it."""
        jobs_path = self._data_dir / "jobs_state.json"
        try:
            existing: Dict[str, Any] = {}
            if jobs_path.exists():
                existing = json.loads(jobs_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
            existing["scheduler"] = {
                "task": task_name,
                "status": status,
                "updated_at": time.time(),
            }
            tmp = jobs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            tmp.replace(jobs_path)
        except OSError:
            pass

    async def _run_loop(self) -> None:
        """Main scheduler loop — poll for idle and run stale tasks."""
        await asyncio.sleep(SCHEDULER_INITIAL_DELAY_SECONDS)
        logger.info("IdleScheduler: entering main loop")

        try:
            from curatorx.scheduler.bootstrap import run_idle_bootstrap

            await run_idle_bootstrap(self)
        except Exception:  # noqa: BLE001
            logger.exception("IdleScheduler: first-start bootstrap failed (continuing)")

        while not self._shutdown:
            try:
                if self.is_idle():
                    stale = self._stale_tasks()
                    for defn in stale:
                        if self._shutdown or not self.is_idle():
                            break
                        await self._execute_task(defn)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("IdleScheduler: loop iteration error")

            try:
                await asyncio.sleep(SCHEDULER_POLL_SECONDS)
            except asyncio.CancelledError:
                break

        logger.info("IdleScheduler: loop exited")
