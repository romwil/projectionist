"""In-memory task-run event log for admin monitoring.

The idle scheduler records high-level start/end/error events automatically.
Individual tasks may also call :func:`emit_task_event` while a run is active
to surface progress lines without changing the ``run_fn`` signature.
"""

from __future__ import annotations

import contextvars
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional


MAX_EVENTS = 1000
MAX_EVENTS_PER_TASK = 400


@dataclass
class TaskRunEvent:
    seq: int
    ts: float
    task: str
    run_id: str
    level: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "task": self.task,
            "run_id": self.run_id,
            "level": self.level,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class CurrentRun:
    run_id: str
    task: str
    started_at: float
    status: str = "running"
    trigger: str = "schedule"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "started_at": self.started_at,
            "status": self.status,
            "trigger": self.trigger,
            "elapsed_ms": int((time.time() - self.started_at) * 1000),
        }


_emitter: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "curatorx_task_run_emitter", default=None
)


def emit_task_event(message: str, *, level: str = "info", **data: Any) -> None:
    """Record a progress/status line for the currently executing task (if any)."""
    emitter = _emitter.get()
    if emitter is None:
        return
    emitter(str(message), level=level, **data)


class TaskRunLogStore:
    """Thread-safe ring buffer of task-run events plus current-run metadata."""

    def __init__(self, *, max_events: int = MAX_EVENTS) -> None:
        self._max_events = max_events
        self._lock = threading.RLock()
        self._seq = 0
        self._events: Deque[TaskRunEvent] = deque(maxlen=max_events)
        self._current: Optional[CurrentRun] = None
        self._last_by_task: Dict[str, Dict[str, Any]] = {}

    def start_run(self, task: str, *, trigger: str = "schedule") -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._current = CurrentRun(
                run_id=run_id,
                task=task,
                started_at=time.time(),
                trigger=trigger,
            )
            self._append_unlocked(
                task,
                run_id,
                "status",
                f"Started ({trigger})",
                {"trigger": trigger},
            )
        return run_id

    def end_run(
        self,
        task: str,
        *,
        status: str,
        duration_ms: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            run_id = self._current.run_id if self._current and self._current.task == task else ""
            started_at = self._current.started_at if self._current and self._current.task == task else None
            finished_at = time.time()
            summary: Dict[str, Any] = {
                "status": status,
                "duration_ms": duration_ms,
            }
            if error:
                summary["error"] = error
            if isinstance(result, dict):
                # Keep payload small for the monitor UI.
                for key in ("status", "enriched", "errors", "caches_built", "found", "reason", "count", "processed"):
                    if key in result:
                        summary[key] = result[key]
            level = "error" if status == "error" or (error is not None) else "status"
            message = f"Finished — {status}"
            if error:
                message = f"Failed — {error}"
            self._append_unlocked(task, run_id or "unknown", level, message, summary)
            self._last_by_task[task] = {
                "run_id": run_id or None,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "duration_ms": duration_ms,
                "error": error,
                "summary": summary,
            }
            if self._current and self._current.task == task:
                self._current = None

    def emit(self, task: str, message: str, *, level: str = "info", **data: Any) -> None:
        with self._lock:
            run_id = self._current.run_id if self._current and self._current.task == task else ""
            self._append_unlocked(task, run_id or "unknown", level, message, dict(data) if data else {})

    def bind_emitter(self, task: str):
        """Return a context-manager token that routes emit_task_event to this store."""

        def _emit(message: str, *, level: str = "info", **data: Any) -> None:
            self.emit(task, message, level=level, **data)

        return _emitter.set(_emit)

    def reset_emitter(self, token) -> None:
        _emitter.reset(token)

    def current_run(self, task: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._current is None:
                return None
            if task is not None and self._current.task != task:
                return None
            return self._current.to_dict()

    def last_run(self, task: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            payload = self._last_by_task.get(task)
            return dict(payload) if payload else None

    def get_events(
        self,
        *,
        task: Optional[str] = None,
        after_seq: int = 0,
        limit: int = 200,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 500))
        after_seq = max(0, int(after_seq or 0))
        with self._lock:
            matched = [
                event
                for event in self._events
                if event.seq > after_seq and (task is None or event.task == task)
            ]
            if task is not None and len(matched) > MAX_EVENTS_PER_TASK:
                matched = matched[-MAX_EVENTS_PER_TASK:]
            sliced = matched[-limit:]
            latest_seq = self._seq
            current = self.current_run(task) if task else (self._current.to_dict() if self._current else None)
            last = self.last_run(task) if task else None
        return {
            "events": [event.to_dict() for event in sliced],
            "latest_seq": latest_seq,
            "current_run": current,
            "last_run": last,
        }

    def _append_unlocked(
        self,
        task: str,
        run_id: str,
        level: str,
        message: str,
        data: Dict[str, Any],
    ) -> None:
        self._seq += 1
        self._events.append(
            TaskRunEvent(
                seq=self._seq,
                ts=time.time(),
                task=task,
                run_id=run_id,
                level=level or "info",
                message=str(message)[:500],
                data=data or {},
            )
        )
