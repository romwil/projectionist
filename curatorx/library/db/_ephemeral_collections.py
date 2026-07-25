"""Track agent-created / movie-night ephemeral Plex collections for TTL prune."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# Visible prefix on Plex so owners can spot CuratorX movie-night shelves.
EPHEMERAL_COLLECTION_PREFIX = "[CuratorX] "
DEFAULT_EPHEMERAL_TTL_HOURS = 168  # 7 days


class EphemeralCollectionsMixin:
    def record_ephemeral_plex_collection(
        self,
        *,
        plex_rating_key: str,
        section_id: str,
        title: str,
        media_type: str,
        ttl_hours: int = DEFAULT_EPHEMERAL_TTL_HOURS,
        created_by_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = str(plex_rating_key or "").strip()
        if not key:
            raise ValueError("plex_rating_key is required")
        now = time.time()
        ttl = max(1, int(ttl_hours or DEFAULT_EPHEMERAL_TTL_HOURS))
        expires_at = now + (ttl * 3600)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ephemeral_plex_collections (
                    plex_rating_key, section_id, title, media_type,
                    created_at, expires_at, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plex_rating_key) DO UPDATE SET
                    section_id = excluded.section_id,
                    title = excluded.title,
                    media_type = excluded.media_type,
                    expires_at = excluded.expires_at,
                    created_by_user_id = COALESCE(
                        excluded.created_by_user_id,
                        ephemeral_plex_collections.created_by_user_id
                    )
                """,
                (
                    key,
                    str(section_id or "").strip(),
                    str(title or "").strip(),
                    str(media_type or "movie").strip() or "movie",
                    now,
                    expires_at,
                    created_by_user_id,
                ),
            )
        return {
            "plex_rating_key": key,
            "created_at": now,
            "expires_at": expires_at,
            "ttl_hours": ttl,
        }

    def list_expired_ephemeral_plex_collections(
        self, *, now: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        cutoff = float(now if now is not None else time.time())
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT plex_rating_key, section_id, title, media_type,
                       created_at, expires_at, created_by_user_id
                FROM ephemeral_plex_collections
                WHERE expires_at <= ?
                ORDER BY expires_at ASC
                """,
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_ephemeral_plex_collections(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT plex_rating_key, section_id, title, media_type,
                       created_at, expires_at, created_by_user_id
                FROM ephemeral_plex_collections
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_ephemeral_plex_collection_row(self, plex_rating_key: str) -> bool:
        key = str(plex_rating_key or "").strip()
        if not key:
            return False
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM ephemeral_plex_collections WHERE plex_rating_key = ?",
                (key,),
            )
            return int(cur.rowcount or 0) > 0
