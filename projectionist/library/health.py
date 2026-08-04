"""Library health metrics for the maintenance dashboard."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from projectionist.library.db import Database

STALE_ADD_DAYS = 90

# Matched review ↔ library title: prefer tmdb+media_type (survives rating_key
# rematch), then fall back to rating_key. CAST tolerates affinity drift.
_REVIEW_MATCHES_ITEM = """
(
  (
    li.tmdb_id IS NOT NULL
    AND r.tmdb_id IS NOT NULL
    AND CAST(r.tmdb_id AS INTEGER) = CAST(li.tmdb_id AS INTEGER)
    AND lower(COALESCE(r.media_type, '')) = lower(COALESCE(li.media_type, ''))
  )
  OR (
    r.rating_key IS NOT NULL AND r.rating_key != ''
    AND li.rating_key IS NOT NULL AND li.rating_key != ''
    AND r.rating_key = li.rating_key
  )
)
"""


def _media_type_health(conn, media_type: str, stale_cutoff: float) -> Dict[str, Any]:
    total = int(
        conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = ?",
            (media_type,),
        ).fetchone()["cnt"]
    )
    unwatched = int(
        conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = ?
              AND (view_count IS NULL OR view_count = 0)
            """,
            (media_type,),
        ).fetchone()["cnt"]
    )
    stale_adds = int(
        conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = ?
              AND added_at IS NOT NULL AND added_at < ?
              AND (view_count IS NULL OR view_count = 0)
            """,
            (media_type, stale_cutoff),
        ).fetchone()["cnt"]
    )
    unwatched_pct = round((unwatched / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "unwatched_count": unwatched,
        "unwatched_pct": unwatched_pct,
        "stale_adds": stale_adds,
    }


def _rating_coverage_note(
    *,
    reviewed: int,
    review_count: int,
) -> Optional[str]:
    """Honest sublabel when 0% would contradict Taste's recent ratings list."""
    if reviewed > 0 or review_count <= 0:
        return None
    return "Ratings not yet linked to watched titles"


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
        # Numerator: watched library titles that attach to at least one review.
        reviewed = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS cnt FROM library_items li
                WHERE li.view_count > 0
                  AND EXISTS (
                    SELECT 1 FROM user_title_reviews r
                    WHERE {_REVIEW_MATCHES_ITEM}
                  )
                """
            ).fetchone()["cnt"]
        )
        review_count = int(
            conn.execute("SELECT COUNT(*) AS cnt FROM user_title_reviews").fetchone()["cnt"]
        )
        reviews_on_unwatched = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS cnt FROM user_title_reviews r
                WHERE EXISTS (
                  SELECT 1 FROM library_items li
                  WHERE (li.view_count IS NULL OR li.view_count = 0)
                    AND {_REVIEW_MATCHES_ITEM}
                )
                AND NOT EXISTS (
                  SELECT 1 FROM library_items li
                  WHERE li.view_count > 0
                    AND {_REVIEW_MATCHES_ITEM}
                )
                """
            ).fetchone()["cnt"]
        )
        by_media_type = {
            "movie": _media_type_health(conn, "movie", stale_cutoff),
            "show": _media_type_health(conn, "show", stale_cutoff),
        }

    unwatched_pct = round((unwatched / total) * 100, 1) if total else 0.0
    rating_coverage_pct = round((reviewed / watched) * 100, 1) if watched else 0.0
    note = _rating_coverage_note(reviewed=reviewed, review_count=review_count)

    return {
        "total": total,
        "unwatched_count": unwatched,
        "unwatched_pct": unwatched_pct,
        "stale_adds": stale_adds,
        "stale_add_days": STALE_ADD_DAYS,
        "watched_count": watched,
        "reviewed_count": reviewed,
        "review_count": review_count,
        "reviews_on_unwatched_count": reviews_on_unwatched,
        "rating_coverage_pct": rating_coverage_pct,
        "rating_coverage_note": note,
        "by_media_type": by_media_type,
        "generated_at": now,
    }
