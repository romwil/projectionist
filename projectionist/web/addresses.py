"""Home and away addresses for signed-in clients.

Away is the owner's public base URL. Home is the origin of a request that
arrived from the home network. Both are published on ``GET /api/features``.
Neither is written into an engine playlist.
"""

from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request

from projectionist.public_url import sanitize_stored_public_base_url
from projectionist.web.ingress import (
    is_tailscale_or_cgnat,
    parse_ip,
    request_is_external,
)
from projectionist.web.rate_limit import trust_proxy_headers

_HOME_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal")
_LOCK = threading.Lock()
_OBSERVED_HOME = ""


def reset_observed_home() -> None:
    """Test helper. A restart also forgets the home address."""
    global _OBSERVED_HOME
    with _LOCK:
        _OBSERVED_HOME = ""


def observed_home() -> str:
    with _LOCK:
        return _OBSERVED_HOME


def remember_home(origin: str) -> None:
    global _OBSERVED_HOME
    cleaned = str(origin or "").strip().rstrip("/")
    if not cleaned:
        return
    with _LOCK:
        _OBSERVED_HOME = cleaned


def public_address_configured(settings: Any = None) -> bool:
    """True when the household has stored an away address."""
    if settings is None:
        import os
        from pathlib import Path

        from projectionist.config_store import load_merged_settings

        data_dir = Path(os.environ.get("DATA_DIR", "/config"))
        try:
            settings = load_merged_settings(data_dir)
        except Exception:
            return False
    return bool(stored_public_base_url(settings))


def stored_public_base_url(settings: Any) -> str:
    network = getattr(settings, "network", None)
    raw = str(getattr(network, "public_base_url", "") or "")
    return sanitize_stored_public_base_url(raw)


def _hostname(netloc: str) -> str:
    host = str(netloc or "").strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 1 else ""
    return host.split(":")[0]


def host_is_home(netloc: str) -> bool:
    """True for a private, loopback, link-local, tailnet, or local name.

    ``testserver`` is the API test client. It is not a home address, so the
    recorded features example stays empty until a real home request arrives.
    """
    name = _hostname(netloc).lower().rstrip(".")
    if not name or name == "testserver":
        return False
    if name in {"localhost", "ip6-localhost"}:
        return True
    if any(name.endswith(suffix) for suffix in _HOME_SUFFIXES):
        return True
    parsed = parse_ip(name)
    if parsed is None:
        return False
    if is_tailscale_or_cgnat(parsed):
        return True
    return bool(parsed.is_private or parsed.is_loopback or parsed.is_link_local)


def peer_may_publish_home(request: Request) -> bool:
    """A tunnel arrival or a public peer cannot teach the server a home address.

    ``X-Forwarded-For`` is not the client. A Cloudflare header counts only
    when the socket peer is a trusted connector (SEC-020).
    """
    return not request_is_external(request)


def request_origin(request: Request) -> str:
    """Scheme and host for this request. No path, query, or userinfo."""
    scheme = str(getattr(request.url, "scheme", "") or "http").lower()
    netloc = str(request.headers.get("host") or getattr(request.url, "netloc", "") or "").strip()
    if trust_proxy_headers():
        forwarded_proto = (
            (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
        )
        if forwarded_proto in {"http", "https"}:
            scheme = forwarded_proto
        forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()
        if forwarded_host:
            netloc = forwarded_host
    if not netloc or scheme not in {"http", "https"}:
        return ""
    # Reject a host header that smuggles userinfo or a path.
    if urlsplit(f"{scheme}://{netloc}").hostname is None:
        return ""
    if "@" in netloc or "/" in netloc:
        return ""
    return f"{scheme}://{netloc}".rstrip("/")


def addresses_payload(request: Request | None, settings: Any) -> dict[str, str]:
    """``home`` and ``away`` for a signed-in features response."""
    away = stored_public_base_url(settings)
    home = observed_home()
    if request is not None and peer_may_publish_home(request):
        origin = request_origin(request)
        host = origin.split("://", 1)[1] if "://" in origin else ""
        if origin and host_is_home(host):
            remember_home(origin)
            home = origin
    return {"home": home, "away": away}
