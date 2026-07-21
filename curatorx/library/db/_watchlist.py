"""Watchlist pins.

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
)



class WatchlistMixin:
    def list_watchlist_pins(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM watchlist_pins
                    WHERE user_id IS NULL
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM watchlist_pins
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_watchlist_pin(row) for row in rows]

    def add_watchlist_pin(
        self,
        *,
        pin_id: str,
        user_id: Optional[str],
        tmdb_id: Optional[int],
        tvdb_id: Optional[int],
        media_type: str,
        title: str,
        plex_rating_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            cols = self._table_columns(conn, "watchlist_pins")
            if "plex_rating_key" in cols:
                conn.execute(
                    """
                    INSERT INTO watchlist_pins (
                        id, user_id, tmdb_id, tvdb_id, media_type, title, created_at, plex_rating_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (pin_id, user_id, tmdb_id, tvdb_id, media_type, title, now, plex_rating_key),
                )
                if plex_rating_key:
                    conn.execute(
                        """
                        UPDATE watchlist_pins
                        SET plex_rating_key = COALESCE(plex_rating_key, ?)
                        WHERE media_type = ?
                          AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                          AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                          AND (
                            (user_id IS NULL AND ? IS NULL) OR user_id = ?
                          )
                        """,
                        (plex_rating_key, media_type, tmdb_id, tvdb_id, user_id, user_id),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO watchlist_pins (
                        id, user_id, tmdb_id, tvdb_id, media_type, title, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (pin_id, user_id, tmdb_id, tvdb_id, media_type, title, now),
                )
            row = conn.execute(
                """
                SELECT * FROM watchlist_pins
                WHERE media_type = ?
                  AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                  AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                  AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                  )
                """,
                (media_type, tmdb_id, tvdb_id, user_id, user_id),
            ).fetchone()
        if row is None:
            raise ValueError("Could not save watchlist pin")
        return self._row_to_watchlist_pin(row)

    def set_watchlist_pin_plex_rating_key(self, pin_id: str, plex_rating_key: str) -> None:
        with self.connect() as conn:
            cols = self._table_columns(conn, "watchlist_pins")
            if "plex_rating_key" not in cols:
                return
            conn.execute(
                "UPDATE watchlist_pins SET plex_rating_key = ? WHERE id = ?",
                (plex_rating_key, pin_id),
            )

    def get_watchlist_pin(self, pin_id: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT * FROM watchlist_pins WHERE id = ?",
                    (pin_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM watchlist_pins WHERE id = ? AND user_id = ?",
                    (pin_id, user_id),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_watchlist_pin(row)

    def delete_watchlist_pin(self, pin_id: str, *, user_id: Optional[str] = None) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    """
                    SELECT id FROM watchlist_pins
                    WHERE id = ? AND user_id IS NULL
                    """,
                    (pin_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM watchlist_pins WHERE id = ? AND user_id = ?",
                    (pin_id, user_id),
                ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM watchlist_pins WHERE id = ?", (pin_id,))
            return True

    def count_chat_sessions_last_days(self, days: int = 30) -> int:
        cutoff = time.time() - (days * 86400)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM chat_sessions WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
        return int(row["count"] or 0) if row else 0

    @staticmethod
    def _row_to_watchlist_pin(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        plex_rating_key = None
        if "plex_rating_key" in keys and row["plex_rating_key"] is not None:
            plex_rating_key = str(row["plex_rating_key"])
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "created_at": float(row["created_at"]),
            "plex_rating_key": plex_rating_key,
        }

