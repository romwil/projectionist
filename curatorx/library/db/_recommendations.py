"""Per-user recommendations.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import sqlite3
import time
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
)



class RecommendationsMixin:
    def create_recommendation(
        self,
        *,
        recommendation_id: str,
        from_user_id: str,
        to_user_id: str,
        media_type: str,
        title: str,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        rating_key: Optional[str] = None,
        year: Optional[int] = None,
        poster_url: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_recommendations (
                    id, from_user_id, to_user_id, media_type, tmdb_id, tvdb_id,
                    rating_key, title, year, poster_url, message, created_at, seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    recommendation_id,
                    from_user_id,
                    to_user_id,
                    media_type,
                    tmdb_id,
                    tvdb_id,
                    rating_key,
                    title,
                    year,
                    poster_url,
                    message,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM user_recommendations WHERE id = ?",
                (recommendation_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_recommendation(row)

    def list_recommendations_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT r.*,
                   COALESCE(fu.preferred_name, fu.display_name) AS from_display_name,
                   fu.avatar_url AS from_avatar_url
            FROM user_recommendations r
            LEFT JOIN users fu ON fu.id = r.from_user_id
            WHERE r.to_user_id = ?
        """
        params: List[Any] = [user_id]
        if unread_only:
            query += " AND r.seen_at IS NULL"
        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_recommendation(row) for row in rows]

    def count_unread_recommendations(self, user_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM user_recommendations
                WHERE to_user_id = ? AND seen_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def mark_recommendations_seen(
        self,
        user_id: str,
        *,
        recommendation_ids: Optional[Sequence[str]] = None,
        all_unread: bool = False,
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            if all_unread:
                cursor = conn.execute(
                    """
                    UPDATE user_recommendations
                    SET seen_at = ?
                    WHERE to_user_id = ? AND seen_at IS NULL
                    """,
                    (now, user_id),
                )
                return int(cursor.rowcount or 0)
            ids = [str(i).strip() for i in (recommendation_ids or []) if str(i).strip()]
            if not ids:
                return 0
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"""
                UPDATE user_recommendations
                SET seen_at = ?
                WHERE to_user_id = ? AND seen_at IS NULL AND id IN ({placeholders})
                """,
                (now, user_id, *ids),
            )
            return int(cursor.rowcount or 0)

    @staticmethod
    def _row_to_recommendation(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return {
            "id": str(row["id"]),
            "from_user_id": str(row["from_user_id"]),
            "to_user_id": str(row["to_user_id"]),
            "media_type": str(row["media_type"]),
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "rating_key": str(row["rating_key"]) if row["rating_key"] is not None else None,
            "title": str(row["title"]),
            "year": int(row["year"]) if row["year"] is not None else None,
            "poster_url": str(row["poster_url"]) if row["poster_url"] is not None else None,
            "message": str(row["message"]) if row["message"] is not None else None,
            "created_at": float(row["created_at"]),
            "seen_at": float(row["seen_at"]) if row["seen_at"] is not None else None,
            "from_display_name": (
                str(row["from_display_name"])
                if "from_display_name" in keys and row["from_display_name"] is not None
                else None
            ),
            "from_avatar_url": (
                str(row["from_avatar_url"])
                if "from_avatar_url" in keys and row["from_avatar_url"] is not None
                else None
            ),
        }

