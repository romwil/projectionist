"""Multi-session Scholar syllabus atop published cinema courses."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from curatorx.library.db import Database

SESSION_BATCH_SIZE = 2  # titles per study session


def _ensure_syllabus_table(db: Database) -> None:
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_syllabus_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                list_id TEXT NOT NULL,
                session_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                focus_note TEXT NOT NULL DEFAULT '',
                item_ids_json TEXT NOT NULL DEFAULT '[]',
                citations_json TEXT NOT NULL DEFAULT '[]',
                chat_session_id TEXT,
                completed_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(user_id, list_id, session_index),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(list_id) REFERENCES curated_lists(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_syllabus_user_list
                ON user_syllabus_sessions(user_id, list_id, session_index);
            """
        )


def _chunk(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _session_dict(row: Any) -> Dict[str, Any]:
    try:
        item_ids = json.loads(row["item_ids_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        item_ids = []
    try:
        citations = json.loads(row["citations_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        citations = []
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "list_id": str(row["list_id"]),
        "session_index": int(row["session_index"]),
        "title": str(row["title"] or ""),
        "focus_note": str(row["focus_note"] or ""),
        "item_ids": item_ids if isinstance(item_ids, list) else [],
        "citations": citations if isinstance(citations, list) else [],
        "chat_session_id": str(row["chat_session_id"]) if row["chat_session_id"] else None,
        "completed_at": float(row["completed_at"]) if row["completed_at"] else None,
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def build_syllabus_for_course(
    db: Database,
    *,
    user_id: str,
    list_id: str,
) -> Dict[str, Any]:
    """Author (or return) a multi-session syllabus from a published course list."""
    _ensure_syllabus_table(db)
    course = db.get_published_list(list_id, include_items=True)
    if course is None:
        owned = db.get_curated_list(list_id, user_id=None, include_items=True)
        if owned and str(owned.get("list_kind") or "") == "course":
            course = owned
    if course is None or str(course.get("list_kind") or "") != "course":
        raise ValueError("Published course not found")

    existing = list_syllabus_sessions(db, user_id=user_id, list_id=list_id)
    if existing:
        return {
            "list_id": list_id,
            "course_name": course.get("name"),
            "sessions": existing,
            "created": False,
        }

    items = list(course.get("items") or [])
    chunks = _chunk(items, SESSION_BATCH_SIZE) or [[]]
    now = time.time()
    sessions: List[Dict[str, Any]] = []
    with db.connect() as conn:
        for index, chunk in enumerate(chunks):
            titles = [str(it.get("title") or "Untitled") for it in chunk]
            notes = [str(it.get("note") or "").strip() for it in chunk if str(it.get("note") or "").strip()]
            session_title = (
                f"Session {index + 1}: " + (" & ".join(titles[:2]) if titles else "Open study")
            )
            focus = notes[0] if notes else (
                f"Study {', '.join(titles)} — note technique, context, and what to watch for next."
                if titles
                else "Open study session for this course."
            )
            item_ids = [str(it.get("id") or "") for it in chunk if it.get("id")]
            citations = [
                {
                    "source": "course",
                    "ref": str(it.get("title") or ""),
                    "note": str(it.get("note") or "")[:200],
                }
                for it in chunk
            ]
            session_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO user_syllabus_sessions (
                    id, user_id, list_id, session_index, title, focus_note,
                    item_ids_json, citations_json, chat_session_id, completed_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    list_id,
                    index,
                    session_title[:200],
                    focus[:2000],
                    json.dumps(item_ids),
                    json.dumps(citations),
                    now,
                    now,
                ),
            )
            sessions.append(
                {
                    "id": session_id,
                    "user_id": user_id,
                    "list_id": list_id,
                    "session_index": index,
                    "title": session_title[:200],
                    "focus_note": focus[:2000],
                    "item_ids": item_ids,
                    "citations": citations,
                    "chat_session_id": None,
                    "completed_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    return {
        "list_id": list_id,
        "course_name": course.get("name"),
        "sessions": sessions,
        "created": True,
    }


def list_syllabus_sessions(
    db: Database, *, user_id: str, list_id: str
) -> List[Dict[str, Any]]:
    _ensure_syllabus_table(db)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM user_syllabus_sessions
            WHERE user_id = ? AND list_id = ?
            ORDER BY session_index ASC
            """,
            (user_id, list_id),
        ).fetchall()
    return [_session_dict(row) for row in rows]


def get_syllabus_session(
    db: Database, *, user_id: str, session_id: str
) -> Optional[Dict[str, Any]]:
    _ensure_syllabus_table(db)
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM user_syllabus_sessions
            WHERE id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()
    return _session_dict(row) if row else None


def mark_syllabus_session(
    db: Database,
    *,
    user_id: str,
    session_id: str,
    chat_session_id: Optional[str] = None,
    completed: bool = False,
    citations: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    _ensure_syllabus_table(db)
    now = time.time()
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM user_syllabus_sessions
            WHERE id = ? AND user_id = ?
            """,
            (session_id, user_id),
        ).fetchone()
        if row is None:
            return None
        next_chat = chat_session_id if chat_session_id is not None else row["chat_session_id"]
        next_completed = now if completed else row["completed_at"]
        if citations is not None:
            citations_json = json.dumps(citations)
        else:
            citations_json = row["citations_json"]
        conn.execute(
            """
            UPDATE user_syllabus_sessions
            SET chat_session_id = ?, completed_at = ?, citations_json = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (next_chat, next_completed, citations_json, now, session_id, user_id),
        )
    return get_syllabus_session(db, user_id=user_id, session_id=session_id)


def syllabus_chat_prompt(session: Dict[str, Any], *, course_name: str = "") -> str:
    """Seed text for chat-from-here on a syllabus session."""
    course = course_name or "this course"
    cites = session.get("citations") or []
    cite_lines = []
    for index, cite in enumerate(cites[:6], start=1):
        ref = str(cite.get("ref") or cite.get("source") or "").strip()
        note = str(cite.get("note") or "").strip()
        if ref or note:
            cite_lines.append(f"[^{index}]: {ref}" + (f" — {note}" if note else ""))
    footnotes = "\n".join(cite_lines)
    body = (
        f"Continue my multi-session syllabus for {course}. "
        f"This is {session.get('title') or 'the next session'}. "
        f"Focus: {session.get('focus_note') or 'study the assigned titles carefully'}. "
        "Teach with rigor, cite sources as footnote-style markdown when you make claims, "
        "and keep this to one study session."
    )
    if footnotes:
        body += f"\n\nAssigned sources:\n{footnotes}"
    return body
