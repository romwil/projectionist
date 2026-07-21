"""Build and persist the weekly in-app library digest."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.feeds import feed_recently_added
from curatorx.library.health import compute_library_health
from curatorx.library.query import compute_knowledge_coverage

WEEK_SECONDS = 7 * 86400


def current_week_start(now: Optional[float] = None) -> float:
    """Return the start of the current fixed weekly bucket (UTC epoch seconds).

    Buckets are 7-day windows aligned to the Unix epoch, giving a single stable
    key per week so the digest upserts rather than duplicating rows.
    """
    ts = time.time() if now is None else float(now)
    return float(int(ts) - (int(ts) % WEEK_SECONDS))


def _library_counts(db: Database) -> Dict[str, int]:
    with db.connect() as conn:
        movies = int(
            conn.execute(
                "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'movie'"
            ).fetchone()["cnt"]
        )
        shows = int(
            conn.execute(
                "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'show'"
            ).fetchone()["cnt"]
        )
    return {"movies": movies, "shows": shows, "total": movies + shows}


def build_weekly_digest(
    db: Database, settings: Optional[Settings] = None, *, now: Optional[float] = None
) -> Dict[str, Any]:
    """Assemble the digest payload from existing aggregations (read-only)."""
    del settings  # reserved for future per-owner tuning
    generated_at = time.time() if now is None else float(now)

    counts = _library_counts(db)

    try:
        health = compute_library_health(db)
    except Exception:  # noqa: BLE001
        health = {}
    try:
        coverage = compute_knowledge_coverage(db)
    except Exception:  # noqa: BLE001
        coverage = {}

    try:
        recent = feed_recently_added(db, limit=8, days=7)
    except Exception:  # noqa: BLE001
        recent = {"items": [], "total": 0}
    recent_items: List[Dict[str, Any]] = list(recent.get("items") or [])
    new_titles = [
        {
            "title": str(item.get("title") or "Untitled"),
            "year": item.get("year"),
            "media_type": item.get("media_type"),
        }
        for item in recent_items[:8]
    ]

    try:
        open_issues = len(db.list_media_issues(status="open", limit=500))
    except Exception:  # noqa: BLE001
        open_issues = 0

    purge_count = 0
    try:
        raw_purge = db.get_config("cached_purge_candidates")
        if raw_purge:
            import json as _json

            parsed = _json.loads(raw_purge)
            if isinstance(parsed, dict):
                items = parsed.get("items")
                purge_count = len(items) if isinstance(items, list) else int(parsed.get("count") or 0)
    except Exception:  # noqa: BLE001
        purge_count = 0

    return {
        "generated_at": generated_at,
        "library": counts,
        "new_this_week": {
            "count": int(recent.get("total") or len(new_titles)),
            "titles": new_titles,
        },
        "health": {
            "unwatched_pct": health.get("unwatched_pct", 0.0),
            "stale_adds": health.get("stale_adds", 0),
            "rating_coverage_pct": health.get("rating_coverage_pct", 0.0),
        },
        "coverage": {
            "with_overview_pct": coverage.get("with_overview_pct", 0.0),
            "with_motifs_pct": coverage.get("with_motifs_pct", 0.0),
            "with_neighbors_pct": coverage.get("with_neighbors_pct", 0.0),
        },
        "issues": {"open": open_issues},
        "purge": {"candidates": purge_count},
    }


def snapshot_weekly_digest(
    db: Database, settings: Optional[Settings] = None, *, now: Optional[float] = None
) -> Dict[str, Any]:
    """Build the digest and persist it for the current weekly bucket."""
    payload = build_weekly_digest(db, settings, now=now)
    week_start = current_week_start(now)
    return db.save_weekly_digest(
        digest_id=str(uuid.uuid4()),
        week_start=week_start,
        payload=payload,
    )
