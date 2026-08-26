"""Theater poster proxy — never emit tokenized Plex URLs on the wire."""

from __future__ import annotations

import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Response

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.theater import POSTER_CACHE_CONTROL

logger = logging.getLogger(__name__)

_ALLOWED_HOST_SUFFIXES = (
    "image.tmdb.org",
    "themoviedb.org",
    "fanart.tv",
    "assets.fanart.tv",
    "artworks.thetvdb.com",
)


def _host_allowed(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


def resolve_library_poster_url(db: Database, rating_key: str) -> Optional[str]:
    key = str(rating_key or "").strip()
    if not key:
        return None
    try:
        row = db.library_item_by_rating_key(key)
    except Exception:  # noqa: BLE001
        return None
    if row is None:
        return None
    raw = row["poster_url"] if "poster_url" in row.keys() else ""
    url = str(raw or "").strip()
    return url or None


async def fetch_poster_bytes(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
) -> Tuple[bytes, str]:
    """Return (body, content_type) for a library poster, fetched server-side."""
    source = resolve_library_poster_url(db, rating_key)
    if not source:
        raise HTTPException(status_code=404, detail="Poster not found")

    if source.startswith("http://") or source.startswith("https://"):
        if "X-Plex-Token=" in source or "X-Plex-Token" in source:
            raise HTTPException(status_code=404, detail="Poster not found")
        if not _host_allowed(source):
            # Absolute non-CDN URL: still proxy once but never rewrite with tokens.
            # Fail closed for unknown hosts that look like Plex.
            parsed = urlparse(source)
            host = (parsed.hostname or "").lower()
            if "plex" in host or host.endswith(".local"):
                raise HTTPException(status_code=404, detail="Poster not found")
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(source)
        except httpx.HTTPError as exc:
            logger.debug("theater poster fetch failed: %s", exc)
            raise HTTPException(status_code=502, detail="Poster upstream failed") from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=404, detail="Poster not found")
        content_type = response.headers.get("content-type") or "image/jpeg"
        return response.content, content_type.split(";")[0].strip()

    # Relative Plex library path — fetch with server token, never leak it.
    if not settings.plex_url or not settings.plex_token:
        raise HTTPException(status_code=404, detail="Poster not found")
    from projectionist.connectors.plex import PlexClient

    client = PlexClient(settings.plex_url, settings.plex_token, timeout=15)
    absolute = client.thumb_url(source)
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http:
            response = await http.get(absolute)
    except httpx.HTTPError as exc:
        logger.debug("theater plex poster fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="Poster upstream failed") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=404, detail="Poster not found")
    content_type = response.headers.get("content-type") or "image/jpeg"
    return response.content, content_type.split(";")[0].strip()


def poster_response(body: bytes, content_type: str) -> Response:
    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": POSTER_CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
        },
    )
