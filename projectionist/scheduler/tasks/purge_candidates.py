"""Idle task: pre-compute and cache purge candidate recommendations.

Calls ``suggest_purge_candidates_rich()`` and stores the result in the
``curator_system_config`` key-value store under ``cached_purge_candidates``.
This avoids re-scanning Tautulli + the full library on every dashboard load.

Buffer target is 5× the dashboard page size so owners can paginate and act
(purge / keep) while a background top-up refills the far end of the window.

Default interval: 6 hours.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.preferences.purge import (
    enrich_purge_candidate_rows,
    suggest_purge_candidates_rich,
)
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours
CACHE_KEY = "cached_purge_candidates"
PAGE_SIZE = 20
BUFFER_TARGET = 100  # 5 × PAGE_SIZE
REFILL_THRESHOLD = 80
DEFAULT_LIMIT = BUFFER_TARGET


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
        "page_size": int(data.get("page_size") or PAGE_SIZE),
        "buffer_target": int(data.get("buffer_target") or BUFFER_TARGET),
        "stale": False,
        "cached": True,
        "refilling": bool(data.get("refilling")),
    }


def write_purge_candidates_cache(
    db: Database,
    items: List[Dict[str, Any]],
    *,
    generated_at: Optional[float] = None,
    refilling: bool = False,
) -> Dict[str, Any]:
    """Persist purge candidates and return the API-shaped payload."""
    payload = {
        "items": items,
        "count": len(items),
        "generated_at": float(generated_at if generated_at is not None else time.time()),
        "page_size": PAGE_SIZE,
        "buffer_target": BUFFER_TARGET,
        "refilling": bool(refilling),
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
    return write_purge_candidates_cache(db, items, refilling=False)


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
        refilling=bool(cached.get("refilling")),
    )


def needs_purge_buffer_refill(db: Database) -> bool:
    cached = read_cached_purge_candidates(db)
    if cached is None:
        return True
    return int(cached.get("count") or 0) < REFILL_THRESHOLD


def top_up_purge_candidates(
    db: Database,
    settings: Settings,
    *,
    target: int = BUFFER_TARGET,
) -> Dict[str, Any]:
    """Append newly scored candidates until the buffer reaches ``target``.

    Existing cached keys and dismissals are excluded so purge/keep actions can
    refill the far end of the window without reshuffling the remaining list.
    """
    cached = read_cached_purge_candidates(db)
    existing = list(cached.get("items") or []) if cached else []
    existing_keys = {
        str(item.get("rating_key") or "")
        for item in existing
        if str(item.get("rating_key") or "").strip()
    }
    need = max(0, int(target) - len(existing))
    if need <= 0:
        return write_purge_candidates_cache(
            db,
            existing,
            generated_at=cached.get("generated_at") if cached else None,
            refilling=False,
        )

    write_purge_candidates_cache(
        db,
        existing,
        generated_at=cached.get("generated_at") if cached else time.time(),
        refilling=True,
    )
    # Over-fetch then filter so exclusions don't leave the buffer short.
    fresh = suggest_purge_candidates_rich(
        db,
        settings,
        limit=max(need * 3, need + 20),
        exclude_rating_keys=set(existing_keys),
    )
    additions: List[Dict[str, Any]] = []
    for item in fresh:
        key = str(item.get("rating_key") or "")
        if not key or key in existing_keys:
            continue
        existing_keys.add(key)
        additions.append(item)
        if len(additions) >= need:
            break

    merged = existing + additions
    payload = write_purge_candidates_cache(
        db,
        merged,
        generated_at=time.time(),
        refilling=False,
    )
    logger.info(
        "Purge buffer topped up: added=%s total=%s target=%s",
        len(additions),
        payload.get("count"),
        target,
    )
    return payload


def maybe_top_up_purge_candidates(db: Database, settings: Settings) -> Optional[Dict[str, Any]]:
    """Top up when below the refill threshold; otherwise no-op."""
    if not needs_purge_buffer_refill(db):
        return None
    return top_up_purge_candidates(db, settings, target=BUFFER_TARGET)


def enrich_cached_purge_items(
    db: Database,
    settings: Settings,
    items: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Refresh size / watch / *arr fields for presentation (visible page)."""
    return enrich_purge_candidate_rows(db, settings, list(items))


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
                "library age (movies + shows), then caches a 5× page buffer for the "
                "Admin Storage Intelligence panel."
            ),
        )
    )
