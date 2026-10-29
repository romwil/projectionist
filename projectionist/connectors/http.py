"""Shared HTTP helpers for connectors."""

from __future__ import annotations

import ipaddress
import json
import logging
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping, Optional

from projectionist.circuit_breaker import host_circuits
from projectionist.logging_config import sanitize_log_message, sanitize_url

logger = logging.getLogger(__name__)

# Idempotent reads only. Mutating methods never retry, even on 429/5xx.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})
_IDEMPOTENT_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 0.25
_RETRY_MAX_DELAY_S = 8.0
_RETRY_AFTER_CAP_S = 30.0
_RETRY_AFTER_JITTER_S = 0.25

_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)


def validate_outbound_url(url: str, *, allow_private: bool = True) -> str:
    """Validate an operator-supplied URL before connector fetches (SSRF guard).

    Blocks non-http(s) schemes, link-local / metadata ranges, and known metadata
    hostnames. Private RFC1918 targets stay allowed by default for homelab
    *arr/Plex URLs when ``allow_private`` is True.
    """
    cleaned = str(url or "").strip()
    if not cleaned:
        raise ValueError("URL is required")
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise ValueError("URL hostname is required")
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".metadata.google.internal"):
        raise ValueError("URL host is not allowed")
    # Literal IP in the hostname (no DNS needed).
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    candidates = [literal] if literal is not None else []
    if literal is None:
        try:
            infos = socket.getaddrinfo(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
        except socket.gaierror:
            # Unresolved hostnames (e.g. .test / mDNS) are allowed; fetch fails later.
            return cleaned
        for info in infos:
            try:
                candidates.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
    for ip in candidates:
        if ip is None:
            continue
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise ValueError("URL resolves to a blocked address range")
        if ip.is_link_local:
            raise ValueError("URL resolves to a link-local or metadata address")
        if ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"):
            raise ValueError("URL resolves to a link-local or metadata address")
        if ip.version == 6 and (
            ip in ipaddress.ip_network("fe80::/10") or ip in ipaddress.ip_network("fd00:ec2::254/128")
        ):
            raise ValueError("URL resolves to a link-local or metadata address")
        if not allow_private and ip.is_private:
            raise ValueError("URL resolves to a private address range")
    return cleaned


def hosts_match(left_url: str, right_url: str) -> bool:
    left = urllib.parse.urlparse(str(left_url or "").strip())
    right = urllib.parse.urlparse(str(right_url or "").strip())
    left_host = (left.hostname or "").strip().lower()
    right_host = (right.hostname or "").strip().lower()
    if not left_host or not right_host:
        return False
    return left_host == right_host


def _http_status_trips_breaker(status: int) -> bool:
    return status >= 500 or status == 429


def _is_idempotent_method(method: str) -> bool:
    return str(method or "").strip().upper() in _IDEMPOTENT_METHODS


def _parse_retry_after(raw: Optional[str]) -> Optional[float]:
    """Parse Retry-After as seconds. Caps at ``_RETRY_AFTER_CAP_S``; past dates -> 0."""
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    try:
        seconds = float(cleaned)
    except ValueError:
        seconds = None
    if seconds is not None:
        if seconds < 0:
            return None
        return min(seconds, _RETRY_AFTER_CAP_S)
    try:
        when = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delay = (when - datetime.now(timezone.utc)).total_seconds()
    if delay < 0:
        return 0.0
    return min(delay, _RETRY_AFTER_CAP_S)


def _retry_after_from_error(error: urllib.error.HTTPError) -> Optional[float]:
    headers = getattr(error, "headers", None) or getattr(error, "hdrs", None)
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    raw = getter("Retry-After")
    if raw is None:
        raw = getter("retry-after")
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    return _parse_retry_after(None if raw is None else str(raw))


def _backoff_seconds(attempt: int, retry_after: Optional[float]) -> float:
    """Delay before the next attempt. ``attempt`` is the 0-based failure index."""
    if retry_after is not None:
        jitter = random.uniform(0.0, _RETRY_AFTER_JITTER_S)
        return min(max(0.0, retry_after) + jitter, _RETRY_AFTER_CAP_S)
    ceiling = min(_RETRY_MAX_DELAY_S, _RETRY_BASE_DELAY_S * (2 ** attempt))
    return random.uniform(0.0, ceiling)


def _log_http_error(
    method: str,
    status: int,
    safe_url: str,
    detail: str,
    *,
    quiet_statuses: Optional[tuple[int, ...]],
) -> None:
    # Optional routes (Plex Live TV when the path is absent) must not warn on every poll.
    if quiet_statuses and status in quiet_statuses:
        logger.debug("HTTP %s %s from %s (quiet)", method, status, safe_url)
    else:
        logger.warning("HTTP %s %s from %s: %s", method, status, safe_url, detail[:500])


def _execute_request(
    url: str,
    *,
    method: str,
    headers: Optional[Mapping[str, str]],
    data: Optional[bytes],
    timeout: int,
    max_bytes: Optional[int] = None,
    quiet_statuses: Optional[tuple[int, ...]] = None,
) -> bytes:
    """urlopen with the shared per-host circuit breaker.

    GET/HEAD retry on 429 and 5xx (cap 3 attempts) with jittered backoff and
    Retry-After. POST/PUT/DELETE never retry. Breaker failures are recorded
    only after retries exhaust so one blip does not trip the host.
    """
    method_upper = str(method or "GET").strip().upper() or "GET"
    attempts = _IDEMPOTENT_RETRY_ATTEMPTS if _is_idempotent_method(method_upper) else 1
    req_headers = dict(headers or {})
    safe_url = sanitize_url(url)

    for attempt in range(attempts):
        host_circuits.before_request(url)
        request = urllib.request.Request(
            url, data=data, method=method_upper, headers=req_headers
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(max_bytes) if max_bytes is not None else response.read()
            host_circuits.record_success(url)
            return body
        except urllib.error.HTTPError as error:
            status = int(error.code)
            detail = sanitize_log_message(error.read().decode("utf-8", errors="replace"))
            retryable = (
                attempt < attempts - 1
                and _is_idempotent_method(method_upper)
                and _http_status_trips_breaker(status)
            )
            if retryable:
                delay = _backoff_seconds(attempt, _retry_after_from_error(error))
                logger.debug(
                    "HTTP %s %s from %s; retrying in %.2fs (attempt %s/%s)",
                    method_upper,
                    status,
                    safe_url,
                    delay,
                    attempt + 1,
                    attempts,
                )
                time.sleep(delay)
                continue
            _log_http_error(
                method_upper, status, safe_url, detail, quiet_statuses=quiet_statuses
            )
            if _http_status_trips_breaker(status):
                host_circuits.record_failure(url, f"HTTP {status}")
            else:
                host_circuits.record_success(url)
            raise RuntimeError(f"HTTP {status} from {safe_url}: {detail}") from error
        except urllib.error.URLError as error:
            reason = error.reason
            if isinstance(reason, socket.timeout):
                logger.warning("Timeout %s %s (timeout=%ss)", method_upper, safe_url, timeout)
            else:
                logger.warning("Request failed %s %s: %s", method_upper, safe_url, reason)
            host_circuits.record_failure(url, str(reason))
            raise RuntimeError(f"Request failed for {safe_url}: {reason}") from error
        except TimeoutError as error:
            logger.warning("Timeout %s %s (timeout=%ss)", method_upper, safe_url, timeout)
            host_circuits.record_failure(url, "timeout")
            raise RuntimeError(f"Timeout requesting {safe_url}") from error
        except OSError as error:
            logger.warning("Request failed %s %s: %s", method_upper, safe_url, error)
            host_circuits.record_failure(url, str(error))
            raise RuntimeError(f"Request failed for {safe_url}: {error}") from error

    raise RuntimeError(f"Request failed for {safe_url}")  # pragma: no cover


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Mapping[str, str]] = None,
    body: Optional[Mapping[str, Any]] = None,
    timeout: int = 30,
) -> Any:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    raw = _execute_request(
        url,
        method=method,
        headers=req_headers,
        data=data,
        timeout=timeout,
    ).decode("utf-8")
    if not raw.strip():
        return None
    return json.loads(raw)


def request_empty(
    url: str,
    *,
    method: str = "PUT",
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
) -> None:
    _execute_request(
        url,
        method=method,
        headers=headers,
        data=None,
        timeout=timeout,
    )


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
    max_bytes: Optional[int] = None,
) -> bytes:
    """GET/POST raw bytes through the shared host circuit breaker."""
    return _execute_request(
        url,
        method=method,
        headers=headers,
        data=None,
        timeout=timeout,
        max_bytes=max_bytes,
    )


def request_xml(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
    quiet_statuses: Optional[tuple[int, ...]] = None,
) -> ET.Element:
    return ET.fromstring(
        _execute_request(
            url,
            method=method,
            headers=headers,
            data=None,
            timeout=timeout,
            quiet_statuses=quiet_statuses,
        )
    )


def optional_int(value: Optional[str]) -> Optional[int]:
    """Parse an optional integer from a string.

    Plex attributes such as ``userRating`` are often float-like (``"9.0"``).
    Coerce via float first so those values do not raise during library sync.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return int(float(value))


def _numeric_provider_id(raw: str) -> Optional[str]:
    """Normalize Plex provider id paths to a bare numeric id.

    Discover / modern Plex Guids often look like ``tmdb://movie/550`` or
    ``tvdb://series/81189`` rather than ``tmdb://550``.
    """
    cleaned = str(raw or "").strip().split("?")[0].strip("/")
    if not cleaned:
        return None
    if cleaned.isdigit():
        return cleaned
    # Prefer the last slash-separated segment when it is numeric.
    tail = cleaned.rsplit("/", 1)[-1]
    if tail.isdigit():
        return tail
    return None


def _provider_id_from_guid(guid: str, marker: str, key: str, result: dict[str, str]) -> None:
    if key in result or marker not in guid:
        return
    numeric = _numeric_provider_id(guid.split(marker, 1)[-1])
    if numeric:
        result[key] = numeric


def parse_plex_guid(guid: str) -> dict[str, str]:
    """Extract provider IDs from Plex GUID strings."""
    result: dict[str, str] = {}
    if not guid:
        return result
    _provider_id_from_guid(guid, "themoviedb://", "tmdb_id", result)
    _provider_id_from_guid(guid, "tmdb://", "tmdb_id", result)
    _provider_id_from_guid(guid, "tvdb://", "tvdb_id", result)
    if "imdb://" in guid or "com.plexapp.agents.imdb://" in guid:
        parts = guid.replace("com.plexapp.agents.imdb://", "imdb://")
        result["imdb_id"] = parts.split("imdb://", 1)[-1].split("?")[0]
    return result


def merge_plex_provider_ids(*guids: str) -> dict[str, str]:
    """Merge provider IDs from Plex primary guid and Guid child entries."""
    merged: dict[str, str] = {}
    for guid in guids:
        for key, value in parse_plex_guid(guid).items():
            merged.setdefault(key, value)
    return merged
