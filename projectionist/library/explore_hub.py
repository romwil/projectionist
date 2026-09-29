"""Explore hub aggregate + short TTL cache for a snappy home page.

Explore used to fire a dozen feed requests (plus overview/health) on every visit.
The hub endpoint returns one payload; an in-process TTL keeps revisits cheap and
avoids re-hitting Plex On Deck for Continue Watching on every paint.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Mapping, Optional

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient
from projectionist.library.db import Database
from projectionist.library.feeds import (
    feed_afterglow,
    feed_continue_watching,
    feed_director_spotlight,
    feed_genre_spotlight,
    feed_on_this_day,
    feed_recent_releases,
    feed_recently_added,
    feed_recently_added_episodes,
    feed_revisit_these,
    feed_seasonal_spotlight,
    feed_tonight_table,
    feed_unfinished,
)
from projectionist.library.health import compute_library_health
from projectionist.library.query import library_overview

# Short enough that arrivals feel fresh; long enough to absorb hub revisits.
HUB_CACHE_TTL_SECONDS = 45.0

_LOCK = threading.Lock()
_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}


def invalidate_explore_hub_cache() -> None:
    """Drop all hub entries (call after library sync / episode sync)."""
    with _LOCK:
        _CACHE.clear()


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        expires_at, payload = hit
        if now >= expires_at:
            _CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: str, payload: Dict[str, Any], *, ttl: float = HUB_CACHE_TTL_SECONDS) -> None:
    with _LOCK:
        _CACHE[key] = (time.monotonic() + max(1.0, ttl), payload)


def _plex_client(settings: Settings) -> Optional[PlexClient]:
    if not settings.plex_url or not settings.plex_token:
        return None
    return PlexClient(
        settings.plex_url,
        settings.plex_token,
        movie_section=settings.plex_movie_section or None,
        tv_section=settings.plex_tv_section or None,
    )


def build_explore_hub(
    db: Database,
    settings: Settings,
    *,
    is_youth: bool = False,
    user_id: Optional[str] = None,
    rail_limit: int = 12,
) -> Dict[str, Any]:
    """Assemble every Explore home rail + pulse in one payload."""
    capped = max(1, min(int(rail_limit or 12), 24))
    plex = _plex_client(settings)
    feeds: Dict[str, Any] = {
        "continue_watching": feed_continue_watching(db, limit=capped, plex_client=plex),
        "tonight_table": feed_tonight_table(db, limit=3),
        "unfinished": feed_unfinished(db, limit=capped, idle_days=60),
        "afterglow": feed_afterglow(db, limit=capped, days=14, user_id=user_id),
        "recently_added": feed_recently_added(db, limit=capped, days=30),
        "recently_added_episodes": feed_recently_added_episodes(db, limit=capped, days=30),
        "recent_releases": feed_recent_releases(db, limit=capped, days=90),
        "revisit_these": feed_revisit_these(db, limit=20, idle_days=60),
        "on_this_day": feed_on_this_day(db, limit=capped),
        "director_spotlight": feed_director_spotlight(db, limit=capped),
        "genre_spotlight": feed_genre_spotlight(db, limit=capped),
        "seasonal_spotlight": feed_seasonal_spotlight(db, limit=capped),
    }
    if is_youth:
        # Youth pick-for-me stays on its own endpoint (age gate + shuffle).
        feeds["pick_for_me"] = None
    overview = library_overview(db, use_cache=True)
    try:
        health = compute_library_health(db)
    except Exception:  # noqa: BLE001 — pulse degrades gracefully
        health = {}
    return {
        "feed": "explore-hub",
        "generated_at": int(time.time()),
        "cached": False,
        "rails": feeds,
        "overview": overview,
        "health": health,
    }


def get_explore_hub(
    db: Database,
    settings: Settings,
    *,
    is_youth: bool = False,
    user_id: Optional[str] = None,
    rail_limit: int = 12,
    bypass_cache: bool = False,
) -> Dict[str, Any]:
    """Return a TTL-cached Explore hub payload."""
    cache_key = f"youth={int(bool(is_youth))}|uid={user_id or ''}|limit={rail_limit}"
    if not bypass_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            # Shallow copy so callers can mutate flags without poisoning the cache.
            out = dict(cached)
            out["cached"] = True
            return out
    payload = build_explore_hub(
        db,
        settings,
        is_youth=is_youth,
        user_id=user_id,
        rail_limit=rail_limit,
    )
    _cache_set(cache_key, payload)
    return dict(payload)


def explore_hub_cache_stats() -> Mapping[str, Any]:
    """Test/debug helper."""
    with _LOCK:
        return {"entries": len(_CACHE), "ttl_seconds": HUB_CACHE_TTL_SECONDS}
