"""Simple in-process per-IP sliding-window rate limiter."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

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
    """True when Projectionist sits behind a trusted reverse proxy.

    Without this flag, ``X-Forwarded-For`` is ignored for rate limiting so
    clients cannot rotate spoofed IPs to bypass auth throttles on a direct
    LAN bind (default homelab deployment). Wizard confirm writes the same
    flag into settings; env still wins when set.
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


def client_ip(request: Request) -> str:
    if trust_proxy_headers():
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    if request.client and request.client.host:
        return request.client.host
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
