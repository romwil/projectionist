"""Optional social signals for adaptive YIR chapters (ratings, shares, Live)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from projectionist.library.db import Database
from projectionist.watch_tracker.rollups import year_bounds_ms


def collect_social_signals(db: Database, *, user_id: str, year: int) -> Dict[str, Any]:
    start_ms, end_ms = year_bounds_ms(int(year))
    start_s = start_ms / 1000.0
    end_s = end_ms / 1000.0
    ratings: List[Dict[str, Any]] = []
    shares_given = 0
    shares_received = 0
    live_sessions = 0

    with db.connect() as conn:
        # User reviews / ratings if table exists
        tables = {
            str(r["name"])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "user_title_reviews" in tables:
            rows = conn.execute(
                """
                SELECT title, stars, created_at FROM user_title_reviews
                WHERE user_id = ? AND created_at >= ? AND created_at < ?
                ORDER BY stars DESC, created_at DESC
                LIMIT 8
                """,
                (user_id, start_s, end_s),
            ).fetchall()
            for row in rows:
                ratings.append(
                    {
                        "title": str(row["title"] or ""),
                        "stars": float(row["stars"]) if row["stars"] is not None else None,
                    }
                )
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
        # Live channel watch sessions — best-effort if table present
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
        "shares_given": shares_given,
        "shares_received": shares_received,
        "live_sessions": live_sessions,
    }
