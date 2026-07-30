"""Live Channels enable-wizard preflight checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from projectionist.live_channels.docker import (
    disk_free_bytes,
    docker_socket_status,
    orchestration_enabled,
)
from projectionist.live_channels.plex_pass import check_plex_pass

# Soft floor for Tunarr image + headroom (~1GB).
_MIN_FREE_BYTES = 1_200_000_000


def run_preflight(
    settings: Any,
    *,
    data_dir: Optional[Path | str] = None,
    owner_confirmed_plex_pass: Optional[bool] = None,
) -> Dict[str, Any]:
    """Return structured preflight checklist for the owner enable flow."""
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    features = getattr(settings, "features", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))

    orch = orchestration_enabled(settings)
    sock = docker_socket_status()
    socket_ok = bool(sock.get("accessible"))
    docker_check = {
        "id": "docker_orchestration",
        "ok": orch and socket_ok,
        "soft": True,
        "label": "Docker orchestration",
        "message": _docker_message(orch, sock),
        "orchestration_enabled": orch,
        "socket_available": socket_ok,
        "socket_present": bool(sock.get("present")),
        "socket_error": sock.get("error"),
        "socket_path": sock.get("path"),
    }

    free = disk_free_bytes(data_dir or Path.cwd())
    disk_ok = free is None or free >= _MIN_FREE_BYTES
    disk_check = {
        "id": "disk_space",
        "ok": disk_ok,
        "soft": True,
        "label": "Disk space (~1 GB for Tunarr image)",
        "message": (
            "Could not measure free disk; ensure ~1 GB is available for the Tunarr image."
            if free is None
            else (
                f"{free // (1024 * 1024)} MB free — enough for the pinned Tunarr image."
                if disk_ok
                else f"Only {free // (1024 * 1024)} MB free; Tunarr image needs ~1 GB."
            )
        ),
        "free_bytes": free,
    }

    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    plex_reachable = False
    plex_message = "Plex URL and token are not configured."
    if plex_url and plex_token:
        try:
            from projectionist.connectors.plex import PlexClient

            client = PlexClient(plex_url, plex_token)
            machine_id, friendly = client.server_identity()
            plex_reachable = True
            plex_message = f"Plex reachable — {friendly or machine_id or 'server'}."
        except Exception as error:  # noqa: BLE001
            plex_message = f"Plex not reachable: {error}"[:200]

    plex_check = {
        "id": "plex_reachable",
        "ok": plex_reachable,
        "soft": False,
        "label": "Plex reachable",
        "message": plex_message,
    }

    confirmed = owner_confirmed_plex_pass
    if confirmed is None and tunarr is not None:
        stored = getattr(tunarr, "plex_pass_confirmed", None)
        if stored is True:
            confirmed = True
        elif stored is False:
            confirmed = False

    plex_pass = check_plex_pass(settings=settings, owner_confirmed=confirmed)
    pass_check = {
        "id": "plex_pass",
        "ok": plex_pass.get("status") == "confirmed",
        "soft": True,
        "label": "Plex Pass / Live TV",
        "message": plex_pass.get("message") or "",
        "status": plex_pass.get("status"),
        "detection": plex_pass.get("detection"),
    }

    tunarr_url_check = {
        "id": "tunarr_url",
        "ok": bool(url) or (orch and socket_ok),
        "soft": False,
        "label": "Tunarr URL or managed Docker",
        "message": (
            f"Tunarr URL configured: {url}"
            if url
            else (
                "No Tunarr URL yet — managed Docker can start a sibling, or set a BYO URL."
                if orch and socket_ok
                else "Set a BYO Tunarr URL (Docker orchestration is not available)."
            )
        ),
        "url": url,
    }

    gpu_check = {
        "id": "gpu",
        "ok": True,
        "soft": True,
        "label": "GPU (optional)",
        "message": (
            "Soft-transcode without a GPU is fine for a single stream. "
            "Multi-stream or heavy libraries may need GPU later — not a hard block."
        ),
    }

    checks: List[Dict[str, Any]] = [
        docker_check,
        disk_check,
        plex_check,
        pass_check,
        tunarr_url_check,
        gpu_check,
    ]
    hard_failures = [c for c in checks if not c["ok"] and not c.get("soft")]
    ready = not hard_failures and plex_check["ok"] and tunarr_url_check["ok"]

    return {
        "ok": ready,
        "ready": ready,
        "live_channels_enabled": enabled,
        "checks": checks,
        "summary": (
            "Preflight looks good — you can continue."
            if ready
            else "Fix the failing required checks before publishing channels."
        ),
    }


def _docker_message(orch: bool, sock: Dict[str, Any] | bool) -> str:
    if isinstance(sock, bool):
        socket_ok = sock
        present = sock
        err = None if sock else "not_found"
    else:
        socket_ok = bool(sock.get("accessible"))
        present = bool(sock.get("present"))
        err = sock.get("error")
    if orch and socket_ok:
        return "Docker orchestration is on and a socket is available."
    if socket_ok and not orch:
        return (
            "Docker socket is present, but orchestration is off. "
            "Enable it in settings or set PROJECTIONIST_DOCKER_ORCHESTRATION=1."
        )
    if orch and present and err == "permission_denied":
        return (
            "Orchestration is on, but the Docker socket is not accessible "
            "(permission denied). Run Projectionist as root, add the docker "
            "group, or set a BYO Tunarr URL."
        )
    if orch and present and not socket_ok:
        detail = err or "inaccessible"
        return (
            f"Orchestration is on, but the Docker socket is {detail} — "
            "use a BYO Tunarr URL or fix socket access."
        )
    if orch and not socket_ok:
        return "Orchestration is on, but no Docker socket was found — use a BYO Tunarr URL."
    return "No Docker socket; Live Channels can still use a BYO Tunarr URL."
