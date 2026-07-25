"""Per-user notification inbox (generalized kinds).

Kinds: recommendation, arrival, access-request, digest, nudge.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence


NOTIFICATION_KINDS = frozenset(
    {"recommendation", "arrival", "access-request", "digest", "nudge"}
)


class NotificationsMixin:
    def create_notification(
        self,
        *,
        notification_id: str,
        user_id: str,
        kind: str,
        title: str,
        body: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        media_type: Optional[str] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        rating_key: Optional[str] = None,
        year: Optional[int] = None,
        poster_url: Optional[str] = None,
        from_user_id: Optional[str] = None,
        related_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned_kind = str(kind or "").strip().lower()
        if cleaned_kind not in NOTIFICATION_KINDS:
            raise ValueError(f"Unsupported notification kind: {kind}")
        now = time.time()
        payload_json = json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_notifications (
                    id, user_id, kind, title, body, payload_json,
                    media_type, tmdb_id, tvdb_id, rating_key, year, poster_url,
                    from_user_id, related_id, created_at, seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    notification_id,
                    user_id,
                    cleaned_kind,
                    str(title or "").strip() or "Notification",
                    (str(body).strip() if body else None) or None,
                    payload_json,
                    media_type,
                    tmdb_id,
                    tvdb_id,
                    rating_key,
                    year,
                    poster_url,
                    from_user_id,
                    related_id,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM user_notifications WHERE id = ?",
                (notification_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_notification(row)

    def list_notifications_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        kinds: Optional[Sequence[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT n.*,
                   COALESCE(fu.preferred_name, fu.display_name) AS from_display_name,
                   fu.avatar_url AS from_avatar_url
            FROM user_notifications n
            LEFT JOIN users fu ON fu.id = n.from_user_id
            WHERE n.user_id = ?
        """
        params: List[Any] = [user_id]
        if unread_only:
            query += " AND n.seen_at IS NULL"
        cleaned_kinds = [
            str(k).strip().lower()
            for k in (kinds or [])
            if str(k).strip().lower() in NOTIFICATION_KINDS
        ]
        if cleaned_kinds:
            placeholders = ",".join("?" for _ in cleaned_kinds)
            query += f" AND n.kind IN ({placeholders})"
            params.extend(cleaned_kinds)
        query += " ORDER BY n.created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def count_unread_notifications(self, user_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM user_notifications
                WHERE user_id = ? AND seen_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def mark_notifications_seen(
        self,
        user_id: str,
        *,
        notification_ids: Optional[Sequence[str]] = None,
        all_unread: bool = False,
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            if all_unread:
                cursor = conn.execute(
                    """
                    UPDATE user_notifications
                    SET seen_at = ?
                    WHERE user_id = ? AND seen_at IS NULL
                    """,
                    (now, user_id),
                )
                return int(cursor.rowcount or 0)
            ids = [str(i).strip() for i in (notification_ids or []) if str(i).strip()]
            if not ids:
                return 0
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"""
                UPDATE user_notifications
                SET seen_at = ?
                WHERE user_id = ? AND seen_at IS NULL AND id IN ({placeholders})
                """,
                (now, user_id, *ids),
            )
            return int(cursor.rowcount or 0)

    def find_notification_by_related(
        self,
        user_id: str,
        *,
        kind: str,
        related_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM user_notifications
                WHERE user_id = ? AND kind = ? AND related_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (user_id, kind, related_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_notification(row)

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        payload: Dict[str, Any] = {}
        raw_payload = row["payload_json"] if "payload_json" in keys else None
        if raw_payload:
            try:
                parsed = json.loads(str(raw_payload))
                if isinstance(parsed, dict):
                    payload = parsed
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "body": str(row["body"]) if row["body"] is not None else None,
            "payload": payload,
            "media_type": str(row["media_type"]) if row["media_type"] is not None else None,
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "rating_key": str(row["rating_key"]) if row["rating_key"] is not None else None,
            "year": int(row["year"]) if row["year"] is not None else None,
            "poster_url": str(row["poster_url"]) if row["poster_url"] is not None else None,
            "from_user_id": str(row["from_user_id"]) if row["from_user_id"] is not None else None,
            "related_id": str(row["related_id"]) if row["related_id"] is not None else None,
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
            # Compatibility aliases so existing recommendation inbox helpers keep working.
            "message": str(row["body"]) if row["body"] is not None else None,
        }
