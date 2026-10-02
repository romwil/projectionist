"""Library/backlog progress helpers for scheduled-task ETA estimates."""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable, Dict, Optional, Protocol, Tuple

from projectionist.library.db import Database


# Admin → Tasks polls the list every 1.2–5s; each poll recounts backlogs with
# ``NOT EXISTS`` scans over library_items / embeddings / item_neighbors. Those
# counts only move at batch granularity, so a short TTL keeps the page honest
# without rescanning a large library on every tick. Set to 0 to disable.
PROGRESS_CACHE_TTL_SECONDS = 10.0
_progress_cache: Dict[Tuple[str, str], Tuple[float, Any]] = {}
_progress_cache_lock = threading.Lock()


def clear_progress_cache() -> None:
    with _progress_cache_lock:
        _progress_cache.clear()


def _cached(db: Database, key: str, compute: Callable[[], Any]) -> Any:
    ttl = float(PROGRESS_CACHE_TTL_SECONDS)
    if ttl <= 0:
        return compute()
    cache_key = (str(getattr(db, "path", id(db))), key)
    now = time.monotonic()
    with _progress_cache_lock:
        hit = _progress_cache.get(cache_key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
    value = compute()
    with _progress_cache_lock:
        _progress_cache[cache_key] = (time.monotonic(), value)
    return value


class _HasProgress(Protocol):
    items_per_cycle: Optional[int]
    progress_scope: Optional[str]


def count_remaining(db: Database, scope: Optional[str]) -> Optional[int]:
    """Return remaining items for a known progress scope, or None if unknown."""
    if not scope:
        return None
    if scope == "metadata_backlog":
        return db.count_items_needing_metadata_enrichment()
    if scope == "llm_logline_backlog":
        return db.count_items_needing_llm_logline()
    if scope == "long_synopsis_backlog":
        return db.count_items_needing_long_synopsis()
    if scope == "embeddings_pending":
        return db.count_items_needing_embeddings()
    if scope == "embeddings_pass":
        return db.count_embeddings()
    if scope == "neighbors_backlog":
        return db.count_items_missing_neighbors()
    return None


def estimate_progress(
    *,
    remaining: Optional[int],
    items_per_cycle: Optional[int],
    interval_seconds: int,
    library_size: int,
    scope: Optional[str],
    items_per_hour: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Build a progress/ETA payload for trickle tasks.

    ``estimated_seconds`` assumes one cycle every ``interval_seconds`` and that
    each cycle processes ``items_per_cycle`` items (idle time ignored), unless
    ``items_per_hour`` is provided from measured run history.
    """
    if items_per_cycle is None or items_per_cycle <= 0 or remaining is None:
        return None
    remaining = max(0, int(remaining))
    per_cycle = max(1, int(items_per_cycle))
    cycles = 0 if remaining == 0 else int(math.ceil(remaining / per_cycle))
    interval = max(60, int(interval_seconds or 60))
    scope_labels = {
        "metadata_backlog": "titles still missing TMDB dates/plot",
        "llm_logline_backlog": "titles still needing an LLM logline",
        "long_synopsis_backlog": "titles still needing an optional long synopsis",
        "embeddings_pending": "titles with plot text still needing embeddings",
        "embeddings_pass": "embedded titles in one full neighbor pass",
        "neighbors_backlog": "embedded titles still missing neighbor rows",
    }
    if items_per_hour is not None and float(items_per_hour) > 0 and remaining > 0:
        estimated_seconds = int(math.ceil((remaining / float(items_per_hour)) * 3600))
        eta_source = "measured"
    else:
        estimated_seconds = cycles * interval
        eta_source = "theoretical"
    payload: Dict[str, Any] = {
        "scope": scope,
        "scope_label": scope_labels.get(scope or "", "remaining work"),
        "remaining_items": remaining,
        "items_per_cycle": per_cycle,
        "library_size": int(library_size),
        "estimated_cycles": cycles,
        "estimated_seconds": estimated_seconds,
        "eta_source": eta_source,
    }
    if items_per_hour is not None:
        payload["items_per_hour"] = float(items_per_hour)
    return payload


def progress_for_definition(
    db: Database,
    defn: Optional[_HasProgress],
    *,
    interval_seconds: int,
    items_per_cycle: Optional[int] = None,
    items_per_hour: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve progress for a registered task definition."""
    if defn is None:
        return None
    batch = items_per_cycle if items_per_cycle is not None else defn.items_per_cycle
    if batch is None:
        return None
    library_size = int(
        _cached(db, "library_items", lambda: db.library_counts().get("items") or 0)
    )
    remaining = _cached(
        db,
        f"remaining:{defn.progress_scope}",
        lambda: count_remaining(db, defn.progress_scope),
    )
    return estimate_progress(
        remaining=remaining,
        items_per_cycle=batch,
        interval_seconds=interval_seconds,
        library_size=library_size,
        scope=defn.progress_scope,
        items_per_hour=items_per_hour,
    )
