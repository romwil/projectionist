"""Chat threads, sessions, messages, and history.

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
    Iterable,
    List,
    Mapping,
    Optional,
)

from ._shared import (
    DEFAULT_CONTEXT_HASH,
    DEFAULT_LENS_ID,
)


class ChatThreadsMixin:
    def _preview_from_blocks(self, blocks_json: Optional[str]) -> str:
        if not blocks_json:
            return ""
        try:
            blocks = json.loads(blocks_json)
        except json.JSONDecodeError:
            return ""
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                content = str(block.get("content") or "").strip()
                if content:
                    return content[:120]
        return ""

    def _row_to_thread_summary(self, row: sqlite3.Row, *, message_count: int = 0, preview: str = "") -> Dict[str, Any]:
        persona_id = row["persona_id"] if "persona_id" in row.keys() else None
        context_label = row["context_label"] if "context_label" in row.keys() else "General Exploration"
        return {
            "id": str(row["id"]),
            "thread_title": str(row["thread_title"] or self.DEFAULT_THREAD_TITLE),
            "context_hash": str(row["context_hash"] or DEFAULT_CONTEXT_HASH),
            "context_label": str(context_label or "General Exploration"),
            "lens_id": str(row["lens_id"] or DEFAULT_LENS_ID),
            "persona_id": str(persona_id) if persona_id else None,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "message_count": message_count,
            "preview": preview,
        }

    def create_chat_thread(
        self,
        session_id: str,
        *,
        lens_id: str = DEFAULT_LENS_ID,
        context_hash: str = DEFAULT_CONTEXT_HASH,
        thread_title: Optional[str] = None,
        user_id: Optional[str] = None,
        persona_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        resolved_lens = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        title = (thread_title or self.DEFAULT_THREAD_TITLE).strip() or self.DEFAULT_THREAD_TITLE
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id, persona_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved_lens, title, resolved_context, user_id, persona_id),
            )
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        assert row is not None
        return self._row_to_thread_summary(row)

    def get_chat_thread(
        self,
        session_id: str,
        *,
        user_id: Optional[str] = None,
        include_orphans: bool = False,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            elif include_orphans:
                # Owner review: also match legacy NULL-owner (orphan) threads.
                row = conn.execute(
                    "SELECT * FROM chat_sessions WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
                    (session_id, user_id),
                ).fetchone()
            else:
                # Members only ever see their own threads — never legacy orphans.
                row = conn.execute(
                    "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_id),
                ).fetchone()
            if not row:
                return None
            count_row = conn.execute(
                "SELECT COUNT(*) AS count FROM chat_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            last_row = conn.execute(
                """
                SELECT blocks_json FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        preview = self._preview_from_blocks(last_row["blocks_json"] if last_row else None)
        return self._row_to_thread_summary(
            row,
            message_count=int(count_row["count"]) if count_row else 0,
            preview=preview,
        )

    def list_chat_threads(
        self,
        *,
        limit: int = 50,
        user_id: Optional[str] = None,
        include_orphans: bool = False,
    ) -> List[Dict[str, Any]]:
        select_prefix = """
                    SELECT
                        s.*,
                        COUNT(m.id) AS message_count,
                        (
                            SELECT blocks_json FROM chat_messages
                            WHERE session_id = s.id
                            ORDER BY created_at DESC
                            LIMIT 1
                        ) AS last_blocks_json
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON m.session_id = s.id
        """
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    select_prefix
                    + " GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            elif include_orphans:
                # Owner view: own threads plus legacy NULL-owner (orphan) threads.
                rows = conn.execute(
                    select_prefix
                    + " WHERE s.user_id IS NULL OR s.user_id = ? GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            else:
                # Members only ever see their own threads — never legacy orphans.
                rows = conn.execute(
                    select_prefix
                    + " WHERE s.user_id = ? GROUP BY s.id ORDER BY s.updated_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
        threads: List[Dict[str, Any]] = []
        for row in rows:
            preview = self._preview_from_blocks(row["last_blocks_json"])
            threads.append(
                self._row_to_thread_summary(
                    row,
                    message_count=int(row["message_count"] or 0),
                    preview=preview,
                )
            )
        return threads

    def update_thread_title(self, session_id: str, thread_title: str) -> Dict[str, Any]:
        title = thread_title.strip()
        if not title:
            raise ValueError("thread_title is required")
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if not existing:
                raise ValueError(f"Unknown session_id: {session_id}")
            conn.execute(
                "UPDATE chat_sessions SET thread_title = ?, updated_at = ? WHERE id = ?",
                (title, now, session_id),
            )
        thread = self.get_chat_thread(session_id)
        assert thread is not None
        return thread

    def update_thread_context_label(self, session_id: str, context_label: str) -> None:
        label = (context_label or "").strip() or "General Exploration"
        with self.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET context_label = ? WHERE id = ?",
                (label, session_id),
            )

    def maybe_auto_title_thread(self, session_id: str, first_message: str) -> None:
        text = first_message.strip()
        if not text:
            return
        title = text[:60] + ("…" if len(text) > 60 else "")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT thread_title FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            current = str(row["thread_title"] or self.DEFAULT_THREAD_TITLE)
            if current != self.DEFAULT_THREAD_TITLE:
                return
            conn.execute(
                "UPDATE chat_sessions SET thread_title = ? WHERE id = ?",
                (title, session_id),
            )

    def delete_chat_thread(
        self,
        session_id: str,
        *,
        user_id: Optional[str] = None,
        include_orphans: bool = False,
    ) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            elif include_orphans:
                row = conn.execute(
                    "SELECT id FROM chat_sessions WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
                    (session_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM chat_sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_id),
                ).fetchone()
            if not row:
                return False
            # PRAGMA foreign_keys is not enabled, so ON DELETE CASCADE is dormant.
            # Delete the transcript rows explicitly before the session so no
            # chat_messages content is left orphaned.
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            return True

    def ensure_chat_session(
        self,
        session_id: str,
        lens_id: str = DEFAULT_LENS_ID,
        *,
        context_hash: str = DEFAULT_CONTEXT_HASH,
        user_id: Optional[str] = None,
        persona_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        resolved = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id, persona_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved, self.DEFAULT_THREAD_TITLE, resolved_context, user_id, persona_id),
            )
            if user_id is not None:
                conn.execute(
                    """
                    UPDATE chat_sessions
                    SET user_id = COALESCE(user_id, ?)
                    WHERE id = ?
                    """,
                    (user_id, session_id),
                )
            conn.execute(
                """
                UPDATE chat_sessions
                SET lens_id = ?, updated_at = ?, context_hash = COALESCE(context_hash, ?)
                WHERE id = ?
                """,
                (resolved, now, resolved_context, session_id),
            )

    def save_chat_message(
        self,
        session_id: str,
        message_id: str,
        role: str,
        blocks: Iterable[Mapping[str, Any]],
        lens_id: str = DEFAULT_LENS_ID,
    ) -> None:
        now = time.time()
        resolved = lens_id or DEFAULT_LENS_ID
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, blocks_json, created_at, lens_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, json.dumps(list(blocks)), now, resolved),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ?, lens_id = ? WHERE id = ?",
                (now, resolved, session_id),
            )

    def chat_history(
        self,
        session_id: str,
        limit: int = 50,
        lens_id: Optional[str] = None,
    ) -> List[Mapping[str, Any]]:
        with self.connect() as conn:
            if lens_id:
                rows = conn.execute(
                    """
                    SELECT * FROM chat_messages
                    WHERE session_id = ? AND lens_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, lens_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            messages = []
            for row in reversed(rows):
                messages.append(
                    {
                        "id": row["id"],
                        "role": row["role"],
                        "blocks": json.loads(row["blocks_json"]),
                        "created_at": row["created_at"],
                        "lens_id": row["lens_id"] if "lens_id" in row.keys() else DEFAULT_LENS_ID,
                    }
                )
            return messages

