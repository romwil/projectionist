"""Shared admin batch-job telemetry.

Matches the Sonarr Find-all-missing snapshot contract: honest phases, live
queued/running/completed/failed, current item, last error, cancel remaining,
and never treats “all submitted” as 100% done.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

TERMINAL_PHASES = {"idle", "done", "searched", "cancelled", "error"}
QUEUED_ITEM_STATUSES = {"queued", "pending"}
RUNNING_ITEM_STATUSES = {"running", "started"}
COMPLETED_ITEM_STATUSES = {"completed", "skipped"}
FAILED_ITEM_STATUSES = {"failed"}
CANCELLED_ITEM_STATUSES = {"cancelled"}
TERMINAL_ITEM_STATUSES = COMPLETED_ITEM_STATUSES | FAILED_ITEM_STATUSES | CANCELLED_ITEM_STATUSES

RunFn = Callable[["AdminExecutionStore", threading.Event], Mapping[str, Any]]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def summarize_items(
    items: Sequence[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the Sonarr-style ``execution`` object from per-item rows."""
    queued = 0
    running = 0
    completed = 0
    failed = 0
    cancelled = 0
    current: Optional[Dict[str, Any]] = None
    last_error = ""
    last_completed_at = ""
    last_completed_ts = 0.0
    stamp_now = time.time() if now is None else float(now)
    rows = [dict(item) for item in items if isinstance(item, Mapping)]

    for row in rows:
        status = str(row.get("status") or "queued").strip().lower()
        if status in QUEUED_ITEM_STATUSES:
            queued += 1
        elif status in RUNNING_ITEM_STATUSES:
            running += 1
            if current is None:
                current = {
                    "id": row.get("id"),
                    "status": status,
                    "name": str(row.get("title") or row.get("name") or "Item"),
                    "message": str(
                        row.get("message") or row.get("title") or row.get("name") or "Working"
                    ),
                }
        elif status in COMPLETED_ITEM_STATUSES:
            completed += 1
        elif status in FAILED_ITEM_STATUSES:
            failed += 1
            err = str(row.get("error") or row.get("message") or "").strip()
            if err:
                last_error = err[:400]
        elif status in CANCELLED_ITEM_STATUSES:
            cancelled += 1
        ended = str(row.get("ended_at") or "")
        if ended and status in TERMINAL_ITEM_STATUSES:
            try:
                stamp = float(row.get("ended_ts") or 0)
            except (TypeError, ValueError):
                stamp = 0.0
            if stamp >= last_completed_ts:
                last_completed_ts = stamp
                last_completed_at = ended

    total = len(rows)
    finished = completed + failed + cancelled
    if total <= 0:
        percent = 0
    elif finished >= total and queued == 0 and running == 0:
        percent = 100
    else:
        percent = min(99, int(100 * finished / max(total, 1)))

    seconds_since: Optional[int] = None
    if last_completed_ts:
        seconds_since = max(0, int(stamp_now - last_completed_ts))

    return {
        "queued": queued,
        "running": running,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
        "pending_submit": queued,
        "total": total,
        "finished": finished,
        "percent": percent,
        "current": current,
        "last_error": last_error,
        "last_completed_at": last_completed_at,
        "seconds_since_last_completion": seconds_since,
        "kind": "item",
    }


def execution_message(summary: Mapping[str, Any], *, current_label: str = "") -> str:
    bits = [
        f"{_int(summary.get('queued'))} queued",
        f"{_int(summary.get('running'))} running",
        f"{_int(summary.get('completed'))} completed",
        f"{_int(summary.get('failed'))} failed",
    ]
    cancelled = _int(summary.get("cancelled"))
    if cancelled:
        bits.append(f"{cancelled} cancelled")
    current = summary.get("current") if isinstance(summary.get("current"), Mapping) else None
    label = current_label or (str(current.get("message") or current.get("name") or "") if current else "")
    if label:
        bits.append(label)
    return " · ".join(bits)


def finished_message(
    summary: Mapping[str, Any],
    *,
    noun: str = "item",
    action: str = "finished",
) -> str:
    completed = _int(summary.get("completed"))
    failed = _int(summary.get("failed"))
    cancelled = _int(summary.get("cancelled"))
    total = _int(summary.get("total"))
    plural = f"{noun}s" if total != 1 else noun
    if cancelled and completed == 0 and failed == 0:
        return f"Cancelled remaining {plural} ({cancelled} cancelled)."
    if failed:
        extra = f" · {cancelled} cancelled" if cancelled else ""
        return (
            f"{action.capitalize()} {total} {plural}: "
            f"{completed} completed · {failed} failed{extra}."
        )
    if cancelled:
        return f"{action.capitalize()} {completed} {plural}; {cancelled} cancelled."
    return f"{action.capitalize()} {completed} {plural}."


class AdminExecutionStore:
    """Process-local snapshot: phase + execution object + per-item queue."""

    def __init__(self, kind: str, *, idle_message: str = "Ready when you are") -> None:
        self.kind = kind
        self.idle_message = idle_message
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = self._idle_state()

    def _idle_state(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "job_id": "",
            "phase": "idle",
            "percent": 0,
            "message": self.idle_message,
            "busy": False,
            "ok": True,
            "error": "",
            "items": [],
            "cancel_requested": False,
            "result": None,
            "updated_at": 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._state = self._idle_state()
            self._state["updated_at"] = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            if isinstance(out.get("result"), dict):
                out["result"] = dict(out["result"])
            items = out.get("items") or []
            out["items"] = [dict(item) if isinstance(item, dict) else item for item in items]
            execution = summarize_items(out["items"], now=time.time())
            phase = str(out.get("phase") or "idle")
            can_cancel = bool(
                out.get("busy")
                and (
                    execution["queued"] > 0
                    or execution["pending_submit"] > 0
                    or phase in {"queued", "registering", "sending", "generating", "running"}
                )
            )
            percent = _int(out.get("percent"))
            if out.get("busy") and execution["total"] > 0:
                percent = max(1, min(99, _int(execution.get("percent")) or 1))
            elif phase in TERMINAL_PHASES and phase != "idle" and execution["total"] > 0:
                percent = 100 if execution["percent"] == 100 else min(percent, 99)
            out["execution"] = execution
            out["can_cancel"] = can_cancel
            out["current"] = execution.get("current")
            out["percent"] = percent
            return out

    def begin(
        self,
        *,
        phase: str = "queued",
        message: str = "Queued…",
        items: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Optional[str]:
        with self._lock:
            if self._state.get("busy"):
                return None
            job_id = uuid.uuid4().hex[:12]
            prepared: List[Dict[str, Any]] = []
            for raw in items or []:
                if not isinstance(raw, Mapping):
                    continue
                row = dict(raw)
                row.setdefault("status", "queued")
                row.setdefault("error", "")
                row.setdefault("outcome", "")
                prepared.append(row)
            self._state = {
                "kind": self.kind,
                "job_id": job_id,
                "phase": phase,
                "percent": 5 if prepared else 1,
                "message": message,
                "busy": True,
                "ok": True,
                "error": "",
                "items": prepared,
                "cancel_requested": False,
                "result": None,
                "updated_at": time.time(),
            }
            return job_id

    def update(self, phase: str, message: str = "", *, percent: Optional[int] = None) -> None:
        with self._lock:
            self._state["phase"] = phase
            terminal = phase in TERMINAL_PHASES
            if percent is not None:
                cap = 100 if terminal else 99
                self._state["percent"] = max(0, min(int(percent), cap))
            if message:
                self._state["message"] = str(message)
            self._state["busy"] = phase not in TERMINAL_PHASES
            self._state["ok"] = phase != "error"
            self._state["updated_at"] = time.time()

    def set_item(
        self,
        item_id: Any,
        status: str,
        *,
        error: str = "",
        outcome: str = "",
        message: str = "",
    ) -> None:
        now = time.time()
        with self._lock:
            rows = list(self._state.get("items") or [])
            found = False
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if row.get("id") != item_id:
                    continue
                found = True
                row["status"] = status
                if error:
                    row["error"] = str(error)[:400]
                if outcome:
                    row["outcome"] = outcome
                if message:
                    row["message"] = message
                if status in TERMINAL_ITEM_STATUSES:
                    row["ended_ts"] = now
                    row["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
                break
            if found:
                self._state["items"] = rows
                summary = summarize_items(rows, now=now)
                self._state["message"] = execution_message(summary)
                if self._state.get("busy"):
                    self._state["percent"] = max(1, min(99, _int(summary.get("percent")) or 1))
                self._state["updated_at"] = now

    def cancel_remaining(self) -> int:
        """Mark queued items cancelled. In-flight items keep running."""
        now = time.time()
        cancelled = 0
        with self._lock:
            self._state["cancel_requested"] = True
            rows = list(self._state.get("items") or [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                status = str(row.get("status") or "")
                if status in QUEUED_ITEM_STATUSES:
                    row["status"] = "cancelled"
                    row["outcome"] = "cancelled"
                    row["ended_ts"] = now
                    row["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
                    cancelled += 1
            self._state["items"] = rows
            self._state["message"] = "Cancel requested — finishing the title already in flight…"
            self._state["updated_at"] = now
        return cancelled

    def request_cancel(self) -> None:
        self.cancel_remaining()

    def set_error(self, message: str) -> None:
        with self._lock:
            self._state["phase"] = "error"
            self._state["percent"] = 100
            self._state["message"] = str(message or "Job failed")
            self._state["busy"] = False
            self._state["ok"] = False
            self._state["error"] = str(message or "Job failed")
            self._state["updated_at"] = time.time()

    def set_done(
        self,
        message: str = "",
        *,
        result: Optional[Mapping[str, Any]] = None,
        phase: str = "done",
    ) -> None:
        with self._lock:
            summary = summarize_items(self._state.get("items") or [])
            self._state["phase"] = phase
            self._state["percent"] = 100 if summary["queued"] == 0 and summary["running"] == 0 else min(
                99, _int(summary.get("percent")) or 99
            )
            self._state["message"] = str(message or "Done")
            self._state["busy"] = False
            self._state["ok"] = True
            self._state["error"] = ""
            if isinstance(result, Mapping):
                self._state["result"] = dict(result)
            self._state["updated_at"] = time.time()


_STORES: Dict[str, AdminExecutionStore] = {}
_STORES_LOCK = threading.Lock()
_WORKERS: Dict[str, Optional[threading.Thread]] = {}
_WORKER_LOCK = threading.Lock()
_CANCELS: Dict[str, threading.Event] = {}


def store_for(kind: str, *, idle_message: str = "Ready when you are") -> AdminExecutionStore:
    with _STORES_LOCK:
        store = _STORES.get(kind)
        if store is None:
            store = AdminExecutionStore(kind, idle_message=idle_message)
            _STORES[kind] = store
        return store


def cancel_event(kind: str) -> threading.Event:
    with _WORKER_LOCK:
        event = _CANCELS.get(kind)
        if event is None:
            event = threading.Event()
            _CANCELS[kind] = event
        return event


def reset_admin_execution_for_tests(kind: Optional[str] = None) -> None:
    with _WORKER_LOCK:
        kinds = [kind] if kind else list(_WORKERS.keys()) + list(_CANCELS.keys())
        for key in kinds:
            _WORKERS[key] = None
            event = _CANCELS.get(key)
            if event is not None:
                event.clear()
    with _STORES_LOCK:
        if kind:
            store = _STORES.get(kind)
            if store is not None:
                store.reset()
        else:
            for store in _STORES.values():
                store.reset()


def worker_alive(kind: str) -> bool:
    with _WORKER_LOCK:
        worker = _WORKERS.get(kind)
        return worker is not None and worker.is_alive()


def start_worker(kind: str, run: RunFn, *, name: str = "") -> bool:
    """Start a daemon thread. Returns False if a worker for this kind is already running."""
    with _WORKER_LOCK:
        existing = _WORKERS.get(kind)
        if existing is not None and existing.is_alive():
            return False
        event = _CANCELS.get(kind)
        if event is None:
            event = threading.Event()
            _CANCELS[kind] = event
        event.clear()

        def _run() -> None:
            store = store_for(kind)
            try:
                result = run(store, event)
                snap = store.snapshot()
                if snap.get("busy"):
                    phase = "cancelled" if event.is_set() else "done"
                    store.set_done(
                        str(snap.get("message") or ("Cancelled." if event.is_set() else "Done.")),
                        result=result if isinstance(result, Mapping) else snap.get("result"),
                        phase=phase,
                    )
            except Exception as error:  # noqa: BLE001 — surface on the job card
                logger.exception("admin execution job %s failed: %s", kind, error)
                store.set_error(str(error)[:400] or f"{kind} failed.")
            finally:
                with _WORKER_LOCK:
                    _WORKERS[kind] = None

        thread = threading.Thread(target=_run, name=name or f"admin-{kind}", daemon=True)
        _WORKERS[kind] = thread
    thread.start()
    return True


def request_cancel(kind: str) -> Dict[str, Any]:
    cancel_event(kind).set()
    store = store_for(kind)
    store.cancel_remaining()
    return flatten_result(store.snapshot())


def flatten_result(snap: Mapping[str, Any]) -> Dict[str, Any]:
    """Copy result keys onto the snapshot when the job is no longer busy.

    Lets existing callers that read ``delivered`` / ``latest`` on the POST body
    still work if the worker finished before the request returned.
    """
    out = dict(snap)
    result = out.get("result")
    if isinstance(result, Mapping) and not out.get("busy"):
        for key, value in result.items():
            out.setdefault(key, value)
    return out
