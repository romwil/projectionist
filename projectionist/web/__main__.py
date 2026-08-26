"""Uvicorn entry point — main app + lobby theater on a second port."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Hostnames that resolve to the local loopback interface only.
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "ip6-localhost"})

# Bare uvicorn (QA :8790 has no Caddy) must drop Slowloris / incomplete clients.
UVICORN_TIMEOUT_KEEP_ALIVE = 5
UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE = 16 * 1024


def resolve_host() -> str:
    """Bind host for the server.

    Defaults to ``0.0.0.0`` so the container port mapping works out of the box
    on Docker / Unraid (the app must listen on all interfaces *inside* the
    container). Operators running bare-metal can restrict exposure by setting
    ``HOST`` (uvicorn convention) or ``PROJECTIONIST_HOST`` /
    ``CURATORX_HOST`` to e.g. ``127.0.0.1``.
    """
    from projectionist.envcompat import branded_env

    host = (os.environ.get("HOST") or branded_env("HOST") or "").strip()
    return host or "0.0.0.0"


def resolve_theater_port() -> int:
    from projectionist.theater import DEFAULT_THEATER_PORT

    raw = (os.environ.get("PROJECTIONIST_THEATER_PORT") or "").strip()
    try:
        return int(raw) if raw else DEFAULT_THEATER_PORT
    except ValueError:
        return DEFAULT_THEATER_PORT


def _is_loopback_host(host: str) -> bool:
    normalized = (host or "").strip().lower()
    if normalized in _LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def bind_exposed_without_auth(host: str, *, multi_user_enabled: bool) -> bool:
    """True when the server will listen beyond loopback with no login gate.

    In single-owner mode (multi-user disabled) there is no authentication, so
    anyone who can reach the port gets full admin. Binding that to a
    non-loopback interface is the exposure called out by SECURITY.md S3 /
    review finding C2. Returns ``False`` for loopback binds or when multi-user
    auth is enabled.
    """
    return not _is_loopback_host(host) and not multi_user_enabled


def _multi_user_enabled() -> bool:
    """Best-effort read of the auth posture for the startup warning.

    Never raises: a config problem must not stop the server from booting.
    """
    try:
        from projectionist.config_store import load_merged_settings

        data_dir = Path(os.environ.get("DATA_DIR", "/config"))
        return bool(load_merged_settings(data_dir).features.multi_user_enabled)
    except Exception:  # pragma: no cover - defensive; warning is advisory only
        logger.debug("Could not resolve auth posture for exposure check", exc_info=True)
        return False


def warn_if_exposed_without_auth(host: str, port: int) -> None:
    if bind_exposed_without_auth(host, multi_user_enabled=_multi_user_enabled()):
        logger.warning(
            "Projectionist is binding to %s:%s with authentication DISABLED "
            "(single-owner mode): anyone who can reach this port has full admin "
            "access. To harden, set HOST=127.0.0.1 (or PROJECTIONIST_HOST), put "
            "Projectionist behind an authenticating reverse proxy, or enable "
            "multi-user auth. See SECURITY.md (S3).",
            host,
            port,
        )


def _uvicorn_config(app: str, *, host: str, port: int, log_level: str):
    import uvicorn

    return uvicorn.Config(
        app,
        host=host,
        port=port,
        reload=False,
        log_level=log_level,
        timeout_keep_alive=UVICORN_TIMEOUT_KEEP_ALIVE,
        h11_max_incomplete_event_size=UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE,
    )


async def _serve_dual(*, host: str, main_port: int, theater_port: int, log_level: str) -> None:
    import uvicorn

    from projectionist.theater.app import create_theater_app
    from projectionist.web.jobs import get_job_manager

    # Ensure job manager / DB exist before theater binds (shared DATA_DIR).
    data_dir = Path(os.environ.get("DATA_DIR", "/config"))
    manager = get_job_manager()

    def settings_factory():
        from projectionist.config_store import load_merged_settings

        return load_merged_settings(data_dir)

    theater_app = create_theater_app(
        data_dir=data_dir,
        db_factory=lambda: manager.db,
        settings_factory=settings_factory,
    )

    main_config = _uvicorn_config(
        "projectionist.web.app:app",
        host=host,
        port=main_port,
        log_level=log_level,
    )
    theater_config = uvicorn.Config(
        theater_app,
        host=host,
        port=theater_port,
        reload=False,
        log_level=log_level,
        timeout_keep_alive=UVICORN_TIMEOUT_KEEP_ALIVE,
        h11_max_incomplete_event_size=UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE,
    )
    main_server = uvicorn.Server(main_config)
    theater_server = uvicorn.Server(theater_config)
    logger.info(
        "Lobby theater listening on %s:%s (LAN-only gate; never publish via public proxy)",
        host,
        theater_port,
    )
    await asyncio.gather(main_server.serve(), theater_server.serve())


def main() -> None:
    import uvicorn

    from projectionist.config_store import load_dotenv_file
    from projectionist.envcompat import skip_dotenv
    from projectionist.logging_config import configure_logging

    if not skip_dotenv():
        load_dotenv_file()

    level = configure_logging()
    host = resolve_host()
    port = int(os.environ.get("PORT", "8788"))
    theater_port = resolve_theater_port()
    log_level = logging.getLevelName(level).lower()
    warn_if_exposed_without_auth(host, port)

    # Dual servers share one process. Tests that patch uvicorn.run still work
    # when PROJECTIONIST_THEATER_DISABLE=1 (single-port fallback).
    if (os.environ.get("PROJECTIONIST_THEATER_DISABLE") or "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }:
        uvicorn.run(
            "projectionist.web.app:app",
            host=host,
            port=port,
            reload=False,
            log_level=log_level,
            timeout_keep_alive=UVICORN_TIMEOUT_KEEP_ALIVE,
            h11_max_incomplete_event_size=UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE,
        )
        return

    try:
        asyncio.run(
            _serve_dual(
                host=host,
                main_port=port,
                theater_port=theater_port,
                log_level=log_level,
            )
        )
    except OSError as exc:
        logger.error(
            "Failed to bind dual servers (main=%s theater=%s): %s",
            port,
            theater_port,
            exc,
        )
        raise


if __name__ == "__main__":
    main()
