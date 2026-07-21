"""Curated lists, list items, collections, and courses.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import time
from typing import (
    Any,
    Dict,
    List,
    Optional,
)



class CuratedListsMixin:
    def list_curated_lists(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.user_id IS NULL
                    ORDER BY l.updated_at DESC, l.created_at DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.user_id = ?
                    ORDER BY l.updated_at DESC, l.created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_curated_list(row) for row in rows]

    def get_curated_list(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        include_items: bool = False,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.id = ? AND l.user_id IS NULL
                    """,
                    (list_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.id = ? AND l.user_id = ?
                    """,
                    (list_id, user_id),
                ).fetchone()
            if row is None:
                return None
            payload = self._row_to_curated_list(row)
            if include_items:
                items = conn.execute(
                    """
                    SELECT * FROM curated_list_items
                    WHERE list_id = ?
                    ORDER BY position ASC, created_at ASC
                    """,
                    (list_id,),
                ).fetchall()
                payload["items"] = [self._row_to_curated_list_item(item) for item in items]
            return payload

    def create_curated_list(
        self,
        *,
        list_id: str,
        user_id: Optional[str],
        name: str,
        description: str = "",
        list_kind: str = "list",
    ) -> Dict[str, Any]:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("name is required")
        if list_kind not in {"list", "playlist", "course"}:
            raise ValueError("list_kind must be list, playlist, or course")
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM curated_lists
                WHERE name = ?
                  AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                  )
                """,
                (cleaned, user_id, user_id),
            ).fetchone()
            if existing is not None:
                raise ValueError("A list with that name already exists")
            conn.execute(
                """
                INSERT INTO curated_lists (id, user_id, name, description, list_kind, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (list_id, user_id, cleaned, (description or "").strip(), list_kind, now, now),
            )
            row = conn.execute(
                """
                SELECT l.*, 0 AS item_count
                FROM curated_lists l
                WHERE l.id = ?
                """,
                (list_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_curated_list(row)

    def update_curated_list(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        list_kind: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if name is None and description is None and list_kind is None:
            raise ValueError("No list fields to update")
        cleaned_name = name.strip() if name is not None else None
        if cleaned_name is not None and not cleaned_name:
            raise ValueError("name cannot be empty")
        if list_kind is not None and list_kind not in {"list", "playlist", "course"}:
            raise ValueError("list_kind must be list, playlist, or course")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                existing = conn.execute(
                    "SELECT * FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT * FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if existing is None:
                return None
            next_name = cleaned_name if cleaned_name is not None else str(existing["name"])
            next_description = (
                description.strip() if description is not None else str(existing["description"] or "")
            )
            next_kind = list_kind if list_kind is not None else str(existing["list_kind"] or "list")
            if cleaned_name is not None and cleaned_name != str(existing["name"]):
                conflict = conn.execute(
                    """
                    SELECT id FROM curated_lists
                    WHERE name = ?
                      AND id != ?
                      AND (
                        (user_id IS NULL AND ? IS NULL) OR user_id = ?
                      )
                    """,
                    (cleaned_name, list_id, user_id, user_id),
                ).fetchone()
                if conflict is not None:
                    raise ValueError("A list with that name already exists")
            conn.execute(
                """
                UPDATE curated_lists
                SET name = ?, description = ?, list_kind = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_name, next_description, next_kind, now, list_id),
            )
        return self.get_curated_list(list_id, user_id=user_id, include_items=False)

    def delete_curated_list(self, list_id: str, *, user_id: Optional[str] = None) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM curated_list_items WHERE list_id = ?", (list_id,))
            conn.execute("DELETE FROM curated_lists WHERE id = ?", (list_id,))
            return True

    def add_curated_list_item(
        self,
        *,
        item_id: str,
        list_id: str,
        user_id: Optional[str],
        tmdb_id: Optional[int],
        tvdb_id: Optional[int],
        media_type: str,
        title: str,
        library_item_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("title is required")
        if media_type not in {"movie", "show"}:
            raise ValueError("media_type must be movie or show")
        if tmdb_id is None and tvdb_id is None:
            raise ValueError("tmdb_id or tvdb_id is required")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                raise ValueError("List not found")
            resolved_library_id = library_item_id
            if resolved_library_id is None:
                if media_type == "movie" and tmdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'movie' AND tmdb_id = ? LIMIT 1",
                        (int(tmdb_id),),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
                elif media_type == "show" and tvdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'show' AND tvdb_id = ? LIMIT 1",
                        (int(tvdb_id),),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
                elif tmdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = ? AND tmdb_id = ? LIMIT 1",
                        (media_type, int(tmdb_id)),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
            position_row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM curated_list_items WHERE list_id = ?",
                (list_id,),
            ).fetchone()
            position = int(position_row["next_pos"] or 0) if position_row else 0
            conn.execute(
                """
                INSERT INTO curated_list_items (
                    id, list_id, tmdb_id, tvdb_id, media_type, title,
                    library_item_id, position, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    item_id,
                    list_id,
                    tmdb_id,
                    tvdb_id,
                    media_type,
                    cleaned_title,
                    resolved_library_id,
                    position,
                    now,
                ),
            )
            conn.execute(
                "UPDATE curated_lists SET updated_at = ? WHERE id = ?",
                (now, list_id),
            )
            row = conn.execute(
                """
                SELECT * FROM curated_list_items
                WHERE list_id = ?
                  AND media_type = ?
                  AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                  AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                """,
                (list_id, media_type, tmdb_id, tvdb_id),
            ).fetchone()
        if row is None:
            raise ValueError("Could not save list item")
        return self._row_to_curated_list_item(row)

    def delete_curated_list_item(
        self,
        list_id: str,
        item_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> bool:
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                return False
            row = conn.execute(
                "SELECT id FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "DELETE FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            )
            conn.execute(
                "UPDATE curated_lists SET updated_at = ? WHERE id = ?",
                (time.time(), list_id),
            )
            return True

    def find_curated_list_item(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        item_id: Optional[str] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        media_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                return None
            if item_id:
                row = conn.execute(
                    "SELECT * FROM curated_list_items WHERE id = ? AND list_id = ?",
                    (item_id, list_id),
                ).fetchone()
                return self._row_to_curated_list_item(row) if row else None
            rows = conn.execute(
                "SELECT * FROM curated_list_items WHERE list_id = ? ORDER BY position ASC, created_at ASC",
                (list_id,),
            ).fetchall()
        for row in rows:
            item = self._row_to_curated_list_item(row)
            if media_type and item["media_type"] != media_type:
                continue
            if tmdb_id is not None and item.get("tmdb_id") == int(tmdb_id):
                return item
            if tvdb_id is not None and item.get("tvdb_id") == int(tvdb_id):
                return item
            if title and item["title"].strip().lower() == title.strip().lower():
                return item
        return None

    def set_curated_list_visibility(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        visibility: str,
    ) -> Optional[Dict[str, Any]]:
        """Publish a list to household members (``published``) or make it private again."""
        if visibility not in {"private", "published"}:
            raise ValueError("visibility must be private or published")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                existing = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if existing is None:
                return None
            published_at = now if visibility == "published" else None
            conn.execute(
                "UPDATE curated_lists SET visibility = ?, published_at = ?, updated_at = ? WHERE id = ?",
                (visibility, published_at, now, list_id),
            )
        return self.get_curated_list(list_id, user_id=user_id, include_items=False)

    def list_published_lists(self) -> List[Dict[str, Any]]:
        """Return every list published to household members, newest first."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT l.*, (
                    SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                ) AS item_count
                FROM curated_lists l
                WHERE l.visibility = 'published'
                ORDER BY l.published_at DESC, l.updated_at DESC
                """
            ).fetchall()
        return [self._row_to_curated_list(row) for row in rows]

    def get_published_list(
        self, list_id: str, *, include_items: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Return a published list by id regardless of owner (members read path)."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT l.*, (
                    SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                ) AS item_count
                FROM curated_lists l
                WHERE l.id = ? AND l.visibility = 'published'
                """,
                (list_id,),
            ).fetchone()
            if row is None:
                return None
            payload = self._row_to_curated_list(row)
            if include_items:
                items = conn.execute(
                    """
                    SELECT * FROM curated_list_items
                    WHERE list_id = ?
                    ORDER BY position ASC, created_at ASC
                    """,
                    (list_id,),
                ).fetchall()
                payload["items"] = [self._row_to_curated_list_item(item) for item in items]
            return payload

    def update_curated_list_item(
        self,
        list_id: str,
        item_id: str,
        *,
        user_id: Optional[str] = None,
        note: Optional[str] = None,
        position: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update a course step's note and/or ordering position (owner authoring)."""
        if note is None and position is None:
            raise ValueError("No item fields to update")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                return None
            existing = conn.execute(
                "SELECT * FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            ).fetchone()
            if existing is None:
                return None
            if note is not None:
                next_note = note.strip()
            elif "note" in existing.keys():
                next_note = str(existing["note"] or "")
            else:
                next_note = ""
            next_position = (
                int(position) if position is not None else int(existing["position"] or 0)
            )
            conn.execute(
                "UPDATE curated_list_items SET note = ?, position = ? WHERE id = ? AND list_id = ?",
                (next_note, next_position, item_id, list_id),
            )
            conn.execute(
                "UPDATE curated_lists SET updated_at = ? WHERE id = ?",
                (now, list_id),
            )
            row = conn.execute(
                "SELECT * FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            ).fetchone()
        return self._row_to_curated_list_item(row) if row else None

