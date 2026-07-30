"""Docker lifecycle for the Tunarr sibling.

Talks to the Docker Engine API over a unix socket when
``PROJECTIONIST_DOCKER_ORCHESTRATION=1`` (or settings.tunarr.docker_orchestration)
and a socket is present. Otherwise returns structured no-ops / unavailable.

Contract:
- ``pull(image)`` — ensure the pinned image exists locally
- ``start(...)`` / ``ensure_running(...)`` — create/start with a config volume
- ``stop(...)`` — stop the container; **keep** the volume (disable ≠ wipe)
- ``status(...)`` — running / stopped / missing / unavailable / skipped
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER_NAME = "projectionist-tunarr"
DEFAULT_IMAGE = "chrisbenincasa/tunarr:1.3.9"
DEFAULT_HOST_PORT = 8000
DEFAULT_HDHR_PORT = 5004
DEFAULT_SOCKET_PATHS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
)


@dataclass(frozen=True)
class DockerLifecycleResult:
    ok: bool
    action: str
    status: str
    message: str
    container_name: str = DEFAULT_CONTAINER_NAME
    image: str = DEFAULT_IMAGE
    detail: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "container_name": self.container_name,
            "image": self.image,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


def docker_socket_available(socket_path: Optional[str] = None) -> bool:
    """True when a Docker engine socket exists and is connectable.

    Existence alone is not enough on Unraid when the process is non-root and
    ``docker.sock`` is mode ``660`` root:docker — report that via
    :func:`docker_socket_status` instead of a false "not found".
    """
    return docker_socket_status(socket_path).get("accessible") is True


def docker_socket_status(socket_path: Optional[str] = None) -> Dict[str, Any]:
    """Probe Docker socket presence + connect permission.

    Returns ``{path, present, accessible, error}`` where ``error`` is one of
    ``None``, ``"not_found"``, ``"permission_denied"``, or a short OSError text.
    """
    path = resolve_docker_socket(socket_path)
    if not path:
        return {
            "path": None,
            "present": False,
            "accessible": False,
            "error": "not_found",
        }
    try:
        import socket as _socket

        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        try:
            sock.connect(path)
        finally:
            sock.close()
    except PermissionError:
        return {
            "path": path,
            "present": True,
            "accessible": False,
            "error": "permission_denied",
        }
    except OSError as error:
        err = str(error) or error.__class__.__name__
        lowered = err.lower()
        kind = "permission_denied" if "permission" in lowered else err[:120]
        return {
            "path": path,
            "present": True,
            "accessible": False,
            "error": kind,
        }
    return {"path": path, "present": True, "accessible": True, "error": None}



def _socket_unavailable_message(socket_path: Optional[str] = None) -> str:
    status = docker_socket_status(socket_path)
    if status.get("error") == "permission_denied":
        return (
            "Docker socket is present but not accessible (permission denied). "
            "Run as root, add the docker group, or use a BYO Tunarr URL."
        )
    if status.get("present") and not status.get("accessible"):
        detail = status.get("error") or "inaccessible"
        return f"Docker socket present but {detail}; use a BYO Tunarr URL or fix socket access."
    return "No Docker socket; use BYO Tunarr URL or mount the socket."


def resolve_docker_socket(socket_path: Optional[str] = None) -> Optional[str]:
    candidates = [socket_path] if socket_path else list(DEFAULT_SOCKET_PATHS)
    env_host = (os.environ.get("DOCKER_HOST") or "").strip()
    if env_host.startswith("unix://"):
        candidates.insert(0, env_host[len("unix://") :])
    for path in candidates:
        if path and Path(path).exists():
            return str(path)
    return None


def orchestration_enabled(settings: Any = None) -> bool:
    """Settings/env gate for dynamic Tunarr include."""
    if settings is not None:
        tunarr = getattr(settings, "tunarr", None)
        if tunarr is not None and bool(getattr(tunarr, "docker_orchestration", False)):
            return True
    from projectionist.envcompat import env_bool

    return bool(env_bool("PROJECTIONIST_DOCKER_ORCHESTRATION"))


def resolve_image(settings: Any = None) -> str:
    if settings is not None:
        tunarr = getattr(settings, "tunarr", None)
        tag = str(getattr(tunarr, "image_tag", "") or "").strip() if tunarr else ""
        if tag:
            return tag
    return DEFAULT_IMAGE


def _split_image(image: str) -> Tuple[str, str]:
    cleaned = str(image or DEFAULT_IMAGE).strip() or DEFAULT_IMAGE
    if ":" in cleaned.rsplit("/", 1)[-1]:
        repo, tag = cleaned.rsplit(":", 1)
        return repo, tag
    return cleaned, "latest"


class TunarrDockerLifecycle:
    """Pull / start / stop interface for the Tunarr sidecar."""

    def __init__(
        self,
        *,
        container_name: str = DEFAULT_CONTAINER_NAME,
        image: str = DEFAULT_IMAGE,
        socket_path: Optional[str] = None,
        orchestration: bool = False,
        host_port: int = DEFAULT_HOST_PORT,
        hdhr_port: int = DEFAULT_HDHR_PORT,
    ) -> None:
        self.container_name = container_name
        self.image = image
        self.socket_path = socket_path
        self.orchestration = bool(orchestration)
        self.host_port = int(host_port)
        self.hdhr_port = int(hdhr_port)

    def available(self) -> bool:
        return docker_socket_available(self.socket_path)

    def can_orchestrate(self) -> bool:
        return self.orchestration and self.available()

    def status(self) -> DockerLifecycleResult:
        if not self.available():
            return DockerLifecycleResult(
                ok=False,
                action="status",
                status="unavailable",
                message=_socket_unavailable_message(self.socket_path),
                container_name=self.container_name,
                image=self.image,
            )
        if not self.orchestration:
            return DockerLifecycleResult(
                ok=True,
                action="status",
                status="skipped",
                message=(
                    "Docker socket present; orchestration is off "
                    "(enable settings or PROJECTIONIST_DOCKER_ORCHESTRATION=1)."
                ),
                container_name=self.container_name,
                image=self.image,
            )
        try:
            code, body = self._engine_request("GET", f"/containers/{self.container_name}/json")
        except Exception as error:  # noqa: BLE001
            return DockerLifecycleResult(
                ok=False,
                action="status",
                status="error",
                message=f"Docker inspect failed: {error}"[:240],
                container_name=self.container_name,
                image=self.image,
            )
        if code == 404:
            return DockerLifecycleResult(
                ok=True,
                action="status",
                status="missing",
                message="Tunarr container not found.",
                container_name=self.container_name,
                image=self.image,
            )
        if code >= 400:
            return DockerLifecycleResult(
                ok=False,
                action="status",
                status="error",
                message=f"Docker inspect returned HTTP {code}",
                container_name=self.container_name,
                image=self.image,
                detail={"http_status": code},
            )
        state = (body or {}).get("State") or {}
        running = bool(state.get("Running"))
        return DockerLifecycleResult(
            ok=True,
            action="status",
            status="running" if running else "stopped",
            message="Tunarr container is running." if running else "Tunarr container is stopped.",
            container_name=self.container_name,
            image=self.image,
            detail={"running": running, "status": state.get("Status")},
        )

    def pull(self) -> DockerLifecycleResult:
        if not self.can_orchestrate():
            return self._skip(
                "pull",
                "Docker orchestration unavailable; skip pull.",
            )
        repo, tag = _split_image(self.image)
        try:
            code, _body = self._engine_request(
                "POST",
                f"/images/create?fromImage={quote(repo, safe='/:@')}&tag={quote(tag)}",
                expect_json=False,
            )
        except Exception as error:  # noqa: BLE001
            return DockerLifecycleResult(
                ok=False,
                action="pull",
                status="error",
                message=f"Docker pull failed: {error}"[:240],
                container_name=self.container_name,
                image=self.image,
            )
        if code >= 400:
            return DockerLifecycleResult(
                ok=False,
                action="pull",
                status="error",
                message=f"Docker pull returned HTTP {code}",
                container_name=self.container_name,
                image=self.image,
            )
        logger.info("Tunarr docker pull ok image=%s", self.image)
        return DockerLifecycleResult(
            ok=True,
            action="pull",
            status="pulled",
            message=f"Pulled {self.image}",
            container_name=self.container_name,
            image=self.image,
        )

    def _reachable_url_hint(self) -> str:
        """URL Projectionist (in Docker) should use to reach published Tunarr.

        Sibling containers must not use 127.0.0.1 (that is the Projectionist
        container itself). host.docker.internal works with Unraid ExtraParams /
        compose extra_hosts host-gateway.
        """
        return f"http://host.docker.internal:{self.host_port}"

    def start(self, *, config_volume: str = "") -> DockerLifecycleResult:
        if not self.can_orchestrate():
            return self._skip("start", "Docker orchestration unavailable; skip start.")
        volume = str(config_volume or "").strip()
        if volume:
            try:
                Path(volume).mkdir(parents=True, exist_ok=True)
            except OSError as error:
                # Host-only paths (PROJECTIONIST_HOST_DATA_DIR) are not writable
                # inside the Projectionist container; Docker creates the bind.
                logger.debug("config_volume mkdir skipped for %s: %s", volume, error)

        existing = self.status()
        if existing.status == "running":
            return DockerLifecycleResult(
                ok=True,
                action="start",
                status="running",
                message="Tunarr container already running.",
                container_name=self.container_name,
                image=self.image,
                detail={"url_hint": self._reachable_url_hint()},
            )
        if existing.status == "stopped":
            try:
                code, _ = self._engine_request(
                    "POST",
                    f"/containers/{self.container_name}/start",
                    expect_json=False,
                )
            except Exception as error:  # noqa: BLE001
                return DockerLifecycleResult(
                    ok=False,
                    action="start",
                    status="error",
                    message=f"Docker start failed: {error}"[:240],
                    container_name=self.container_name,
                    image=self.image,
                )
            if code not in (204, 304) and code >= 400:
                return DockerLifecycleResult(
                    ok=False,
                    action="start",
                    status="error",
                    message=f"Docker start returned HTTP {code}",
                    container_name=self.container_name,
                    image=self.image,
                )
            return DockerLifecycleResult(
                ok=True,
                action="start",
                status="running",
                message="Started existing Tunarr container.",
                container_name=self.container_name,
                image=self.image,
                detail={"url_hint": self._reachable_url_hint()},
            )

        # missing or unknown — create then start
        binds = [f"{volume}:/config"] if volume else []
        body = {
            "Image": self.image,
            "ExposedPorts": {
                "8000/tcp": {},
                "5004/tcp": {},
            },
            "HostConfig": {
                "Binds": binds,
                "PortBindings": {
                    "8000/tcp": [{"HostPort": str(self.host_port)}],
                    "5004/tcp": [{"HostPort": str(self.hdhr_port)}],
                },
                "RestartPolicy": {"Name": "unless-stopped"},
            },
        }
        try:
            code, created = self._engine_request(
                "POST",
                f"/containers/create?name={quote(self.container_name)}",
                json_body=body,
            )
        except Exception as error:  # noqa: BLE001
            return DockerLifecycleResult(
                ok=False,
                action="start",
                status="error",
                message=f"Docker create failed: {error}"[:240],
                container_name=self.container_name,
                image=self.image,
            )
        if code == 409:
            # Name conflict — try start of existing
            return self.start(config_volume=volume)
        if code >= 400:
            return DockerLifecycleResult(
                ok=False,
                action="start",
                status="error",
                message=f"Docker create returned HTTP {code}",
                container_name=self.container_name,
                image=self.image,
                detail={"response": created} if created else None,
            )
        cid = str((created or {}).get("Id") or self.container_name)
        try:
            start_code, _ = self._engine_request(
                "POST",
                f"/containers/{cid}/start",
                expect_json=False,
            )
        except Exception as error:  # noqa: BLE001
            return DockerLifecycleResult(
                ok=False,
                action="start",
                status="error",
                message=f"Docker start after create failed: {error}"[:240],
                container_name=self.container_name,
                image=self.image,
            )
        if start_code not in (204, 304) and start_code >= 400:
            return DockerLifecycleResult(
                ok=False,
                action="start",
                status="error",
                message=f"Docker start returned HTTP {start_code}",
                container_name=self.container_name,
                image=self.image,
            )
        logger.info(
            "Tunarr docker started name=%s image=%s volume=%s",
            self.container_name,
            self.image,
            volume or "(none)",
        )
        return DockerLifecycleResult(
            ok=True,
            action="start",
            status="running",
            message=f"Created and started Tunarr ({self.image}).",
            container_name=self.container_name,
            image=self.image,
            detail={"url_hint": self._reachable_url_hint()},
        )

    def ensure_running(self, *, config_volume: str = "") -> DockerLifecycleResult:
        """Pull pinned image (best-effort) then start/create the container."""
        if not self.can_orchestrate():
            return self._skip(
                "ensure_running",
                "Docker orchestration unavailable; skip ensure_running.",
            )
        pull_result = self.pull()
        if not pull_result.ok:
            # Still try start if image may already be local
            logger.warning("Tunarr pull soft-failed: %s", pull_result.message)
        start_result = self.start(config_volume=config_volume)
        detail: Dict[str, Any] = {
            "pull": pull_result.to_dict(),
            "start": start_result.to_dict(),
        }
        start_detail = start_result.detail if isinstance(start_result.detail, dict) else {}
        url_hint = str(start_detail.get("url_hint") or "").strip()
        if start_result.ok and start_result.status == "running":
            detail["url_hint"] = url_hint or self._reachable_url_hint()
        return DockerLifecycleResult(
            ok=start_result.ok,
            action="ensure_running",
            status=start_result.status,
            message=start_result.message
            if start_result.ok
            else f"{pull_result.message}; {start_result.message}",
            container_name=self.container_name,
            image=self.image,
            detail=detail,
        )

    def stop(self, *, keep_volume: bool = True) -> DockerLifecycleResult:
        """Stop the sidecar. Volume is always retained in v1 (disable ≠ wipe)."""
        if not keep_volume:
            logger.warning("keep_volume=False ignored; volume retention is mandatory")
        if not self.can_orchestrate():
            return self._skip("stop", "Docker orchestration unavailable; skip stop.")
        try:
            code, _ = self._engine_request(
                "POST",
                f"/containers/{self.container_name}/stop?t=10",
                expect_json=False,
            )
        except Exception as error:  # noqa: BLE001
            return DockerLifecycleResult(
                ok=False,
                action="stop",
                status="error",
                message=f"Docker stop failed: {error}"[:240],
                container_name=self.container_name,
                image=self.image,
            )
        if code == 404:
            return DockerLifecycleResult(
                ok=True,
                action="stop",
                status="missing",
                message="Tunarr container not found (already stopped).",
                container_name=self.container_name,
                image=self.image,
            )
        if code not in (204, 304) and code >= 400:
            return DockerLifecycleResult(
                ok=False,
                action="stop",
                status="error",
                message=f"Docker stop returned HTTP {code}",
                container_name=self.container_name,
                image=self.image,
            )
        logger.info(
            "Tunarr docker stopped name=%s (volume retained)",
            self.container_name,
        )
        return DockerLifecycleResult(
            ok=True,
            action="stop",
            status="stopped",
            message="Stopped Tunarr container; config volume kept.",
            container_name=self.container_name,
            image=self.image,
        )

    def _skip(self, action: str, message: str) -> DockerLifecycleResult:
        return DockerLifecycleResult(
            ok=False,
            action=action,
            status="unavailable",
            message=message,
            container_name=self.container_name,
            image=self.image,
        )

    def _engine_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        expect_json: bool = True,
        timeout: float = 120.0,
    ) -> Tuple[int, Any]:
        """HTTP call to Docker Engine via unix socket (httpx UDS transport)."""
        import httpx

        sock = resolve_docker_socket(self.socket_path)
        if not sock:
            raise RuntimeError("Docker socket not available")
        transport = httpx.HTTPTransport(uds=sock)
        url = f"http://docker{path}"
        content = None
        headers: Dict[str, str] = {}
        if json_body is not None:
            content = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.request(method, url, content=content, headers=headers)
        if not expect_json or not response.content:
            return response.status_code, None
        try:
            return response.status_code, response.json()
        except Exception:  # noqa: BLE001
            return response.status_code, None


def lifecycle_from_settings(
    settings: Any,
    *,
    socket_path: Optional[str] = None,
) -> TunarrDockerLifecycle:
    return TunarrDockerLifecycle(
        image=resolve_image(settings),
        socket_path=socket_path,
        orchestration=orchestration_enabled(settings),
    )


def resolve_config_volume(settings: Any, data_dir: Path | str) -> str:
    """Absolute **host** path for Tunarr `/config` bind mount under DATA_DIR.

    When Projectionist runs in Docker with the engine socket mounted, paths
    passed to the Docker API are interpreted on the **host**. Set
    ``PROJECTIONIST_HOST_DATA_DIR`` (or ``HOST_DATA_DIR``) to the host-side
    path of the config volume (e.g. ``/mnt/user/appdata/projectionist/config``)
    so sibling binds land under appdata instead of a bogus host ``/config/...``.
    """
    tunarr = getattr(settings, "tunarr", None)
    rel = str(getattr(tunarr, "volume_path", "") or "tunarr").strip() or "tunarr"
    # Reject absolute escapes; keep under data_dir / host data dir.
    safe = Path(rel).name if Path(rel).is_absolute() else Path(rel)
    host_root = (
        os.environ.get("PROJECTIONIST_HOST_DATA_DIR")
        or os.environ.get("HOST_DATA_DIR")
        or ""
    ).strip()
    root = Path(host_root) if host_root else Path(data_dir)
    # Host roots from env are already absolute; do not resolve() against the
    # container cwd (which would invent a non-existent /app/... path).
    if host_root:
        path = (root / safe) if not root.is_absolute() else root / safe
        path = Path(os.path.normpath(str(path)))
        try:
            path.relative_to(Path(os.path.normpath(str(root))))
        except ValueError:
            path = Path(os.path.normpath(str(root / "tunarr")))
        return str(path)
    path = (root / safe).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        path = (root / "tunarr").resolve()
    return str(path)


def disk_free_bytes(path: Path | str) -> Optional[int]:
    """Best-effort free bytes for preflight (~1GB image check)."""
    try:
        usage = shutil.disk_usage(str(path))
        return int(usage.free)
    except Exception:  # noqa: BLE001
        return None
