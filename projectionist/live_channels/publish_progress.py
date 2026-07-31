"""In-process progress store for async Live Channels publish jobs.

Mirrors ``continuity_progress`` so long collection/craft publishes do not block
the Admin UI behind a reverse-proxy timeout.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

PhaseCallback = Callable[[str, str], None]

PHASE_META: Dict[str, tuple[int, str]] = {
    "idle": (0, "Idle"),
    "queued": (5, "Publish queued…"),
    "wiring": (15, "Wiring Plex media source…"),
    "matching": (35, "Matching collection titles…"),
    "publishing": (55, "Creating station + lineup…"),
    "plex_sync": (75, "Refreshing Plex Live TV channels…"),
    "warming": (90, "Warming streams…"),
    "done": (100, "Publish finished"),
    "error": (100, "Publish failed"),
}


class PublishProgressStore:
    """Thread-safe snapshot of the current publish job."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = self._idle_state()

    @staticmethod
    def _idle_state() -> Dict[str, Any]:
        return {
            "phase": "idle",
            "percent": 0,
            "message": PHASE_META["idle"][1],
            "busy": False,
            "ok": True,
            "error": "",
            "result": None,
            "mode": "",
            "updated_at": 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._state = self._idle_state()
            self._state["updated_at"] = time.time()

    def begin(self, *, mode: str = "publish") -> bool:
        """Start a job if idle. Returns False when another job is already busy."""
        with self._lock:
            if self._state.get("busy"):
                return False
            self._state.update(
                {
                    "phase": "queued",
                    "percent": PHASE_META["queued"][0],
                    "message": PHASE_META["queued"][1],
                    "busy": True,
                    "ok": True,
                    "error": "",
                    "result": None,
                    "mode": str(mode or "publish"),
                    "updated_at": time.time(),
                }
            )
            return True

    def set_phase(
        self,
        phase: str,
        message: str = "",
        *,
        percent: Optional[int] = None,
    ) -> None:
        meta = PHASE_META.get(phase)
        default_pct, default_msg = meta if meta else (50, phase.replace("_", " ").title())
        with self._lock:
            self._state["phase"] = phase
            self._state["percent"] = int(percent if percent is not None else default_pct)
            self._state["message"] = str(message or default_msg)
            self._state["busy"] = phase not in {"idle", "done", "error"}
            self._state["ok"] = phase != "error"
            if phase == "error":
                self._state["error"] = str(message or default_msg)
            elif phase == "done":
                self._state["error"] = ""
            self._state["updated_at"] = time.time()
        logger.info(
            "live_channels.publish phase=%s percent=%s message=%s",
            phase,
            self._state["percent"],
            self._state["message"],
        )

    def set_error(self, message: str) -> None:
        self.set_phase("error", message)

    def set_done(self, message: str = "", *, result: Optional[Mapping[str, Any]] = None) -> None:
        with self._lock:
            self._state["phase"] = "done"
            self._state["percent"] = PHASE_META["done"][0]
            self._state["message"] = str(message or PHASE_META["done"][1])
            self._state["busy"] = False
            self._state["ok"] = True
            self._state["error"] = ""
            self._state["result"] = dict(result) if isinstance(result, Mapping) else result
            self._state["updated_at"] = time.time()
        logger.info(
            "live_channels.publish phase=done message=%s",
            self._state["message"],
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            if isinstance(out.get("result"), dict):
                out["result"] = dict(out["result"])
            return out


_STORE = PublishProgressStore()
_WORKER_LOCK = threading.Lock()
_WORKER: Optional[threading.Thread] = None


def progress_store() -> PublishProgressStore:
    return _STORE


def reset_progress_for_tests() -> None:
    """Test helper — clear process-local progress between cases."""
    global _WORKER
    with _WORKER_LOCK:
        _WORKER = None
    _STORE.reset()


def make_phase_callback(store: Optional[PublishProgressStore] = None) -> PhaseCallback:
    target = store or _STORE

    def _on_phase(phase: str, message: str = "") -> None:
        target.set_phase(phase, message)

    return _on_phase


def build_publish_job_status() -> Dict[str, Any]:
    """Owner-facing progress snapshot for publish polling."""
    snap = progress_store().snapshot()
    return {
        "phase": snap.get("phase") or "idle",
        "percent": int(snap.get("percent") or 0),
        "message": str(snap.get("message") or ""),
        "busy": bool(snap.get("busy")),
        "ok": bool(snap.get("ok", True)),
        "error": str(snap.get("error") or ""),
        "mode": str(snap.get("mode") or ""),
        "result": snap.get("result"),
        "determinate": True,
        "updated_at": snap.get("updated_at") or 0,
    }


def start_publish_job(
    runner: Callable[[], None],
    *,
    mode: str = "publish",
) -> Dict[str, Any]:
    """Begin a background publish job. Returns an accepted/busy snapshot."""
    global _WORKER
    store = progress_store()
    if not store.begin(mode=mode):
        snap = build_publish_job_status()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "Publish already running."
        return snap

    def _wrapped() -> None:
        try:
            runner()
        except Exception as error:  # noqa: BLE001 — surface on progress store
            logger.exception("live_channels.publish job failed: %s", error)
            if store.snapshot().get("busy"):
                store.set_error(str(error)[:400] or "Publish failed.")
        finally:
            global _WORKER
            with _WORKER_LOCK:
                _WORKER = None

    thread = threading.Thread(
        target=_wrapped,
        name="live-channels-publish",
        daemon=True,
    )
    with _WORKER_LOCK:
        _WORKER = thread
    thread.start()
    snap = build_publish_job_status()
    snap["accepted"] = True
    return snap


class PublishJobError(Exception):
    """Raised with an HTTP-ish status code so the job can map to owner feedback."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)
