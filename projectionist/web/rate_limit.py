"""Simple in-process per-IP sliding-window rate limiter."""

from __future__ import annotations

import ipaddress
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

from fastapi import HTTPException, Request

_TRUTHY = frozenset({"1", "true", "yes", "on"})
HITS_CAP = 4096


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def check(self, *, key: str, bucket: str, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._hits[(bucket, key)]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                retry_after = max(1, int(window_seconds - (now - q[0])) + 1)
                if len(self._hits) > HITS_CAP:
                    self._evict_hits(protect=(bucket, key))
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )
            q.append(now)
            if len(self._hits) > HITS_CAP:
                self._evict_hits(protect=(bucket, key))

    def _evict_hits(self, *, protect: Tuple[str, str] | None = None) -> None:
        empty = [bucket_key for bucket_key, hits in self._hits.items() if not hits]
        for bucket_key in empty:
            if protect is not None and bucket_key == protect:
                continue
            del self._hits[bucket_key]
        overflow = len(self._hits) - HITS_CAP
        if overflow <= 0:
            return
        oldest = sorted(
            self._hits.items(),
            key=lambda item: item[1][0] if item[1] else 0.0,
        )
        evicted = 0
        for bucket_key, _hits in oldest:
            if evicted >= overflow:
                break
            if protect is not None and bucket_key == protect:
                continue
            del self._hits[bucket_key]
            evicted += 1

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = SlidingWindowRateLimiter()


def trust_proxy_headers() -> bool:
    """True when forwarded protocol headers may be believed.

    This flag still decides ``Secure`` cookies and ``X-Forwarded-Proto``.
    It does **not** choose the rate-limit key. That key uses
    ``CF-Connecting-IP`` only when the direct peer is on the trusted-proxy
    list (SEC-017). A client-supplied ``X-Forwarded-For`` is never the key.
    """
    from projectionist.envcompat import branded_env

    env_raw = (branded_env("TRUST_PROXY_HEADERS") or "").strip().lower()
    if env_raw:
        return env_raw in _TRUTHY
    try:
        from pathlib import Path

        from projectionist.config_store import load_merged_settings

        data_dir = Path(os.environ.get("DATA_DIR", "/config"))
        flags = load_merged_settings(data_dir).features
        return bool(getattr(flags, "trust_proxy_headers", False))
    except Exception:
        return False


def normalize_trusted_proxies(value: object) -> List[str]:
    """Keep tokens that are one IP or one CIDR. Drop anything else."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            parts.extend(str(item).split(","))
    else:
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for part in parts:
        token = str(part).strip()
        if not token or token in seen:
            continue
        try:
            ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        seen.add(token)
        cleaned.append(token)
    return cleaned


def configured_trusted_proxies() -> List[str]:
    """Connector addresses that may supply ``CF-Connecting-IP``.

    ``PROJECTIONIST_TRUSTED_PROXIES`` wins when it is set. Otherwise the
    list is ``network.trusted_proxies`` in settings. An empty list means
    no peer is trusted, including loopback.
    """
    from projectionist.envcompat import branded_env

    env_raw = branded_env("TRUSTED_PROXIES")
    if env_raw is not None:
        return normalize_trusted_proxies(env_raw)
    try:
        from pathlib import Path

        from projectionist.config_store import load_merged_settings

        data_dir = Path(os.environ.get("DATA_DIR", "/config"))
        network = load_merged_settings(data_dir).network
        return normalize_trusted_proxies(getattr(network, "trusted_proxies", []))
    except Exception:
        return []


def _peer_addresses(host: str) -> List[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        ip = ipaddress.ip_address(str(host).strip())
    except ValueError:
        return []
    found: List[ipaddress.IPv4Address | ipaddress.IPv6Address] = [ip]
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        found.append(mapped)
    return found


def peer_is_trusted_proxy(host: str) -> bool:
    """True when this socket peer is a configured tunnel connector."""
    peers = _peer_addresses(host)
    if not peers:
        return False
    for token in configured_trusted_proxies():
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        if any(peer in network for peer in peers):
            return True
    return False


def _single_ip_header(request: Request, name: str) -> str:
    """One valid IP, or empty. A list or a junk value is ignored."""
    raw = (request.headers.get(name) or "").strip()
    if not raw or "," in raw or any(char.isspace() for char in raw):
        return ""
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return ""
    return raw


def client_ip(request: Request) -> str:
    """Address used as the rate-limit key (SEC-017).

    ``CF-Connecting-IP`` counts only when the direct peer is on the
    trusted-proxy list. Otherwise the key is the socket peer. The first
    ``X-Forwarded-For`` hop is never the key, trusted peer or not.
    """
    peer = ""
    if request.client and request.client.host:
        peer = str(request.client.host).strip()
    if peer and peer_is_trusted_proxy(peer):
        connecting = _single_ip_header(request, "cf-connecting-ip")
        if connecting:
            return connecting
        return peer
    if peer:
        return peer
    return "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    limit: int,
    window_seconds: float = 60.0,
) -> None:
    _limiter.check(
        key=client_ip(request),
        bucket=bucket,
        limit=limit,
        window_seconds=window_seconds,
    )


def clear_rate_limits() -> None:
    """Test helper."""
    _limiter.clear()
