"""Append-only watch event storage and identity mapping."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, Mapping, Optional, Sequence

from projectionist.library.db import Database
from projectionist.watch_tracker.identity import (
    MAPPING_UNMAPPED,
    resolve_user_id as _resolve_user_id_with_method,
)
from projectionist.watch_tracker.models import IngestResult, SOURCE_EVENT_KINDS, WatchEventInput

logger = logging.getLogger(__name__)
_RECONNECT_KINDS = {"history_played", "plex_scrobble"}
_RECONNECT_WINDOW_MS = 120_000
_CROSS_SOURCE_WINDOW_MS = 5 * 60 * 1000


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
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_user_id(db: Database, source_user_key: str) -> Optional[str]:
    user_id, _method = _resolve_user_id_with_method(db, source_user_key)
    return user_id


def _upsert_identity(
    conn,
    *,
    source: str,
    server_machine_id: str,
    source_user_key: str,
    user_id: Optional[str],
    display_name: Optional[str],
    mapping_method: str,
    now: float,
) -> None:
    method = str(mapping_method or MAPPING_UNMAPPED).strip() or MAPPING_UNMAPPED
    if user_id and method == MAPPING_UNMAPPED:
        method = "plex_account_id"
    if not user_id:
        method = MAPPING_UNMAPPED
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
            method,
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
                user_id, mapping_method = _resolve_user_id_with_method(db, source_user_key)
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
                    mapping_method=mapping_method,
                    now=now,
                )
                digest = payload_hash_for(event)
                event_id = str(uuid.uuid4())
                source_event_id = (
                    str(event.source_event_id).strip() if event.source_event_id else None
                )
                duplicate_of = _find_duplicate_event_id(
                    conn,
                    event=event,
                    source_user_key=source_user_key,
                    server_machine_id=server_id,
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
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                            duplicate_of,
                            now,
                        ),
                    )
                    local.inserted += 1
                    local.event_ids.append(event_id)
                except sqlite3.IntegrityError as exc:
                    if "UNIQUE constraint failed" not in str(exc):
                        raise
                    local.deduped += 1
        return local

    saved = db.run_write(_write, label="ingest_watch_events")
    if saved.event_ids:
        placeholders = ",".join("?" for _ in saved.event_ids)
        with db.connect() as conn:
            inserted_rows = conn.execute(
                f"""
                SELECT DISTINCT user_id, source_user_key
                FROM watch_events
                WHERE id IN ({placeholders})
                """,
                tuple(saved.event_ids),
            ).fetchall()
        user_ids = sorted(
            {str(row["user_id"]) for row in inserted_rows if row["user_id"] is not None}
        )
        unmapped_keys = sorted(
            {
                str(row["source_user_key"])
                for row in inserted_rows
                if row["user_id"] is None
            }
        )
        from projectionist.watch_tracker.correlate import correlate_after_ingest

        correlate_after_ingest(
            db,
            user_ids=user_ids,
            source_user_keys=unmapped_keys,
        )
    return saved


def _find_duplicate_event_id(
    conn,
    *,
    event: WatchEventInput,
    source_user_key: str,
    server_machine_id: str,
) -> Optional[str]:
    kind = str(event.source_event_kind)
    if kind in _RECONNECT_KINDS:
        row = conn.execute(
            """
            SELECT id FROM watch_events
            WHERE duplicate_of_event_id IS NULL
              AND server_machine_id = ?
              AND source_user_key = ?
              AND rating_key = ?
              AND source_event_kind IN ('history_played', 'plex_scrobble')
              AND occurred_at_ms BETWEEN ? AND ?
              AND COALESCE(client_key, '') = COALESCE(?, '')
            ORDER BY occurred_at_ms ASC, id ASC
            LIMIT 1
            """,
            (
                server_machine_id,
                source_user_key,
                str(event.rating_key),
                int(event.occurred_at_ms) - _RECONNECT_WINDOW_MS,
                int(event.occurred_at_ms) + _RECONNECT_WINDOW_MS,
                event.client_key,
            ),
        ).fetchone()
        if row is not None:
            return str(row["id"])
    if event.terminal:
        row = conn.execute(
            """
            SELECT id FROM watch_events
            WHERE duplicate_of_event_id IS NULL
              AND server_machine_id = ?
              AND source_user_key = ?
              AND rating_key = ?
              AND terminal = 1
              AND source <> ?
              AND occurred_at_ms BETWEEN ? AND ?
            ORDER BY occurred_at_ms ASC, id ASC
            LIMIT 1
            """,
            (
                server_machine_id,
                source_user_key,
                str(event.rating_key),
                str(event.source),
                int(event.occurred_at_ms) - _CROSS_SOURCE_WINDOW_MS,
                int(event.occurred_at_ms) + _CROSS_SOURCE_WINDOW_MS,
            ),
        ).fetchone()
        if row is not None:
            return str(row["id"])
    return None


def _completion_pct(event: WatchEventInput) -> Optional[float]:
    if event.progress_ms is None or event.duration_ms is None:
        return None
    duration = int(event.duration_ms)
    if duration <= 0:
        return None
    return min(100.0, (float(event.progress_ms) / float(duration)) * 100.0)


def list_user_watch_summary(
    db: Database,
    *,
    user_id: str,
    rating_key: str,
) -> Dict[str, Any]:
    """Return accepted tracker state for one user and one playable title."""
    uid = str(user_id or "").strip()
    key = str(rating_key or "").strip()
    confidence = {"certain": 0, "likely": 0, "plex_event_only": 0}
    with db.connect() as conn:
        sessions = conn.execute(
            """
            SELECT COUNT(*) AS logical_viewings,
                   COALESCE(SUM(event_count), 0) AS sittings_observed
            FROM watch_sessions
            WHERE user_id = ? AND rating_key = ?
            """,
            (uid, key),
        ).fetchone()
        completion_rows = conn.execute(
            """
            SELECT confidence, COUNT(*) AS count
            FROM watch_completions
            WHERE user_id = ? AND rating_key = ?
              AND superseded_by_completion_id IS NULL
            GROUP BY confidence
            """,
            (uid, key),
        ).fetchall()
        timeline_rows = conn.execute(
            """
            SELECT c.completed_at_ms, c.confidence, c.basis, c.threshold_pct,
                   s.event_count AS sittings_observed
            FROM watch_completions c
            JOIN watch_sessions s ON s.id = c.session_id
            WHERE c.user_id = ? AND c.rating_key = ?
              AND c.superseded_by_completion_id IS NULL
            ORDER BY c.completed_at_ms DESC, c.id DESC
            """,
            (uid, key),
        ).fetchall()
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM watch_events WHERE user_id = ? AND rating_key = ?",
            (uid, key),
        ).fetchone()
    for row in completion_rows:
        name = str(row["confidence"])
        if name in confidence:
            confidence[name] = int(row["count"] or 0)
    tracked = sum(confidence.values())
    evidence_count = int(event_count["count"] if event_count else 0)
    return {
        "rating_key": key,
        "tracked_completions": tracked,
        "completion_confidence": confidence,
        "logical_viewings": int(sessions["logical_viewings"] if sessions else 0),
        "sittings_observed": int(sessions["sittings_observed"] if sessions else 0),
        "last_tracked_completion_at": (
            int(timeline_rows[0]["completed_at_ms"]) if timeline_rows else None
        ),
        "tracker_coverage": "partial" if evidence_count else "none",
        "completion_timeline": [
            {
                "completed_at_ms": int(row["completed_at_ms"]),
                "confidence": str(row["confidence"]),
                "basis": str(row["basis"]),
                "threshold_pct": (
                    float(row["threshold_pct"])
                    if row["threshold_pct"] is not None
                    else None
                ),
                "sittings_observed": int(row["sittings_observed"] or 0),
            }
            for row in timeline_rows
        ],
    }


def list_user_show_watch_summary(
    db: Database,
    *,
    user_id: str,
    rating_key: str,
) -> Dict[str, Any]:
    """Roll episode correlation units up to one show for one user."""
    uid = str(user_id or "").strip()
    key = str(rating_key or "").strip()
    confidence = {"certain": 0, "likely": 0, "plex_event_only": 0}
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT rating_key, confidence, completed_at_ms
            FROM watch_completions
            WHERE user_id = ? AND parent_rating_key = ? AND media_type = 'episode'
              AND superseded_by_completion_id IS NULL
            ORDER BY completed_at_ms DESC
            """,
            (uid, key),
        ).fetchall()
        in_progress = conn.execute(
            """
            SELECT COUNT(DISTINCT s.rating_key) AS count
            FROM watch_sessions s
            LEFT JOIN watch_completions c ON c.session_id = s.id
            WHERE s.user_id = ? AND s.parent_rating_key = ? AND s.media_type = 'episode'
              AND c.id IS NULL
            """,
            (uid, key),
        ).fetchone()
    for row in rows:
        name = str(row["confidence"])
        if name in confidence:
            confidence[name] += 1
    episode_completions: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        episode_key = str(row["rating_key"])
        entry = episode_completions.setdefault(
            episode_key,
            {
                "tracked_completions": 0,
                "completion_confidence": {
                    "certain": 0,
                    "likely": 0,
                    "plex_event_only": 0,
                },
                "last_tracked_completion_at": None,
            },
        )
        entry["tracked_completions"] += 1
        entry["completion_confidence"][str(row["confidence"])] += 1
        if entry["last_tracked_completion_at"] is None:
            entry["last_tracked_completion_at"] = int(row["completed_at_ms"])
    unique_completed = len(episode_completions)
    return {
        "rating_key": key,
        "unique_episodes_completed": unique_completed,
        "total_episode_completions": len(rows),
        "repeat_episode_completions": max(0, len(rows) - unique_completed),
        "episodes_in_progress": int(in_progress["count"] if in_progress else 0),
        "most_recently_completed_episode": (
            {
                "rating_key": str(rows[0]["rating_key"]),
                "completed_at_ms": int(rows[0]["completed_at_ms"]),
            }
            if rows
            else None
        ),
        "completion_confidence": confidence,
        "episode_completions": episode_completions,
        "recent_activity": [
            {
                "rating_key": str(row["rating_key"]),
                "completed_at_ms": int(row["completed_at_ms"]),
                "confidence": str(row["confidence"]),
            }
            for row in rows[:20]
        ],
        "tracker_coverage": "partial" if rows or (in_progress and in_progress["count"]) else "none",
    }


def attach_user_watch_summaries(
    db: Database,
    payload: Any,
    *,
    user_id: Optional[str],
) -> Any:
    """Add user-scoped tracker fields beside legacy Plex count semantics.

    The recursive pass caches each title summary so repeated card/detail
    representations in one tool or API response do not repeat database reads.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return payload
    cache: Dict[tuple[str, str], Dict[str, Any]] = {}

    def _walk(value: Any) -> Any:
        if isinstance(value, list):
            for index, item in enumerate(value):
                value[index] = _walk(item)
            return value
        if not isinstance(value, Mapping):
            return value
        if not isinstance(value, dict):
            value = dict(value)
        for child_key, child in list(value.items()):
            value[child_key] = _walk(child)
        rating_key = str(value.get("rating_key") or "").strip()
        media_type = str(value.get("media_type") or "").strip().lower()
        if rating_key and media_type in {"movie", "show", "episode"}:
            cache_key = (media_type, rating_key)
            summary = cache.get(cache_key)
            if summary is None:
                summary = (
                    list_user_show_watch_summary(
                        db,
                        user_id=uid,
                        rating_key=rating_key,
                    )
                    if media_type == "show"
                    else list_user_watch_summary(
                        db,
                        user_id=uid,
                        rating_key=rating_key,
                    )
                )
                cache[cache_key] = summary
            if "view_count" in value:
                value["plex_played_event_count"] = int(value.get("view_count") or 0)
            value.update(summary)
        return value

    return _walk(payload)


def list_watch_evidence_diagnostics(
    db: Database,
    *,
    user_id: Optional[str] = None,
    rating_key: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Owner review payload without provider identity keys or raw payloads."""
    clauses = ["1=1"]
    params: list[Any] = []
    if user_id:
        clauses.append("e.user_id = ?")
        params.append(str(user_id))
    if rating_key:
        clauses.append("e.rating_key = ?")
        params.append(str(rating_key))
    params.append(min(max(1, int(limit)), 200))
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT e.id, e.source, e.source_event_kind, e.user_id, e.rating_key,
                   e.parent_rating_key, e.media_type, e.occurred_at_ms,
                   e.progress_ms, e.duration_ms, e.completion_pct, e.terminal,
                   e.manual, e.duplicate_of_event_id, se.session_id,
                   c.id AS completion_id, c.confidence, c.basis
            FROM watch_events e
            LEFT JOIN watch_session_events se ON se.event_id = e.id
            LEFT JOIN watch_completions c ON c.session_id = se.session_id
            WHERE {' AND '.join(clauses)}
            ORDER BY e.occurred_at_ms DESC, e.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    items = [dict(row) for row in rows]
    return {"items": items, "count": len(items)}


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
    now = time.time()
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
        source_counts = conn.execute(
            """
            SELECT source, server_machine_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) AS mapped,
                   SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) AS unmapped
            FROM watch_events
            GROUP BY source, server_machine_id
            """
        ).fetchall()
    counts_by_cursor = {
        (str(row["source"]), str(row["server_machine_id"])): {
            "events_total": int(row["total"] or 0),
            "events_mapped": int(row["mapped"] or 0),
            "events_unmapped": int(row["unmapped"] or 0),
        }
        for row in source_counts
    }

    def _source_status(row) -> Dict[str, Any]:
        last_success = row["last_success_at"]
        last_error_at = row["last_error_at"]
        has_current_error = bool(row["last_error"]) and (
            last_success is None
            or (last_error_at is not None and float(last_error_at) > float(last_success))
        )
        capability = (
            "degraded"
            if has_current_error
            else "available"
            if last_success is not None
            else "unknown"
        )
        return {
            "source": str(row["source"]),
            "capability": capability,
            "cursor_age_seconds": (
                max(0, int(now - float(last_success)))
                if last_success is not None
                else None
            ),
            "high_watermark_ms": row["high_watermark_ms"],
            "last_success_at": last_success,
            "last_error_at": last_error_at,
            "last_error": str(row["last_error"]) if has_current_error else None,
            **counts_by_cursor.get(
                (str(row["source"]), str(row["server_machine_id"])),
                {
                    "events_total": 0,
                    "events_mapped": 0,
                    "events_unmapped": 0,
                },
            ),
        }

    sources = [_source_status(row) for row in cursors]
    if not sources:
        sources = [
            {
                "source": "plex_history",
                "capability": "unknown",
                "cursor_age_seconds": None,
                "high_watermark_ms": None,
                "last_success_at": None,
                "last_error_at": None,
                "last_error": None,
                "events_total": 0,
                "events_mapped": 0,
                "events_unmapped": 0,
            }
        ]
    return {
        "events_total": int(total["c"] if total else 0),
        "events_mapped": int(mapped["c"] if mapped else 0),
        "events_unmapped": int(unmapped["c"] if unmapped else 0),
        "sessions": int(sessions["c"] if sessions else 0),
        "completions": int(completions["c"] if completions else 0),
        "sources": sources,
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
