"""Optional social signals for adaptive YIR chapters (ratings, shares, Live)."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from projectionist.library.db import Database
from projectionist.watch_tracker.rollups import year_bounds_ms

# Cap how many rating highlights we surface in the reel.
MAX_RATING_HIGHLIGHTS = 8


def collect_social_signals(db: Database, *, user_id: str, year: int) -> Dict[str, Any]:
    start_ms, end_ms = year_bounds_ms(int(year))
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    ratings: List[Dict[str, Any]] = []
    shares_given = 0
    shares_received = 0
    live_sessions = 0
    has_projectionist_ratings = False
    has_plex_ratings = False
    plex_ratings_available = False

    with db.connect() as conn:
        tables = {
            str(r["name"])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        seen_keys: Set[str] = set()

        if "user_title_reviews" in tables:
            rows = conn.execute(
                """
                SELECT rating_key, title, stars, created_at FROM user_title_reviews
                WHERE user_id = ? AND created_at >= ? AND created_at < ?
                  AND stars IS NOT NULL
                ORDER BY stars DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, start_s, end_s, MAX_RATING_HIGHLIGHTS),
            ).fetchall()
            for row in rows:
                key = str(row["rating_key"] or row["title"] or "").strip()
                if key:
                    seen_keys.add(key)
                has_projectionist_ratings = True
                ratings.append(
                    {
                        "title": str(row["title"] or ""),
                        "stars": float(row["stars"]) if row["stars"] is not None else None,
                        "source": "projectionist",
                        "rating_key": str(row["rating_key"] or "") or None,
                    }
                )

        # Plex star ratings live on library rows (server-token sync). They have no
        # per-user/year stamp, so only attach them to titles this user finished
        # this year — a relevance proxy, labeled as Plex library ratings.
        if "library_items" in tables and "watch_completions" in tables:
            item_cols = {
                str(r["name"]) for r in conn.execute("PRAGMA table_info(library_items)").fetchall()
            }
            if "plex_user_rating_stars" in item_cols:
                plex_count_row = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM library_items
                    WHERE plex_user_rating_stars IS NOT NULL
                    """
                ).fetchone()
                plex_ratings_available = int(plex_count_row["c"] if plex_count_row else 0) > 0
                if plex_ratings_available and len(ratings) < MAX_RATING_HIGHLIGHTS:
                    plex_rows = conn.execute(
                        """
                        SELECT i.rating_key, i.title, i.plex_user_rating_stars AS stars,
                               MAX(c.completed_at_ms) AS last_at
                        FROM watch_completions c
                        JOIN library_items i ON i.rating_key = c.rating_key
                        WHERE c.user_id = ?
                          AND c.superseded_by_completion_id IS NULL
                          AND c.completed_at_ms >= ?
                          AND c.completed_at_ms < ?
                          AND i.plex_user_rating_stars IS NOT NULL
                        GROUP BY i.rating_key
                        ORDER BY i.plex_user_rating_stars DESC, last_at DESC
                        LIMIT ?
                        """,
                        (
                            user_id,
                            start_ms,
                            end_ms,
                            MAX_RATING_HIGHLIGHTS,
                        ),
                    ).fetchall()
                    for row in plex_rows:
                        key = str(row["rating_key"] or "").strip()
                        if key and key in seen_keys:
                            continue
                        if key:
                            seen_keys.add(key)
                        has_plex_ratings = True
                        ratings.append(
                            {
                                "title": str(row["title"] or ""),
                                "stars": float(row["stars"]) if row["stars"] is not None else None,
                                "source": "plex",
                                "rating_key": key or None,
                            }
                        )
                        if len(ratings) >= MAX_RATING_HIGHLIGHTS:
                            break
                    # Prefer highest stars overall after merge.
                    ratings.sort(
                        key=lambda r: (
                            -(float(r["stars"]) if r.get("stars") is not None else -1.0),
                            0 if r.get("source") == "projectionist" else 1,
                        )
                    )
                    ratings = ratings[:MAX_RATING_HIGHLIGHTS]

        if "user_recommendations" in tables:
            given = conn.execute(
                """
                SELECT COUNT(*) AS c FROM user_recommendations
                WHERE from_user_id = ? AND created_at >= ? AND created_at < ?
                """,
                (user_id, start_s, end_s),
            ).fetchone()
            received = conn.execute(
                """
                SELECT COUNT(*) AS c FROM user_recommendations
                WHERE to_user_id = ? AND created_at >= ? AND created_at < ?
                """,
                (user_id, start_s, end_s),
            ).fetchone()
            shares_given = int(given["c"] if given else 0)
            shares_received = int(received["c"] if received else 0)
        for candidate in ("live_channel_sessions", "live_watch_sessions", "live_sessions"):
            if candidate not in tables:
                continue
            cols = {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({candidate})").fetchall()}
            if "user_id" not in cols:
                continue
            time_col = "started_at" if "started_at" in cols else (
                "created_at" if "created_at" in cols else None
            )
            if not time_col:
                continue
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM {candidate}
                WHERE user_id = ? AND {time_col} >= ? AND {time_col} < ?
                """,
                (user_id, start_s, end_s),
            ).fetchone()
            live_sessions = int(row["c"] if row else 0)
            break

    return {
        "ratings": ratings,
        "ratings_sources": {
            "projectionist": has_projectionist_ratings,
            "plex": has_plex_ratings,
            "plex_available": plex_ratings_available,
        },
        "shares_given": shares_given,
        "shares_received": shares_received,
        "live_sessions": live_sessions,
    }
