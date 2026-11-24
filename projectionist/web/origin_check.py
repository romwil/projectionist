"""Reject a cookie-authenticated write that came from another site (SEC-023).

A bearer token is the client's own credential, so those requests are exempt.
A request that sends neither ``Origin`` nor ``Referer`` is left alone: a
browser sends one of them on an unsafe method.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request

from projectionist.web.session_tokens import SESSION_COOKIE_NAME

_UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
ORIGIN_REJECTED = "That request did not come from this household."


def _origin_of(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return ""
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def cookie_origin_rejected(request: Request) -> bool:
    """True when this cookie write names a site that is not the household."""
    if request.method.upper() not in _UNSAFE:
        return False
    authorization = str(request.headers.get("authorization") or "")
    if authorization.lower().startswith("bearer "):
        return False
    if not request.cookies.get(SESSION_COOKIE_NAME):
        return False
    presented = _origin_of(request.headers.get("origin") or "") or _origin_of(
        request.headers.get("referer") or ""
    )
    if not presented:
        return False

    from projectionist.config_store import load_merged_settings
    from projectionist.web.addresses import (
        host_is_home,
        observed_home,
        request_origin,
        stored_public_base_url,
    )

    allowed = {
        request_origin(request),
        observed_home(),
    }
    try:
        settings = load_merged_settings(Path(os.environ.get("DATA_DIR", "/config")))
        allowed.add(stored_public_base_url(settings))
    except Exception:
        pass
    allowed.discard("")
    if presented in allowed:
        return False
    host = urlsplit(presented).hostname or ""
    return not host_is_home(host)
