"""Saved library pages.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
)



class SavedLibraryMixin:
    @staticmethod
    def _row_to_saved_library_page(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "name": str(row["name"]),
            "source_session_id": row["source_session_id"],
            "source_message_id": row["source_message_id"],
            "persona_id": row["persona_id"] if "persona_id" in row.keys() else None,
            "summary": str(row["summary"] or "") if "summary" in row.keys() else "",
            "searchable_text": str(row["searchable_text"] or ""),
            "content": json.loads(row["content_json"]),
            "created_at": float(row["created_at"]),
        }

    def create_saved_library_page(
        self,
        *,
        page_id: str,
        user_id: str,
        name: str,
        content: Mapping[str, Any],
        searchable_text: str,
        source_session_id: Optional[str] = None,
        source_message_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        summary: str = "",
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO saved_library_pages (
                    id, user_id, name, source_session_id, source_message_id,
                    persona_id, summary, searchable_text, content_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page_id,
                    user_id,
                    name.strip(),
                    source_session_id,
                    source_message_id,
                    persona_id,
                    summary.strip(),
                    searchable_text,
                    json.dumps(dict(content)),
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM saved_library_pages WHERE id = ?", (page_id,)).fetchone()
        assert row is not None
        return self._row_to_saved_library_page(row)

    def first_saved_library_page_without_summary(self, *, user_id: str) -> Optional[Dict[str, Any]]:
        """Return one oldest unsummarized page so grooming stays bounded."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM saved_library_pages
                WHERE user_id = ? AND trim(COALESCE(summary, '')) = ''
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return self._row_to_saved_library_page(row) if row else None

    def update_saved_library_summary(self, page_id: str, *, user_id: str, summary: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE saved_library_pages SET summary = ? WHERE id = ? AND user_id = ?",
                (summary.strip(), page_id, user_id),
            )
        return cursor.rowcount > 0

    def list_saved_library_pages(self, *, user_id: str, query: str = "") -> List[Dict[str, Any]]:
        pattern = f"%{query.strip().lower()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM saved_library_pages
                WHERE user_id = ? AND (lower(name) LIKE ? OR lower(searchable_text) LIKE ?)
                ORDER BY created_at DESC
                """,
                (user_id, pattern, pattern),
            ).fetchall()
        return [self._row_to_saved_library_page(row) for row in rows]

    def get_saved_library_page(self, page_id: str, *, user_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM saved_library_pages WHERE id = ? AND user_id = ?",
                (page_id, user_id),
            ).fetchone()
        return self._row_to_saved_library_page(row) if row else None

    def delete_saved_library_page(self, page_id: str, *, user_id: str) -> bool:
        with self.connect() as conn:
            result = conn.execute(
                "DELETE FROM saved_library_pages WHERE id = ? AND user_id = ?",
                (page_id, user_id),
            )
        return result.rowcount > 0

