"""Silent ingress handshake: bind + direct peer, never forwarded credentials.

Classification is topology only. Docker's 172.16.0.0/12 is *not* LAN when the
process is bound to all interfaces without a trusted proxy. RFC 6598 shared
address space (``100.64.0.0/10``, Tailscale/CGNAT) is not a visible public peer
— do not rely on ``ipaddress.is_private`` for that range (3.12 vs 3.13 differ).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any, Dict, Mapping, Optional, Union

from fastapi import Request

from projectionist.web.rate_limit import trust_proxy_headers

logger = logging.getLogger(__name__)

DOCKER_BRIDGE = ipaddress.ip_network("172.16.0.0/12")
# RFC 6598 shared address space — Tailscale's default userspace CGNAT range.
# Python 3.12: IPv4Address.is_private is False here; 3.13+ may treat it as private.
CGNAT_SHARED = ipaddress.ip_network("100.64.0.0/10")
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "testclient"})
_ALL_INTERFACES = frozenset({"0.0.0.0", "::", ""})
_SECRET_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "x-plex-token",
        "x-api-key",
        "x-mcp-key",
        "x-projectionist-webhook-secret",
        "cf-access-jwt-assertion",
        "cf-access-client-secret",
    }
)
_SNAPSHOT_FORBIDDEN_SUBSTRINGS = (
    "authorization",
    "cookie",
    "x-plex-token",
    "x-forwarded-for",
    "x-forwarded-proto",
    "cf-connecting-ip",
    "invite",
    "token",
    "bearer ",
)

IpAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

JOIN_LINK_DETAIL = (
    "An invite is required to join this household. Ask the household admin for a join link."
)
WAN_INTERLOCK_DETAIL = (
    "This instance is reachable from a public network without household login. "
    "Enable household login (multi-user) or complete setup from your local network."
)


def resolve_bind_host() -> str:
    """Listen address for handshake snapshots (same rules as the uvicorn entry)."""
    from projectionist.envcompat import branded_env

    host = (os.environ.get("HOST") or branded_env("HOST") or "").strip()
    return host or "0.0.0.0"


def resolve_bind_port() -> int:
    from projectionist.envcompat import branded_env

    raw = (os.environ.get("PORT") or branded_env("PORT") or "8788").strip()
    try:
        return int(raw)
    except ValueError:
        return 8788


def parse_ip(host: str) -> Optional[IpAddress]:
    cleaned = str(host or "").strip()
    if not cleaned or cleaned.lower() in _LOOPBACK_HOSTNAMES:
        return None
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        return None


def is_docker_nat_peer(peer: IpAddress) -> bool:
    if peer.version != 4:
        return False
    return peer in DOCKER_BRIDGE


def is_tailscale_or_cgnat(peer: IpAddress) -> bool:
    """True for RFC 6598 shared address space (Tailscale CGNAT ``100.64.0.0/10``).

    Explicit network membership — do not use ``is_private``, which disagrees
    across CPython 3.12 vs 3.13+ for this range.
    """
    if peer.version != 4:
        return False
    return peer in CGNAT_SHARED


def setup_posture(
    *,
    bind_host: str,
    peer: IpAddress,
    trusted_proxy: bool,
) -> str:
    """Return lan | halt_wan | public_failsafe | proxy.

    ``ipaddress.is_private`` alone must not choose Private Household: Docker
    bridge addresses (172.16.0.0/12, including 172.17.0.1) are private but
    are not LAN when we listen on 0.0.0.0 without a trusted proxy.
    """
    bind = str(bind_host or "").strip()
    if trusted_proxy:
        return "proxy"
    if peer.is_loopback or bind in {"127.0.0.1", "::1"}:
        return "lan"
    if is_tailscale_or_cgnat(peer):
        return "lan"
    if not peer.is_private:
        return "halt_wan"
    if bind in _ALL_INTERFACES and is_docker_nat_peer(peer):
        return "public_failsafe"
    if peer.is_private and not is_docker_nat_peer(peer):
        return "lan"
    return "public_failsafe"


def peer_class_name(peer: Optional[IpAddress]) -> str:
    """Coarse class for logs — never the raw address."""
    if peer is None:
        return "unknown"
    if peer.is_loopback:
        return "loopback"
    if peer.is_link_local:
        return "link_local"
    if is_docker_nat_peer(peer):
        return "docker_bridge"
    if is_tailscale_or_cgnat(peer):
        return "cgnat_shared"
    if peer.is_private:
        return "rfc1918_or_unique_local"
    return "public"


def direct_peer(request: Request) -> tuple[str, int]:
    """Raw socket peer from ``request.client`` — not X-Forwarded-For."""
    if request.client is None:
        return "", 0
    host = str(request.client.host or "")
    port = int(request.client.port or 0)
    return host, port


def bind_family(bind_host: str) -> str:
    host = str(bind_host or "").strip()
    if host in {"::", "::1"} or ":" in host:
        return "AF_INET6"
    return "AF_INET"


def forwarded_header_present(request: Request, name: str) -> bool:
    return bool((request.headers.get(name) or "").strip())


def classify_request(
    request: Request,
    *,
    bind_host: Optional[str] = None,
    trusted_proxy: Optional[bool] = None,
) -> Dict[str, Any]:
    bind = bind_host if bind_host is not None else resolve_bind_host()
    trusted = trust_proxy_headers() if trusted_proxy is None else bool(trusted_proxy)
    peer_host, peer_port = direct_peer(request)
    peer = parse_ip(peer_host)
    if peer is None:
        if str(peer_host).strip().lower() in _LOOPBACK_HOSTNAMES or not peer_host:
            # TestClient / missing peer: do not invent a public address.
            peer = ipaddress.ip_address("127.0.0.1")
            classification = "lan" if not trusted else "proxy"
        else:
            classification = "public_failsafe"
            peer = ipaddress.ip_address("0.0.0.0")
    else:
        classification = setup_posture(bind_host=bind, peer=peer, trusted_proxy=trusted)

    snapshot = build_detection_snapshot(
        bind_host=bind,
        bind_port=resolve_bind_port(),
        peer_host=peer_host or str(peer),
        peer_port=peer_port,
        classification=classification,
        forwarded_proto_present=forwarded_header_present(request, "x-forwarded-proto"),
        forwarded_for_present=forwarded_header_present(request, "x-forwarded-for"),
        trusted_proxy_mode=trusted,
    )
    preselect = "public" if classification in {"proxy", "public_failsafe", "halt_wan"} else "private"
    return {
        "classification": classification,
        "preselect_profile": preselect,
        "halt": classification == "halt_wan",
        "peer_class": peer_class_name(parse_ip(peer_host) if peer_host else peer),
        "snapshot": snapshot,
        "trusted_proxy": trusted,
    }


def build_detection_snapshot(
    *,
    bind_host: str,
    bind_port: int,
    peer_host: str,
    peer_port: int,
    classification: str,
    forwarded_proto_present: bool,
    forwarded_for_present: bool,
    trusted_proxy_mode: bool,
) -> Dict[str, Any]:
    """Raw socket tuple + derived flags. Never headers, cookies, or tokens."""
    snapshot = {
        "family": bind_family(bind_host),
        "bind_host": str(bind_host or ""),
        "bind_port": int(bind_port or 0),
        "peer_host": str(peer_host or ""),
        "peer_port": int(peer_port or 0),
        "classification": str(classification or ""),
        "forwarded_proto_present": bool(forwarded_proto_present),
        "forwarded_for_present": bool(forwarded_for_present),
        "trusted_proxy_mode": bool(trusted_proxy_mode),
    }
    return sanitize_detection_snapshot(snapshot)


def sanitize_detection_snapshot(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Drop anything that is not the allowed socket-tuple schema."""
    allowed = {
        "family",
        "bind_host",
        "bind_port",
        "peer_host",
        "peer_port",
        "classification",
        "forwarded_proto_present",
        "forwarded_for_present",
        "trusted_proxy_mode",
    }
    out: Dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).strip().lower()
        if lowered not in allowed:
            continue
        if lowered in _SECRET_HEADER_NAMES:
            continue
        if any(token in lowered for token in ("authorization", "cookie", "x-plex-token")):
            continue
        if isinstance(value, str) and _looks_like_secret_blob(value):
            continue
        out[lowered] = value
    return out


def _looks_like_secret_blob(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _SNAPSHOT_FORBIDDEN_SUBSTRINGS)


def snapshot_contains_secrets(payload: Mapping[str, Any]) -> bool:
    blob = " ".join(f"{k}={v}" for k, v in payload.items()).lower()
    if "authorization" in blob or "x-plex-token" in blob or "cookie=" in blob:
        return True
    for key in payload:
        if str(key).lower() in _SECRET_HEADER_NAMES:
            return True
    return False


def request_is_trusted_https(request: Optional[Request]) -> bool:
    """True when this request is HTTPS on the socket, or via a trusted proxy."""
    if request is None:
        return False
    if str(request.url.scheme or "").lower() == "https":
        return True
    if not trust_proxy_headers():
        return False
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return forwarded == "https"


def _is_visible_public_peer(peer: Optional[IpAddress]) -> bool:
    """True when the address is a globally routed client (not RFC1918 / ULA / loopback / link-local / CGNAT)."""
    if peer is None:
        return False
    if is_tailscale_or_cgnat(peer):
        return False
    return not (peer.is_private or peer.is_loopback or peer.is_link_local)


def wan_interlock_blocks(
    request: Request,
    *,
    multi_user_enabled: bool,
    bind_host: Optional[str] = None,
) -> bool:
    """Block single-owner API only for a visible public client.

    Setup handshake posture (``setup_posture``) may still treat Docker NAT on a
    ``0.0.0.0`` bind as Public Household. This runtime lock must not: Docker
    bridge peers and trusted ``X-Forwarded-Proto: https`` hops are not WAN.
    ``bind_host`` is accepted for call-site compatibility; bind is setup-only.
    """
    if multi_user_enabled:
        return False
    trusted = trust_proxy_headers()
    peer_host, _peer_port = direct_peer(request)
    peer = parse_ip(peer_host)

    client = peer
    if trusted:
        forwarded_ip = parse_ip((request.headers.get("x-forwarded-for") or "").split(",")[0].strip())
        if forwarded_ip is not None:
            client = forwarded_ip

    return _is_visible_public_peer(client)


def log_honeypot_ping(request: Request, *, honeypot: str) -> None:
    peer_host, _port = direct_peer(request)
    peer = parse_ip(peer_host)
    logger.info(
        "honeypot ping honeypot=%s peer_class=%s bind_host=%s",
        honeypot,
        peer_class_name(peer),
        resolve_bind_host(),
    )


def default_family_for_bind(bind_host: str) -> int:
    return socket.AF_INET6 if bind_family(bind_host) == "AF_INET6" else socket.AF_INET
