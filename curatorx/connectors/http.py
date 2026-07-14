"""Shared HTTP helpers for connectors."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Mapping, Optional

from curatorx.logging_config import sanitize_log_message, sanitize_url

logger = logging.getLogger(__name__)

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
    request = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    safe_url = sanitize_url(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw.strip():
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        detail = sanitize_log_message(error.read().decode("utf-8", errors="replace"))
        logger.warning("HTTP %s %s from %s: %s", method, error.code, safe_url, detail[:500])
        raise RuntimeError(f"HTTP {error.code} from {safe_url}: {detail}") from error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, socket.timeout):
            logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        else:
            logger.warning("Request failed %s %s: %s", method, safe_url, reason)
        raise RuntimeError(f"Request failed for {safe_url}: {reason}") from error
    except TimeoutError as error:
        logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        raise RuntimeError(f"Timeout requesting {safe_url}") from error


def request_empty(
    url: str,
    *,
    method: str = "PUT",
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
) -> None:
    request = urllib.request.Request(url, method=method, headers=dict(headers or {}))
    safe_url = sanitize_url(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as error:
        detail = sanitize_log_message(error.read().decode("utf-8", errors="replace"))
        logger.warning("HTTP %s %s from %s: %s", method, error.code, safe_url, detail[:500])
        raise RuntimeError(f"HTTP {error.code} from {safe_url}: {detail}") from error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, socket.timeout):
            logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        else:
            logger.warning("Request failed %s %s: %s", method, safe_url, reason)
        raise RuntimeError(f"Request failed for {safe_url}: {reason}") from error
    except TimeoutError as error:
        logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        raise RuntimeError(f"Timeout requesting {safe_url}") from error


def request_xml(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Mapping[str, str]] = None,
    timeout: int = 30,
) -> ET.Element:
    request = urllib.request.Request(url, method=method, headers=dict(headers or {}))
    safe_url = sanitize_url(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return ET.fromstring(response.read())
    except urllib.error.HTTPError as error:
        detail = sanitize_log_message(error.read().decode("utf-8", errors="replace"))
        logger.warning("HTTP %s %s from %s: %s", method, error.code, safe_url, detail[:500])
        raise RuntimeError(f"HTTP {error.code} from {safe_url}: {detail}") from error
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, socket.timeout):
            logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        else:
            logger.warning("Request failed %s %s: %s", method, safe_url, reason)
        raise RuntimeError(f"Request failed for {safe_url}: {reason}") from error
    except TimeoutError as error:
        logger.warning("Timeout %s %s (timeout=%ss)", method, safe_url, timeout)
        raise RuntimeError(f"Timeout requesting {safe_url}") from error


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


def _provider_id_from_guid(guid: str, marker: str, key: str, result: dict[str, str]) -> None:
    if key in result or marker not in guid:
        return
    result[key] = guid.split(marker, 1)[-1].split("?")[0]


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
