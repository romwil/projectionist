"""Shared consecutive-failure circuit breaker.

The idle scheduler quarantines tasks with this type. Connector HTTP helpers
use the same class, keyed by host, so Live Channels pollers and every other
``request_json`` / ``request_xml`` / ``request_empty`` caller fail fast when
Plex or Tunarr is unreachable instead of hammering the local socket.

The shared Plex breaker is a cheap health check. A timeout on a heavy call
(a transcode start, a metadata lookup, a session list) does not count, even
when no start is currently held. A transcode-start timeout stays on that
title. A refused connection, or a failed ``/identity`` check, still opens
the host breaker. An HTTP 5xx on another host still opens that host.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, Optional

logger = logging.getLogger(__name__)

QUARANTINE_THRESHOLD = 3
DEFAULT_QUARANTINE_COOLDOWN_SECONDS = 3600  # scheduler task quarantine
# Connector hosts recover faster than background tasks; 60s stops tight loops
# without hour-long Live TV blackouts after a brief Tunarr/Plex hiccup.
HOST_CIRCUIT_COOLDOWN_SECONDS = 60


class CircuitOpenError(RuntimeError):
    """Raised when a host circuit breaker is open (no socket attempt)."""

    def __init__(self, host: str, remaining_seconds: float) -> None:
        self.host = host
        self.remaining_seconds = float(remaining_seconds)
        super().__init__(
            f"Circuit open for {host}; retry in {int(self.remaining_seconds)}s"
        )


@dataclass
class QuarantineInfo:
    """In-memory consecutive-failure breaker (scheduler tasks or HTTP hosts)."""

    consecutive_failures: int = 0
    last_error: str = ""
    quarantined_at: Optional[float] = None
    cooldown_seconds: int = DEFAULT_QUARANTINE_COOLDOWN_SECONDS

    @property
    def is_quarantined(self) -> bool:
        if self.quarantined_at is None:
            return False
        elapsed = time.time() - self.quarantined_at
        if elapsed >= self.cooldown_seconds:
            self.release()
            return False
        return True

    @property
    def remaining_seconds(self) -> Optional[float]:
        if self.quarantined_at is None:
            return None
        remaining = self.cooldown_seconds - (time.time() - self.quarantined_at)
        return max(0.0, remaining)

    def record_failure(self, error: str) -> bool:
        """Record a failure. Returns True if the breaker is now open."""
        self.consecutive_failures += 1
        self.last_error = error
        if self.consecutive_failures >= QUARANTINE_THRESHOLD and self.quarantined_at is None:
            self.quarantined_at = time.time()
            return True
        return False

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_error = ""
        self.quarantined_at = None

    def release(self) -> None:
        """Manually clear quarantine (admin reset or cooldown expiry)."""
        self.consecutive_failures = 0
        self.last_error = ""
        self.quarantined_at = None


def host_key(url: str) -> str:
    """Stable host:port key for per-upstream breakers."""
    parsed = urllib.parse.urlparse(str(url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""
    port = parsed.port
    return f"{host}:{port}" if port is not None else host


def failure_is_timeout(error: str) -> bool:
    """A slow answer, as opposed to a refused connection or an HTTP error."""
    text = str(error or "").strip().lower()
    return "timed out" in text or "timeout" in text


def is_health_check_url(url: str) -> bool:
    """Plex ``/identity``. A failure here is the shared host check."""
    path = urllib.parse.urlparse(str(url or "").strip()).path.rstrip("/")
    return path == "/identity" or path.endswith("/identity")


def is_heavy_call_url(url: str) -> bool:
    """A slow Plex call. Its timeout stays off the shared host breaker."""
    path = urllib.parse.urlparse(str(url or "").strip()).path
    return any(
        marker in path
        for marker in (
            "transcode/universal",
            "/library/metadata",
            "/status/sessions",
            "/library/sections",
        )
    )


def failure_is_refused(error: str) -> bool:
    """The host is not accepting connections."""
    text = str(error or "").strip().lower()
    return "connection refused" in text or "actively refused" in text or "errno 111" in text


def is_transcode_start_url(url: str) -> bool:
    """Plex universal HLS start. One of these is in flight per library play."""
    path = urllib.parse.urlparse(str(url or "").strip()).path
    return "transcode/universal/start.m3u8" in path


def transcode_start_title(url: str) -> str:
    """Rating key carried on a universal start URL, or empty."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(str(url or "").strip()).query)
    raw = str((query.get("path") or [""])[0] or "")
    marker = "/library/metadata/"
    if marker not in raw:
        return ""
    return raw.split(marker, 1)[1].split("/", 1)[0].strip()


def transcode_start_key(url: str) -> str:
    """Per-title key. A slow start of one rating key does not name the host."""
    host = host_key(url)
    if not host:
        return ""
    title = transcode_start_title(url) or "unknown"
    return f"{host}|transcode-start|{title}"


class HostCircuitRegistry:
    """Process-wide per-host breakers shared by all connector HTTP helpers."""

    def __init__(self, *, cooldown_seconds: int = HOST_CIRCUIT_COOLDOWN_SECONDS) -> None:
        self._cooldown_seconds = int(cooldown_seconds)
        self._lock = threading.Lock()
        self._breakers: Dict[str, QuarantineInfo] = {}
        # Hosts with a library transcode start in flight. Timeouts while the
        # count is positive stay off the shared host breaker.
        self._start_holds: Dict[str, int] = {}

    def _get_locked(self, key: str) -> QuarantineInfo:
        info = self._breakers.get(key)
        if info is None:
            info = QuarantineInfo(cooldown_seconds=self._cooldown_seconds)
            self._breakers[key] = info
        return info

    @contextmanager
    def hold_transcode_start(self, url: str) -> Iterator[None]:
        """Mark ``url``'s host as waiting on one library transcode start.

        Nested starts on the same host share one count. Timeouts recorded
        while the count is positive do not open the host breaker.
        """
        host = host_key(url)
        if not host:
            yield
            return
        with self._lock:
            self._start_holds[host] = self._start_holds.get(host, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                left = int(self._start_holds.get(host, 0)) - 1
                if left <= 0:
                    self._start_holds.pop(host, None)
                else:
                    self._start_holds[host] = left

    def before_request(self, url: str) -> None:
        if getattr(_bypass, "active", False):
            return
        host = host_key(url)
        if not host:
            return
        with self._lock:
            info = self._get_locked(host)
            if info.is_quarantined:
                remaining = float(info.remaining_seconds or 0.0)
                raise CircuitOpenError(host, remaining)
            if is_transcode_start_url(url):
                title_key = transcode_start_key(url)
                title = self._breakers.get(title_key)
                if title is not None and title.is_quarantined:
                    remaining = float(title.remaining_seconds or 0.0)
                    raise CircuitOpenError(title_key, remaining)

    def record_success(self, url: str) -> None:
        host = host_key(url)
        if not host:
            return
        with self._lock:
            self._get_locked(host).record_success()
            if is_transcode_start_url(url):
                title = self._breakers.get(transcode_start_key(url))
                if title is not None:
                    title.record_success()

    def record_failure(self, url: str, error: str) -> None:
        host = host_key(url)
        if not host:
            return
        with self._lock:
            held = int(self._start_holds.get(host, 0)) > 0
            # A heavy timeout is one title being slow. It does not say the
            # host is down. ``/identity`` does. A refused connection does.
            # A transcode start's own timeout stays on that title so a later
            # start of the same rating key can fail fast, without closing
            # the breaker the next title uses.
            if failure_is_timeout(error) and is_transcode_start_url(url):
                key = transcode_start_key(url)
            elif failure_is_timeout(error) and is_health_check_url(url):
                key = host
            elif failure_is_timeout(error) and (is_heavy_call_url(url) or held):
                return
            else:
                key = host
            info = self._get_locked(key)
            opened = info.record_failure(error)
        if opened:
            logger.warning(
                "Circuit opened for %s after %s consecutive failures: %s",
                key,
                QUARANTINE_THRESHOLD,
                error,
            )

    def is_open(self, url: str) -> bool:
        key = host_key(url)
        if not key:
            return False
        with self._lock:
            info = self._breakers.get(key)
            if info is None:
                return False
            return info.is_quarantined

    def remaining_seconds(self, url: str) -> Optional[float]:
        key = host_key(url)
        if not key:
            return None
        with self._lock:
            info = self._breakers.get(key)
            if info is None or not info.is_quarantined:
                return None
            return info.remaining_seconds

    def reset(self) -> None:
        with self._lock:
            self._breakers.clear()
            self._start_holds.clear()


host_circuits = HostCircuitRegistry()
_bypass = threading.local()


@contextmanager
def bypass_host_circuits() -> Iterator[None]:
    """Allow HTTP probes while still recording success/failure (Tunarr startup wait)."""
    previous = getattr(_bypass, "active", False)
    _bypass.active = True
    try:
        yield
    finally:
        _bypass.active = previous


def is_host_circuit_open(url: str) -> bool:
    return host_circuits.is_open(url)


def circuit_remaining_seconds(url: str) -> Optional[float]:
    return host_circuits.remaining_seconds(url)


def circuit_backoff_seconds(url: str, *, floor: int) -> int:
    remaining = host_circuits.remaining_seconds(url)
    if remaining is None:
        return int(floor)
    return max(int(floor), int(remaining))


def reset_host_circuits() -> None:
    """Clear per-host breakers (unit tests only)."""
    host_circuits.reset()
