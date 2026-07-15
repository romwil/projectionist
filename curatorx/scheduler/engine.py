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
Each task runs with a configurable timeout (default 5 minutes).  If a task
hangs beyond its timeout, it is cancelled and logged as a timeout failure.
Tasks can call ``heartbeat()`` on the provided callback during long operations
to reset the timeout window.

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


@dataclass
class TaskState:
    """Runtime state of a registered task, persisted in SQLite."""

    name: str
    last_run_at: Optional[float] = None
    enabled: bool = True
    run_interval_seconds: int = 3600
    last_duration_ms: Optional[int] = None
    last_status: Optional[str] = None


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
    """Passed to tasks so they can call ``heartbeat()`` to reset the timeout window.

    Long-running tasks (e.g. batch embedding) should call this between batches
    to signal liveness without requiring the entire task to complete within a
    single timeout window.
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
        self._task: Optional[asyncio.Task[None]] = None
        self._ensure_table()

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
            result.append(
                {
                    "name": state.name,
                    "enabled": state.enabled,
                    "run_interval_seconds": interval,
                    "last_run_at": state.last_run_at,
                    "next_run_at": next_run,
                    "last_duration_ms": state.last_duration_ms,
                    "last_status": state.last_status,
                    "registered": defn is not None,
                    "running": self._running_task == state.name,
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
    ) -> Optional[Dict[str, Any]]:
        """Enable/disable a task or adjust its interval. Returns updated state."""
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
            if not updates:
                return self._row_to_dict(row)
            params.append(name)
            conn.execute(
                f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE name = ?",
                params,
            )
            updated = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE name = ?", (name,)
            ).fetchone()
            return self._row_to_dict(updated) if updated else None

    async def trigger_task(self, name: str) -> Dict[str, Any]:
        """Manually trigger a task regardless of idle state or schedule."""
        defn = self._definitions.get(name)
        if defn is None or defn.run_fn is None:
            return {"error": f"Task '{name}' not found or has no run function"}
        return await self._execute_task(defn, force=True)

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
                    last_status TEXT
                )
                """
            )

    def _upsert_task_state(self, defn: TaskDefinition) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_tasks (name, enabled, run_interval_seconds)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    run_interval_seconds = CASE
                        WHEN scheduled_tasks.run_interval_seconds != excluded.run_interval_seconds
                             AND scheduled_tasks.last_run_at IS NULL
                        THEN excluded.run_interval_seconds
                        ELSE scheduled_tasks.run_interval_seconds
                    END
                """,
                (defn.name, 1 if defn.enabled else 0, defn.run_interval_seconds),
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
        return TaskState(
            name=str(row["name"]),
            last_run_at=last_run_at,
            enabled=bool(row["enabled"]),
            run_interval_seconds=int(row["run_interval_seconds"]),
            last_duration_ms=int(row["last_duration_ms"]) if row["last_duration_ms"] is not None else None,
            last_status=str(row["last_status"]) if row["last_status"] is not None else None,
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

    async def _execute_task(
        self, defn: TaskDefinition, *, force: bool = False
    ) -> Dict[str, Any]:
        """Run a single task with timeout watchdog and failure tracking.

        The task runs inside ``asyncio.wait_for`` with the configured timeout.
        A :class:`_HeartbeatHandle` is threaded through the ``should_stop``
        callback so tasks can call ``heartbeat()`` to reset the deadline.

        On success the failure counter resets.  On failure the counter increments;
        after ``QUARANTINE_THRESHOLD`` consecutive failures the task is quarantined.
        """
        assert defn.run_fn is not None
        self._running_task = defn.name
        logger.info("Scheduler: starting task '%s'%s", defn.name, " (manual)" if force else "")
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

            timeout = defn.timeout_seconds

            async def _run_with_heartbeat() -> Dict[str, Any]:
                """Execute the task, extending the deadline on each heartbeat."""
                assert defn.run_fn is not None

                def stop_with_heartbeat() -> bool:
                    hb.heartbeat()
                    return stop_check()

                return await defn.run_fn(self._db, settings, stop_with_heartbeat)

            result = await asyncio.wait_for(_run_with_heartbeat(), timeout=timeout)
            elapsed_ms = int((time.time() - start) * 1000)

            status = result.get("status", "completed") if isinstance(result, dict) else "completed"
            qinfo.record_success()
            self._record_run(defn.name, elapsed_ms, status)
            self._emit_progress(defn.name, "completed")
            logger.info(
                "Scheduler: task '%s' finished in %dms — %s",
                defn.name,
                elapsed_ms,
                status,
            )
            return {"name": defn.name, "status": status, "duration_ms": elapsed_ms, **(result or {})}

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
            self._record_run(defn.name, elapsed_ms, f"error: {error_msg}")
            self._emit_progress(defn.name, "error")
            return {"name": defn.name, "status": "error", "duration_ms": elapsed_ms, "error": error_msg}

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
            self._record_run(defn.name, elapsed_ms, f"error: {exc}")
            self._emit_progress(defn.name, "error")
            return {"name": defn.name, "status": "error", "duration_ms": elapsed_ms, "error": error_msg}
        finally:
            self._running_task = None

    def _record_run(self, name: str, duration_ms: int, status: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = ?, last_duration_ms = ?, last_status = ?
                WHERE name = ?
                """,
                (str(time.time()), duration_ms, status[:200], name),
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
