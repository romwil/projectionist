"""Grooming action log, snapshots/undo, weekly digest, purge.

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
    Optional,
)

from ._shared import (
    run_with_db_lock_retry,
)


class GroomingDigestMixin:
    def delete_library_items_by_rating_keys(self, rating_keys: List[str]) -> int:
        """Delete library items (and related episodes/embeddings) by rating_key list."""
        if not rating_keys:
            return 0
        keys = [str(k) for k in rating_keys if str(k).strip()]
        if not keys:
            return 0

        def _write() -> int:
            with self.connect() as conn:
                placeholders = ", ".join("?" for _ in keys)
                item_ids = [
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM library_items WHERE rating_key IN ({placeholders})",
                        keys,
                    ).fetchall()
                ]
                if not item_ids:
                    return 0
                id_ph = ", ".join("?" for _ in item_ids)
                conn.execute(
                    f"DELETE FROM library_episodes WHERE show_item_id IN ({id_ph})",
                    item_ids,
                )
                conn.execute(
                    f"DELETE FROM embeddings WHERE item_id IN ({id_ph})",
                    item_ids,
                )
                cursor = conn.execute(
                    f"DELETE FROM library_items WHERE id IN ({id_ph})",
                    item_ids,
                )
                return int(cursor.rowcount)

        return run_with_db_lock_retry(_write, label="delete_library_items")

    def snapshot_library_items_by_rating_keys(
        self, rating_keys: List[str]
    ) -> Dict[str, Any]:
        """Capture full ``library_items`` (+ episodes) rows so a delete is reversible.

        Embeddings are intentionally NOT captured — they are large, derived
        vectors that idle enrichment regenerates. The snapshot restores the index
        rows the owner sees; embeddings backfill on the next enrichment cycle.
        """
        keys = [str(k) for k in rating_keys if str(k).strip()]
        if not keys:
            return {"items": [], "episodes": []}
        with self.connect() as conn:
            placeholders = ", ".join("?" for _ in keys)
            item_rows = conn.execute(
                f"SELECT * FROM library_items WHERE rating_key IN ({placeholders})",
                keys,
            ).fetchall()
            items = [dict(row) for row in item_rows]
            item_ids = [int(row["id"]) for row in item_rows]
            episodes: List[Dict[str, Any]] = []
            if item_ids:
                id_ph = ", ".join("?" for _ in item_ids)
                episode_rows = conn.execute(
                    f"SELECT * FROM library_episodes WHERE show_item_id IN ({id_ph})",
                    item_ids,
                ).fetchall()
                episodes = [dict(row) for row in episode_rows]
        return {"items": items, "episodes": episodes}

    def restore_library_items_snapshot(self, snapshot: Dict[str, Any]) -> int:
        """Re-insert previously-deleted ``library_items`` (+ episodes) rows.

        Idempotent per row: rows whose id already exists are skipped. Returns the
        number of library items restored.
        """
        items = list((snapshot or {}).get("items") or [])
        episodes = list((snapshot or {}).get("episodes") or [])
        if not items:
            return 0

        def _write() -> int:
            restored = 0
            with self.connect() as conn:
                item_cols = self._table_columns(conn, "library_items")
                episode_cols = self._table_columns(conn, "library_episodes")
                existing_ids = {
                    int(row["id"])
                    for row in conn.execute("SELECT id FROM library_items").fetchall()
                }
                restored_ids: set[int] = set()
                for row in items:
                    row_id = row.get("id")
                    if row_id is not None and int(row_id) in existing_ids:
                        continue
                    cols = [c for c in row.keys() if c in item_cols]
                    if not cols:
                        continue
                    placeholders = ", ".join("?" for _ in cols)
                    col_sql = ", ".join(cols)
                    conn.execute(
                        f"INSERT OR IGNORE INTO library_items ({col_sql}) VALUES ({placeholders})",
                        [row.get(c) for c in cols],
                    )
                    if row_id is not None:
                        restored_ids.add(int(row_id))
                    restored += 1
                for row in episodes:
                    show_id = row.get("show_item_id")
                    if show_id is None or int(show_id) not in restored_ids:
                        continue
                    cols = [c for c in row.keys() if c in episode_cols]
                    if not cols:
                        continue
                    placeholders = ", ".join("?" for _ in cols)
                    col_sql = ", ".join(cols)
                    conn.execute(
                        f"INSERT OR IGNORE INTO library_episodes ({col_sql}) VALUES ({placeholders})",
                        [row.get(c) for c in cols],
                    )
            return restored

        return run_with_db_lock_retry(_write, label="restore_library_items")

    def record_grooming_action(
        self,
        *,
        action_id: str,
        action_type: str,
        actor_user_id: Optional[str],
        summary: str,
        item_count: int,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist a reversible grooming action with its restore snapshot."""
        now = time.time()
        payload = json.dumps(snapshot or {}, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO grooming_action_log (
                    id, action_type, actor_user_id, summary, item_count,
                    snapshot_json, created_at, undone_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    action_id,
                    str(action_type),
                    actor_user_id,
                    str(summary or "")[:500],
                    int(item_count),
                    payload,
                    now,
                ),
            )
        got = self.get_grooming_action(action_id)
        assert got is not None
        return got

    @staticmethod
    def _row_to_grooming_action(
        row: sqlite3.Row, *, include_snapshot: bool = False
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": str(row["id"]),
            "action_type": str(row["action_type"]),
            "actor_user_id": str(row["actor_user_id"]) if row["actor_user_id"] is not None else None,
            "summary": str(row["summary"] or ""),
            "item_count": int(row["item_count"] or 0),
            "created_at": float(row["created_at"]),
            "undone_at": float(row["undone_at"]) if row["undone_at"] is not None else None,
            "reversible": row["undone_at"] is None and int(row["item_count"] or 0) > 0,
        }
        if include_snapshot:
            try:
                payload["snapshot"] = json.loads(str(row["snapshot_json"] or "{}"))
            except (TypeError, json.JSONDecodeError):
                payload["snapshot"] = {}
        return payload

    def get_grooming_action(
        self, action_id: str, *, include_snapshot: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM grooming_action_log WHERE id = ?",
                (action_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_grooming_action(row, include_snapshot=include_snapshot)

    def list_grooming_actions(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        capped = max(1, min(int(limit or 20), 100))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM grooming_action_log ORDER BY created_at DESC LIMIT ?",
                (capped,),
            ).fetchall()
        return [self._row_to_grooming_action(row) for row in rows]

    def undo_grooming_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Restore a recorded grooming action's snapshot and mark it undone.

        Returns the updated action dict with a ``restored`` count, or ``None`` if
        the action does not exist. Raises ``ValueError`` if already undone.
        """
        action = self.get_grooming_action(action_id, include_snapshot=True)
        if action is None:
            return None
        if action.get("undone_at") is not None:
            raise ValueError("This grooming action has already been undone")
        restored = self.restore_library_items_snapshot(action.get("snapshot") or {})
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                "UPDATE grooming_action_log SET undone_at = ? WHERE id = ?",
                (now, action_id),
            )
        updated = self.get_grooming_action(action_id)
        assert updated is not None
        updated["restored"] = restored
        return updated

    def save_weekly_digest(
        self, *, digest_id: str, week_start: float, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert a weekly digest snapshot keyed by week_start."""
        now = time.time()
        body = json.dumps(payload or {}, separators=(",", ":"))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO weekly_digests (id, week_start, generated_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(week_start) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    payload_json = excluded.payload_json
                """,
                (digest_id, float(week_start), now, body),
            )
        got = self.get_latest_weekly_digest()
        assert got is not None
        return got

    @staticmethod
    def _row_to_weekly_digest(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        return {
            "id": str(row["id"]),
            "week_start": float(row["week_start"]),
            "generated_at": float(row["generated_at"]),
            "payload": payload if isinstance(payload, dict) else {},
        }

    def get_latest_weekly_digest(self) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM weekly_digests ORDER BY week_start DESC LIMIT 1"
            ).fetchone()
        return self._row_to_weekly_digest(row) if row else None

    def list_weekly_digests(self, *, limit: int = 8) -> List[Dict[str, Any]]:
        capped = max(1, min(int(limit or 8), 52))
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM weekly_digests ORDER BY week_start DESC LIMIT ?",
                (capped,),
            ).fetchall()
        return [self._row_to_weekly_digest(row) for row in rows]

    def dismiss_purge_candidates(self, rating_keys: List[str]) -> int:
        """Mark rating_keys as dismissed so they won't appear as purge candidates."""
        if not rating_keys:
            return 0
        keys = [str(k) for k in rating_keys if str(k).strip()]
        if not keys:
            return 0
        now = time.time()

        def _write() -> int:
            with self.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO purge_dismissals (rating_key, dismissed_at)
                    VALUES (?, ?)
                    ON CONFLICT(rating_key) DO UPDATE SET dismissed_at = excluded.dismissed_at
                    """,
                    [(k, now) for k in keys],
                )
                return len(keys)

        return run_with_db_lock_retry(_write, label="dismiss_purge_candidates")

    def dismissed_purge_keys(self) -> set:
        """Return set of rating_keys that have been dismissed from purge."""
        with self.connect() as conn:
            try:
                rows = conn.execute("SELECT rating_key FROM purge_dismissals").fetchall()
                return {str(row["rating_key"]) for row in rows}
            except Exception:
                return set()

