"""CuratorX-owned household access-request queue (guest → owner approve)."""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional


ACCESS_REQUEST_STATUSES = frozenset({"pending", "approved", "denied"})


class AccessRequestsMixin:
    def create_access_request(
        self,
        *,
        display_name: str,
        email: Optional[str] = None,
        message: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        name = str(display_name or "").strip()
        if len(name) < 2:
            raise ValueError("display_name must be at least 2 characters")
        email_clean = str(email or "").strip() or None
        message_clean = str(message or "").strip() or None
        rid = request_id or uuid.uuid4().hex
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO access_requests (
                    id, display_name, email, message, status, created_at,
                    resolved_at, resolved_by, created_user_id
                ) VALUES (?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL)
                """,
                (rid, name, email_clean, message_clean, now),
            )
            row = conn.execute("SELECT * FROM access_requests WHERE id = ?", (rid,)).fetchone()
        assert row is not None
        return self._row_to_access_request(row)

    def list_access_requests(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM access_requests"
        params: List[Any] = []
        cleaned = str(status or "").strip().lower()
        if cleaned:
            if cleaned not in ACCESS_REQUEST_STATUSES:
                raise ValueError(f"Unsupported status: {status}")
            query += " WHERE status = ?"
            params.append(cleaned)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_access_request(row) for row in rows]

    def get_access_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM access_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_access_request(row)

    def resolve_access_request(
        self,
        request_id: str,
        *,
        status: str,
        resolved_by: str,
        created_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned = str(status or "").strip().lower()
        if cleaned not in {"approved", "denied"}:
            raise ValueError("status must be approved or denied")
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM access_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Unknown access request: {request_id}")
            if str(existing["status"]) != "pending":
                raise ValueError("Access request is already resolved")
            conn.execute(
                """
                UPDATE access_requests
                SET status = ?, resolved_at = ?, resolved_by = ?, created_user_id = ?
                WHERE id = ?
                """,
                (cleaned, now, resolved_by, created_user_id, request_id),
            )
            row = conn.execute(
                "SELECT * FROM access_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_access_request(row)

    @staticmethod
    def _row_to_access_request(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "display_name": str(row["display_name"]),
            "email": str(row["email"]) if row["email"] is not None else None,
            "message": str(row["message"]) if row["message"] is not None else None,
            "status": str(row["status"]),
            "created_at": float(row["created_at"]),
            "resolved_at": float(row["resolved_at"]) if row["resolved_at"] is not None else None,
            "resolved_by": str(row["resolved_by"]) if row["resolved_by"] is not None else None,
            "created_user_id": (
                str(row["created_user_id"]) if row["created_user_id"] is not None else None
            ),
        }
