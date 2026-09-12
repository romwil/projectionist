"""One serialized Live Channels job for Stations, Setup, and Overview.

Approach B primitive: a single ``{ kind, phase, percent, message, startedAt }``
object. Engine / continuity / publish keep their existing stores; this module
aggregates them with Plex refresh/rebuild and refill so the UI can show one
sticky rail and refuse a second mutating Live job.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

KIND_PLEX_REFRESH = "plex_refresh"
KIND_PLEX_REBUILD = "plex_rebuild"
KIND_ENGINE = "engine"
KIND_CONTINUITY = "continuity"
KIND_PUBLISH = "publish"
KIND_REFILL = "refill"

KIND_LABELS = {
    KIND_PLEX_REFRESH: "Refreshing Plex map",
    KIND_PLEX_REBUILD: "Rebuilding tuner in Plex",
    KIND_ENGINE: "Starting TV engine",
    KIND_CONTINUITY: "Rescanning filler",
    KIND_PUBLISH: "Publishing station",
    KIND_REFILL: "Refilling station",
}

_OWNED_KINDS = frozenset({KIND_PLEX_REFRESH, KIND_PLEX_REBUILD, KIND_REFILL})

_OWNED_PHASES: Dict[str, tuple[int, str]] = {
    "idle": (0, "Idle"),
    "queued": (5, "Queued…"),
    "preparing": (15, "Preparing stations…"),
    "injecting": (30, "Injecting tuner…"),
    "scanning": (50, "Scanning channels…"),
    "mapping": (70, "Mapping channels…"),
    "reloading": (85, "Reloading guide…"),
    "refilling": (40, "Refilling lineup…"),
    "done": (100, "Finished"),
    "error": (100, "Failed"),
}

_BUSY_DETAIL = "Another Live job is running. Don't start another Live job."


def _iso(ts: float) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shape(
    *,
    kind: Optional[str],
    phase: str = "idle",
    percent: int = 0,
    message: str = "",
    started_at: Optional[str] = None,
    busy: bool = False,
) -> Dict[str, Any]:
    label = KIND_LABELS.get(str(kind or ""), "")
    return {
        "kind": kind,
        "phase": phase or "idle",
        "percent": int(percent or 0),
        "message": str(message or label or ""),
        "started_at": started_at,
        "startedAt": started_at,
        "busy": bool(busy),
        "label": label,
    }


def idle_live_job() -> Dict[str, Any]:
    return _shape(kind=None, phase="idle", percent=0, message="", busy=False)


class LiveOwnedJobStore:
    """Plex refresh/rebuild + refill — kinds that have no dedicated store yet."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = self._idle()

    @staticmethod
    def _idle() -> Dict[str, Any]:
        return {
            "kind": None,
            "phase": "idle",
            "percent": 0,
            "message": "",
            "busy": False,
            "ok": True,
            "error": "",
            "result": None,
            "started_at": 0.0,
            "updated_at": 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._state = self._idle()
            self._state["updated_at"] = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def begin(self, kind: str) -> bool:
        kind = str(kind or "").strip()
        if kind not in _OWNED_KINDS:
            return False
        with self._lock:
            if self._state.get("busy"):
                return False
            now = time.time()
            self._state.update(
                {
                    "kind": kind,
                    "phase": "queued",
                    "percent": _OWNED_PHASES["queued"][0],
                    "message": KIND_LABELS.get(kind, "Working…"),
                    "busy": True,
                    "ok": True,
                    "error": "",
                    "result": None,
                    "started_at": now,
                    "updated_at": now,
                }
            )
            return True

    def set_phase(self, phase: str, message: str = "", *, percent: Optional[int] = None) -> None:
        meta = _OWNED_PHASES.get(phase)
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

    def set_error(self, message: str) -> None:
        self.set_phase("error", message)

    def set_done(self, message: str = "", *, result: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._state["phase"] = "done"
            self._state["percent"] = 100
            self._state["message"] = str(message or "Finished")
            self._state["busy"] = False
            self._state["ok"] = True
            self._state["error"] = ""
            self._state["result"] = result
            self._state["updated_at"] = time.time()


_OWNED = LiveOwnedJobStore()


def owned_store() -> LiveOwnedJobStore:
    return _OWNED


def reset_live_job_for_tests() -> None:
    _OWNED.reset()


def _peer_snapshots() -> list[tuple[str, Dict[str, Any]]]:
    peers: list[tuple[str, Dict[str, Any]]] = []
    try:
        from projectionist.live_channels.lifecycle_progress import progress_store as life

        peers.append((KIND_ENGINE, life().snapshot()))
    except Exception:  # noqa: BLE001
        pass
    try:
        from projectionist.live_channels.continuity_progress import progress_store as cont

        peers.append((KIND_CONTINUITY, cont().snapshot()))
    except Exception:  # noqa: BLE001
        pass
    try:
        from projectionist.live_channels.publish_progress import progress_store as pub

        peers.append((KIND_PUBLISH, pub().snapshot()))
    except Exception:  # noqa: BLE001
        pass
    return peers


def _peer_busy(snap: Dict[str, Any]) -> bool:
    if snap.get("busy"):
        return True
    phase = str(snap.get("phase") or "idle")
    if phase in {"idle", "done", "error", "ready"}:
        return False
    return bool(phase)


def build_live_job() -> Dict[str, Any]:
    """Current job for Admin surfaces. Prefer an in-flight owned/peer job."""
    owned = _OWNED.snapshot()
    if owned.get("busy"):
        return _shape(
            kind=str(owned.get("kind") or KIND_PLEX_REFRESH),
            phase=str(owned.get("phase") or "queued"),
            percent=int(owned.get("percent") or 0),
            message=str(owned.get("message") or ""),
            started_at=_iso(float(owned.get("started_at") or 0)),
            busy=True,
        )
    for kind, snap in _peer_snapshots():
        if _peer_busy(snap):
            started = snap.get("started_at") or snap.get("updated_at") or 0
            return _shape(
                kind=kind,
                phase=str(snap.get("phase") or "queued"),
                percent=int(snap.get("percent") or 0),
                message=str(snap.get("message") or ""),
                started_at=_iso(float(started or 0)),
                busy=True,
            )
    return idle_live_job()


def conflicting_live_job() -> Optional[Dict[str, Any]]:
    job = build_live_job()
    if job.get("busy"):
        return job
    return None


def live_job_busy_detail() -> str:
    return _BUSY_DETAIL


def begin_owned_job(kind: str) -> bool:
    """Start a Plex/refill job if nothing else is running."""
    if conflicting_live_job():
        return False
    return _OWNED.begin(kind)
