"""In-process progress for Live Channels Step 2 (Start engine).

The owner UI polls ``GET /api/admin/live-channels/lifecycle-status`` while
``POST …/lifecycle`` runs ``ensure_running`` (and afterward until Tunarr is
ready). Progress is process-local — fine for single-owner Projectionist.

Readiness is HTTP-first: the container log line ``Tunarr is ready!`` is a soft
signal only. Transient Meilisearch / mid-scan / SIGTERM noise during recreate
must not count as success or hard failure.

Admin first paint must never wait on Docker inspect / Tunarr HTTP: those probes
run via SWR (see :func:`get_lifecycle_status`). The cheap progress-store snapshot
is always overlaid live so busy/phase never lag during ensure_running.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

from projectionist.swr_cache import SwrCache

logger = logging.getLogger(__name__)

# Short soft TTL: Step 2 polls while starting; background refresh stays snappy.
LIFECYCLE_SOFT_TTL_SECONDS = 5.0
LIFECYCLE_HARD_TTL_SECONDS = 3600.0
LIFECYCLE_COLD_WAIT_SECONDS = 0.0

LIFECYCLE_CACHE = SwrCache(
    "admin_live_lifecycle",
    soft_ttl=LIFECYCLE_SOFT_TTL_SECONDS,
    hard_ttl=LIFECYCLE_HARD_TTL_SECONDS,
    durable=False,
)

READY_LOG_MARKER = "Tunarr is ready!"

# Noise that often appears during recreate / Meili boot — never treat as hard fail.
_TRANSIENT_LOG_NOISE = (
    "meilisearch",
    "meili",
    "sigterm",
    "sigkill",
    "expected?=true",
    "could not acquire lock",
    "econnrefused",
    "connect econnrefused",
    "fetch failed",
    "undici",
)

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
    LIFECYCLE_CACHE.clear()


def invalidate_lifecycle_status_cache() -> None:
    """Mark the probe snapshot soft-stale (payload kept for instant paint)."""
    LIFECYCLE_CACHE.invalidate()


def make_phase_callback(store: Optional[LifecycleProgressStore] = None) -> PhaseCallback:
    target = store or _STORE

    def _on_phase(phase: str, message: str = "") -> None:
        target.set_phase(phase, message)

    return _on_phase


def logs_indicate_ready(text: str) -> bool:
    """Soft signal: Tunarr printed its ready banner (HTTP may still be down)."""
    return READY_LOG_MARKER in str(text or "")


def logs_look_transient(text: str) -> bool:
    """True when recent logs are dominated by known recreate / Meili boot noise."""
    lowered = str(text or "").lower()
    if not lowered.strip():
        return False
    return any(token in lowered for token in _TRANSIENT_LOG_NOISE)


def probe_tunarr_http_ready(base_url: str, *, timeout: float = 2.0) -> bool:
    """True when Tunarr ``/api/version`` (or ``/api/system/health``) responds OK."""
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return False
    try:
        from projectionist.circuit_breaker import bypass_host_circuits
        from projectionist.connectors.tunarr import TunarrClient

        with bypass_host_circuits():
            client = TunarrClient(url, timeout=timeout)
            client.version()
            return True
    except Exception:  # noqa: BLE001
        try:
            from projectionist.circuit_breaker import bypass_host_circuits
            from projectionist.connectors.tunarr import TunarrClient

            with bypass_host_circuits():
                TunarrClient(url, timeout=timeout).health()
            return True
        except Exception:  # noqa: BLE001
            return False


def wait_for_tunarr_ready(
    base_url: str,
    *,
    timeout_s: float = 90.0,
    interval_s: float = 2.0,
    http_timeout: float = 4.0,
    lifecycle: Any = None,
) -> Dict[str, Any]:
    """Poll HTTP until Tunarr serves, or return an honest still-starting / hard-fail.

    Does not treat log markers, Meili noise, or SIGTERM during recreate as success.
    """
    url = str(base_url or "").strip().rstrip("/")
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    attempts = 0
    container_running = True
    logs_ready = False
    last_snippet = ""

    if not url and lifecycle is not None:
        try:
            url = str(lifecycle._reachable_url_hint() or "").strip()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            url = ""

    while time.monotonic() < deadline:
        attempts += 1
        if lifecycle is not None:
            try:
                docker_probe = probe_ready_from_docker(lifecycle)
                container_running = bool(docker_probe.get("container_running"))
                logs_ready = bool(docker_probe.get("logs_ready"))
                last_snippet = str(docker_probe.get("log_snippet") or "")
                if not container_running:
                    return {
                        "ok": False,
                        "ready": False,
                        "http_ready": False,
                        "logs_ready": logs_ready,
                        "still_starting": False,
                        "hard_fail": True,
                        "attempts": attempts,
                        "tunarr_url": url,
                        "message": (
                            "Tunarr container is not running — start the broadcast "
                            "engine again."
                        ),
                    }
            except Exception as error:  # noqa: BLE001
                logger.debug("wait_for_tunarr_ready docker probe: %s", error)

        if url and probe_tunarr_http_ready(url, timeout=http_timeout):
            return {
                "ok": True,
                "ready": True,
                "http_ready": True,
                "logs_ready": logs_ready,
                "still_starting": False,
                "hard_fail": False,
                "attempts": attempts,
                "tunarr_url": url,
                "message": "Tunarr is ready!",
            }

        time.sleep(max(0.2, float(interval_s)))

    soft = (
        "Tunarr is still starting — HTTP not ready yet"
        + (" (startup log seen)" if logs_ready else "")
        + ". Retry in a moment."
    )
    if last_snippet and logs_look_transient(last_snippet):
        soft = (
            "Tunarr is still starting (Meili/scan noise during boot is normal). "
            "HTTP not ready yet — retry shortly."
        )
    return {
        "ok": False,
        "ready": False,
        "http_ready": False,
        "logs_ready": logs_ready,
        "still_starting": bool(container_running),
        "hard_fail": not container_running,
        "attempts": attempts,
        "tunarr_url": url,
        "message": soft if container_running else (
            "Tunarr container stopped before becoming ready."
        ),
    }


def probe_ready_from_docker(lifecycle: Any) -> Dict[str, Any]:
    """Inspect container + logs for ready / container id."""
    out: Dict[str, Any] = {
        "container_running": False,
        "container_id": "",
        "logs_ready": False,
        "log_snippet": "",
        "transient_noise": False,
    }
    try:
        # Status polls must not inherit the 120s pull/create Docker timeout.
        code, body = lifecycle._engine_request(  # noqa: SLF001 — intentional
            "GET",
            f"/containers/{lifecycle.container_name}/json",
            timeout=5.0,
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
            text = lifecycle.container_logs(tail=80, timeout=5.0)
            out["log_snippet"] = text[-400:] if text else ""
            out["logs_ready"] = logs_indicate_ready(text)
            out["transient_noise"] = logs_look_transient(text)
        except Exception as error:  # noqa: BLE001
            out["log_error"] = str(error)[:160]
    return out


def _resolve_probe_url(settings: Any, lifecycle: Any) -> str:
    """Prefer configured Tunarr URL; fall back to published host-port hint."""
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if url:
        return url.rstrip("/")
    try:
        return str(lifecycle._reachable_url_hint() or "").strip().rstrip("/")  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return ""


def build_lifecycle_status(settings: Any) -> Dict[str, Any]:
    """Owner-facing progress + ready probe for Step 2.

    Success requires HTTP. Log ``Tunarr is ready!`` only upgrades the waiting
    message — it never flips ``ready`` by itself.
    """
    from projectionist.live_channels.docker import lifecycle_from_settings

    store = progress_store()
    snap = store.snapshot()
    life = lifecycle_from_settings(settings)

    docker_probe: Dict[str, Any] = {}
    if life.available() and life.orchestration:
        docker_probe = probe_ready_from_docker(life)
        if docker_probe.get("container_id"):
            store.set_container(
                container_id=str(docker_probe["container_id"]),
                container_name=life.container_name,
            )

    url = _resolve_probe_url(settings, life)
    http_ready = probe_tunarr_http_ready(url) if url else False
    logs_ready = bool(docker_probe.get("logs_ready"))
    # HTTP is authoritative. Logs are a soft "still booting / almost there" hint.
    ready = bool(http_ready)

    waiting_message = "Waiting for Tunarr ready"
    if docker_probe.get("container_running") and not http_ready:
        if logs_ready:
            waiting_message = (
                "Startup log seen — waiting for Tunarr HTTP to respond"
            )
        elif docker_probe.get("transient_noise"):
            waiting_message = (
                "Container is up — Meili/scan boot noise is normal; waiting for HTTP"
            )
        else:
            waiting_message = "Container is up — waiting for Tunarr HTTP"

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
                and snap.get("phase") in {"pulling", "creating", "starting", "waiting_ready"}
            ):
                store.set_phase(
                    "waiting_ready",
                    waiting_message,
                    container_id=str(docker_probe.get("container_id") or ""),
                    percent=85 if logs_ready else None,
                )
                snap = store.snapshot()
            payload = dict(snap)
            payload.update(
                {
                    "http_ready": http_ready,
                    "logs_ready": logs_ready,
                    "container_running": bool(docker_probe.get("container_running")),
                    "tunarr_url": url,
                    "still_starting": bool(
                        docker_probe.get("container_running") and not http_ready
                    ),
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
            waiting_message,
            container_id=str(docker_probe.get("container_id") or ""),
            percent=85 if logs_ready else 80,
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
        "still_starting": bool(
            docker_probe.get("container_running") and not http_ready
        ),
        "tunarr_url": url,
        "determinate": True,
        "updated_at": snap.get("updated_at") or 0,
    }


def _lifecycle_cache_key(settings: Any) -> str:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    orch = bool(getattr(tunarr, "docker_orchestration", False)) if tunarr else False
    return f"orch={int(orch)}|url={url}"


def _warming_lifecycle_status(settings: Any) -> Dict[str, Any]:
    """Probe-free skeleton from the in-process progress store only."""
    from projectionist.live_channels.docker import lifecycle_from_settings

    snap = progress_store().snapshot()
    life = lifecycle_from_settings(settings)
    url = _resolve_probe_url(settings, life)
    return {
        "phase": snap.get("phase") or "idle",
        "percent": int(snap.get("percent") or 0),
        "message": str(snap.get("message") or PHASE_META["idle"][1]),
        "ready": bool(snap.get("ready")),
        "busy": bool(snap.get("busy")),
        "ok": bool(snap.get("ok", True)),
        "error": str(snap.get("error") or ""),
        "container_id": str(snap.get("container_id") or ""),
        "container_name": str(snap.get("container_name") or life.container_name),
        "http_ready": False,
        "logs_ready": False,
        "container_running": False,
        "still_starting": False,
        "tunarr_url": url,
        "determinate": True,
        "updated_at": snap.get("updated_at") or 0,
        "warming": True,
    }


def _overlay_live_progress(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep busy/phase/percent live even when probe fields are stale."""
    snap = progress_store().snapshot()
    out = dict(payload)
    for key in (
        "phase",
        "percent",
        "message",
        "ready",
        "busy",
        "ok",
        "error",
        "container_id",
        "container_name",
        "updated_at",
    ):
        if key in snap and snap[key] is not None and snap[key] != "":
            out[key] = snap[key]
    # Store ready wins when ensure_running just flipped; probe http_ready can lag.
    if snap.get("ready"):
        out["ready"] = True
        out["still_starting"] = False
    elif out.get("http_ready"):
        out["ready"] = True
        out["still_starting"] = False
    return out


def get_lifecycle_status(
    settings: Any,
    *,
    fresh: bool = False,
    cold_wait: float = LIFECYCLE_COLD_WAIT_SECONDS,
) -> Dict[str, Any]:
    """Cached lifecycle probes; progress-store fields always overlaid live.

    ``fresh=True`` forces a synchronous Docker + Tunarr rebuild (diagnostics).
    """
    key = _lifecycle_cache_key(settings)
    if fresh:
        payload = LIFECYCLE_CACHE.refresh_now(key, lambda: build_lifecycle_status(settings))
        out = _overlay_live_progress(payload)
        out.update({"cached": False, "stale": False, "warming": False})
        return out

    # While ensure_running is in flight, prefer a short soft age so polls refresh
    # probes in the background without blocking the request path.
    snap = progress_store().snapshot()
    if snap.get("busy"):
        LIFECYCLE_CACHE.invalidate()

    result = LIFECYCLE_CACHE.get(
        key,
        lambda: build_lifecycle_status(settings),
        warming=lambda: _warming_lifecycle_status(settings),
        cold_wait=cold_wait,
    )
    out = _overlay_live_progress(result.annotated())
    return out


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
        store.set_phase("waiting_ready", "Waiting for Tunarr HTTP ready", container_id=cid)
        return
    store.set_phase("waiting_ready", message or "Waiting for Tunarr HTTP ready")
