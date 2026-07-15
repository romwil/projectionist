"""Idle task: pre-warm recommendation candidate lists.

Generates cached recommendation sets for common patterns:
  - Unwatched titles by the user's top genres
  - Recently-added unwatched titles
  - Mood-like clusters (e.g., "feel-good", "tense thriller")

Results are stored in a ``cached_recommendations`` table with TTL for
freshness management.

Default interval: 12 hours.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
MAX_ITEMS_PER_CACHE = 50
TTL_HOURS = 24


def _ensure_table(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cached_recommendations (
                cache_key TEXT PRIMARY KEY,
                items_json TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                ttl_hours INTEGER NOT NULL DEFAULT 24
            )
            """
        )


def _store_cache(db: Database, key: str, items: List[Dict[str, Any]]) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO cached_recommendations (cache_key, items_json, generated_at, ttl_hours)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                items_json = excluded.items_json,
                generated_at = excluded.generated_at,
                ttl_hours = excluded.ttl_hours
            """,
            (key, json.dumps(items), str(time.time()), TTL_HOURS),
        )


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    _ensure_table(db)
    rows = list(db.all_library_items())
    if not rows:
        return {"status": "completed", "caches_built": 0}

    caches_built = 0

    # 1. Top genres — find the 5 most common genres, build an unwatched list per genre.
    genre_counter: Counter[str] = Counter()
    for row in rows:
        genres_raw = row["genres"]
        try:
            genres = json.loads(genres_raw) if isinstance(genres_raw, str) else []
        except (json.JSONDecodeError, TypeError):
            genres = []
        if isinstance(genres, list):
            for g in genres:
                genre_counter[str(g).strip()] += 1

    if should_stop():
        return {"status": "interrupted", "caches_built": caches_built}

    top_genres = [g for g, _ in genre_counter.most_common(5) if g]
    for genre in top_genres:
        unwatched = [
            {"id": int(r["id"]), "title": str(r["title"]), "media_type": str(r["media_type"])}
            for r in rows
            if (int(r["view_count"] or 0) == 0)
            and genre.lower() in str(r["genres"] or "").lower()
        ][:MAX_ITEMS_PER_CACHE]
        _store_cache(db, f"unwatched_genre:{genre.lower()}", unwatched)
        caches_built += 1

    if should_stop():
        return {"status": "interrupted", "caches_built": caches_built}

    # 2. Recently added unwatched.
    cutoff = time.time() - (30 * 86400)  # last 30 days
    recent_unwatched = [
        {"id": int(r["id"]), "title": str(r["title"]), "media_type": str(r["media_type"])}
        for r in rows
        if (int(r["view_count"] or 0) == 0)
        and r["added_at"] is not None
        and int(r["added_at"]) >= cutoff
    ][:MAX_ITEMS_PER_CACHE]
    _store_cache(db, "recently_added_unwatched", recent_unwatched)
    caches_built += 1

    if should_stop():
        return {"status": "interrupted", "caches_built": caches_built}

    # 3. Highly-rated unwatched (vote_average >= 7.0).
    highly_rated = [
        {"id": int(r["id"]), "title": str(r["title"]), "media_type": str(r["media_type"]),
         "vote_average": float(r["vote_average"] or 0)}
        for r in rows
        if (int(r["view_count"] or 0) == 0)
        and r["vote_average"] is not None
        and float(r["vote_average"]) >= 7.0
    ]
    highly_rated.sort(key=lambda x: x["vote_average"], reverse=True)
    _store_cache(db, "highly_rated_unwatched", highly_rated[:MAX_ITEMS_PER_CACHE])
    caches_built += 1

    logger.info("Recommendation warmup: built %d caches from %d items", caches_built, len(rows))
    return {"status": "completed", "caches_built": caches_built, "library_size": len(rows)}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="recommendation_warmup",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
        )
    )
