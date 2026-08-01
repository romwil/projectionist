"""Telemetry, pending actions, sync state, config, integrations.

Behavior-preserving split of the original ``projectionist.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``projectionist/library/db/__init__.py``.
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

from ._shared import (
    run_with_db_lock_retry,
)


class TelemetryConfigMixin:
    def insert_telemetry_event(
        self,
        *,
        event_id: str,
        event_class: str,
        payload_json: str,
        media_node_id: Optional[str] = None,
        associated_context_hash: Optional[str] = None,
    ) -> None:
        """Insert a single event into the telemetry stream table."""

        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO system_telemetry_stream
                        (id, event_class, payload_json, media_node_id, associated_context_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (event_id, event_class, payload_json, media_node_id, associated_context_hash),
                )

        self.run_write(_write, label="insert_telemetry_event")

    def telemetry_summary(self, *, hours: int = 24) -> Dict[str, Any]:
        """Return event counts grouped by event_class within the last *hours*."""
        cutoff = f"-{hours} hours"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_class, COUNT(*) AS count
                FROM system_telemetry_stream
                WHERE timestamp >= datetime('now', ?)
                GROUP BY event_class
                ORDER BY count DESC
                """,
                (cutoff,),
            ).fetchall()
        return {str(row["event_class"]): int(row["count"]) for row in rows}

    def telemetry_events(
        self,
        *,
        event_class: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return recent telemetry events, optionally filtered by class."""
        if event_class:
            rows = self._query(
                "SELECT * FROM system_telemetry_stream WHERE event_class = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (event_class, limit, offset),
            )
        else:
            rows = self._query(
                "SELECT * FROM system_telemetry_stream ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(row) for row in rows]

    def _query(self, sql: str, params=()) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    # --- Data retention / pruning ---

    def insert_llm_usage(
        self,
        *,
        usage_id: str,
        purpose: str,
        model: str = "",
        provider: str = "",
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        estimated_usd: Optional[float] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        meta_json: str = "{}",
        created_at: Optional[float] = None,
    ) -> None:
        """Insert one row into the ``llm_usage`` accounting table."""

        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO llm_usage (
                        id, created_at, purpose, model, provider,
                        prompt_tokens, completion_tokens, total_tokens,
                        latency_ms, estimated_usd, persona_id, session_id,
                        user_id, meta_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        usage_id,
                        float(created_at if created_at is not None else time.time()),
                        purpose,
                        model,
                        provider,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        latency_ms,
                        estimated_usd,
                        persona_id,
                        session_id,
                        user_id,
                        meta_json or "{}",
                    ),
                )

        self.run_write(_write, label="insert_llm_usage")

    def llm_usage_summary(
        self,
        *,
        days: int = 7,
        model: Optional[str] = None,
        purpose: Optional[str] = None,
        persona_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate LLM usage for the owner BI explorer."""
        days = max(1, min(int(days or 7), 90))
        cutoff = time.time() - (days * 86400)
        clauses = ["created_at >= ?"]
        params: List[Any] = [cutoff]
        if model:
            clauses.append("model = ?")
            params.append(model)
        if purpose:
            clauses.append("purpose = ?")
            params.append(purpose)
        if persona_id:
            clauses.append("persona_id = ?")
            params.append(persona_id)
        where = " AND ".join(clauses)

        with self.connect() as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS call_count,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(estimated_usd), 0) AS estimated_usd,
                    COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
                FROM llm_usage
                WHERE {where}
                """,
                params,
            ).fetchone()

            by_day = conn.execute(
                f"""
                SELECT date(created_at, 'unixepoch', 'localtime') AS day,
                       COUNT(*) AS call_count,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COALESCE(SUM(estimated_usd), 0) AS estimated_usd
                FROM llm_usage
                WHERE {where}
                GROUP BY day
                ORDER BY day ASC
                """,
                params,
            ).fetchall()

            by_model = conn.execute(
                f"""
                SELECT model, COUNT(*) AS call_count,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COALESCE(SUM(estimated_usd), 0) AS estimated_usd
                FROM llm_usage
                WHERE {where}
                GROUP BY model
                ORDER BY total_tokens DESC, call_count DESC
                LIMIT 40
                """,
                params,
            ).fetchall()

            by_purpose = conn.execute(
                f"""
                SELECT purpose, COUNT(*) AS call_count,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COALESCE(SUM(estimated_usd), 0) AS estimated_usd
                FROM llm_usage
                WHERE {where}
                GROUP BY purpose
                ORDER BY total_tokens DESC, call_count DESC
                """,
                params,
            ).fetchall()

            by_persona = conn.execute(
                f"""
                SELECT COALESCE(persona_id, '') AS persona_id,
                       COUNT(*) AS call_count,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COALESCE(SUM(estimated_usd), 0) AS estimated_usd
                FROM llm_usage
                WHERE {where}
                GROUP BY COALESCE(persona_id, '')
                ORDER BY total_tokens DESC, call_count DESC
                LIMIT 40
                """,
                params,
            ).fetchall()

            filter_models = [
                str(row["model"])
                for row in conn.execute(
                    "SELECT DISTINCT model FROM llm_usage WHERE created_at >= ? AND model != '' ORDER BY model",
                    (cutoff,),
                ).fetchall()
            ]
            filter_purposes = [
                str(row["purpose"])
                for row in conn.execute(
                    "SELECT DISTINCT purpose FROM llm_usage WHERE created_at >= ? ORDER BY purpose",
                    (cutoff,),
                ).fetchall()
            ]
            filter_personas = [
                str(row["persona_id"])
                for row in conn.execute(
                    """
                    SELECT DISTINCT persona_id FROM llm_usage
                    WHERE created_at >= ? AND persona_id IS NOT NULL AND persona_id != ''
                    ORDER BY persona_id
                    """,
                    (cutoff,),
                ).fetchall()
            ]

        def _rows(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
            return [dict(row) for row in rows]

        return {
            "days": days,
            "filters": {
                "model": model,
                "purpose": purpose,
                "persona_id": persona_id,
                "models": filter_models,
                "purposes": filter_purposes,
                "personas": filter_personas,
            },
            "totals": {
                "call_count": int(totals["call_count"] or 0),
                "prompt_tokens": int(totals["prompt_tokens"] or 0),
                "completion_tokens": int(totals["completion_tokens"] or 0),
                "total_tokens": int(totals["total_tokens"] or 0),
                "estimated_usd": float(totals["estimated_usd"] or 0),
                "avg_latency_ms": float(totals["avg_latency_ms"] or 0),
            },
            "by_day": _rows(by_day),
            "by_model": _rows(by_model),
            "by_purpose": _rows(by_purpose),
            "by_persona": _rows(by_persona),
        }

    def prune_llm_usage(self, retention_days: int) -> int:
        """Delete LLM usage rows older than *retention_days*. Returns rows deleted."""
        days = max(1, int(retention_days))
        cutoff = time.time() - (days * 86400)

        def _write() -> int:
            with self.connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM llm_usage WHERE created_at < ?",
                    (cutoff,),
                )
                return int(cursor.rowcount or 0)

        return int(self.run_write(_write, label="prune_llm_usage") or 0)

    def prune_telemetry(self, retention_days: int) -> int:
        """Delete telemetry events older than *retention_days*. Returns rows deleted."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM system_telemetry_stream WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def prune_interaction_telemetry(self, retention_days: int) -> int:
        """Delete interaction telemetry older than *retention_days*. Returns rows deleted."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM interaction_telemetry WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def prune_daily_anniversaries(self, retention_days: int) -> int:
        """Delete daily anniversary entries older than *retention_days*. Returns rows deleted.

        The ``daily_anniversaries`` table is created lazily by the anniversary
        scanner task, so this method tolerates its absence.
        """
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_anniversaries'"
            ).fetchone()
            if not exists:
                return 0
            cursor = conn.execute(
                "DELETE FROM daily_anniversaries WHERE scanned_date < date('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def vacuum(self) -> None:
        """Run VACUUM to reclaim space after large deletes.

        VACUUM cannot run inside a transaction, so we use a raw connection.
        """
        conn = self._open_connection()
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()

    def export_training_corpus(self) -> Dict[str, Any]:
        with self.connect() as conn:
            feedback_rows = conn.execute(
                "SELECT * FROM message_feedback ORDER BY created_at ASC"
            ).fetchall()
            fact_rows = conn.execute(
                "SELECT * FROM preference_facts ORDER BY created_at ASC"
            ).fetchall()
            review_rows = conn.execute(
                "SELECT * FROM user_title_reviews ORDER BY created_at ASC"
            ).fetchall()
        return {
            "exported_at": time.time(),
            "message_feedback": [dict(row) for row in feedback_rows],
            "preference_facts": [dict(row) for row in fact_rows],
            "user_title_reviews": [dict(row) for row in review_rows],
        }

    def save_pending_action(
        self,
        token: str,
        action_type: str,
        payload: Mapping[str, Any],
        ttl_seconds: int = 600,
        *,
        user_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_actions
                    (token, action_type, payload_json, created_at, expires_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, action_type, json.dumps(dict(payload)), now, now + ttl_seconds, user_id),
            )

    def pop_pending_action(
        self,
        token: str,
        *,
        user_id: Optional[str] = None,
    ) -> Optional[Mapping[str, Any]]:
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT * FROM pending_actions WHERE token = ? AND expires_at > ?",
                    (token, now),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM pending_actions
                    WHERE token = ? AND expires_at > ?
                      AND (user_id IS NULL OR user_id = ?)
                    """,
                    (token, now, user_id),
                ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM pending_actions WHERE token = ?", (token,))
            return json.loads(row["payload_json"])

    def set_sync_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, time.time()),
            )

    def get_sync_state(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

    # --- System config ---

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT config_value FROM curator_system_config WHERE config_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return default
            return str(row["config_value"])

    def set_config(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curator_system_config (config_key, config_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_value=excluded.config_value,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def get_all_config(self) -> Dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT config_key, config_value FROM curator_system_config ORDER BY config_key"
            ).fetchall()
            return {str(r["config_key"]): str(r["config_value"]) for r in rows}

    def sync_llm_config(
        self,
        *,
        llm_provider: str,
        llm_base_url: str,
        llm_model: str,
    ) -> None:
        self.set_config("llm_provider", llm_provider)
        self.set_config("llm_base_url", llm_base_url)
        self.set_config("llm_model", llm_model)

    # --- Service integrations ---

    def upsert_service_integration(
        self,
        service_name: str,
        *,
        base_url: str = "",
        credential_marker: str = "",
        api_token_encrypted: str = "",
        connection_status: str = "unverified",
        last_tested_at: Optional[str] = None,
        certified: Optional[int] = None,
    ) -> None:
        """Upsert a service integration row.

        ``credential_marker`` is the honest name (presence marker only — not ciphertext).
        ``api_token_encrypted`` remains accepted as a deprecated alias.
        """
        marker = str(credential_marker or api_token_encrypted or "").strip()
        tested_at = last_tested_at or time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        certified_value = 0 if certified is None else int(bool(certified))
        with self.connect() as conn:
            cols = self._table_columns(conn, "service_integrations")
            col = "credential_marker" if "credential_marker" in cols else "api_token_encrypted"
            conn.execute(
                f"""
                INSERT INTO service_integrations (
                    service_name, base_url, {col}, connection_status,
                    last_tested_at, certified
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_name) DO UPDATE SET
                    base_url=excluded.base_url,
                    {col}=excluded.{col},
                    connection_status=excluded.connection_status,
                    last_tested_at=excluded.last_tested_at,
                    certified=excluded.certified
                """,
                (
                    service_name,
                    base_url,
                    marker,
                    connection_status,
                    tested_at,
                    certified_value,
                ),
            )

    def invalidate_service_certification(self, service_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE service_integrations
                SET certified = 0, connection_status = 'unverified'
                WHERE service_name = ?
                """,
                (service_name,),
            )

    def get_service_integration(self, service_name: str) -> Optional[sqlite3.Row]:
        def _read() -> Optional[sqlite3.Row]:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT * FROM service_integrations WHERE service_name = ?",
                    (service_name,),
                ).fetchone()

        return run_with_db_lock_retry(_read, label="get_service_integration")

    def get_service_integrations(self) -> List[sqlite3.Row]:
        def _read() -> List[sqlite3.Row]:
            with self.connect() as conn:
                return list(
                    conn.execute(
                        "SELECT * FROM service_integrations ORDER BY service_name ASC"
                    ).fetchall()
                )

        return run_with_db_lock_retry(_read, label="get_service_integrations")

