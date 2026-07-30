"""In-process progress for Live Channels Step 2 (Start engine).

The owner UI polls ``GET /api/admin/live-channels/lifecycle-status`` while
``POST …/lifecycle`` runs ``ensure_running`` (and afterward until Tunarr is
ready). Progress is process-local — fine for single-owner Projectionist.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

READY_LOG_MARKER = "Tunarr is ready!"

# phase → (percent, default label)
PHASE_META: Dict[str, tuple[int, str]] = {
    "idle": (0, "Ready when you are"),
    "pulling": (20, "Pulling image"),
    "creating": (45, "Creating container"),
    "starting": (65, "Starting"),
    "waiting_ready": (80, "Waiting for Tunarr ready"),
    "ready": (100, "Tunarr is ready"),
    "error": (0, "Broadcast engine failed"),
}

PhaseCallback = Callable[[str, str], None]


class LifecycleProgressStore:
    """Thread-safe snapshot of the current Start-engine operation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "phase": "idle",
            "percent": 0,
            "message": PHASE_META["idle"][1],
            "ready": False,
            "busy": False,
            "ok": True,
            "error": "",
            "container_id": "",
            "container_name": "",
            "updated_at": 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._state = {
                "phase": "idle",
                "percent": 0,
                "message": PHASE_META["idle"][1],
                "ready": False,
                "busy": False,
                "ok": True,
                "error": "",
                "container_id": "",
                "container_name": "",
                "updated_at": time.time(),
            }

    def begin(self, *, container_name: str = "") -> None:
        with self._lock:
            self._state.update(
                {
                    "phase": "pulling",
                    "percent": PHASE_META["pulling"][0],
                    "message": PHASE_META["pulling"][1],
                    "ready": False,
                    "busy": True,
                    "ok": True,
                    "error": "",
                    "container_id": "",
                    "container_name": str(container_name or ""),
                    "updated_at": time.time(),
                }
            )

    def set_phase(
        self,
        phase: str,
        message: str = "",
        *,
        container_id: str = "",
        percent: Optional[int] = None,
    ) -> None:
        meta = PHASE_META.get(phase)
        default_pct, default_msg = meta if meta else (50, phase.replace("_", " ").title())
        with self._lock:
            self._state["phase"] = phase
            self._state["percent"] = int(percent if percent is not None else default_pct)
            self._state["message"] = str(message or default_msg)
            self._state["busy"] = phase not in {"idle", "ready", "error"}
            self._state["ready"] = phase == "ready"
            self._state["ok"] = phase != "error"
            if phase == "error":
                self._state["error"] = str(message or default_msg)
            elif phase == "ready":
                self._state["error"] = ""
            if container_id:
                self._state["container_id"] = str(container_id)
            self._state["updated_at"] = time.time()

    def set_error(self, message: str) -> None:
        self.set_phase("error", message)

    def set_ready(self, message: str = "", *, container_id: str = "") -> None:
        self.set_phase(
            "ready",
            message or PHASE_META["ready"][1],
            container_id=container_id,
        )

    def set_container(self, *, container_id: str = "", container_name: str = "") -> None:
        with self._lock:
            if container_id:
                self._state["container_id"] = str(container_id)
            if container_name:
                self._state["container_name"] = str(container_name)
            self._state["updated_at"] = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)


_STORE = LifecycleProgressStore()


def progress_store() -> LifecycleProgressStore:
    return _STORE


def reset_progress_for_tests() -> None:
    """Test helper — clear process-local progress between cases."""
    _STORE.reset()


def make_phase_callback(store: Optional[LifecycleProgressStore] = None) -> PhaseCallback:
    target = store or _STORE

    def _on_phase(phase: str, message: str = "") -> None:
        target.set_phase(phase, message)

    return _on_phase


def logs_indicate_ready(text: str) -> bool:
    return READY_LOG_MARKER in str(text or "")


def probe_tunarr_http_ready(base_url: str, *, timeout: float = 4.0) -> bool:
    """True when Tunarr ``/api/version`` (or ``/api`` health) responds OK."""
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return False
    try:
        from projectionist.connectors.tunarr import TunarrClient

        client = TunarrClient(url, timeout=timeout)
        client.version()
        return True
    except Exception:  # noqa: BLE001
        try:
            from projectionist.connectors.tunarr import TunarrClient

            TunarrClient(url, timeout=timeout).health()
            return True
        except Exception:  # noqa: BLE001
            return False


def probe_ready_from_docker(lifecycle: Any) -> Dict[str, Any]:
    """Inspect container + logs for ready / container id."""
    out: Dict[str, Any] = {
        "container_running": False,
        "container_id": "",
        "logs_ready": False,
        "log_snippet": "",
    }
    try:
        code, body = lifecycle._engine_request(  # noqa: SLF001 — intentional
            "GET", f"/containers/{lifecycle.container_name}/json"
        )
    except Exception as error:  # noqa: BLE001
        out["error"] = str(error)[:200]
        return out
    if code == 404 or not isinstance(body, dict):
        return out
    state = body.get("State") or {}
    out["container_running"] = bool(state.get("Running"))
    out["container_id"] = str(body.get("Id") or "")[:12]
    if out["container_running"]:
        try:
            text = lifecycle.container_logs(tail=120)
            out["log_snippet"] = text[-400:] if text else ""
            out["logs_ready"] = logs_indicate_ready(text)
        except Exception as error:  # noqa: BLE001
            out["log_error"] = str(error)[:160]
    return out


def build_lifecycle_status(settings: Any) -> Dict[str, Any]:
    """Owner-facing progress + ready probe for Step 2."""
    from projectionist.live_channels.docker import lifecycle_from_settings

    store = progress_store()
    snap = store.snapshot()
    life = lifecycle_from_settings(settings)
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""

    docker_probe: Dict[str, Any] = {}
    if life.available() and life.orchestration:
        docker_probe = probe_ready_from_docker(life)
        if docker_probe.get("container_id"):
            store.set_container(
                container_id=str(docker_probe["container_id"]),
                container_name=life.container_name,
            )

    http_ready = probe_tunarr_http_ready(url) if url else False
    logs_ready = bool(docker_probe.get("logs_ready"))
    ready = bool(http_ready or logs_ready)

    # When an ensure_running is in flight, prefer the live phase over a cold probe.
    if snap.get("busy") and snap.get("phase") not in {"ready", "error", "idle"}:
        if ready:
            store.set_ready(
                "Tunarr is ready!",
                container_id=str(docker_probe.get("container_id") or ""),
            )
            snap = store.snapshot()
        else:
            # Soft bump into waiting_ready once the container is up.
            if (
                docker_probe.get("container_running")
                and snap.get("phase") in {"pulling", "creating", "starting"}
            ):
                store.set_phase(
                    "waiting_ready",
                    "Waiting for Tunarr ready",
                    container_id=str(docker_probe.get("container_id") or ""),
                )
                snap = store.snapshot()
            payload = dict(snap)
            payload.update(
                {
                    "http_ready": http_ready,
                    "logs_ready": logs_ready,
                    "container_running": bool(docker_probe.get("container_running")),
                    "tunarr_url": url,
                    "determinate": True,
                }
            )
            return payload

    if ready:
        store.set_ready(
            "Tunarr is ready!",
            container_id=str(docker_probe.get("container_id") or snap.get("container_id") or ""),
        )
        snap = store.snapshot()
    elif snap.get("phase") == "error":
        pass
    elif docker_probe.get("container_running"):
        store.set_phase(
            "waiting_ready",
            "Container is up — waiting for Tunarr ready",
            container_id=str(docker_probe.get("container_id") or ""),
            percent=85,
        )
        snap = store.snapshot()
    elif snap.get("phase") not in {"error"} and not snap.get("busy"):
        # Idle / not started yet.
        if snap.get("phase") != "idle":
            # Keep last error; otherwise show idle.
            pass

    snap = store.snapshot()
    return {
        "phase": snap.get("phase") or "idle",
        "percent": int(snap.get("percent") or 0),
        "message": str(snap.get("message") or ""),
        "ready": bool(snap.get("ready") or ready),
        "busy": bool(snap.get("busy")),
        "ok": bool(snap.get("ok", True)),
        "error": str(snap.get("error") or ""),
        "container_id": str(snap.get("container_id") or docker_probe.get("container_id") or ""),
        "container_name": str(snap.get("container_name") or life.container_name),
        "http_ready": http_ready,
        "logs_ready": logs_ready,
        "container_running": bool(docker_probe.get("container_running")),
        "tunarr_url": url,
        "determinate": True,
        "updated_at": snap.get("updated_at") or 0,
    }


def mark_waiting_after_lifecycle(result: Mapping[str, Any]) -> None:
    """Called after ensure_running/start returns — move into waiting_ready or error."""
    store = progress_store()
    ok = bool(result.get("ok"))
    status = str(result.get("status") or "")
    message = str(result.get("message") or "")
    if not ok:
        store.set_error(message or "Broadcast engine failed to start.")
        return
    if status == "running":
        detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
        cid = ""
        if isinstance(detail, dict):
            start = detail.get("start") if isinstance(detail.get("start"), dict) else {}
            # container id is not always in detail; leave empty
            del start
        store.set_phase("waiting_ready", "Waiting for Tunarr ready", container_id=cid)
        return
    store.set_phase("waiting_ready", message or "Waiting for Tunarr ready")
