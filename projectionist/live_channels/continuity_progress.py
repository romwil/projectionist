"""In-process progress for Live Channels continuity repair / filler rescan.

Owner UI polls ``GET /api/admin/live-channels/continuity/status`` while
``POST …/continuity/repair`` runs in a background thread. Progress is
process-local — fine for single-owner Projectionist.

Repair remounts Tunarr, force-scans filler, attaches continuity, optionally
refills lineups, and warms streams — often several minutes. A synchronous HTTP
handler times out at the reverse proxy and surfaces as a generic 502/503.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

# phase → (percent, default label)
PHASE_META: Dict[str, tuple[int, str]] = {
    "idle": (0, "Ready when you are"),
    "queued": (5, "Queued continuity repair"),
    "remounting": (15, "Remounting Tunarr with filler paths"),
    "waiting_ready": (28, "Waiting for Tunarr ready"),
    "scoping_libraries": (38, "Scoping media libraries"),
    "scanning_filler": (50, "Scanning filler shorts"),
    "attaching": (65, "Attaching continuity to stations"),
    "refilling": (78, "Refilling station lineups"),
    "warming": (90, "Warming station streams"),
    "done": (100, "Continuity repair finished"),
    "error": (0, "Continuity repair failed"),
}

PhaseCallback = Callable[[str, str], None]


class ContinuityProgressStore:
    """Thread-safe snapshot of the current continuity repair / rescan."""

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

    def begin(self, *, mode: str = "repair") -> bool:
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
                    "mode": str(mode or "repair"),
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
            "live_channels.continuity phase=%s percent=%s message=%s",
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
            "live_channels.continuity phase=done message=%s",
            self._state["message"],
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            if isinstance(out.get("result"), dict):
                out["result"] = dict(out["result"])
            return out


_STORE = ContinuityProgressStore()
_WORKER_LOCK = threading.Lock()
_WORKER: Optional[threading.Thread] = None


def progress_store() -> ContinuityProgressStore:
    return _STORE


def reset_progress_for_tests() -> None:
    """Test helper — clear process-local progress between cases."""
    global _WORKER
    with _WORKER_LOCK:
        _WORKER = None
    _STORE.reset()


def make_phase_callback(store: Optional[ContinuityProgressStore] = None) -> PhaseCallback:
    target = store or _STORE

    def _on_phase(phase: str, message: str = "") -> None:
        target.set_phase(phase, message)

    return _on_phase


def build_continuity_job_status() -> Dict[str, Any]:
    """Owner-facing progress snapshot for Repair / Rescan polling."""
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


def start_continuity_repair_job(
    runner: Callable[[], None],
    *,
    mode: str = "repair",
) -> Dict[str, Any]:
    """Begin a background continuity job. Returns an accepted/busy snapshot."""
    global _WORKER
    store = progress_store()
    if not store.begin(mode=mode):
        snap = build_continuity_job_status()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "Continuity repair already running."
        return snap

    def _wrapped() -> None:
        try:
            runner()
        except Exception as error:  # noqa: BLE001 — surface on progress store
            logger.exception("live_channels.continuity job failed: %s", error)
            if store.snapshot().get("busy"):
                store.set_error(str(error)[:400] or "Continuity repair failed.")
        finally:
            global _WORKER
            with _WORKER_LOCK:
                _WORKER = None

    thread = threading.Thread(
        target=_wrapped,
        name="live-channels-continuity-repair",
        daemon=True,
    )
    with _WORKER_LOCK:
        _WORKER = thread
    thread.start()
    snap = build_continuity_job_status()
    snap["accepted"] = True
    return snap


class ContinuityRepairError(Exception):
    """Raised with an HTTP-ish status code so the job can map to owner feedback."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)


def execute_continuity_repair(
    settings: Any,
    *,
    data_dir: Any,
    rescan: bool = True,
    repair: bool = True,
    refill_lineups: bool = True,
    on_phase: Optional[PhaseCallback] = None,
    save_settings_fn: Optional[Callable[[Any, Any], None]] = None,
) -> Dict[str, Any]:
    """Run remount / rescan / attach / refill / warm with stage callbacks.

    Raises :class:`ContinuityRepairError` for owner-facing failures.
    """
    from dataclasses import asdict

    from projectionist.config_store import Settings
    from projectionist.live_channels.docker import (
        lifecycle_from_settings,
        resolve_config_volume,
    )
    from projectionist.live_channels.filler import (
        ensure_continuity_filler_list,
        repair_jumpstart_stations,
    )
    from projectionist.live_channels.lifecycle_progress import wait_for_tunarr_ready
    from projectionist.live_channels.publish import (
        ensure_media_libraries_enabled,
        resolve_channel_icon_url,
        tunarr_client_from_settings,
    )

    def _phase(phase: str, message: str = "") -> None:
        if on_phase is not None:
            try:
                on_phase(phase, message)
            except Exception:  # noqa: BLE001
                pass
        logger.info(
            "live_channels.continuity stage=%s message=%s",
            phase,
            message or phase,
        )

    docker_state: Dict[str, Any] = {"skipped": True}
    ready_state: Dict[str, Any] = {"skipped": True}
    libraries_state: Dict[str, Any] = {"skipped": True}

    if rescan:
        life = lifecycle_from_settings(settings)
        if life.can_orchestrate():
            _phase("remounting", "Remounting Tunarr with current filler / media binds")
            volume = resolve_config_volume(settings, data_dir)
            # Recreate when filler/media binds drifted (kills active transcoder
            # sessions — expected; Tunarr logs may show SIGKILL expected?=true).
            start_result = life.start(config_volume=volume)
            docker_state = start_result.to_dict()
            if not start_result.ok:
                raise ContinuityRepairError(
                    start_result.message
                    or "Could not (re)start Tunarr with current filler mounts",
                    status_code=502,
                )
            detail = start_result.detail if isinstance(start_result.detail, dict) else {}
            url_hint = str(detail.get("url_hint") or "").strip()
            tunarr_url = (
                url_hint or str(getattr(settings.tunarr, "url", "") or "").strip()
            )
            if url_hint and url_hint != str(getattr(settings.tunarr, "url", "") or ""):
                settings.tunarr.url = url_hint
            _phase("waiting_ready", "Waiting for Tunarr HTTP after remount")
            ready_state = wait_for_tunarr_ready(
                tunarr_url,
                timeout_s=90.0,
                interval_s=2.0,
                lifecycle=life,
            )
            if not ready_state.get("ready"):
                raise ContinuityRepairError(
                    str(
                        ready_state.get("message")
                        or "Tunarr is not ready yet after recreate"
                    ),
                    status_code=503 if ready_state.get("still_starting") else 502,
                )

    try:
        client = tunarr_client_from_settings(settings)
    except ValueError as error:
        raise ContinuityRepairError(str(error), status_code=400) from error

    if rescan or repair:
        _phase("scoping_libraries", "Scoping Tunarr media libraries")
        try:
            libraries_state = ensure_media_libraries_enabled(
                client, scan=False, force_scan=False, settings=settings
            )
        except Exception as error:  # noqa: BLE001
            libraries_state = {
                "ok": False,
                "message": f"Could not scope Tunarr libraries: {error}"[:240],
            }

    filler: Dict[str, Any] = {}
    if rescan:
        _phase("scanning_filler", "Force-scanning filler shorts and rebuilding Continuity list")
        try:
            filler = ensure_continuity_filler_list(
                client,
                settings,
                shuffle=True,
                scan=True,
                force_scan=True,
                wait_for_programs=True,
                wait_timeout_s=60.0,
            )
        except Exception as error:  # noqa: BLE001
            raise ContinuityRepairError(
                f"Could not rebuild continuity filler list: {error}"[:400],
                status_code=502,
            ) from error
        if filler.get("ok") is False and not filler.get("ready"):
            raise ContinuityRepairError(
                str(
                    filler.get("message")
                    or "Filler rescan finished without indexed shorts"
                )[:400],
                status_code=409,
            )

    repair_result: Dict[str, Any] = {"ok": True, "skipped": True}
    if repair:
        try:
            repair_result = repair_jumpstart_stations(
                client,
                settings,
                icon_url=resolve_channel_icon_url(settings),
                refill_lineups=bool(refill_lineups),
                ensure_filler=not bool(filler.get("filler_list_id")),
                filler_list_id=str(filler.get("filler_list_id") or ""),
                on_phase=on_phase,
            )
        except Exception as error:  # noqa: BLE001
            raise ContinuityRepairError(
                f"Could not repair station continuity: {error}"[:400],
                status_code=502,
            ) from error

    if save_settings_fn is not None:
        tunarr = asdict(settings.tunarr)
        if filler.get("filler_list_id"):
            tunarr["continuity_filler_list_id"] = str(filler["filler_list_id"])
        if repair_result.get("ok") or filler.get("ok"):
            tunarr["last_error"] = ""
        save_settings_fn(
            data_dir,
            Settings.from_mapping({**asdict(settings), "tunarr": tunarr}),
        )

    message = (
        repair_result.get("message")
        or filler.get("message")
        or "Continuity update finished."
    )
    skipped_libs = (
        libraries_state.get("skipped") if isinstance(libraries_state, dict) else None
    )
    if isinstance(skipped_libs, list) and skipped_libs:
        names = ", ".join(
            str(row.get("name") or "")
            for row in skipped_libs[:4]
            if isinstance(row, dict)
        )
        if names:
            message = f"{message} Disabled out-of-scope libs: {names}."

    return {
        "ok": bool(repair_result.get("ok") or filler.get("ready")),
        "filler": filler,
        "repair": repair_result,
        "docker": docker_state,
        "ready": ready_state,
        "libraries": libraries_state,
        "message": message,
    }
