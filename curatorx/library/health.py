"""Library health metrics for the maintenance dashboard."""

from __future__ import annotations

import time
from typing import Any, Dict

from curatorx.library.db import Database

STALE_ADD_DAYS = 90


def compute_library_health(db: Database) -> Dict[str, Any]:
    now = time.time()
    stale_cutoff = now - STALE_ADD_DAYS * 86400

    with db.connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) AS cnt FROM library_items").fetchone()["cnt"])
        unwatched = int(
            conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM library_items
                WHERE view_count IS NULL OR view_count = 0
                """
            ).fetchone()["cnt"]
        )
        stale_adds = int(
            conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM library_items
                WHERE added_at IS NOT NULL AND added_at < ?
                  AND (view_count IS NULL OR view_count = 0)
                """,
                (stale_cutoff,),
            ).fetchone()["cnt"]
        )
        watched = int(
            conn.execute(
                "SELECT COUNT(*) AS cnt FROM library_items WHERE view_count > 0"
            ).fetchone()["cnt"]
        )
        reviewed = int(
            conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM library_items li
                WHERE li.view_count > 0
                  AND (
                    EXISTS (
                      SELECT 1 FROM user_title_reviews r
                      WHERE r.rating_key IS NOT NULL AND r.rating_key != ''
                        AND r.rating_key = li.rating_key
                    )
                    OR EXISTS (
                      SELECT 1 FROM user_title_reviews r
                      WHERE r.tmdb_id IS NOT NULL
                        AND r.tmdb_id = li.tmdb_id
                        AND r.media_type = li.media_type
                    )
                  )
                """
            ).fetchone()["cnt"]
        )

    unwatched_pct = round((unwatched / total) * 100, 1) if total else 0.0
    rating_coverage_pct = round((reviewed / watched) * 100, 1) if watched else 0.0

    return {
        "total": total,
        "unwatched_count": unwatched,
        "unwatched_pct": unwatched_pct,
        "stale_adds": stale_adds,
        "stale_add_days": STALE_ADD_DAYS,
        "watched_count": watched,
        "reviewed_count": reviewed,
        "rating_coverage_pct": rating_coverage_pct,
        "generated_at": now,
    }
