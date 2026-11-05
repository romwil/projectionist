"""Passcode gate in front of first-run setup (SEC-008, SEC-010).

A data directory with no real owner answers only ``GET /api/health``,
``GET /api/ready``, and the lock page until the
container owner passcode is entered. Ready stays a readiness probe (status,
version, and whether the database answers). That passcode is
``PROJECTIONIST_OWNER_PASSWORD`` (the same variable that seeds an existing
owner). There is no second secret and no first-login fallback.

An install that already has an owner never shows the lock. If that owner
later disappears, the same passcode opens setup again. Login cannot take
the owner role by arriving first while the install is ownerless.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from typing import Optional

from fastapi import Request, Response

logger = logging.getLogger(__name__)

SETUP_UNLOCK_COOKIE = "projectionist_setup_unlock"
SETUP_UNLOCK_CONFIG_KEY = "setup_unlock"
SETUP_UNLOCK_TTL_SECONDS = 24 * 60 * 60
_MAX_PASSCODE_CHARS = 1024

UNSET_DETAIL = (
    "Set PROJECTIONIST_OWNER_PASSWORD on the container (8 or more characters) "
    "and restart. This install stays locked until that passcode is entered. "
    "Signing in first will not make someone the owner."
)
MISMATCH_DETAIL = "That passcode does not match PROJECTIONIST_OWNER_PASSWORD."


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _current_passcode() -> str:
    from projectionist.web.auth import resolve_owner_credentials

    _username, password = resolve_owner_credentials()
    return str(password or "").strip()


def passcode_configured() -> bool:
    """True when the container owner password is long enough to unlock setup."""
    from projectionist.web.auth import MIN_OWNER_PASSWORD_LENGTH

    return len(_current_passcode()) >= MIN_OWNER_PASSWORD_LENGTH


def passcode_matches(candidate: str) -> bool:
    """Constant-time check of the setup passcode. Never logs the value."""
    presented = str(candidate or "")
    if not presented or len(presented) > _MAX_PASSCODE_CHARS or not passcode_configured():
        return False
    return hmac.compare_digest(_digest(presented), _digest(_current_passcode()))


def install_known_active() -> bool:
    """True when this process already knows the lock does not apply.

    ``PROJECTIONIST_SETUP_STATE=active`` is an explicit override (tests and
    operators). A confirmed real owner is remembered on the database object
    so later requests, including ``/api/ready``, do not open SQLite just to
    learn the lock is finished.
    """
    from projectionist.envcompat import branded_env

    if (branded_env("SETUP_STATE") or "").strip().lower() == "active":
        return True
    try:
        from projectionist.web.jobs import get_job_manager

        db = get_job_manager().db
    except Exception:  # noqa: BLE001
        return False
    return bool(getattr(db, "_projectionist_active_mode", False))


def issue_setup_unlock(db) -> str:
    """Remember that this passcode was accepted. Returns the raw cookie value."""
    raw = secrets.token_urlsafe(32)
    record = {
        "digest": _digest(raw),
        "pass": _digest(_current_passcode()),
        "expires_at": time.time() + SETUP_UNLOCK_TTL_SECONDS,
    }
    db.set_config(SETUP_UNLOCK_CONFIG_KEY, json.dumps(record))
    logger.info("Setup passcode accepted; this browser may finish setup.")
    return raw


def set_setup_unlock_cookie(
    response: Response, raw: str, request: Optional[Request] = None
) -> None:
    from projectionist.web.auth import _cookie_should_be_secure

    response.set_cookie(
        key=SETUP_UNLOCK_COOKIE,
        value=raw,
        httponly=True,
        samesite="lax",
        max_age=SETUP_UNLOCK_TTL_SECONDS,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def setup_unlock_cookie_ok(db, request: Optional[Request]) -> bool:
    """True when this browser entered the current container passcode."""
    if request is None or not passcode_configured():
        return False
    presented = str(request.cookies.get(SETUP_UNLOCK_COOKIE) or "").strip()
    if not presented:
        return False
    raw = db.get_config(SETUP_UNLOCK_CONFIG_KEY)
    if not raw:
        return False
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(record, dict):
        return False
    try:
        expires_at = float(record.get("expires_at") or 0)
    except (TypeError, ValueError):
        return False
    if expires_at <= time.time():
        return False
    return hmac.compare_digest(
        _digest(presented), str(record.get("digest") or "")
    ) and hmac.compare_digest(_digest(_current_passcode()), str(record.get("pass") or ""))


def request_passes_setup_lock(request: Request) -> bool:
    """False when the response must be the lock (or a 404, for APIs).

    A real owner skips the lock. A browser that already entered the passcode
    may continue into setup. Everyone else is locked.
    """
    from projectionist.web.auth import has_real_owner
    from projectionist.web.jobs import get_job_manager
    from projectionist.web.setup_mode import SETUP_STATE_ACTIVE, resolve_setup_state

    db = get_job_manager().db
    if has_real_owner(db):
        if resolve_setup_state(db) == SETUP_STATE_ACTIVE:
            db._projectionist_active_mode = True
        return True
    # No owner: force the setup ratchet back open, including after a previous
    # active boot whose owner row is gone.
    resolve_setup_state(db)
    return setup_unlock_cookie_ok(db, request)


def is_setup_lock_document(method: str, path: str) -> bool:
    """HTML navigations get the lock page. Assets and APIs do not."""
    if str(method or "GET").upper() not in {"GET", "HEAD"}:
        return False
    cleaned = (path or "").split("?", 1)[0]
    if cleaned.startswith("/api/") or cleaned.startswith("/mcp"):
        return False
    if cleaned.startswith("/assets/") or cleaned.startswith("/static/"):
        return False
    leaf = cleaned.rsplit("/", 1)[-1]
    return "." not in leaf


def lock_page_html(*, configured: bool, error: str = "") -> str:
    """Self-contained lock screen. No household data and no SPA bundle."""
    message = html.escape(error) if error else ""
    error_html = (
        f'<p class="setup-lock-error" data-testid="setup-lock-error">{message}</p>'
        if message
        else ""
    )
    if configured:
        body = f"""
        <p>Enter the owner passcode from <code>PROJECTIONIST_OWNER_PASSWORD</code>
        to start setup. Setup creates the owner account. Plex is optional.
        A Plex, SSO, or local sign-in cannot become the owner by arriving first.</p>
        {error_html}
        <form method="post" action="/api/setup/unlock" data-testid="setup-lock-form">
          <label>Owner passcode
            <input type="password" name="passcode" autocomplete="current-password"
              required data-testid="setup-lock-passcode">
          </label>
          <button type="submit">Unlock setup</button>
        </form>
        """
    else:
        body = f"""
        <p data-testid="setup-lock-unset">{html.escape(UNSET_DETAIL)}</p>
        {error_html}
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Projectionist setup</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #12110e; color: #f4f0e6;
      margin: 0; min-height: 100vh; display: grid; place-items: center; }}
    main {{ max-width: 28rem; padding: 2rem; }}
    h1 {{ font-size: 1.4rem; font-weight: 600; }}
    label {{ display: block; margin: 1rem 0; }}
    input {{ display: block; width: 100%; box-sizing: border-box; margin-top: 0.4rem;
      padding: 0.6rem; font-size: 1rem; }}
    button {{ font-size: 1rem; padding: 0.6rem 1rem; }}
    .setup-lock-error {{ color: #ffb4a8; }}
    code {{ font-size: 0.95em; }}
  </style>
</head>
<body>
  <main data-testid="setup-lock">
    <h1>Set up this server</h1>
    {body}
  </main>
</body>
</html>
"""
