"""Preferences, user memory notes, and repository (entity) memory.

Behavior-preserving split of the original ``projectionist.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``projectionist/library/db/__init__.py``.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
)

from projectionist.privacy import erasures, registry

from ._shared import (
    logger,
)

# Interaction-stream rows carry the account in their metadata payload, not a column.
_STREAM_USER_MATCH = "json_extract(payload_json, '$.user_id') = ?"

# Export sections shaped by hand below; every other registry store is exported raw.
_SHAPED_EXPORT_TABLES = (
    "chat_sessions",
    "chat_messages",
    "saved_library_pages",
    "preference_facts",
    "watch_events",
    "watch_sessions",
    "watch_completions",
    "system_telemetry_stream",
)

_PURGE_COUNT_KEYS = {
    "notes_deleted": "user_memory_notes",
    "chat_sessions_deleted": "chat_sessions",
    "chat_messages_deleted": "chat_messages",
    "saved_library_pages_deleted": "saved_library_pages",
    "preference_facts_deleted": "preference_facts",
    "watch_events_deleted": "watch_events",
    "watch_sessions_deleted": "watch_sessions",
    "watch_completions_deleted": "watch_completions",
    "watch_source_identities_deleted": "watch_source_identities",
    "interaction_events_deleted": "system_telemetry_stream",
}


class MemoryMixin:
    def add_preference(self, signal_type: str, text: str, **kwargs: Any) -> None:
        user_id = kwargs.get("user_id")
        if user_id:
            self.add_user_memory_note(
                str(user_id),
                kind="preference",
                text=text,
                metadata={
                    "signal_type": signal_type,
                    "weight": kwargs.get("weight", 1.0),
                    "tmdb_id": kwargs.get("tmdb_id"),
                    "tvdb_id": kwargs.get("tvdb_id"),
                    "media_type": kwargs.get("media_type"),
                },
            )
            # Keep the legacy row during the compatibility window.  New agent
            # reads use user_memory_notes; this preserves existing integrations
            # and rollback-safe historical queries until preference_facts retires.
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preference_facts
                    (signal_type, text, weight, tmdb_id, tvdb_id, media_type, created_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_type,
                    text,
                    kwargs.get("weight", 1.0),
                    kwargs.get("tmdb_id"),
                    kwargs.get("tvdb_id"),
                    kwargs.get("media_type"),
                    time.time(),
                    kwargs.get("user_id"),
                ),
            )

    def preference_facts(self, limit: int = 50, *, user_id: Optional[str] = None) -> List[sqlite3.Row]:
        with self.connect() as conn:
            if user_id is None:
                return list(
                    conn.execute(
                        "SELECT * FROM preference_facts ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                )
            return list(
                conn.execute(
                    """
                    SELECT * FROM preference_facts
                    WHERE user_id = ? OR user_id IS NULL
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )

    # --- Curator memory (v1.8.29) ---

    def set_user_youth(self, user_id: str, is_youth: bool) -> Dict[str, Any]:
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise ValueError("User not found")
            conn.execute("UPDATE users SET is_youth = ? WHERE id = ?", (int(is_youth), user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def add_user_memory_note(
        self, user_id: str, *, kind: str, text: str, metadata: Optional[Mapping[str, Any]] = None
    ) -> Dict[str, Any]:
        cleaned = str(text or "").strip()
        if not cleaned:
            raise ValueError("Memory text is required")
        now = time.time()
        note_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO user_memory_notes
                   (id, user_id, kind, text, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (note_id, user_id, str(kind or "note")[:64], cleaned[:4000],
                 json.dumps(dict(metadata or {})), now, now),
            )
            conn.execute(
                """INSERT INTO user_memory_events (id, user_id, event_type, target_id, created_at)
                   VALUES (?, ?, 'remember', ?, ?)""",
                (uuid.uuid4().hex, user_id, note_id, now),
            )
        return self.get_user_memory_note(note_id, user_id=user_id) or {}

    def get_user_memory_note(self, note_id: str, *, user_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM user_memory_notes
                   WHERE id = ? AND user_id = ? AND archived_at IS NULL""", (note_id, user_id)
            ).fetchone()
        return self._memory_note_dict(row) if row else None

    def list_user_memory_notes(self, user_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM user_memory_notes WHERE user_id = ? AND archived_at IS NULL
                   ORDER BY updated_at DESC LIMIT ?""", (user_id, min(max(limit, 1), 500))
            ).fetchall()
        return [self._memory_note_dict(row) for row in rows]

    def update_user_memory_note(
        self, user_id: str, note_id: str, *, text: str, kind: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        cleaned = str(text or "").strip()
        if not cleaned:
            raise ValueError("Memory text is required")
        now = time.time()
        with self.connect() as conn:
            if kind:
                conn.execute(
                    """UPDATE user_memory_notes SET text = ?, kind = ?, updated_at = ?
                       WHERE id = ? AND user_id = ? AND archived_at IS NULL""",
                    (cleaned[:4000], kind[:64], now, note_id, user_id),
                )
            else:
                conn.execute(
                    """UPDATE user_memory_notes SET text = ?, updated_at = ?
                       WHERE id = ? AND user_id = ? AND archived_at IS NULL""",
                    (cleaned[:4000], now, note_id, user_id),
                )
            if not conn.execute("SELECT 1 FROM user_memory_notes WHERE id = ? AND user_id = ?", (note_id, user_id)).fetchone():
                return None
            conn.execute(
                "INSERT INTO user_memory_events (id, user_id, event_type, target_id, created_at) VALUES (?, ?, 'update', ?, ?)",
                (uuid.uuid4().hex, user_id, note_id, now),
            )
        return self.get_user_memory_note(note_id, user_id=user_id)

    def delete_user_memory_note(self, note_id: str, *, user_id: str) -> bool:
        """Hard-delete one of the caller's notes (not archive)."""
        with self.connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            cur = conn.execute(
                "DELETE FROM user_memory_notes WHERE id = ? AND user_id = ?", (note_id, user_id)
            )
            if cur.rowcount:
                conn.execute(
                    "INSERT INTO user_memory_events (id, user_id, event_type, target_id, created_at) "
                    "VALUES (?, ?, 'delete', ?, ?)",
                    (uuid.uuid4().hex, user_id, note_id, time.time()),
                )
        return bool(cur.rowcount)

    def export_user_memory(self, user_id: str) -> Dict[str, Any]:
        """Everything this account owns, per the personal-data registry.

        Chats, saved pages, preference facts, watch evidence, and activity counts
        are shaped for reading; every other ``export=True`` registry store is in
        ``stores`` as rows (secrets such as password hashes and tokens removed).
        Only rows matching ``user_id`` are read.
        """
        notes = self.list_user_memory_notes(user_id, limit=500)
        now = time.time()
        with self.connect() as conn:
            session_rows = conn.execute(
                "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            ).fetchall()
            chat_threads: List[Dict[str, Any]] = []
            for session in session_rows:
                keys = session.keys()
                message_rows = conn.execute(
                    """SELECT id, role, blocks_json, created_at, lens_id
                       FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC""",
                    (session["id"],),
                ).fetchall()
                messages = [
                    {
                        "id": str(m["id"]),
                        "role": str(m["role"]),
                        "created_at": float(m["created_at"]),
                        "lens_id": m["lens_id"],
                        "blocks": json.loads(m["blocks_json"]) if m["blocks_json"] else None,
                    }
                    for m in message_rows
                ]
                chat_threads.append(
                    {
                        "id": str(session["id"]),
                        "thread_title": session["thread_title"],
                        "lens_id": session["lens_id"],
                        "context_hash": session["context_hash"],
                        "persona_id": session["persona_id"] if "persona_id" in keys else None,
                        "created_at": float(session["created_at"]),
                        "updated_at": float(session["updated_at"]),
                        "messages": messages,
                    }
                )

            saved_rows = conn.execute(
                "SELECT * FROM saved_library_pages WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            ).fetchall()
            saved_library_pages = [self._row_to_saved_library_page(row) for row in saved_rows]

            preference_facts: List[Dict[str, Any]] = []
            if "user_id" in self._table_columns(conn, "preference_facts"):
                pref_rows = conn.execute(
                    """SELECT id, signal_type, text, weight, tmdb_id, tvdb_id, media_type, created_at
                       FROM preference_facts WHERE user_id = ? ORDER BY created_at ASC""",
                    (user_id,),
                ).fetchall()
                preference_facts = [dict(row) for row in pref_rows]

            watch_events = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, source, source_event_kind, rating_key,
                           parent_rating_key, media_type, occurred_at_ms,
                           progress_ms, duration_ms, completion_pct, terminal, manual
                    FROM watch_events
                    WHERE user_id = ?
                    ORDER BY occurred_at_ms ASC, id ASC
                    """,
                    (user_id,),
                ).fetchall()
            ]
            watch_sessions = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, rating_key, parent_rating_key, media_type,
                           started_at_ms, ended_at_ms, start_progress_ms,
                           max_progress_ms, duration_ms, client_count, event_count,
                           terminal_reason, algorithm_version
                    FROM watch_sessions
                    WHERE user_id = ?
                    ORDER BY started_at_ms ASC, id ASC
                    """,
                    (user_id,),
                ).fetchall()
            ]
            watch_completions = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT id, session_id, rating_key, parent_rating_key, media_type,
                           completed_at_ms, confidence, basis, threshold_pct,
                           superseded_by_completion_id, algorithm_version
                    FROM watch_completions
                    WHERE user_id = ?
                    ORDER BY completed_at_ms ASC, id ASC
                    """,
                    (user_id,),
                ).fetchall()
            ]

            interaction_events = [
                {
                    "id": str(row["id"]),
                    "event_class": str(row["event_class"]),
                    "timestamp": row["timestamp"],
                    "payload": json.loads(row["payload_json"] or "{}"),
                }
                for row in conn.execute(
                    f"SELECT id, event_class, timestamp, payload_json FROM system_telemetry_stream "
                    f"WHERE {_STREAM_USER_MATCH} ORDER BY timestamp ASC",
                    (user_id,),
                ).fetchall()
            ]

            stores = registry.export_rows(conn, user_id, skip_tables=_SHAPED_EXPORT_TABLES)
            conn.execute(
                "INSERT INTO user_memory_events (id, user_id, event_type, created_at) VALUES (?, ?, 'export', ?)",
                (uuid.uuid4().hex, user_id, now),
            )
        return {
            "format_version": 2,
            "user_id": user_id,
            "exported_at": now,
            "stores": stores,
            "notes": notes,
            "chat_threads": chat_threads,
            "saved_library_pages": saved_library_pages,
            "preference_facts": preference_facts,
            "watch_tracker": {
                "events": watch_events,
                "sessions": watch_sessions,
                "completions": watch_completions,
            },
            "interaction_events": interaction_events,
        }

    def _erase_account_rows(
        self, user_id: str, *, groups: tuple = registry.ERASE_ALL, account: bool = False
    ) -> Dict[str, int]:
        """One write transaction over the registry, then scrub freed pages.

        ``secure_delete`` zeroes freed content on this connection, and the WAL
        checkpoint afterwards truncates the log, so deleted chat text is not left
        readable in the database file or its WAL. The erasure is then recorded
        in the ledger so a backup restore re-applies it.
        """
        now = time.time()
        with self.connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute("BEGIN IMMEDIATE")
            if account and conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise ValueError("User not found")
            counts = registry.erase_user(conn, user_id, groups=groups, account=account)
            if not account:
                conn.execute(
                    "INSERT INTO user_memory_events (id, user_id, event_type, created_at) "
                    "VALUES (?, ?, 'purge', ?)",
                    (uuid.uuid4().hex, user_id, now),
                )
        try:
            with self.connect() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            logger.warning("WAL checkpoint after erasure did not complete", exc_info=True)
        erasures.record_erasure(
            self._erasure_ledger_dir(),
            user_id,
            kind=erasures.KIND_ACCOUNT if account else erasures.KIND_DATA,
            groups=() if account else groups,
            at=now,
        )
        return counts

    def _erasure_ledger_dir(self):
        from pathlib import Path

        return Path(str(self.path)).resolve().parent

    def purge_user_memory_and_chats(self, user_id: str) -> Dict[str, int]:
        """Delete private memory, chats, saved pages, preference facts, Plex
        viewing evidence, and activity counts (the registry's ``memory`` group).

        Foreign keys are on, but every store is deleted explicitly (children
        before parents) so tables without a foreign key are not left orphaned.
        """
        counts = self._erase_account_rows(user_id, groups=registry.ERASE_MEMORY)
        return {key: int(counts.get(table, 0)) for key, table in _PURGE_COUNT_KEYS.items()}

    def erase_user_data(self, user_id: str) -> Dict[str, int]:
        """Delete my data: every registry store in ``memory`` and ``activity``.

        The account row, sign-in, and notification settings stay so the member
        can keep using the app. Returns rows removed per table.
        """
        return self._erase_account_rows(user_id, groups=registry.ERASE_ALL)

    def save_repository_research(
        self, *, entity_type: str, name: str, payload: Mapping[str, Any],
        external_ids: Optional[Mapping[str, Any]] = None, library_item_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Append a sanitized research snapshot; repository history is never overwritten."""
        now = time.time()
        entity_id = uuid.uuid4().hex
        entity_type = entity_type if entity_type in {"person", "company", "title", "location", "other"} else "other"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM memory_entities WHERE entity_type = ? AND name = ?",
                (entity_type, str(name).strip()),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO memory_entities
                       (id, entity_type, name, external_ids_json, library_item_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (entity_id, entity_type, str(name).strip(), json.dumps(dict(external_ids or {})),
                     library_item_id, now, now),
                )
            else:
                entity_id = str(row["id"])
                conn.execute("UPDATE memory_entities SET updated_at = ? WHERE id = ?", (now, entity_id))
            snapshot_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO memory_snapshots (id, entity_id, payload_json, sources_json, fetched_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (snapshot_id, entity_id, json.dumps(dict(payload)),
                 json.dumps(dict(payload).get("sources_checked", {})), now, now),
            )
        return {"entity_id": entity_id, "snapshot_id": snapshot_id, "freshness": now}

    def repository_entities_due_for_enrichment(
        self, *, older_than_seconds: float, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Return public entities whose newest research snapshot has gone stale."""
        cutoff = time.time() - older_than_seconds
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.entity_type, e.name, e.external_ids_json, MAX(s.fetched_at) AS last_fetched_at
                FROM memory_entities e
                JOIN memory_snapshots s ON s.entity_id = e.id
                WHERE e.archived_at IS NULL
                GROUP BY e.id
                HAVING MAX(s.fetched_at) < ?
                ORDER BY MAX(s.fetched_at) ASC
                LIMIT ?
                """,
                (cutoff, max(1, min(int(limit), 50))),
            ).fetchall()
        entities: List[Dict[str, Any]] = []
        for row in rows:
            try:
                external_ids = json.loads(row["external_ids_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                external_ids = {}
            entities.append(
                {
                    "id": str(row["id"]),
                    "entity_type": str(row["entity_type"]),
                    "name": str(row["name"]),
                    "external_ids": external_ids if isinstance(external_ids, dict) else {},
                    "last_fetched_at": float(row["last_fetched_at"]),
                }
            )
        return entities

    @staticmethod
    def _normalize_insight_citations(citations: Any) -> List[Dict[str, Any]]:
        """Coerce agent-supplied citations into safe {source, ref, note} records."""
        normalized: List[Dict[str, Any]] = []
        if not isinstance(citations, (list, tuple)):
            return normalized
        for entry in citations:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    normalized.append({"source": text[:200], "ref": "", "note": ""})
                continue
            if not isinstance(entry, Mapping):
                continue
            source = str(entry.get("source") or entry.get("provider") or "").strip()
            ref = str(entry.get("ref") or entry.get("url") or entry.get("reference") or "").strip()
            note = str(entry.get("note") or "").strip()
            if not (source or ref or note):
                continue
            normalized.append({"source": source[:200], "ref": ref[:500], "note": note[:500]})
        return normalized

    def _resolve_memory_entity_row(
        self, conn: sqlite3.Connection, name: str, entity_type: Optional[str] = None
    ) -> Optional[sqlite3.Row]:
        cleaned = str(name or "").strip()
        if not cleaned:
            return None
        if entity_type:
            row = conn.execute(
                "SELECT * FROM memory_entities WHERE entity_type = ? AND name = ? COLLATE NOCASE "
                "AND archived_at IS NULL ORDER BY updated_at DESC LIMIT 1",
                (str(entity_type), cleaned),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM memory_entities WHERE name = ? COLLATE NOCASE "
                "AND archived_at IS NULL ORDER BY updated_at DESC LIMIT 1",
                (cleaned,),
            ).fetchone()
        return row

    def get_repository_entity(
        self, name: str, entity_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Return the latest research snapshot, freshness, insights, and activity for an entity.

        Only provider-normalized, path-free research payloads are ever stored, so the
        returned snapshot mirrors the same sanitization the research tools apply at write time.
        Returns ``None`` when nothing is known about the entity yet.
        """
        with self.connect() as conn:
            row = self._resolve_memory_entity_row(conn, name, entity_type)
            if row is None:
                return None
            entity_id = str(row["id"])
            snapshot = conn.execute(
                "SELECT payload_json, sources_json, fetched_at FROM memory_snapshots "
                "WHERE entity_id = ? ORDER BY fetched_at DESC LIMIT 1",
                (entity_id,),
            ).fetchone()
            activity = conn.execute(
                "SELECT discussion_count, last_discussed_at FROM memory_entity_activity WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            insight_rows = conn.execute(
                "SELECT id, insight, citations_json, created_at FROM memory_insights "
                "WHERE entity_id = ? AND archived_at IS NULL ORDER BY created_at DESC",
                (entity_id,),
            ).fetchall()
        payload: Dict[str, Any] = {}
        fetched_at: Optional[float] = None
        if snapshot is not None:
            try:
                loaded = json.loads(snapshot["payload_json"] or "{}")
                payload = loaded if isinstance(loaded, dict) else {}
            except (TypeError, json.JSONDecodeError):
                payload = {}
            fetched_at = float(snapshot["fetched_at"])
        try:
            external_ids = json.loads(row["external_ids_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            external_ids = {}
        return {
            "entity_id": entity_id,
            "entity_type": str(row["entity_type"]),
            "name": str(row["name"]),
            "external_ids": external_ids if isinstance(external_ids, dict) else {},
            "known_since": float(row["created_at"]),
            "fetched_at": fetched_at,
            "snapshot": payload,
            "insights": [self._insight_dict(insight) for insight in insight_rows],
            "discussion_count": int(activity["discussion_count"]) if activity else 0,
            "last_discussed_at": (
                float(activity["last_discussed_at"])
                if activity and activity["last_discussed_at"] is not None
                else None
            ),
        }

    def search_repository_memory(self, query: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Fuzzy-match repository entities by name (and snapshot text) for "what do I know about X"."""
        cleaned = str(query or "").strip()
        if not cleaned:
            return []
        like = f"%{cleaned}%"
        capped = max(1, min(int(limit), 50))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.entity_type, e.name, e.created_at,
                       MAX(s.fetched_at) AS last_fetched_at,
                       (SELECT s2.payload_json FROM memory_snapshots s2
                        WHERE s2.entity_id = e.id ORDER BY s2.fetched_at DESC LIMIT 1) AS latest_payload
                FROM memory_entities e
                LEFT JOIN memory_snapshots s ON s.entity_id = e.id
                WHERE e.archived_at IS NULL
                  AND (e.name LIKE ? COLLATE NOCASE
                       OR EXISTS (SELECT 1 FROM memory_snapshots sp
                                  WHERE sp.entity_id = e.id AND sp.payload_json LIKE ? COLLATE NOCASE))
                GROUP BY e.id
                ORDER BY (e.name LIKE ? COLLATE NOCASE) DESC, MAX(s.fetched_at) DESC
                LIMIT ?
                """,
                (like, like, like, capped),
            ).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "entity_id": str(row["id"]),
                    "entity_type": str(row["entity_type"]),
                    "name": str(row["name"]),
                    "known_since": float(row["created_at"]),
                    "fetched_at": (
                        float(row["last_fetched_at"]) if row["last_fetched_at"] is not None else None
                    ),
                }
            )
        return results

    def list_repository_insights(self, entity_id: str) -> List[Dict[str, Any]]:
        """Return active, source-cited insights recorded against a repository entity."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, insight, citations_json, created_at FROM memory_insights "
                "WHERE entity_id = ? AND archived_at IS NULL ORDER BY created_at DESC",
                (str(entity_id),),
            ).fetchall()
        return [self._insight_dict(row) for row in rows]

    def save_repository_insight(
        self, entity_id: str, insight: str, citations: Any = None
    ) -> Dict[str, Any]:
        """Persist a durable, source-cited insight for an existing repository entity."""
        cleaned = str(insight or "").strip()
        if not cleaned:
            raise ValueError("Insight text is required")
        normalized = self._normalize_insight_citations(citations)
        now = time.time()
        insight_id = uuid.uuid4().hex
        with self.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM memory_entities WHERE id = ? AND archived_at IS NULL", (str(entity_id),)
            ).fetchone() is None:
                raise ValueError("Unknown repository entity")
            conn.execute(
                """INSERT INTO memory_insights (id, entity_id, insight, citations_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (insight_id, str(entity_id), cleaned[:4000], json.dumps(normalized), now),
            )
        return {
            "id": insight_id,
            "entity_id": str(entity_id),
            "insight": cleaned[:4000],
            "citations": normalized,
            "created_at": now,
        }

    def resolve_memory_entity_id(self, name: str, entity_type: Optional[str] = None) -> Optional[str]:
        """Return the id of the newest matching repository entity, or None."""
        with self.connect() as conn:
            row = self._resolve_memory_entity_row(conn, name, entity_type)
        return str(row["id"]) if row is not None else None

    def record_entity_discussion(self, entity_id: str, *, at: Optional[float] = None) -> None:
        """Best-effort bump of an entity's discussion count/last-discussed time."""
        if not entity_id:
            return
        when = at if at is not None else time.time()
        try:
            with self.connect() as conn:
                conn.execute(
                    """INSERT INTO memory_entity_activity (entity_id, discussion_count, last_discussed_at)
                       VALUES (?, 1, ?)
                       ON CONFLICT(entity_id) DO UPDATE SET
                           discussion_count = discussion_count + 1,
                           last_discussed_at = excluded.last_discussed_at""",
                    (str(entity_id), when),
                )
        except sqlite3.Error:
            logger.debug("Could not record entity discussion for %s", entity_id, exc_info=True)

    @staticmethod
    def _insight_dict(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            citations = json.loads(row["citations_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            citations = []
        return {
            "id": str(row["id"]),
            "insight": str(row["insight"]),
            "citations": citations if isinstance(citations, list) else [],
            "created_at": float(row["created_at"]),
        }

    @staticmethod
    def _memory_note_dict(row: sqlite3.Row) -> Dict[str, Any]:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        return {
            "id": str(row["id"]), "user_id": str(row["user_id"]), "kind": str(row["kind"]),
            "text": str(row["text"]), "metadata": metadata,
            "created_at": float(row["created_at"]), "updated_at": float(row["updated_at"]),
        }

    # --- Telemetry ---

