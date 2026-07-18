"""Audience-aware sanitizers for library / MCP payloads.

Privacy and member audiences get PublicContentSchema (content yes, infrastructure no).
Owner and mcp_full get InternalPlexSchema minus live X-Plex-Token URLs.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Literal, Mapping, Optional
from urllib.parse import urlparse

Audience = Literal["privacy", "member", "owner", "mcp_full"]

TMDB_IMAGE_HOST = "image.tmdb.org"
TMDB_IMAGE_PREFIX = f"https://{TMDB_IMAGE_HOST}/t/p/"

POSTER_SIZES = ("w185", "w342", "w500", "w780")
BACKDROP_SIZES = ("w300", "w780", "w1280", "original")

# Fields never emitted for privacy / member audiences.
_PUBLIC_DROP_KEYS = frozenset(
    {
        "rating_key",
        "show_rating_key",
        "episode_rating_key",
        "user_id",
        "plex_user_id",
        "email",
        "avatar",
        "avatar_url",
        "file_size",
        "file_size_bytes",
        "view_count",
        "view_offset_ms",
        "duration_ms",
        "added_at",
        "last_viewed_at",
        "in_radarr",
        "in_sonarr",
        "arr_id",
        "path",
        "file_path",
        "absolute_path",
        "plex_token",
        "machine_id",
        "client_id",
        "server_id",
    }
)

_TOKEN_IN_URL = re.compile(r"([?&]X-Plex-Token=)[^&]*", re.IGNORECASE)
_TMDB_SIZE_RE = re.compile(
    r"^(https?://image\.tmdb\.org/t/p/)(w\d+|original)(/.*)$",
    re.IGNORECASE,
)


def _normalize_poster_size(size: Optional[str]) -> str:
    value = str(size or "w500").strip()
    return value if value in POSTER_SIZES else "w500"


def _normalize_backdrop_size(size: Optional[str]) -> str:
    value = str(size or "w1280").strip()
    return value if value in BACKDROP_SIZES else "w1280"


def _settings_image_sizes(settings: Any) -> tuple[str, str]:
    poster = _normalize_poster_size(getattr(settings, "mcp_tmdb_poster_size", None) if settings else None)
    backdrop = _normalize_backdrop_size(
        getattr(settings, "mcp_tmdb_backdrop_size", None) if settings else None
    )
    return poster, backdrop


def is_tmdb_cdn_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == TMDB_IMAGE_HOST


def rewrite_tmdb_size(url: str, size: str) -> str:
    """Rewrite `image.tmdb.org/t/p/{size}/…` to the configured size; else return as-is."""
    match = _TMDB_SIZE_RE.match(str(url or "").strip())
    if not match:
        return str(url or "")
    return f"{match.group(1)}{size}{match.group(3)}"


def strip_plex_token_from_url(url: str) -> str:
    """Remove live X-Plex-Token query params. Empty if the URL was only useful with a token."""
    cleaned = str(url or "").strip()
    if not cleaned:
        return ""
    if "X-Plex-Token" not in cleaned and "x-plex-token" not in cleaned.lower():
        return cleaned
    # Drop token; if nothing secret remains that identifies LAN plex art, prefer empty
    # for non-TMDB hosts so we never re-emit tokenized thumbs.
    without = _TOKEN_IN_URL.sub(r"\1***", cleaned)
    if is_tmdb_cdn_url(cleaned):
        return without.replace("X-Plex-Token=***", "").replace("x-plex-token=***", "")
    return ""


def strip_plex_token_urls(payload: Any) -> Any:
    """Recursively scrub X-Plex-Token from URL-like string fields."""
    if isinstance(payload, Mapping):
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            key_l = str(key).lower()
            if isinstance(value, str) and (
                "url" in key_l or "uri" in key_l or "thumb" in key_l or "art" in key_l
            ):
                out[key] = strip_plex_token_from_url(value)
            else:
                out[key] = strip_plex_token_urls(value)
        return out
    if isinstance(payload, list):
        return [strip_plex_token_urls(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(strip_plex_token_urls(item) for item in payload)
    if isinstance(payload, str) and "X-Plex-Token" in payload:
        return strip_plex_token_from_url(payload)
    return payload


def derive_watch_state(item: Mapping[str, Any]) -> str:
    """Qualitative watch state for public schema (no raw view/added timestamps).

    Uses shared ``watch_progress_state``; maps ``partial`` → ``in_progress`` for
    existing public/MCP consumers. Returns ``unknown`` when no watch signals exist.
    """
    from curatorx.library.watch_progress import watch_progress_state

    total_eps = int(item.get("total_episode_count") or 0)
    has_view_count = "view_count" in item and item.get("view_count") is not None
    has_offset = "view_offset_ms" in item and item.get("view_offset_ms") is not None
    if total_eps <= 0 and not has_view_count and not has_offset:
        return "unknown"

    state = watch_progress_state(item)
    if state == "partial":
        return "in_progress"
    return state


def public_image_urls(
    row: Mapping[str, Any],
    settings: Any = None,
) -> Dict[str, str]:
    """Emit TMDB CDN poster/backdrop only; never Plex/Fanart tokenized thumbs.

    Resolution:
    1. Stored URL already on image.tmdb.org → rewrite to configured size.
    2. Else omit (empty). Callers with tmdb_id may refresh via TMDB separately.
    """
    poster_size, backdrop_size = _settings_image_sizes(settings)
    poster = str(row.get("poster_url") or "").strip()
    backdrop = str(row.get("backdrop_url") or "").strip()
    out_poster = rewrite_tmdb_size(poster, poster_size) if is_tmdb_cdn_url(poster) else ""
    out_backdrop = (
        rewrite_tmdb_size(backdrop, backdrop_size) if is_tmdb_cdn_url(backdrop) else ""
    )
    return {"poster_url": out_poster, "backdrop_url": out_backdrop}


def _is_public_audience(audience: Audience) -> bool:
    return audience in ("privacy", "member")


def _sanitize_mapping(
    payload: Mapping[str, Any],
    *,
    audience: Audience,
    settings: Any,
) -> Dict[str, Any]:
    public = _is_public_audience(audience)
    out: Dict[str, Any] = {}

    # Derive watch_state before dropping telemetry fields.
    watch_state: Optional[str] = None
    if public and any(
        k in payload
        for k in (
            "view_count",
            "view_offset_ms",
            "total_episode_count",
            "unwatched_episode_count",
        )
    ):
        watch_state = derive_watch_state(payload)

    for key, value in payload.items():
        if public and key in _PUBLIC_DROP_KEYS:
            continue
        if key in ("poster_url", "backdrop_url"):
            continue
        out[key] = _sanitize_value(value, audience=audience, settings=settings)

    images = public_image_urls(payload, settings)
    if "poster_url" in payload or images["poster_url"]:
        out["poster_url"] = images["poster_url"]
    if "backdrop_url" in payload or images["backdrop_url"]:
        out["backdrop_url"] = images["backdrop_url"]

    # Internal audiences may retain file paths? No — still never emit secrets / tokens.
    if not public:
        out = strip_plex_token_urls(out)  # type: ignore[assignment]
        # Re-apply TMDB-only image policy for posters (prefer CDN over scrubbed plex).
        images = public_image_urls(payload, settings)
        if "poster_url" in payload:
            # Prefer TMDB; if none, leave empty rather than tokenized plex.
            out["poster_url"] = images["poster_url"]
        if "backdrop_url" in payload:
            out["backdrop_url"] = images["backdrop_url"]

    if public and watch_state is not None:
        out["watch_state"] = watch_state

    # Truncate long overviews for public audiences.
    if public:
        for overview_key in ("overview", "summary", "recommendation_reason", "purge_reason"):
            if overview_key in out and isinstance(out[overview_key], str):
                text = out[overview_key]
                if len(text) > 480:
                    out[overview_key] = text[:477].rstrip() + "..."

    return out


def _sanitize_value(value: Any, *, audience: Audience, settings: Any) -> Any:
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, audience=audience, settings=settings)
    if isinstance(value, list):
        return [_sanitize_value(item, audience=audience, settings=settings) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item, audience=audience, settings=settings) for item in value)
    if isinstance(value, str) and "X-Plex-Token" in value:
        return strip_plex_token_from_url(value)
    return value


def sanitize(
    payload: Any,
    *,
    audience: Audience = "privacy",
    settings: Any = None,
) -> Any:
    """Return a deep-copied payload scrubbed for the given audience."""
    if payload is None:
        return None
    # Work on a copy so callers keep originals.
    cloned = copy.deepcopy(payload)
    return _sanitize_value(cloned, audience=audience, settings=settings)
