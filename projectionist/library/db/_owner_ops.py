"""Owner operations: security audit trail, stewardship checklist marks, local event counts.

Everything here stays on the box. Rows hold ids, event names, and field names —
never secret values or message text.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

# Oldest audit rows drop past this cap so a noisy sign-in loop cannot grow the file.
SECURITY_AUDIT_MAX_ROWS = 20_000


class OwnerOpsMixin:
    # --- Security audit (SEC-012) ---

    def record_security_event(
        self,
        event: str,
        *,
        actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        outcome: str = "ok",
        detail: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> int:
        payload = json.dumps(detail or {}, default=str, separators=(",", ":"), sort_keys=True)
        created_at = time.time() if now is None else float(now)

        def _write() -> int:
            with self.connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO security_audit_log
                        (created_at, event, actor_id, target_id, outcome, detail_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created_at,
                        str(event),
                        str(actor_id) if actor_id else None,
                        str(target_id) if target_id else None,
                        str(outcome or "ok"),
                        payload,
                    ),
                )
                row_id = int(cur.lastrowid or 0)
                conn.execute(
                    """
                    DELETE FROM security_audit_log WHERE id IN (
                        SELECT id FROM security_audit_log
                        ORDER BY id DESC LIMIT -1 OFFSET ?
                    )
                    """,
                    (SECURITY_AUDIT_MAX_ROWS,),
                )
                return row_id

        return self.run_write(_write, label="record_security_event")

    def owner_actions_on_user(self, user_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        """Audit rows where someone else acted on ``user_id`` (PRIV-023 owner-access log)."""
        from projectionist.security_audit import OWNER_ACCESS_LABELS

        events = list(OWNER_ACCESS_LABELS)
        marks = ", ".join("?" for _ in events)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT a.created_at, a.event, a.outcome, a.detail_json, u.display_name AS actor_name
                FROM security_audit_log a
                LEFT JOIN users u ON u.id = a.actor_id
                WHERE a.target_id = ? AND a.actor_id IS NOT NULL AND a.actor_id != ?
                  AND a.event IN ({marks})
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT ?
                """,
                (user_id, user_id, *events, int(limit)),
            ).fetchall()
        items = []
        for row in rows:
            try:
                detail = json.loads(row["detail_json"] or "{}")
            except (TypeError, ValueError):
                detail = {}
            items.append(
                {
                    "created_at": float(row["created_at"]),
                    "event": row["event"],
                    "label": OWNER_ACCESS_LABELS.get(str(row["event"]), str(row["event"])),
                    "outcome": row["outcome"],
                    "actor_name": row["actor_name"] or "The owner",
                    "detail": detail if isinstance(detail, dict) else {},
                }
            )
        return items

    def list_security_events(
        self,
        *,
        event: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        clauses: List[str] = []
        params: List[Any] = []
        if event:
            clauses.append("event = ?")
            params.append(event)
        if user_id:
            clauses.append("(actor_id = ? OR target_id = ?)")
            params.extend([user_id, user_id])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM security_audit_log {where}", params
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT id, created_at, event, actor_id, target_id, outcome, detail_json
                FROM security_audit_log {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, int(limit), int(offset)],
            ).fetchall()
            event_rows = conn.execute(
                "SELECT DISTINCT event FROM security_audit_log ORDER BY event ASC"
            ).fetchall()
        items = []
        for row in rows:
            try:
                detail = json.loads(row["detail_json"] or "{}")
            except (TypeError, ValueError):
                detail = {}
            items.append(
                {
                    "id": int(row["id"]),
                    "created_at": float(row["created_at"]),
                    "event": str(row["event"]),
                    "actor_id": row["actor_id"],
                    "target_id": row["target_id"],
                    "outcome": str(row["outcome"]),
                    "detail": detail if isinstance(detail, dict) else {},
                }
            )
        return {
            "items": items,
            "total": int(total_row["c"] if total_row else 0),
            "events": [str(r["event"]) for r in event_rows],
        }

    # --- Stewardship checklist marks (OPS-030 / UX-036) ---

    def set_checklist_mark(
        self,
        scope: str,
        item_id: str,
        status: str,
        *,
        period: str = "",
        user_id: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Dict[str, Any]:
        updated_at = time.time() if now is None else float(now)

        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO owner_checklist_marks
                        (scope, item_id, period, status, updated_at, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scope, item_id, period) DO UPDATE SET
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (scope, item_id, period, status, updated_at, user_id),
                )

        self.run_write(_write, label="set_checklist_mark")
        return {
            "scope": scope,
            "item_id": item_id,
            "period": period,
            "status": status,
            "updated_at": updated_at,
            "updated_by": user_id,
        }

    def clear_checklist_mark(self, scope: str, item_id: str, *, period: str = "") -> None:
        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    "DELETE FROM owner_checklist_marks WHERE scope = ? AND item_id = ? AND period = ?",
                    (scope, item_id, period),
                )

        self.run_write(_write, label="clear_checklist_mark")

    def list_checklist_marks(self, scope: str, *, period: str = "") -> Dict[str, Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT item_id, status, updated_at, updated_by
                FROM owner_checklist_marks WHERE scope = ? AND period = ?
                """,
                (scope, period),
            ).fetchall()
        return {
            str(row["item_id"]): {
                "status": str(row["status"]),
                "updated_at": float(row["updated_at"]),
                "updated_by": row["updated_by"],
            }
            for row in rows
        }

    def last_checklist_mark(self, scope: str, item_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT period, status, updated_at, updated_by
                FROM owner_checklist_marks WHERE scope = ? AND item_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (scope, item_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "period": str(row["period"]),
            "status": str(row["status"]),
            "updated_at": float(row["updated_at"]),
            "updated_by": row["updated_by"],
        }

    # --- Local event spine counts (GRO-007 / GRO-014) ---

    def local_event_counts(self, *, days: int = 7) -> Dict[str, int]:
        from projectionist.telemetry.likely_picks import likely_pick_watch_count

        cutoff = f"-{int(days)} days"
        with self.connect() as conn:
            chat_row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM system_telemetry_stream
                WHERE event_class = 'chat_turn' AND timestamp >= datetime('now', ?)
                """,
                (cutoff,),
            ).fetchone()
            play_rows = conn.execute(
                """
                SELECT payload_json FROM system_telemetry_stream
                WHERE event_class = 'play_start' AND timestamp >= datetime('now', ?)
                """,
                (cutoff,),
            ).fetchall()
        attributed = 0
        for row in play_rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("rec_id"):
                attributed += 1
        return {
            "chat_turns": int(chat_row["c"] if chat_row else 0),
            "plays": len(play_rows),
            "plays_from_picks": attributed,
            "plays_likely_from_picks": likely_pick_watch_count(self, days=days),
        }
