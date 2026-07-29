"""Central logging configuration for CuratorX (stdout + durable file under DATA_DIR)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

_CONFIGURED = False

_VALID_LEVELS = {"ERROR", "WARNING", "INFO", "DEBUG"}
_DEFAULT_LEVEL = "INFO"

# Durable app log under DATA_DIR (Docker/Unraid: /config/logs/projectionist.log).
_DEFAULT_LOG_RELATIVE = Path("logs") / "projectionist.log"
_DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB
_DEFAULT_LOG_BACKUP_COUNT = 3
_FILE_HANDLER_NAME = "projectionist.file"

# Query params and header-like patterns that may carry secrets.
_API_KEY_PARAM = re.compile(r"(api_key=)[^&\s\"']+", re.IGNORECASE)
_TOKEN_PARAM = re.compile(r"(token=)[^&\s\"']+", re.IGNORECASE)
_BEARER = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_SK_PREFIX = re.compile(r"\bsk-[a-zA-Z0-9-]{10,}\b")
_X_API_KEY = re.compile(r"(X-Api-Key:\s*)\S+", re.IGNORECASE)


class _RedactionFilter(logging.Filter):
    """Redact likely secrets on the record itself.

    Runs before formatting so redaction applies under *both* the JSON and the
    default text formatter. We resolve the fully-interpolated message once via
    ``record.getMessage()``, redact it, and store it back as ``record.msg`` with
    ``record.args`` cleared so downstream formatters emit the sanitized text
    without re-applying ``%`` args (which would raise on the arg-free message).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive: never drop a log line
            return True
        cleaned = sanitize_log_message(message)
        if cleaned != message or record.args:
            record.msg = cleaned
            record.args = None
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_log_message(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def resolve_log_level(raw: str | None = None) -> int:
    """Parse PROJECTIONIST_LOG_LEVEL / CURATORX_LOG_LEVEL or LOG_LEVEL."""
    from projectionist.envcompat import branded_env

    value = (
        raw
        or branded_env("LOG_LEVEL")
        or os.environ.get("LOG_LEVEL")
        or _DEFAULT_LEVEL
    )
    normalized = str(value).strip().upper()
    if normalized not in _VALID_LEVELS:
        normalized = _DEFAULT_LEVEL
    return getattr(logging, normalized)


def resolve_log_format(raw: str | None = None) -> str:
    from projectionist.envcompat import branded_env

    value = (
        raw
        or os.environ.get("LOG_FORMAT")
        or branded_env("LOG_FORMAT")
        or "text"
    )
    normalized = str(value).strip().lower()
    return "json" if normalized == "json" else "text"


def resolve_data_dir() -> Path:
    """Return the config/data directory (Docker default ``/config``)."""
    return Path(os.environ.get("DATA_DIR", "/config")).expanduser()


def resolve_log_file_path(raw: str | None = None) -> Path:
    """Path of the durable application log file.

    Override with ``PROJECTIONIST_LOG_FILE`` / ``CURATORX_LOG_FILE``, or absolute
    ``LOG_FILE``. Relative values resolve under ``DATA_DIR``.
    """
    from projectionist.envcompat import branded_env

    value = (
        raw
        or branded_env("LOG_FILE")
        or os.environ.get("LOG_FILE")
        or ""
    ).strip()
    if value:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = resolve_data_dir() / path
        return path
    return resolve_data_dir() / _DEFAULT_LOG_RELATIVE


def resolve_log_max_bytes() -> int:
    raw = os.environ.get("PROJECTIONIST_LOG_MAX_BYTES") or os.environ.get(
        "CURATORX_LOG_MAX_BYTES"
    )
    if raw:
        try:
            value = int(str(raw).strip())
            if value >= 64 * 1024:
                return value
        except ValueError:
            pass
    return _DEFAULT_LOG_MAX_BYTES


def resolve_log_backup_count() -> int:
    raw = os.environ.get("PROJECTIONIST_LOG_BACKUP_COUNT") or os.environ.get(
        "CURATORX_LOG_BACKUP_COUNT"
    )
    if raw:
        try:
            value = int(str(raw).strip())
            if 0 <= value <= 20:
                return value
        except ValueError:
            pass
    return _DEFAULT_LOG_BACKUP_COUNT


def sanitize_log_message(message: str) -> str:
    """Redact likely secrets from log text (never log API keys or tokens)."""
    cleaned = str(message or "")
    cleaned = _API_KEY_PARAM.sub(r"\1***", cleaned)
    cleaned = _TOKEN_PARAM.sub(r"\1***", cleaned)
    cleaned = _BEARER.sub(r"\1***", cleaned)
    cleaned = _SK_PREFIX.sub("sk-***", cleaned)
    cleaned = _X_API_KEY.sub(r"\1***", cleaned)
    return cleaned


def sanitize_url(url: str) -> str:
    """Strip credential query params from URLs before logging."""
    return sanitize_log_message(url)


def _make_formatter(log_format: str) -> logging.Formatter:
    if log_format == "json":
        return _JsonFormatter()
    return logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _attach_file_handler(root: logging.Logger, *, level: int, log_format: str) -> Optional[Path]:
    """Add a rotating file handler under DATA_DIR. Returns the path, or None on failure."""
    path = resolve_log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path,
            maxBytes=resolve_log_max_bytes(),
            backupCount=resolve_log_backup_count(),
            encoding="utf-8",
        )
    except OSError as exc:
        # Never fail boot because the log directory is unwritable (permissions, read-only FS).
        sys.stderr.write(f"projectionist: could not open log file {path}: {exc}\n")
        return None

    handler.set_name(_FILE_HANDLER_NAME)
    handler.setLevel(level)
    handler.addFilter(_RedactionFilter())
    handler.setFormatter(_make_formatter(log_format))
    root.addHandler(handler)
    return path


def configure_logging(*, force: bool = False) -> int:
    """Configure root and framework loggers once. Returns numeric log level.

    Emits to stdout (Docker-friendly) and a rotating file at
    ``{DATA_DIR}/logs/projectionist.log`` for the in-app owner log viewer.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return resolve_log_level()

    level = resolve_log_level()
    log_format = resolve_log_format()

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    # Redact secrets on the record before formatting so both the JSON and the
    # default text formatter emit sanitized output.
    handler.addFilter(_RedactionFilter())
    handler.setFormatter(_make_formatter(log_format))
    root.addHandler(handler)

    log_path = _attach_file_handler(root, level=level, log_format=log_format)

    # Keep third-party noise down unless debugging.
    for name in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING if level > logging.DEBUG else logging.DEBUG)

    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        logging.getLogger(name).setLevel(level)

    # Access logs: INFO+ shows requests; WARNING hides routine traffic.
    access_level = level if level <= logging.INFO else logging.WARNING
    logging.getLogger("uvicorn.access").setLevel(access_level)

    logging.captureWarnings(True)
    _CONFIGURED = True

    logging.getLogger(__name__).debug(
        "Logging configured level=%s format=%s file=%s",
        logging.getLevelName(level),
        log_format,
        log_path or "(none)",
    )
    return level
