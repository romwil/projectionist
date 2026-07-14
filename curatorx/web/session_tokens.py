"""Signed session cookies for optional multi-user auth."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

SESSION_COOKIE_NAME = "curatorx_session"
DEFAULT_TTL_SECONDS = 30 * 86400
DEV_SESSION_SECRET = "curatorx-dev-session-secret"
SESSION_SECRET_FILENAME = "session_secret"
_ENV_SESSION_SECRET = "CURATORX_SESSION_SECRET"

logger = logging.getLogger(__name__)

_cached_secret: Optional[str] = None


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def session_secret_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / SESSION_SECRET_FILENAME


def _env_secret() -> str:
    return os.environ.get(_ENV_SESSION_SECRET, "").strip()


def is_dev_session_secret(value: str) -> bool:
    return (value or "").strip() == DEV_SESSION_SECRET


def has_usable_session_secret(data_dir: Optional[Path] = None) -> bool:
    """True when a non-default secret is available via env or persisted file.

    An environment value equal to the public development default is never usable,
    even if a stronger file exists — set a real env secret or unset the env var.
    """
    env = _env_secret()
    if env:
        return not is_dev_session_secret(env)
    path = session_secret_path(data_dir)
    if not path.is_file():
        return False
    try:
        stored = path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(stored) and not is_dev_session_secret(stored)


def resolve_session_secret(data_dir: Optional[Path] = None, *, persist: bool = True) -> str:
    """Return a cryptographically strong session secret.

    Prefer ``CURATORX_SESSION_SECRET`` when set to a non-default value, else a
    persisted ``session_secret`` file under DATA_DIR, else generate and persist one.
    Never returns the public development default.
    """
    global _cached_secret
    if _cached_secret and not is_dev_session_secret(_cached_secret):
        env = _env_secret()
        if not env or env == _cached_secret:
            return _cached_secret

    root = data_dir or _data_dir()
    env = _env_secret()
    if env and not is_dev_session_secret(env):
        _cached_secret = env
        return env

    path = session_secret_path(root)
    if path.is_file():
        try:
            stored = path.read_text(encoding="utf-8").strip()
        except OSError:
            stored = ""
        if stored and not is_dev_session_secret(stored):
            _cached_secret = stored
            return stored

    if not persist:
        raise RuntimeError("No usable CuratorX session secret configured")

    secret = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("Generated session secret at %s", path)
    _cached_secret = secret
    return secret


def ensure_session_secret(data_dir: Optional[Path] = None) -> str:
    """Bootstrap a persisted session secret on first boot / startup."""
    return resolve_session_secret(data_dir, persist=True)


def clear_session_secret_cache() -> None:
    """Test helper: drop in-process secret cache."""
    global _cached_secret
    _cached_secret = None


def _secret() -> bytes:
    return resolve_session_secret().encode("utf-8")


def create_session_token(user_id: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    payload = {"uid": user_id, "exp": time.time() + ttl_seconds}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    sig = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_session_token(token: str) -> Optional[str]:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None
    user_id = payload.get("uid")
    exp = payload.get("exp")
    if not user_id or not isinstance(exp, (int, float)) or float(exp) < time.time():
        return None
    return str(user_id)
