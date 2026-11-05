"""Public-only outbound guard for user-supplied notification destinations (SEC-007).

Two layers:

* ``check_public_destination`` resolves a URL's host before anything is sent and
  refuses private, loopback, link-local, and cloud-metadata targets.
* ``public_only_outbound`` is a context manager that checks every DNS resolution
  made by the current thread while it is active. ``urllib3`` / ``requests`` and
  ``smtplib`` resolve through ``socket.getaddrinfo`` before every connect, so a
  redirect to an internal host is refused before its socket opens.

The connect-time check follows a ``contextvars`` context. Apprise 2.1 copies
that context onto the worker thread it uses for a timed notify, so a redirect
is still refused before connect. A plain ``threading.Thread`` does not inherit
it, so Plex and *arr keep their LAN access.
"""

from __future__ import annotations

import contextvars
import ipaddress
import re
import socket
import threading
import urllib.parse
from contextlib import contextmanager
from typing import Iterator, Optional

BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "instance-data",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)

_LINK_LOCAL_V4 = ipaddress.ip_network("169.254.0.0/16")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")
_AWS_METADATA_V6 = ipaddress.ip_network("fd00:ec2::254/128")
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")
_TOKEN_HOST = re.compile(r"^(?:[0-9]+|0x[0-9a-f]+)$")


class OutboundBlocked(socket.gaierror, ValueError):
    """Raised when an outbound destination is not a public address.

    A ``gaierror`` so HTTP / SMTP transports treat it like a failed lookup and
    never open the socket.
    """


def blocked_ip_reason(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool = False
) -> Optional[str]:
    """Return a short reason when ``ip`` must not be contacted, else ``None``."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address):
        if ip.is_link_local or ip in _LINK_LOCAL_V4:
            return "link-local or metadata address"
        if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            return "blocked address range"
        if not allow_private and (ip.is_private or ip in _CGNAT_V4):
            return "private address range"
        return None
    if ip.is_link_local or ip in _LINK_LOCAL_V6 or ip in _AWS_METADATA_V6:
        return "link-local or metadata address"
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return "blocked address range"
    if not allow_private and ip.is_private:
        return "private address range"
    return None


def _host_is_blocked_name(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    return host in BLOCKED_HOSTNAMES or host.endswith(".metadata.google.internal")


_real_getaddrinfo = socket.getaddrinfo


def _resolve(host: str, port: int | str | None):
    return _real_getaddrinfo(host, port, 0, socket.SOCK_STREAM)


def check_public_host(host: str, port: int | str | None = None) -> None:
    """Raise ``OutboundBlocked`` when ``host`` is (or resolves to) a non-public address.

    Hostnames that do not resolve are allowed here; the connect-time guard
    re-checks whatever they resolve to when the transport connects.
    """
    hostname = str(host or "").strip().strip("[]").lower()
    if not hostname:
        return
    if _host_is_blocked_name(hostname):
        raise OutboundBlocked("Destination host is not allowed")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        reason = blocked_ip_reason(literal)
        if reason:
            raise OutboundBlocked(f"Destination resolves to a {reason}")
        return
    if _TOKEN_HOST.match(hostname):
        # Apprise vendor schemes put numeric ids in the host slot (discord://<id>/...);
        # the resolver would read them as legacy IPv4 integers.
        return
    try:
        infos = _resolve(hostname, port)
    except (socket.gaierror, UnicodeError, OSError):
        return
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        except ValueError:
            continue
        reason = blocked_ip_reason(ip)
        if reason:
            raise OutboundBlocked(f"Destination resolves to a {reason}")


def check_public_destination(url: str) -> None:
    """Preflight one destination URL (any scheme that carries a network host)."""
    parsed = urllib.parse.urlparse(str(url or "").strip())
    try:
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise OutboundBlocked("Destination URL is malformed") from exc
    check_public_host(hostname, port)


class _GuardState:
    """Mutable so a copied context (Apprise's worker) shares the refusal with the caller."""

    __slots__ = ("depth", "blocked")

    def __init__(self) -> None:
        self.depth = 0
        self.blocked: Optional[str] = None


_state_var: contextvars.ContextVar[_GuardState] = contextvars.ContextVar("projectionist_outbound_guard")
_install_lock = threading.Lock()
_installed = False


def _state() -> _GuardState:
    try:
        return _state_var.get()
    except LookupError:
        state = _GuardState()
        _state_var.set(state)
        return state


def _guard_active() -> bool:
    return _state().depth > 0


def _refuse(message: str) -> None:
    _state().blocked = message
    raise OutboundBlocked(message)


def last_block_reason() -> Optional[str]:
    """Reason for the most recent refusal inside ``public_only_outbound`` on this context."""
    try:
        return _state_var.get().blocked
    except LookupError:
        return None


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    if not _guard_active():
        return _real_getaddrinfo(host, port, *args, **kwargs)
    hostname = host.decode("idna") if isinstance(host, bytes) else str(host or "")
    if _host_is_blocked_name(hostname):
        _refuse("Destination host is not allowed")
    infos = _real_getaddrinfo(host, port, *args, **kwargs)
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        except ValueError:
            continue
        reason = blocked_ip_reason(ip)
        if reason:
            _refuse(f"Destination resolves to a {reason}")
    return infos


def _install() -> None:
    global _installed
    with _install_lock:
        if _installed:
            return
        socket.getaddrinfo = _guarded_getaddrinfo
        _installed = True


@contextmanager
def public_only_outbound() -> Iterator[None]:
    """Refuse non-public DNS answers in this context until the block exits."""
    _install()
    state = _state()
    if state.depth == 0:
        state.blocked = None
    state.depth += 1
    try:
        yield
    finally:
        state.depth -= 1
