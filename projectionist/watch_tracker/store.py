"""Append-only watch event storage and identity mapping."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from projectionist.library.db import Database
from projectionist.watch_tracker.models import IngestResult, SOURCE_EVENT_KINDS, WatchEventInput

logger = logging.getLogger(__name__)


def payload_hash_for(event: WatchEventInput) -> str:
    """Deterministic SHA-256 over normalized identity/title/time/progress fields."""
    payload = {
        "source": event.source,
        "server_machine_id": event.server_machine_id,
        "source_user_key": event.source_user_key,
        "source_event_kind": event.source_event_kind,
        "rating_key": event.rating_key,
        "parent_rating_key": event.parent_rating_key or "",
        "media_type": event.media_type,
        "occurred_at_ms": int(event.occurred_at_ms),
        "client_key": event.client_key or "",
        "session_key": event.session_key or "",
        "progress_ms": event.progress_ms if event.progress_ms is not None else "",
        "duration_ms": event.duration_ms if event.duration_ms is not None else "",
        "terminal": bool(event.terminal),
        "manual": bool(event.manual),
        "source_event_id": event.source_event_id or "",
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_user_id(db: Database, source_user_key: str) -> Optional[str]:
    key = str(source_user_key or "").strip()
    if not key:
        return None
    row = db.get_user_by_plex_id(key)
    if row is None:
        return None
    return str(row["id"])


def _upsert_identity(
    conn,
    *,
    source: str,
    server_machine_id: str,
    source_user_key: str,
    user_id: Optional[str],
    display_name: Optional[str],
    now: float,
) -> None:
    mapping_method = "plex_account_id" if user_id else "unmapped"
    conn.execute(
        """
        INSERT INTO watch_source_identities (
            source, server_machine_id, source_user_key, user_id, display_name,
            mapping_method, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, server_machine_id, source_user_key) DO UPDATE SET
            user_id = COALESCE(excluded.user_id, watch_source_identities.user_id),
            display_name = COALESCE(excluded.display_name, watch_source_identities.display_name),
            mapping_method = CASE
                WHEN excluded.user_id IS NOT NULL THEN excluded.mapping_method
                ELSE watch_source_identities.mapping_method
            END,
            last_seen_at = excluded.last_seen_at
        """,
        (
            source,
            server_machine_id,
            source_user_key,
            user_id,
            display_name,
            mapping_method,
            now,
            now,
        ),
    )


def ingest_watch_events(
    db: Database,
    events: Sequence[WatchEventInput],
    *,
    display_names: Optional[Dict[str, str]] = None,
) -> IngestResult:
    """Normalize, map exact identities, fingerprint, and idempotently insert."""
    result = IngestResult(fetched=len(events))
    if not events:
        return result
    names = display_names or {}
    now = time.time()

    def _write() -> IngestResult:
        local = IngestResult(fetched=len(events))
        with db.connect() as conn:
            for event in events:
                kind = str(event.source_event_kind or "").strip()
                if kind not in SOURCE_EVENT_KINDS:
                    local.deduped += 1
                    continue
                source_user_key = str(event.source_user_key or "").strip()
                rating_key = str(event.rating_key or "").strip()
                server_id = str(event.server_machine_id or "").strip()
                if not source_user_key or not rating_key or not server_id:
                    local.deduped += 1
                    continue
                if event.media_type not in {"movie", "episode"}:
                    local.deduped += 1
                    continue
                user_id = _resolve_user_id(db, source_user_key)
                if user_id:
                    local.mapped += 1
                else:
                    local.unmapped += 1
                _upsert_identity(
                    conn,
                    source=event.source,
                    server_machine_id=server_id,
                    source_user_key=source_user_key,
                    user_id=user_id,
                    display_name=names.get(source_user_key),
                    now=now,
                )
                digest = payload_hash_for(event)
                event_id = str(uuid.uuid4())
                source_event_id = (
                    str(event.source_event_id).strip() if event.source_event_id else None
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO watch_events (
                            id, source, source_event_id, source_event_kind, server_machine_id,
                            source_user_key, user_id, rating_key, parent_rating_key, media_type,
                            occurred_at_ms, client_key, session_key, progress_ms, duration_ms,
                            completion_pct, terminal, manual, payload_hash, duplicate_of_event_id,
                            ingested_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?
                        )
                        """,
                        (
                            event_id,
                            event.source,
                            source_event_id,
                            kind,
                            server_id,
                            source_user_key,
                            user_id,
                            rating_key,
                            event.parent_rating_key,
                            event.media_type,
                            int(event.occurred_at_ms),
                            event.client_key,
                            event.session_key,
                            event.progress_ms,
                            event.duration_ms,
                            _completion_pct(event),
                            1 if event.terminal else 0,
                            1 if event.manual else 0,
                            digest,
                            now,
                        ),
                    )
                    local.inserted += 1
                    local.event_ids.append(event_id)
                except Exception:  # noqa: BLE001 — unique constraint → dedupe
                    local.deduped += 1
        return local

    return db.run_write(_write, label="ingest_watch_events")


def _completion_pct(event: WatchEventInput) -> Optional[float]:
    if event.progress_ms is None or event.duration_ms is None:
        return None
    duration = int(event.duration_ms)
    if duration <= 0:
        return None
    return min(100.0, (float(event.progress_ms) / float(duration)) * 100.0)


def get_ingest_cursor(
    db: Database, *, source: str, server_machine_id: str
) -> Optional[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM watch_ingest_cursors
            WHERE source = ? AND server_machine_id = ?
            """,
            (source, server_machine_id),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def set_ingest_cursor(
    db: Database,
    *,
    source: str,
    server_machine_id: str,
    cursor_value: Optional[str] = None,
    high_watermark_ms: Optional[int] = None,
    last_error: Optional[str] = None,
    success: bool = True,
) -> None:
    now = time.time()

    def _write() -> None:
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO watch_ingest_cursors (
                    source, server_machine_id, cursor_value, high_watermark_ms,
                    last_success_at, last_error_at, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, server_machine_id) DO UPDATE SET
                    cursor_value = COALESCE(excluded.cursor_value, watch_ingest_cursors.cursor_value),
                    high_watermark_ms = COALESCE(
                        excluded.high_watermark_ms, watch_ingest_cursors.high_watermark_ms
                    ),
                    last_success_at = CASE
                        WHEN ? THEN excluded.last_success_at
                        ELSE watch_ingest_cursors.last_success_at
                    END,
                    last_error_at = CASE
                        WHEN ? THEN watch_ingest_cursors.last_error_at
                        ELSE excluded.last_error_at
                    END,
                    last_error = CASE
                        WHEN ? THEN NULL
                        ELSE excluded.last_error
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    source,
                    server_machine_id,
                    cursor_value,
                    high_watermark_ms,
                    now if success else None,
                    None if success else now,
                    None if success else (last_error or "error"),
                    now,
                    1 if success else 0,
                    1 if success else 0,
                    1 if success else 0,
                ),
            )

    db.run_write(_write, label="set_ingest_cursor")


def watch_tracker_status(db: Database) -> Dict[str, Any]:
    """Owner-facing health — no titles or source identity keys."""
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM watch_events").fetchone()
        mapped = conn.execute(
            "SELECT COUNT(*) AS c FROM watch_events WHERE user_id IS NOT NULL"
        ).fetchone()
        unmapped = conn.execute(
            "SELECT COUNT(*) AS c FROM watch_events WHERE user_id IS NULL"
        ).fetchone()
        completions = conn.execute(
            "SELECT COUNT(*) AS c FROM watch_completions WHERE superseded_by_completion_id IS NULL"
        ).fetchone()
        sessions = conn.execute("SELECT COUNT(*) AS c FROM watch_sessions").fetchone()
        cursors = conn.execute(
            """
            SELECT source, server_machine_id, high_watermark_ms, last_success_at,
                   last_error_at, last_error, updated_at
            FROM watch_ingest_cursors
            """
        ).fetchall()
    return {
        "events_total": int(total["c"] if total else 0),
        "events_mapped": int(mapped["c"] if mapped else 0),
        "events_unmapped": int(unmapped["c"] if unmapped else 0),
        "sessions": int(sessions["c"] if sessions else 0),
        "completions": int(completions["c"] if completions else 0),
        "cursors": [
            {
                "source": str(row["source"]),
                "server_machine_id_present": bool(row["server_machine_id"]),
                "high_watermark_ms": row["high_watermark_ms"],
                "last_success_at": row["last_success_at"],
                "last_error_at": row["last_error_at"],
                "has_error": bool(row["last_error"]),
                "updated_at": row["updated_at"],
            }
            for row in cursors
        ],
    }
