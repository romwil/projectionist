"""Theater poster proxy — never emit tokenized Plex URLs on the wire."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Response

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.theater import POSTER_CACHE_CONTROL
from projectionist.theater.poster_cache import (
    CachedPoster,
    get_poster_cache,
)

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


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Poster not found")


async def _http_get_bytes(url: str) -> Tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.debug("theater poster fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="Poster upstream failed") from exc
    if response.status_code >= 400:
        raise _not_found()
    content_type = response.headers.get("content-type") or "image/jpeg"
    return response.content, content_type.split(";")[0].strip()


def _http_get_bytes_sync(url: str) -> Tuple[bytes, str]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        logger.debug("theater poster fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="Poster upstream failed") from exc
    if response.status_code >= 400:
        raise _not_found()
    content_type = response.headers.get("content-type") or "image/jpeg"
    return response.content, content_type.split(";")[0].strip()


def _resolve_upstream_url(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
) -> str:
    """Return absolute fetch URL. Prefer CDN; use tokenized Plex only as fallback."""
    source = resolve_library_poster_url(db, rating_key)
    if not source:
        raise _not_found()

    if source.startswith("http://") or source.startswith("https://"):
        if "X-Plex-Token=" in source or "X-Plex-Token" in source:
            raise _not_found()
        if _host_allowed(source):
            return source
        # Absolute non-CDN URL: still proxy once but never rewrite with tokens.
        # Fail closed for unknown hosts that look like Plex.
        parsed = urlparse(source)
        host = (parsed.hostname or "").lower()
        if "plex" in host or host.endswith(".local"):
            raise _not_found()
        return source

    # Relative Plex library path — fetch with server token, never leak it.
    if not settings.plex_url or not settings.plex_token:
        raise _not_found()
    from projectionist.connectors.plex import PlexClient

    client = PlexClient(settings.plex_url, settings.plex_token, timeout=15)
    return client.thumb_url(source)


async def _upstream_fetch(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
) -> Tuple[bytes, str, str]:
    url = _resolve_upstream_url(db, settings, rating_key=rating_key)
    body, content_type = await _http_get_bytes(url)
    return body, content_type, url


def _upstream_fetch_sync(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
) -> Tuple[bytes, str, str]:
    url = _resolve_upstream_url(db, settings, rating_key=rating_key)
    body, content_type = _http_get_bytes_sync(url)
    return body, content_type, url


async def fetch_poster_bytes(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
    data_dir: Optional[Path] = None,
) -> Tuple[bytes, str, str]:
    """Return (body, content_type, etag) for a library poster, with shared cache."""
    key = str(rating_key or "").strip()
    if not key:
        raise _not_found()

    cache = get_poster_cache(data_dir) if data_dir is not None else None
    if cache is not None:
        if cache.is_negative(key):
            raise _not_found()
        hit = cache.get(key)
        if hit is not None:
            return hit.body, hit.content_type, hit.etag

        async def _load() -> CachedPoster:
            # Re-check after winning single-flight.
            again = cache.get(key)
            if again is not None:
                return again
            try:
                body, content_type, source = await _upstream_fetch(
                    db, settings, rating_key=key
                )
            except HTTPException as exc:
                if exc.status_code == 404:
                    cache.remember_miss(key)
                raise
            return cache.put(key, body, content_type, source=source)

        poster = await cache.single_flight(key, _load)
        return poster.body, poster.content_type, poster.etag

    body, content_type, _source = await _upstream_fetch(db, settings, rating_key=key)
    from projectionist.theater.poster_cache import content_etag

    return body, content_type, content_etag(body)


def fetch_poster_bytes_sync(
    db: Database,
    settings: Settings,
    *,
    rating_key: str,
    data_dir: Optional[Path] = None,
) -> Tuple[bytes, str, str]:
    """Sync variant for background prefetch threads."""
    key = str(rating_key or "").strip()
    if not key:
        raise _not_found()

    cache = get_poster_cache(data_dir) if data_dir is not None else None
    if cache is not None:
        if cache.is_negative(key):
            raise _not_found()
        hit = cache.get(key)
        if hit is not None:
            return hit.body, hit.content_type, hit.etag
        try:
            body, content_type, source = _upstream_fetch_sync(
                db, settings, rating_key=key
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                cache.remember_miss(key)
            raise
        poster = cache.put(key, body, content_type, source=source)
        return poster.body, poster.content_type, poster.etag

    body, content_type, _source = _upstream_fetch_sync(db, settings, rating_key=key)
    from projectionist.theater.poster_cache import content_etag

    return body, content_type, content_etag(body)


def poster_response(
    body: bytes,
    content_type: str,
    *,
    etag: str = "",
) -> Response:
    headers = {
        "Cache-Control": POSTER_CACHE_CONTROL,
        "X-Content-Type-Options": "nosniff",
    }
    if etag:
        headers["ETag"] = etag
    return Response(
        content=body,
        media_type=content_type,
        headers=headers,
    )
