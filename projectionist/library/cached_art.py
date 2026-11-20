"""Authenticated cached posters and backdrops (EXP-006).

Payloads point at ``/api/library/art/...``. The route reads the library row and
fetches under the SEC-013 policy. Clients never receive the upstream URL.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional
from urllib.parse import quote, urlencode

from projectionist.library.art_egress import (
    ArtBlocked,
    ArtUnavailable,
    ArtUpstream,
    fetch_art,
    plan_art_fetch,
)
from projectionist.theater.poster_cache import get_poster_cache

ART_CACHE_NAME = "library-art-cache"
_KINDS = frozenset({"poster", "backdrop"})
_MEDIA_TYPES = frozenset({"movie", "show"})


class ArtNotFound(Exception):
    """No art for this title, or this viewer may not see it."""


def art_route(media_type: str, id_type: str, item_id: str, kind: str) -> str:
    query = urlencode((("id_type", id_type), ("kind", kind)))
    return f"/api/library/art/{quote(media_type, safe='')}/{quote(str(item_id), safe='')}?{query}"


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _identity(item: Mapping[str, Any]) -> Optional[tuple[str, str, str]]:
    if item.get("in_library") is False:
        return None
    media_type = str(item.get("media_type") or "").strip().lower()
    if media_type == "episode":
        media_type = "show"
    if media_type not in _MEDIA_TYPES:
        return None
    tmdb_id = _positive_int(item.get("tmdb_id"))
    if tmdb_id:
        return media_type, "tmdb", str(tmdb_id)
    rating_key = str(item.get("rating_key") or "").strip()
    if rating_key:
        return media_type, "rating_key", rating_key
    if media_type == "show":
        tvdb_id = _positive_int(item.get("tvdb_id"))
        if tvdb_id:
            return media_type, "tvdb", str(tvdb_id)
    return None


def point_cached_art(payload: Any, settings: object) -> Any:
    """Replace servable poster and backdrop URLs with the art route.

    Copies the payload. Items that are not in the library keep a public CDN
    URL when they already have one.
    """
    if isinstance(payload, Mapping):
        out = {key: point_cached_art(value, settings) for key, value in payload.items()}
        identity = _identity(payload)
        if identity is None:
            return out
        media_type, id_type, item_id = identity
        for kind, field in (("poster", "poster_url"), ("backdrop", "backdrop_url")):
            raw = payload.get(field)
            if isinstance(raw, str) and plan_art_fetch(raw, settings) is not None:
                out[field] = art_route(media_type, id_type, item_id, kind)
        return out
    if isinstance(payload, list):
        return [point_cached_art(item, settings) for item in payload]
    return payload


def _row_dict(row: Any) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    try:
        return {key: row[key] for key in row.keys()}
    except (AttributeError, TypeError):
        return None


def resolve_art_row(
    db: Any, media_type: str, item_id: str, id_type: str
) -> Optional[dict[str, Any]]:
    kind = str(media_type or "").strip().lower()
    ident = str(item_id or "").strip()
    which = str(id_type or "").strip().lower()
    if kind not in _MEDIA_TYPES or not ident:
        return None
    row = None
    if which == "rating_key":
        row = db.library_item_by_rating_key(ident)
    elif which == "tmdb":
        tmdb_id = _positive_int(ident)
        if tmdb_id:
            row = db.library_item_by_tmdb(tmdb_id, kind)
    elif which == "tvdb" and kind == "show":
        tvdb_id = _positive_int(ident)
        if tvdb_id:
            row = db.library_item_by_tvdb(tvdb_id)
    found = _row_dict(row)
    if found is None:
        return None
    if str(found.get("media_type") or "").strip().lower() not in {kind, ""}:
        return None
    return found


async def load_cached_art(
    db: Any,
    settings: Any,
    *,
    media_type: str,
    item_id: str,
    id_type: str,
    kind: str,
    user: Any,
    data_dir: Any,
) -> tuple[bytes, str, str]:
    """Return ``(body, media_type, etag)`` for one poster or backdrop."""
    art_kind = str(kind or "").strip().lower()
    if art_kind not in _KINDS:
        raise ArtNotFound()
    row = resolve_art_row(db, media_type, item_id, id_type)
    if row is None:
        raise ArtNotFound()
    from projectionist.youth.apply import title_allowed_for_user

    if not title_allowed_for_user(row, user=user, settings=settings):
        raise ArtNotFound()
    field = "poster_url" if art_kind == "poster" else "backdrop_url"
    plan = plan_art_fetch(str(row.get(field) or ""), settings)
    if plan is None:
        raise ArtNotFound()

    cache_key = f"{id_type}:{media_type}:{item_id}:{art_kind}"
    cache = get_poster_cache(data_dir, cache_name=ART_CACHE_NAME) if data_dir is not None else None
    if cache is not None:
        if cache.is_negative(cache_key):
            raise ArtNotFound()
        hit = cache.get(cache_key)
        if hit is not None:
            return hit.body, hit.content_type, hit.etag

        async def _load():
            again = cache.get(cache_key)
            if again is not None:
                return again
            try:
                body, media = await fetch_art(plan, settings)
            except (ArtBlocked, ArtUnavailable) as exc:
                cache.remember_miss(cache_key)
                raise ArtNotFound() from exc
            except ArtUpstream:
                raise
            return cache.put(cache_key, body, media, source=plan.url)

        stored = await cache.single_flight(cache_key, _load)
        return stored.body, stored.content_type, stored.etag

    try:
        body, media = await fetch_art(plan, settings)
    except (ArtBlocked, ArtUnavailable) as exc:
        raise ArtNotFound() from exc
    from projectionist.theater.poster_cache import content_etag

    return body, media, content_etag(body)
