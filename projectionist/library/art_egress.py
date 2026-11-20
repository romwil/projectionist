"""SEC-013: one SSRF-safe policy for fetching household art.

Public art hosts are an exact HTTPS allowlist. Library thumbs are fetched only
from the configured Plex origin, and the server token never leaves this process.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from projectionist.connectors.outbound_guard import OutboundBlocked, public_only_outbound

PUBLIC_ART_HOSTS = frozenset(
    {
        "image.tmdb.org",
        "artworks.thetvdb.com",
        "assets.fanart.tv",
    }
)

MAX_ART_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 3
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


class ArtBlocked(Exception):
    """The URL is not allowed, or a redirect left the policy."""


class ArtUnavailable(Exception):
    """The upstream had no image we can cache."""


class ArtUpstream(Exception):
    """The upstream could not be reached."""


@dataclass(frozen=True)
class ArtFetch:
    url: str
    public: bool
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


def sniff_image(body: bytes) -> str:
    """Return an image media type, or empty when the bytes are not an image."""
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(body) >= 12 and body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _plex_origin(settings: object) -> tuple[str, str, int] | None:
    raw = str(getattr(settings, "plex_url", "") or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").lower()
    if not host or parsed.username or parsed.password:
        return None
    scheme = (parsed.scheme or "http").lower()
    if scheme not in {"http", "https"}:
        return None
    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def _origin(url: str) -> tuple[str, str, int] | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()
    if not host or scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def _plex_art_path(path: str) -> bool:
    if not path or ".." in path or "\\" in path:
        return False
    return (
        path.startswith("/library/")
        or path.startswith("/photo/")
        or path == "/thumb"
        or path.startswith("/thumb/")
    )


def _without_plex_token(query: str) -> str:
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() != "x-plex-token"
    ]
    return urlencode(kept)


def _plex_fetch(settings: object, path: str, query: str) -> ArtFetch | None:
    origin = _plex_origin(settings)
    token = str(getattr(settings, "plex_token", "") or "").strip()
    if origin is None or not token or not _plex_art_path(path):
        return None
    scheme, host, port = origin
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = host if default_port else f"{host}:{port}"
    cleaned = _without_plex_token(query)
    url = urlunparse((scheme, netloc, path, "", cleaned, ""))
    return ArtFetch(
        url=url,
        public=False,
        headers={"X-Plex-Token": token, "Accept": "image/*,*/*;q=0.8"},
    )


def plan_art_fetch(raw: str, settings: object) -> ArtFetch | None:
    """Return a fetch the policy allows, or None. Never echoes a Plex token."""
    text = str(raw or "").strip()
    if not text or text.lower().startswith(("file:", "data:", "javascript:")):
        return None
    if text.startswith("/"):
        parsed = urlparse(text)
        return _plex_fetch(settings, parsed.path or "", parsed.query)

    parsed = urlparse(text)
    origin = _origin(text)
    if origin is None:
        return None
    scheme, host, port = origin
    plex = _plex_origin(settings)
    if plex is not None and (scheme, host, port) == plex:
        return _plex_fetch(settings, parsed.path or "", parsed.query)
    if scheme != "https" or host not in PUBLIC_ART_HOSTS:
        return None
    if parsed.path and (".." in parsed.path or "\\" in parsed.path):
        return None
    return ArtFetch(url=text.split("#", 1)[0], public=True, headers={"Accept": "image/*,*/*;q=0.8"})


def next_art_fetch(current: ArtFetch, location: str, settings: object) -> ArtFetch | None:
    """Validate one redirect. A public host cannot bounce onto the LAN."""
    target = urljoin(current.url, str(location or "").strip())
    planned = plan_art_fetch(target, settings)
    if planned is None:
        return None
    if current.public and not planned.public:
        return None
    return planned


async def request_art(url: str, headers: Mapping[str, str], *, public: bool) -> ArtHttpResponse:
    """GET one hop. Public hosts are refused if DNS answers with a private address."""
    guard = public_only_outbound() if public else nullcontext()
    try:
        with guard:
            async with httpx.AsyncClient(timeout=20.0) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers=dict(headers),
                    follow_redirects=False,
                ) as response:
                    if response.status_code in _REDIRECTS:
                        return ArtHttpResponse(
                            response.status_code,
                            {key.lower(): value for key, value in response.headers.items()},
                            b"",
                        )
                    length = response.headers.get("content-length")
                    if length and length.isdigit() and int(length) > MAX_ART_BYTES:
                        raise ArtUnavailable("image too large")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_ART_BYTES:
                            raise ArtUnavailable("image too large")
                        chunks.append(chunk)
                    return ArtHttpResponse(
                        response.status_code,
                        {key.lower(): value for key, value in response.headers.items()},
                        b"".join(chunks),
                    )
    except OutboundBlocked as exc:
        raise ArtBlocked("destination is not allowed") from exc
    except ArtUnavailable:
        raise
    except httpx.HTTPError as exc:
        raise ArtUpstream("art upstream failed") from exc


async def fetch_art(plan: ArtFetch, settings: object) -> tuple[bytes, str]:
    """Follow a few redirects inside the policy and return image bytes."""
    current = plan
    for _ in range(MAX_REDIRECTS + 1):
        response = await request_art(current.url, current.headers, public=current.public)
        if response.status_code in _REDIRECTS:
            nxt = next_art_fetch(current, str(response.headers.get("location") or ""), settings)
            if nxt is None:
                raise ArtBlocked("redirect is not allowed")
            current = nxt
            continue
        if response.status_code >= 400 or not response.body:
            raise ArtUnavailable("no image")
        media_type = sniff_image(response.body)
        if not media_type:
            raise ArtUnavailable("not an image")
        return response.body, media_type
    raise ArtBlocked("too many redirects")
