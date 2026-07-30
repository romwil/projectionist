"""Docker lifecycle for the Tunarr sibling.

Talks to the Docker Engine API over a unix socket when
``PROJECTIONIST_DOCKER_ORCHESTRATION=1`` (or settings.tunarr.docker_orchestration)
and a socket is present. Otherwise returns structured no-ops / unavailable.

Contract:
- ``pull(image)`` — ensure the pinned image exists locally
- ``start(...)`` / ``ensure_running(...)`` — create/start with a config volume
  and optional media library binds (so Tunarr ffmpeg can read Plex files locally)
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
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

PhaseCallback = Callable[[str, str], None]

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER_NAME = "projectionist-tunarr"
DEFAULT_IMAGE = "chrisbenincasa/tunarr:1.3.9"
# Prefer obscure high ports — Unraid hosts often already bind classic 8000 / 5004.
DEFAULT_HOST_PORT = 18765
DEFAULT_HDHR_PORT = 15004
# Tunarr container still listens on these internally; we remap host ports.
TUNARR_CONTAINER_HTTP_PORT = 8000
TUNARR_CONTAINER_HDHR_PORT = 5004
HOST_PORT_PROBE_ATTEMPTS = 32
HDHR_PORT_PROBE_ATTEMPTS = 16
DEFAULT_SOCKET_PATHS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
)


def normalize_bind_spec(spec: str) -> str:
    """Normalize ``host:container[:mode]`` for comparison (drop mode)."""
    text = str(spec or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return text


def parse_media_binds(value: Any) -> List[str]:
    """Parse media bind specs from a list or comma-separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [str(part).strip() for part in value]
    else:
        items = [str(value).strip()]
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        if not item or ":" not in item:
            continue
        key = normalize_bind_spec(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def resolve_media_binds(settings: Any = None) -> List[str]:
    """Media library binds for Tunarr (settings nest and/or env)."""
    from projectionist.envcompat import branded_env

    env_raw = branded_env("TUNARR_MEDIA_BINDS")
    if env_raw is not None and str(env_raw).strip() != "":
        return parse_media_binds(env_raw)
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    return parse_media_binds(getattr(tunarr, "media_binds", None) if tunarr else None)


def binds_include(current: Sequence[str], desired: Sequence[str]) -> bool:
    """True when every desired ``host:container`` appears in current binds."""
    have = {normalize_bind_spec(b) for b in current if normalize_bind_spec(b)}
    need = [normalize_bind_spec(b) for b in desired if normalize_bind_spec(b)]
    return all(key in have for key in need)


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
            "The app runs as a non-root user — recreate with --group-add "
            "matching the sock group (Unraid docker: 281), or use a BYO Tunarr URL."
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


def _parse_host_port(value: Any) -> Optional[int]:
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    if 1 <= port <= 65535:
        return port
    return None


def collect_published_host_ports(containers: Any) -> set[int]:
    """Extract published host TCP/UDP ports from Docker ``/containers/json``."""
    used: set[int] = set()
    if not isinstance(containers, list):
        return used
    for item in containers:
        if not isinstance(item, dict):
            continue
        ports = item.get("Ports") or []
        if isinstance(ports, list):
            for entry in ports:
                if not isinstance(entry, dict):
                    continue
                public = _parse_host_port(entry.get("PublicPort"))
                if public:
                    used.add(public)
        # Some engine versions also embed NetworkSettings.Ports on inspect only;
        # list endpoint uses Ports[] above.
    return used


def choose_free_port(
    preferred: int,
    used: set[int],
    *,
    attempts: int = HOST_PORT_PROBE_ATTEMPTS,
    reserved: Optional[set[int]] = None,
) -> Optional[int]:
    """Return preferred if free, else preferred+1 … for ``attempts`` candidates."""
    start = _parse_host_port(preferred) or DEFAULT_HOST_PORT
    blocked = set(used)
    if reserved:
        blocked |= set(reserved)
    for offset in range(max(1, int(attempts or 1))):
        candidate = start + offset
        if candidate > 65535:
            break
        if candidate not in blocked:
            return candidate
    return None


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
        media_binds: Optional[Sequence[str]] = None,
    ) -> None:
        self.container_name = container_name
        self.image = image
        self.socket_path = socket_path
        self.orchestration = bool(orchestration)
        self.host_port = int(host_port or DEFAULT_HOST_PORT)
        self.hdhr_port = int(hdhr_port or DEFAULT_HDHR_PORT)
        self.media_binds = parse_media_binds(media_binds or ())

    def available(self) -> bool:
        return docker_socket_available(self.socket_path)

    def can_orchestrate(self) -> bool:
        return self.orchestration and self.available()

    def list_used_host_ports(self) -> set[int]:
        """Host ports already published by any container (best-effort)."""
        try:
            code, body = self._engine_request("GET", "/containers/json?all=1")
        except Exception as error:  # noqa: BLE001
            logger.debug("list published ports failed: %s", error)
            return set()
        if code >= 400:
            return set()
        return collect_published_host_ports(body)

    def allocate_host_ports(self) -> Tuple[int, int]:
        """Pick free host ports for HTTP + HDHR before container create.

        Raises RuntimeError when no free HTTP port is found. HDHR falls back with
        a warning if the preferred range is exhausted (Plex attach uses HTTP URL).
        """
        used = self.list_used_host_ports()
        http_port = choose_free_port(
            self.host_port,
            used,
            attempts=HOST_PORT_PROBE_ATTEMPTS,
        )
        if http_port is None:
            raise RuntimeError(
                f"No free host port near {self.host_port} for Tunarr HTTP "
                f"(tried {HOST_PORT_PROBE_ATTEMPTS} candidates). "
                "Set tunarr.host_port / PROJECTIONIST_TUNARR_HOST_PORT to a free port."
            )
        hdhr_port = choose_free_port(
            self.hdhr_port,
            used,
            attempts=HDHR_PORT_PROBE_ATTEMPTS,
            reserved={http_port},
        )
        if hdhr_port is None:
            raise RuntimeError(
                f"No free host port near {self.hdhr_port} for Tunarr HDHR "
                f"(tried {HDHR_PORT_PROBE_ATTEMPTS} candidates). "
                "Free a port or set tunarr.hdhr_port / PROJECTIONIST_TUNARR_HDHR_PORT."
            )
        self.host_port = http_port
        self.hdhr_port = hdhr_port
        return http_port, hdhr_port

    def _sync_ports_from_inspect(self, body: Mapping[str, Any]) -> None:
        """Adopt published host ports from an existing container (do not recreate)."""
        ports = ((body.get("NetworkSettings") or {}).get("Ports")) or {}
        http_bindings = ports.get(f"{TUNARR_CONTAINER_HTTP_PORT}/tcp") or []
        hdhr_bindings = ports.get(f"{TUNARR_CONTAINER_HDHR_PORT}/tcp") or []
        if isinstance(http_bindings, list) and http_bindings:
            parsed = _parse_host_port((http_bindings[0] or {}).get("HostPort"))
            if parsed:
                self.host_port = parsed
        if isinstance(hdhr_bindings, list) and hdhr_bindings:
            parsed = _parse_host_port((hdhr_bindings[0] or {}).get("HostPort"))
            if parsed:
                self.hdhr_port = parsed

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
        if isinstance(body, dict):
            self._sync_ports_from_inspect(body)
        state = (body or {}).get("State") or {}
        running = bool(state.get("Running"))
        return DockerLifecycleResult(
            ok=True,
            action="status",
            status="running" if running else "stopped",
            message="Tunarr container is running." if running else "Tunarr container is stopped.",
            container_name=self.container_name,
            image=self.image,
            detail={
                "running": running,
                "status": state.get("Status"),
                "host_port": self.host_port,
                "hdhr_port": self.hdhr_port,
            },
        )

    def pull(self, *, on_phase: Optional[PhaseCallback] = None) -> DockerLifecycleResult:
        if not self.can_orchestrate():
            return self._skip(
                "pull",
                "Docker orchestration unavailable; skip pull.",
            )
        if on_phase:
            on_phase("pulling", f"Pulling image {self.image}")
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

        This is API-only — never paste into Plex. See ``_public_url_hint``.
        """
        return f"http://host.docker.internal:{self.host_port}"

    def _published_host_ip(self) -> str:
        """Best-effort HostIp from Tunarr container port bindings (non-0.0.0.0)."""
        try:
            code, body = self._engine_request(
                "GET", f"/containers/{self.container_name}/json"
            )
        except Exception:  # noqa: BLE001
            return ""
        if code >= 400 or not isinstance(body, dict):
            return ""
        ports = ((body.get("NetworkSettings") or {}).get("Ports")) or {}
        for key in (
            f"{TUNARR_CONTAINER_HTTP_PORT}/tcp",
            f"{self.host_port}/tcp",
        ):
            bindings = ports.get(key) or []
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                host_ip = str(binding.get("HostIp") or "").strip()
                if host_ip and host_ip not in {"0.0.0.0", "::", ""}:
                    return host_ip
        return ""

    def _public_url_hint(self) -> str:
        """LAN-facing Tunarr base for Plex attach (never host.docker.internal)."""
        from projectionist.live_channels.plex_attach import derive_managed_public_url

        return derive_managed_public_url(
            host_port=self.host_port,
            published_host_ip=self._published_host_ip(),
        )

    def _url_hints_detail(self) -> Dict[str, Any]:
        detail: Dict[str, Any] = {
            "url_hint": self._reachable_url_hint(),
            "host_port": self.host_port,
            "hdhr_port": self.hdhr_port,
        }
        public = self._public_url_hint()
        if public:
            detail["public_url_hint"] = public
        if self.media_binds:
            detail["media_binds"] = list(self.media_binds)
        return detail

    def _inspect_binds(self) -> List[str]:
        """HostConfig.Binds from the named container (empty when missing)."""
        try:
            code, body = self._engine_request(
                "GET", f"/containers/{self.container_name}/json"
            )
        except Exception:  # noqa: BLE001
            return []
        if code >= 400 or not isinstance(body, dict):
            return []
        if isinstance(body, dict):
            self._sync_ports_from_inspect(body)
        binds = ((body.get("HostConfig") or {}).get("Binds")) or []
        if not isinstance(binds, list):
            return []
        return [str(b) for b in binds if str(b).strip()]

    def _config_binds(self, config_volume: str) -> List[str]:
        volume = str(config_volume or "").strip()
        binds: List[str] = [f"{volume}:/config"] if volume else []
        for spec in self.media_binds:
            key = normalize_bind_spec(spec)
            if key and key not in {normalize_bind_spec(b) for b in binds}:
                binds.append(spec)
        return binds

    def _needs_recreate_for_binds(self, config_volume: str) -> bool:
        if not self.media_binds:
            return False
        current = self._inspect_binds()
        return not binds_include(current, self.media_binds) or (
            bool(config_volume)
            and not binds_include(current, [f"{config_volume}:/config"])
        )

    def _remove_container(self) -> Optional[str]:
        """Stop + remove named container; return error message or None."""
        try:
            self._engine_request(
                "POST",
                f"/containers/{self.container_name}/stop?t=10",
                expect_json=False,
            )
        except Exception as error:  # noqa: BLE001
            logger.debug("Tunarr stop before recreate: %s", error)
        try:
            code, _ = self._engine_request(
                "DELETE",
                f"/containers/{self.container_name}?force=1",
                expect_json=False,
            )
        except Exception as error:  # noqa: BLE001
            return f"Docker remove failed: {error}"[:240]
        if code not in (204, 404) and code >= 400:
            return f"Docker remove returned HTTP {code}"
        return None

    def _create_and_start(
        self,
        *,
        config_volume: str,
        on_phase: Optional[PhaseCallback] = None,
        allocate_ports: bool = True,
    ) -> DockerLifecycleResult:
        volume = str(config_volume or "").strip()
        if allocate_ports:
            try:
                self.allocate_host_ports()
            except RuntimeError as error:
                return DockerLifecycleResult(
                    ok=False,
                    action="start",
                    status="error",
                    message=str(error)[:240],
                    container_name=self.container_name,
                    image=self.image,
                )
        if on_phase:
            on_phase("creating", "Creating Tunarr container")
        binds = self._config_binds(volume)
        http_key = f"{TUNARR_CONTAINER_HTTP_PORT}/tcp"
        hdhr_key = f"{TUNARR_CONTAINER_HDHR_PORT}/tcp"
        body = {
            "Image": self.image,
            "ExposedPorts": {
                http_key: {},
                hdhr_key: {},
            },
            "HostConfig": {
                "Binds": binds,
                "PortBindings": {
                    http_key: [{"HostPort": str(self.host_port)}],
                    hdhr_key: [{"HostPort": str(self.hdhr_port)}],
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
            return self.start(config_volume=volume, on_phase=on_phase)
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
        if on_phase:
            on_phase("starting", "Starting Tunarr container")
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
            "Tunarr docker started name=%s image=%s volume=%s media_binds=%s",
            self.container_name,
            self.image,
            volume or "(none)",
            self.media_binds or [],
        )
        detail = self._url_hints_detail()
        detail["container_id"] = cid[:12] if cid else ""
        detail["binds"] = binds
        return DockerLifecycleResult(
            ok=True,
            action="start",
            status="running",
            message=f"Created and started Tunarr ({self.image}).",
            container_name=self.container_name,
            image=self.image,
            detail=detail,
        )

    def start(
        self,
        *,
        config_volume: str = "",
        on_phase: Optional[PhaseCallback] = None,
    ) -> DockerLifecycleResult:
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
        if existing.status in {"running", "stopped"} and self._needs_recreate_for_binds(
            volume
        ):
            if on_phase:
                on_phase(
                    "creating",
                    "Recreating Tunarr with media library mounts",
                )
            err = self._remove_container()
            if err:
                return DockerLifecycleResult(
                    ok=False,
                    action="start",
                    status="error",
                    message=err,
                    container_name=self.container_name,
                    image=self.image,
                )
            # Keep already-synced host ports; do not re-probe into a new pair.
            return self._create_and_start(
                config_volume=volume,
                on_phase=on_phase,
                allocate_ports=False,
            )

        if existing.status == "running":
            # status() already synced published ports from the living container.
            if on_phase:
                on_phase("starting", "Tunarr container already running.")
            return DockerLifecycleResult(
                ok=True,
                action="start",
                status="running",
                message="Tunarr container already running.",
                container_name=self.container_name,
                image=self.image,
                detail=self._url_hints_detail(),
            )
        if existing.status == "stopped":
            if on_phase:
                on_phase("starting", "Starting existing Tunarr container")
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
                detail=self._url_hints_detail(),
            )

        # missing or unknown — probe free host ports, then create + start
        return self._create_and_start(
            config_volume=volume,
            on_phase=on_phase,
            allocate_ports=True,
        )

    def ensure_running(
        self,
        *,
        config_volume: str = "",
        on_phase: Optional[PhaseCallback] = None,
    ) -> DockerLifecycleResult:
        """Pull pinned image (best-effort) then start/create the container."""
        if not self.can_orchestrate():
            return self._skip(
                "ensure_running",
                "Docker orchestration unavailable; skip ensure_running.",
            )
        pull_result = self.pull(on_phase=on_phase)
        if not pull_result.ok:
            # Still try start if image may already be local
            logger.warning("Tunarr pull soft-failed: %s", pull_result.message)
        start_result = self.start(config_volume=config_volume, on_phase=on_phase)
        detail: Dict[str, Any] = {
            "pull": pull_result.to_dict(),
            "start": start_result.to_dict(),
        }
        start_detail = start_result.detail if isinstance(start_result.detail, dict) else {}
        url_hint = str(start_detail.get("url_hint") or "").strip()
        public_hint = str(start_detail.get("public_url_hint") or "").strip()
        if start_result.ok and start_result.status == "running":
            detail["url_hint"] = url_hint or self._reachable_url_hint()
            public_hint = public_hint or self._public_url_hint()
            if public_hint:
                detail["public_url_hint"] = public_hint
            detail["host_port"] = int(
                start_detail.get("host_port") or self.host_port or DEFAULT_HOST_PORT
            )
            detail["hdhr_port"] = int(
                start_detail.get("hdhr_port") or self.hdhr_port or DEFAULT_HDHR_PORT
            )
            if start_detail.get("container_id"):
                detail["container_id"] = start_detail.get("container_id")
            if on_phase:
                on_phase("waiting_ready", "Waiting for Tunarr ready")
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

    def container_logs(self, *, tail: int = 200) -> str:
        """Return recent stdout/stderr from the Tunarr container (Docker Engine API)."""
        if not self.available():
            raise RuntimeError(_socket_unavailable_message(self.socket_path))
        limit = max(1, min(int(tail or 200), 2000))
        name = quote(self.container_name, safe="")
        path = (
            f"/containers/{name}/logs"
            f"?stdout=1&stderr=1&timestamps=1&tail={limit}"
        )
        status, body = self._engine_request(
            "GET", path, expect_json=False, timeout=30.0, raw_text=True
        )
        if status == 404:
            raise RuntimeError(
                f"Container {self.container_name} not found — start the broadcast engine first."
            )
        if status >= 400:
            raise RuntimeError(
                f"Docker logs HTTP {status} for {self.container_name}"
            )
        if isinstance(body, (bytes, bytearray)):
            text = _decode_docker_multiplexed_logs(bytes(body))
        else:
            text = str(body or "")
        return text

    def _engine_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        expect_json: bool = True,
        timeout: float = 120.0,
        raw_text: bool = False,
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
        if raw_text:
            return response.status_code, response.content
        if not expect_json or not response.content:
            return response.status_code, None
        try:
            return response.status_code, response.json()
        except Exception:  # noqa: BLE001
            return response.status_code, None


def _decode_docker_multiplexed_logs(payload: bytes) -> str:
    """Strip Docker Engine multiplexed stream headers (8 bytes per frame)."""
    if not payload:
        return ""
    # Heuristic: multiplexed frames start with stream type 1/2 and size in big-endian.
    if len(payload) < 8 or payload[0] not in (0, 1, 2):
        return payload.decode("utf-8", errors="replace")
    out = bytearray()
    offset = 0
    while offset + 8 <= len(payload):
        size = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        offset += 8
        chunk = payload[offset : offset + size]
        if len(chunk) < size:
            out.extend(chunk)
            break
        out.extend(chunk)
        offset += size
    if not out:
        return payload.decode("utf-8", errors="replace")
    return out.decode("utf-8", errors="replace")


def lifecycle_from_settings(
    settings: Any,
    *,
    socket_path: Optional[str] = None,
) -> TunarrDockerLifecycle:
    tunarr = getattr(settings, "tunarr", None)
    preferred_http = _parse_host_port(getattr(tunarr, "host_port", None)) or DEFAULT_HOST_PORT
    preferred_hdhr = _parse_host_port(getattr(tunarr, "hdhr_port", None)) or DEFAULT_HDHR_PORT
    return TunarrDockerLifecycle(
        image=resolve_image(settings),
        socket_path=socket_path,
        orchestration=orchestration_enabled(settings),
        host_port=preferred_http,
        hdhr_port=preferred_hdhr,
        media_binds=resolve_media_binds(settings),
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
