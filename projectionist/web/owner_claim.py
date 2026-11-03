"""One-time owner claim: who may become the first household owner (SEC-008).

Before this, the first Plex or OIDC identity to sign in while no real owner
existed became owner. On a shared LAN, anyone faster than the operator could
take the server.

Now the first owner needs proof:

- ``PROJECTIONIST_OWNER_PASSWORD`` seeds the owner at startup (``seed_env_owner``), or
- the setup wizard creates the owner, or
- the browser that turned on household sign-in holds a one-time claim cookie.

The claim cookie is issued only to an owner session (single-owner mode treats
every LAN caller as owner, so this binds the claim to the person who flipped
the switch rather than to whoever signs in first). It is single-use and expires.
Without proof, first sign-in fails closed with ``NO_OWNER_DETAIL``.

This does not change the new-install default; it only removes the race.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional

from fastapi import Request, Response

from projectionist.library.db import Database

logger = logging.getLogger(__name__)

OWNER_CLAIM_COOKIE = "projectionist_owner_claim"
OWNER_CLAIM_CONFIG_KEY = "owner_claim"
OWNER_CLAIM_TTL_SECONDS = 24 * 60 * 60

NO_OWNER_DETAIL = (
    "This server has no owner yet, so new sign-ins are paused. "
    "To finish setup, the owner sets PROJECTIONIST_OWNER_PASSWORD on the container "
    "and restarts, then signs in with that password."
)


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_owner_claim(db: Database) -> str:
    """Create a fresh claim, replacing any earlier one. Returns the raw token."""
    raw = secrets.token_urlsafe(32)
    record = {"digest": _digest(raw), "expires_at": time.time() + OWNER_CLAIM_TTL_SECONDS}
    db.set_config(OWNER_CLAIM_CONFIG_KEY, json.dumps(record))
    logger.info("Issued one-time owner claim to the session that enabled household sign-in.")
    return raw


def set_owner_claim_cookie(response: Response, raw: str, request: Optional[Request] = None) -> None:
    from projectionist.web.auth import _cookie_should_be_secure

    response.set_cookie(
        key=OWNER_CLAIM_COOKIE,
        value=raw,
        httponly=True,
        samesite="lax",
        max_age=OWNER_CLAIM_TTL_SECONDS,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def _load(db: Database) -> Optional[dict]:
    raw = db.get_config(OWNER_CLAIM_CONFIG_KEY)
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def request_holds_owner_claim(db: Database, request: Optional[Request]) -> bool:
    """True when ``request`` carries the live, unexpired claim cookie."""
    if request is None:
        return False
    presented = str(request.cookies.get(OWNER_CLAIM_COOKIE) or "").strip()
    if not presented:
        return False
    record = _load(db)
    if not record:
        return False
    try:
        expires_at = float(record.get("expires_at") or 0)
    except (TypeError, ValueError):
        return False
    if expires_at <= time.time():
        return False
    return hmac.compare_digest(_digest(presented), str(record.get("digest") or ""))


def consume_owner_claim(db: Database) -> None:
    """Invalidate the claim once an owner exists."""
    db.set_config(OWNER_CLAIM_CONFIG_KEY, "")
