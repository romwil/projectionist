"""Idle task: pre-compute and cache purge candidate recommendations.

Calls ``suggest_purge_candidates_rich()`` and stores the result in the
``curator_system_config`` key-value store under ``cached_purge_candidates``.
This avoids re-scanning Tautulli + the full library on every dashboard load.

Default interval: 6 hours.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.preferences.purge import suggest_purge_candidates_rich
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours
CACHE_KEY = "cached_purge_candidates"
DEFAULT_LIMIT = 25


def read_cached_purge_candidates(db: Database) -> Optional[Dict[str, Any]]:
    """Return cached purge payload, or None when missing/invalid."""
    raw = db.get_config(CACHE_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list):
        return None
    return {
        "items": items,
        "count": int(data.get("count") if data.get("count") is not None else len(items)),
        "generated_at": data.get("generated_at"),
        "stale": False,
        "cached": True,
    }


def write_purge_candidates_cache(
    db: Database,
    items: List[Dict[str, Any]],
    *,
    generated_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Persist purge candidates and return the API-shaped payload."""
    payload = {
        "items": items,
        "count": len(items),
        "generated_at": float(generated_at if generated_at is not None else time.time()),
    }
    db.set_config(CACHE_KEY, json.dumps(payload))
    return {
        **payload,
        "stale": False,
        "cached": True,
    }


def recompute_purge_candidates(
    db: Database,
    settings: Settings,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Compute purge candidates, cache them, and return the payload."""
    items = suggest_purge_candidates_rich(db, settings, limit=limit)
    return write_purge_candidates_cache(db, items)


def drop_cached_purge_keys(db: Database, rating_keys: List[str]) -> Optional[Dict[str, Any]]:
    """Remove rating keys from the cached purge list without a full recompute."""
    cached = read_cached_purge_candidates(db)
    if cached is None:
        return None
    drop = {str(key) for key in rating_keys}
    items = [
        item
        for item in cached.get("items") or []
        if str(item.get("rating_key") or "") not in drop
    ]
    return write_purge_candidates_cache(
        db,
        items,
        generated_at=cached.get("generated_at"),
    )


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}

    payload = recompute_purge_candidates(db, settings, limit=DEFAULT_LIMIT)
    logger.info(
        "Purge candidates cached: count=%s generated_at=%s",
        payload.get("count"),
        payload.get("generated_at"),
    )
    return {"status": "completed", "count": payload.get("count", 0)}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="purge_candidates",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Pre-computes purge candidate recommendations from watch history and "
                "library age, then caches them for the Admin dashboard."
            ),
        )
    )
