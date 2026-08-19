"""Shared consecutive-failure circuit breaker.

The idle scheduler quarantines tasks with this type. Connector HTTP helpers
use the same class, keyed by host, so Live Channels pollers and every other
``request_json`` / ``request_xml`` / ``request_empty`` caller fail fast when
Plex or Tunarr is unreachable instead of hammering the local socket.
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


class HostCircuitRegistry:
    """Process-wide per-host breakers shared by all connector HTTP helpers."""

    def __init__(self, *, cooldown_seconds: int = HOST_CIRCUIT_COOLDOWN_SECONDS) -> None:
        self._cooldown_seconds = int(cooldown_seconds)
        self._lock = threading.Lock()
        self._breakers: Dict[str, QuarantineInfo] = {}

    def _get_locked(self, key: str) -> QuarantineInfo:
        info = self._breakers.get(key)
        if info is None:
            info = QuarantineInfo(cooldown_seconds=self._cooldown_seconds)
            self._breakers[key] = info
        return info

    def before_request(self, url: str) -> None:
        if getattr(_bypass, "active", False):
            return
        key = host_key(url)
        if not key:
            return
        with self._lock:
            info = self._get_locked(key)
            if info.is_quarantined:
                remaining = float(info.remaining_seconds or 0.0)
                raise CircuitOpenError(key, remaining)

    def record_success(self, url: str) -> None:
        key = host_key(url)
        if not key:
            return
        with self._lock:
            self._get_locked(key).record_success()

    def record_failure(self, url: str, error: str) -> None:
        key = host_key(url)
        if not key:
            return
        with self._lock:
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
