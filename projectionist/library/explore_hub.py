"""Explore hub aggregate with stale-while-revalidate caching.

Explore used to fire a dozen feed requests (plus overview/health) on every visit.
The hub endpoint returns one payload. Recompute is intentionally **off the request
path** after the first successful build:

* Soft TTL — payload is considered fresh.
* After soft TTL — serve the last payload immediately and refresh in the background.
* Process restart — hydrate from durable ``sync_state`` and refresh in the background.
* True cold miss — return a warming skeleton immediately (do not hang first paint);
  a single-flight background build fills memory + disk for the next request / client poll.
"""

from __future__ import annotations

import copy
import json
import logging
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

logger = logging.getLogger(__name__)

# Fresh window — after this, still serve cache but kick a background recompute.
HUB_CACHE_SOFT_TTL_SECONDS = 120.0
# Keep memory/disk entries this long for SWR (revalidate asynchronously).
HUB_CACHE_HARD_TTL_SECONDS = 6 * 3600.0
HUB_DISK_KEY_PREFIX = "explore_hub:"

HUB_CACHE_TTL_SECONDS = HUB_CACHE_SOFT_TTL_SECONDS  # back-compat alias for tests/stats

_LOCK = threading.Lock()
# key -> (soft_expires_at, hard_expires_at, payload)
_CACHE: Dict[str, tuple[float, float, Dict[str, Any]]] = {}
# Single-flight background refresh keys.
_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()

_RAIL_KEYS = (
    "continue_watching",
    "tonight_table",
    "unfinished",
    "afterglow",
    "recently_added",
    "recently_added_episodes",
    "recent_releases",
    "revisit_these",
    "on_this_day",
    "director_spotlight",
    "genre_spotlight",
    "seasonal_spotlight",
)


def invalidate_explore_hub_cache() -> None:
    """Mark hub entries stale so the next request serves SWR + background refresh.

    Does **not** drop payloads — wiping would force a cold hang on the next visit
    right after library sync.
    """
    now = time.monotonic()
    with _LOCK:
        for key, (_soft, hard, payload) in list(_CACHE.items()):
            _CACHE[key] = (now, hard, payload)


def _empty_rail(feed_name: str) -> Dict[str, Any]:
    return {"feed": feed_name, "items": [], "total": 0, "note": None}


def _warming_payload(*, rail_limit: int, is_youth: bool) -> Dict[str, Any]:
    rails: Dict[str, Any] = {
        "continue_watching": _empty_rail("continue-watching"),
        "tonight_table": _empty_rail("tonight-table"),
        "unfinished": _empty_rail("unfinished"),
        "afterglow": _empty_rail("afterglow"),
        "recently_added": _empty_rail("recently-added"),
        "recently_added_episodes": _empty_rail("recently-added-episodes"),
        "recent_releases": _empty_rail("recent-releases"),
        "revisit_these": _empty_rail("revisit-these"),
        "on_this_day": _empty_rail("on-this-day"),
        "director_spotlight": _empty_rail("director-spotlight"),
        "genre_spotlight": _empty_rail("genre-spotlight"),
        "seasonal_spotlight": _empty_rail("seasonal-spotlight"),
    }
    if is_youth:
        rails["pick_for_me"] = None
    return {
        "feed": "explore-hub",
        "generated_at": int(time.time()),
        "cached": False,
        "stale": False,
        "warming": True,
        "rails": rails,
        "overview": {},
        "health": {},
        "rail_limit": max(1, min(int(rail_limit or 12), 24)),
    }


def _cache_get_entry(
    key: str,
) -> Optional[tuple[bool, bool, Dict[str, Any]]]:
    """Return (fresh, within_hard, payload) or None if missing/hard-expired."""
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        soft_expires, hard_expires, payload = hit
        if now >= hard_expires:
            _CACHE.pop(key, None)
            return None
        fresh = now < soft_expires
        return fresh, True, payload


def _cache_set(key: str, payload: Dict[str, Any], *, soft_ttl: float = HUB_CACHE_SOFT_TTL_SECONDS) -> None:
    soft = max(0.0, float(soft_ttl))
    hard = max(soft if soft > 0 else 1.0, HUB_CACHE_HARD_TTL_SECONDS)
    now = time.monotonic()
    with _LOCK:
        # soft_ttl=0 → immediately soft-stale (SWR from disk / post-invalidate).
        _CACHE[key] = (now + soft, now + hard, payload)


def _disk_key(cache_key: str) -> str:
    return f"{HUB_DISK_KEY_PREFIX}{cache_key}"


def _disk_load(db: Database, cache_key: str) -> Optional[Dict[str, Any]]:
    raw = db.get_sync_state(_disk_key(cache_key))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("rails"), dict):
        return None
    generated_at = parsed.get("generated_at")
    try:
        age = time.time() - float(generated_at or 0)
    except (TypeError, ValueError):
        age = HUB_CACHE_HARD_TTL_SECONDS + 1
    if age > HUB_CACHE_HARD_TTL_SECONDS:
        return None
    return parsed


def _disk_store(db: Database, cache_key: str, payload: Dict[str, Any]) -> None:
    try:
        to_store = {
            "feed": payload.get("feed"),
            "generated_at": payload.get("generated_at"),
            "rails": payload.get("rails") or {},
            "overview": payload.get("overview") or {},
            "health": payload.get("health") or {},
            "rail_limit": payload.get("rail_limit"),
        }
        db.set_sync_state(_disk_key(cache_key), json.dumps(to_store))
    except Exception:  # noqa: BLE001 — disk cache must never break Explore
        logger.debug("explore hub disk store failed", exc_info=True)


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
        "stale": False,
        "warming": False,
        "rails": feeds,
        "overview": overview,
        "health": health,
        "rail_limit": capped,
    }


def _public_copy(
    payload: Dict[str, Any],
    *,
    cached: bool,
    stale: bool,
    warming: bool = False,
) -> Dict[str, Any]:
    out = copy.deepcopy(payload)
    out["cached"] = cached
    out["stale"] = stale
    out["warming"] = warming
    return out


def _schedule_refresh(
    cache_key: str,
    db: Database,
    settings: Settings,
    *,
    is_youth: bool,
    user_id: Optional[str],
    rail_limit: int,
) -> None:
    with _REFRESH_LOCK:
        if cache_key in _REFRESHING:
            return
        _REFRESHING.add(cache_key)

    def _run() -> None:
        try:
            payload = build_explore_hub(
                db,
                settings,
                is_youth=is_youth,
                user_id=user_id,
                rail_limit=rail_limit,
            )
            _cache_set(cache_key, payload)
            _disk_store(db, cache_key, payload)
        except Exception:  # noqa: BLE001 — background refresh must not crash the worker
            logger.exception("explore hub background refresh failed key=%s", cache_key)
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(cache_key)

    thread = threading.Thread(
        target=_run,
        name=f"explore-hub-refresh:{cache_key[:48]}",
        daemon=True,
    )
    thread.start()


def get_explore_hub(
    db: Database,
    settings: Settings,
    *,
    is_youth: bool = False,
    user_id: Optional[str] = None,
    rail_limit: int = 12,
    bypass_cache: bool = False,
) -> Dict[str, Any]:
    """Return Explore hub via stale-while-revalidate (never block on soft-expired)."""
    cache_key = f"youth={int(bool(is_youth))}|uid={user_id or ''}|limit={rail_limit}"

    if bypass_cache:
        payload = build_explore_hub(
            db,
            settings,
            is_youth=is_youth,
            user_id=user_id,
            rail_limit=rail_limit,
        )
        _cache_set(cache_key, payload)
        _disk_store(db, cache_key, payload)
        return _public_copy(payload, cached=False, stale=False, warming=False)

    entry = _cache_get_entry(cache_key)
    if entry is not None:
        fresh, _within_hard, payload = entry
        if fresh:
            return _public_copy(payload, cached=True, stale=False)
        _schedule_refresh(
            cache_key,
            db,
            settings,
            is_youth=is_youth,
            user_id=user_id,
            rail_limit=rail_limit,
        )
        return _public_copy(payload, cached=True, stale=True)

    disk = _disk_load(db, cache_key)
    if disk is not None:
        _cache_set(cache_key, disk, soft_ttl=0.0)  # immediately soft-stale
        _schedule_refresh(
            cache_key,
            db,
            settings,
            is_youth=is_youth,
            user_id=user_id,
            rail_limit=rail_limit,
        )
        return _public_copy(disk, cached=True, stale=True)

    # Cold miss — do not hang first paint on full recompute.
    _schedule_refresh(
        cache_key,
        db,
        settings,
        is_youth=is_youth,
        user_id=user_id,
        rail_limit=rail_limit,
    )
    return _warming_payload(rail_limit=rail_limit, is_youth=is_youth)


def explore_hub_cache_stats() -> Mapping[str, Any]:
    """Test/debug helper."""
    with _LOCK:
        entries = len(_CACHE)
    with _REFRESH_LOCK:
        refreshing = len(_REFRESHING)
    return {
        "entries": entries,
        "ttl_seconds": HUB_CACHE_SOFT_TTL_SECONDS,
        "soft_ttl_seconds": HUB_CACHE_SOFT_TTL_SECONDS,
        "hard_ttl_seconds": HUB_CACHE_HARD_TTL_SECONDS,
        "refreshing": refreshing,
        "rail_keys": list(_RAIL_KEYS),
    }
