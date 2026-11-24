"""Youth join approvals (SES-009).

The row is the approval. Push delivery waits for NAT-006. Approvals expire,
are single-use, and the server checks the member and the session again when
someone answers.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

_TTL_SECONDS = 600.0
_KIND = "youth_join"


def _clean(raw: str, limit: int) -> str:
    return " ".join(str(raw or "").split())[:limit]


def ensure_youth_approval(
    db: Any,
    *,
    session_id: str,
    requester_id: str,
    requester_name: str,
    owner_id: str,
    ceiling: str,
    title: str,
    content_rating: str,
    title_above: bool,
) -> str:
    """One open request per member and session. Returns its id."""
    now = time.time()

    def _write() -> str:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            existing = conn.execute(
                """
                SELECT id FROM session_approvals
                WHERE session_id = ? AND requester_id = ? AND kind = ? AND status = 'pending'
                  AND expires_at > ?
                """,
                (session_id, requester_id, _KIND, now),
            ).fetchone()
            if existing is not None:
                return str(existing["id"])
            approval_id = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO session_approvals (
                    id, kind, session_id, requester_id, requester_name, owner_id,
                    ceiling, title, content_rating, title_above, status,
                    created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    approval_id,
                    _KIND,
                    session_id,
                    requester_id,
                    _clean(requester_name, 40) or "Someone",
                    owner_id,
                    _clean(ceiling, 20),
                    _clean(title, 120),
                    _clean(content_rating, 20),
                    1 if title_above else 0,
                    now,
                    now + _TTL_SECONDS,
                ),
            )
            return approval_id

    return db.run_write(_write, label="youth_join_approval")


def _expire(conn: Any, now: float) -> None:
    conn.execute(
        """
        UPDATE session_approvals
        SET status = 'expired', acted_at = ?
        WHERE status = 'pending' AND expires_at <= ?
        """,
        (now, now),
    )


def list_approvals(db: Any, *, viewer_id: str) -> dict[str, Any]:
    now = time.time()

    def _read() -> list[Any]:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            _expire(conn, now)
            return conn.execute(
                """
                SELECT * FROM session_approvals
                WHERE owner_id = ? OR requester_id = ?
                ORDER BY created_at DESC
                LIMIT 40
                """,
                (viewer_id, viewer_id),
            ).fetchall()

    rows = db.run_write(_read, label="list_session_approvals")
    return {"approvals": [_public(row, viewer_id) for row in rows]}


def _public(row: Any, viewer_id: str) -> dict[str, Any]:
    body = {
        "id": str(row["id"]),
        "kind": str(row["kind"]),
        "status": str(row["status"]),
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }
    if str(row["owner_id"]) == viewer_id:
        body.update(
            {
                "session_id": str(row["session_id"]),
                "requester_name": str(row["requester_name"]),
                "ceiling": str(row["ceiling"]),
                "title": str(row["title"]),
                "content_rating": str(row["content_rating"]),
                "title_above": bool(row["title_above"]),
            }
        )
    return body


def open_approval(db: Any, approval_id: str, *, actor_id: str) -> dict[str, Any] | None:
    """The pending row for this owner, or None. Does not consume it."""
    now = time.time()

    def _read() -> dict[str, Any] | None:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            _expire(conn, now)
            row = conn.execute(
                "SELECT * FROM session_approvals WHERE id = ?",
                (str(approval_id or "").strip().lower(),),
            ).fetchone()
            if row is None or str(row["status"]) != "pending":
                return None
            if str(row["owner_id"]) != actor_id:
                return None
            return dict(row)

    return db.run_write(_read, label="read_session_approval")


def finish_approval(db: Any, approval_id: str, *, actor_id: str, decision: str) -> bool:
    choice = str(decision or "").strip().lower()
    if choice not in {"approve", "not_now"}:
        raise ValueError(choice)
    status = "approved" if choice == "approve" else "declined"
    now = time.time()

    def _write() -> bool:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            updated = conn.execute(
                """
                UPDATE session_approvals
                SET status = ?, acted_at = ?, acted_by = ?
                WHERE id = ? AND owner_id = ? AND status = 'pending'
                """,
                (status, now, actor_id, str(approval_id or "").strip().lower(), actor_id),
            )
            return updated.rowcount == 1

    return bool(db.run_write(_write, label="finish_session_approval"))
