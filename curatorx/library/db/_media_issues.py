"""Media issues (and shared row-mapping helpers).

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



class MediaIssuesMixin:
    def create_media_issue(
        self,
        *,
        issue_id: str,
        reporter_user_id: Optional[str],
        rating_key: Optional[str],
        tmdb_id: Optional[int],
        tvdb_id: Optional[int],
        media_type: str,
        title: str,
        code: str,
        note: str = "",
    ) -> Dict[str, Any]:
        if media_type not in {"movie", "show"}:
            raise ValueError("media_type must be movie or show")
        if not (title or "").strip():
            raise ValueError("title is required")
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO media_issues (
                    id, reporter_user_id, rating_key, tmdb_id, tvdb_id, media_type,
                    title, code, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue_id, reporter_user_id, rating_key, tmdb_id, tvdb_id, media_type,
                    title.strip(), code, (note or "").strip(), now, now,
                ),
            )
        issue = self.get_media_issue(issue_id)
        assert issue is not None
        return issue

    def get_media_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM media_issues WHERE id = ?", (issue_id,)).fetchone()
        return self._row_to_media_issue(row) if row is not None else None

    def list_media_issues(
        self, *, status: Optional[str] = None, code: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if code:
            clauses.append("code = ?")
            params.append(code)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(min(max(1, int(limit)), 500))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM media_issues {where} ORDER BY updated_at DESC LIMIT ?", params
            ).fetchall()
        return [self._row_to_media_issue(row) for row in rows]

    def update_media_issue(
        self,
        issue_id: str,
        *,
        status: Optional[str] = None,
        repair_action: Optional[str] = None,
        repair_log_entry: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM media_issues WHERE id = ?", (issue_id,)).fetchone()
            if row is None:
                return None
            next_status = status or str(row["status"])
            log = json.loads(str(row["repair_log"] or "[]"))
            if not isinstance(log, list):
                log = []
            if repair_log_entry is not None:
                log.append(dict(repair_log_entry))
            now = time.time()
            conn.execute(
                """
                UPDATE media_issues
                SET status = ?, repair_action = ?, repair_log = ?, updated_at = ?,
                    resolved_at = CASE WHEN ? IN ('resolved', 'rejected') THEN ? ELSE resolved_at END
                WHERE id = ?
                """,
                (
                    next_status,
                    repair_action if repair_action is not None else str(row["repair_action"] or ""),
                    json.dumps(log), now, next_status, now, issue_id,
                ),
            )
        return self.get_media_issue(issue_id)

    @staticmethod
    def _row_to_media_issue(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            repair_log = json.loads(str(row["repair_log"] or "[]"))
        except json.JSONDecodeError:
            repair_log = []
        return {
            "id": str(row["id"]),
            "reporter_user_id": row["reporter_user_id"],
            "rating_key": row["rating_key"],
            "tmdb_id": row["tmdb_id"],
            "tvdb_id": row["tvdb_id"],
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "code": str(row["code"]),
            "note": str(row["note"] or ""),
            "status": str(row["status"]),
            "repair_action": str(row["repair_action"] or ""),
            "repair_log": repair_log if isinstance(repair_log, list) else [],
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "resolved_at": float(row["resolved_at"]) if row["resolved_at"] is not None else None,
        }

    @staticmethod
    def _row_to_curated_list(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        item_count = int(row["item_count"]) if "item_count" in keys and row["item_count"] is not None else 0
        visibility = (
            str(row["visibility"] or "private") if "visibility" in keys else "private"
        )
        published_at = (
            float(row["published_at"])
            if "published_at" in keys and row["published_at"] is not None
            else None
        )
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "list_kind": str(row["list_kind"] or "list") if "list_kind" in keys else "list",
            "visibility": visibility,
            "published_at": published_at,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "item_count": item_count,
        }

    @staticmethod
    def _row_to_curated_list_item(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        library_item_id = None
        if "library_item_id" in keys and row["library_item_id"] is not None:
            library_item_id = int(row["library_item_id"])
        return {
            "id": str(row["id"]),
            "list_id": str(row["list_id"]),
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "library_item_id": library_item_id,
            "position": int(row["position"] or 0),
            "note": str(row["note"] or "") if "note" in keys else "",
            "created_at": float(row["created_at"]),
        }
