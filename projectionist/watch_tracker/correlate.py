"""Deterministic session merge and completion derivation."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from projectionist.library.db import Database
from projectionist.watch_tracker import (
    ALGORITHM_VERSION,
    CLIENT_HANDOFF_GAP_MS,
    COMPLETION_THRESHOLD_PCT,
    IMPLAUSIBLE_RECOMPLETE_MS,
    RESTART_PROGRESS_PCT,
    SCROBBLE_DEDUPE_WINDOW_MS,
    SESSION_GAP_MS,
)

logger = logging.getLogger(__name__)


def _progress_pct(progress_ms: Optional[int], duration_ms: Optional[int]) -> Optional[float]:
    if progress_ms is None or duration_ms is None or int(duration_ms) <= 0:
        return None
    return min(100.0, (float(progress_ms) / float(duration_ms)) * 100.0)


def _rewind_tolerance_ms(duration_ms: Optional[int]) -> int:
    base = 60_000
    if duration_ms and int(duration_ms) > 0:
        return max(base, int(float(duration_ms) * 0.02))
    return base


def _event_sort_key(row: Any) -> Tuple[Any, ...]:
    return (
        str(row["source_user_key"]),
        str(row["rating_key"]),
        int(row["occurred_at_ms"]),
        str(row["id"]),
    )


_DERIVATION_NAMESPACE = uuid.UUID("dc472216-ceec-4acd-853b-b47de69bad12")


def _stable_id(kind: str, *parts: object) -> str:
    material = "\x1f".join([kind, *(str(part) for part in parts)])
    return str(uuid.uuid5(_DERIVATION_NAMESPACE, material))


def rebuild_watch_derivations(
    db: Database,
    *,
    user_id: Optional[str] = None,
    source_user_key: Optional[str] = None,
    since_ms: Optional[int] = None,
    algorithm_version: int = ALGORITHM_VERSION,
) -> Dict[str, Any]:
    """Regenerate sessions/completions for a scoped window from immutable events."""

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            query = """
                SELECT * FROM watch_events
                WHERE duplicate_of_event_id IS NULL
            """
            params: List[Any] = []
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            if source_user_key:
                query += " AND source_user_key = ?"
                params.append(source_user_key)
            if since_ms is not None:
                query += " AND occurred_at_ms >= ?"
                params.append(int(since_ms))
            rows = list(conn.execute(query, tuple(params)).fetchall())
            rows.sort(key=_event_sort_key)

            # Clear prior derivations for the same scope (supersede via delete in v1 window).
            if user_id or source_user_key or since_ms is not None:
                del_sessions = "DELETE FROM watch_sessions WHERE 1=1"
                del_params: List[Any] = []
                if user_id:
                    del_sessions += " AND user_id = ?"
                    del_params.append(user_id)
                if source_user_key:
                    del_sessions += " AND source_user_key = ?"
                    del_params.append(source_user_key)
                if since_ms is not None:
                    del_sessions += " AND started_at_ms >= ?"
                    del_params.append(int(since_ms))
                # Cascade deletes session_events + completions via FK.
                conn.execute(del_sessions, tuple(del_params))
            else:
                conn.execute("DELETE FROM watch_session_events")
                conn.execute("DELETE FROM watch_completions")
                conn.execute("DELETE FROM watch_sessions")

            built_sessions: List[Tuple[Dict[str, Any], List[Any]]] = []
            current: Optional[Dict[str, Any]] = None
            current_events: List[Any] = []

            def flush() -> None:
                nonlocal current, current_events
                if current is None or not current_events:
                    current = None
                    current_events = []
                    return
                built_sessions.append((current, list(current_events)))
                current = None
                current_events = []

            for row in rows:
                if current is None:
                    current = _new_session_state(row)
                    current_events = [row]
                    continue
                if _can_merge(current, row):
                    _merge_into(current, row)
                    current_events.append(row)
                else:
                    flush()
                    current = _new_session_state(row)
                    current_events = [row]
            flush()

            sessions_built = 0
            completions_built = 0
            last_completion: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            for state, session_events in built_sessions:
                first = session_events[0]
                last = session_events[-1]
                session_id = _stable_id(
                    "session",
                    algorithm_version,
                    state["server_machine_id"],
                    state["source_user_key"],
                    state["rating_key"],
                    first["id"],
                    last["id"],
                )
                created_at = min(float(event["ingested_at"]) for event in session_events)
                updated_at = max(float(event["ingested_at"]) for event in session_events)
                conn.execute(
                    """
                    INSERT INTO watch_sessions (
                        id, user_id, source_user_key, rating_key, parent_rating_key,
                        media_type, started_at_ms, ended_at_ms, start_progress_ms,
                        max_progress_ms, duration_ms, first_event_id, last_event_id,
                        primary_client_key, client_count, event_count, terminal_reason,
                        algorithm_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        state.get("user_id"),
                        state["source_user_key"],
                        state["rating_key"],
                        state.get("parent_rating_key"),
                        state["media_type"],
                        state["started_at_ms"],
                        state.get("ended_at_ms"),
                        state.get("start_progress_ms"),
                        state.get("max_progress_ms"),
                        state.get("duration_ms"),
                        str(first["id"]),
                        str(last["id"]),
                        state.get("primary_client_key"),
                        state.get("client_count", 1),
                        len(session_events),
                        state.get("terminal_reason"),
                        algorithm_version,
                        created_at,
                        updated_at,
                    ),
                )
                for ordinal, ev in enumerate(session_events):
                    conn.execute(
                        """
                        INSERT INTO watch_session_events (session_id, event_id, ordinal)
                        VALUES (?, ?, ?)
                        """,
                        (session_id, str(ev["id"]), ordinal),
                    )
                sessions_built += 1
                completion = _derive_completion(state, session_events)
                completion_key = (
                    state["server_machine_id"],
                    state["source_user_key"],
                    state["rating_key"],
                )
                prior = last_completion.get(completion_key)
                if completion and prior and _is_implausible_recompletion(
                    state, completion, prior
                ):
                    completion = None
                if completion:
                    completion_id = _stable_id(
                        "completion", algorithm_version, session_id, completion["evidence_event_id"]
                    )
                    conn.execute(
                        """
                        INSERT INTO watch_completions (
                            id, session_id, user_id, rating_key, parent_rating_key,
                            media_type, completed_at_ms, confidence, basis, threshold_pct,
                            evidence_event_id, superseded_by_completion_id,
                            algorithm_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                        """,
                        (
                            completion_id,
                            session_id,
                            state.get("user_id"),
                            state["rating_key"],
                            state.get("parent_rating_key"),
                            state["media_type"],
                            completion["completed_at_ms"],
                            completion["confidence"],
                            completion["basis"],
                            COMPLETION_THRESHOLD_PCT,
                            completion["evidence_event_id"],
                            algorithm_version,
                            updated_at,
                        ),
                    )
                    completions_built += 1
                    last_completion[completion_key] = {
                        "completed_at_ms": completion["completed_at_ms"],
                        "duration_ms": state.get("duration_ms"),
                    }
            return {
                "sessions": sessions_built,
                "completions": completions_built,
                "events": len(rows),
                "algorithm_version": algorithm_version,
            }

    return db.run_write(_write, label="rebuild_watch_derivations")


def _new_session_state(row: Any) -> Dict[str, Any]:
    clients = {str(row["client_key"])} if row["client_key"] else set()
    return {
        "user_id": row["user_id"],
        "source_user_key": str(row["source_user_key"]),
        "rating_key": str(row["rating_key"]),
        "parent_rating_key": row["parent_rating_key"],
        "media_type": str(row["media_type"]),
        "server_machine_id": str(row["server_machine_id"]),
        "started_at_ms": int(row["occurred_at_ms"]),
        "ended_at_ms": int(row["occurred_at_ms"]),
        "start_progress_ms": row["progress_ms"],
        "max_progress_ms": row["progress_ms"],
        "duration_ms": row["duration_ms"],
        "primary_client_key": row["client_key"],
        "clients": clients,
        "client_count": max(1, len(clients)),
        "terminal_reason": str(row["source_event_kind"]) if row["terminal"] else None,
        "saw_below_threshold": (
            (_progress_pct(row["progress_ms"], row["duration_ms"]) or 100) < COMPLETION_THRESHOLD_PCT
        ),
        "saw_at_or_above_threshold": (
            (_progress_pct(row["progress_ms"], row["duration_ms"]) or 0) >= COMPLETION_THRESHOLD_PCT
        ),
        "has_progress": row["progress_ms"] is not None,
        "manual_only": bool(row["manual"]) and str(row["source_event_kind"]) == "manual_scrobble",
        "kinds": {str(row["source_event_kind"])},
        "crossing_event_id": None,
        "crossing_at_ms": None,
    }


def _merge_into(current: Dict[str, Any], row: Any) -> None:
    current["ended_at_ms"] = int(row["occurred_at_ms"])
    if row["progress_ms"] is not None:
        max_p = current.get("max_progress_ms")
        if max_p is None or int(row["progress_ms"]) > int(max_p):
            current["max_progress_ms"] = row["progress_ms"]
        current["has_progress"] = True
    if row["duration_ms"] is not None:
        current["duration_ms"] = row["duration_ms"]
    if row["client_key"]:
        current["clients"].add(str(row["client_key"]))
        current["client_count"] = len(current["clients"])
        if not current.get("primary_client_key"):
            current["primary_client_key"] = row["client_key"]
    if row["terminal"]:
        current["terminal_reason"] = str(row["source_event_kind"])
    pct = _progress_pct(row["progress_ms"], row["duration_ms"])
    if pct is not None:
        if pct < COMPLETION_THRESHOLD_PCT:
            current["saw_below_threshold"] = True
        if pct >= COMPLETION_THRESHOLD_PCT:
            if current.get("saw_below_threshold") and not current.get("crossing_event_id"):
                current["crossing_event_id"] = str(row["id"])
                current["crossing_at_ms"] = int(row["occurred_at_ms"])
            current["saw_at_or_above_threshold"] = True
    current["kinds"].add(str(row["source_event_kind"]))
    if not (bool(row["manual"]) and str(row["source_event_kind"]) == "manual_scrobble"):
        current["manual_only"] = False


def _can_merge(
    current: Dict[str, Any],
    row: Any,
) -> bool:
    if str(row["server_machine_id"]) != current["server_machine_id"]:
        return False
    if str(row["source_user_key"]) != current["source_user_key"]:
        return False
    if str(row["rating_key"]) != current["rating_key"]:
        return False
    if str(row["media_type"]) != current["media_type"]:
        return False
    gap = int(row["occurred_at_ms"]) - int(current["ended_at_ms"])
    if gap > SESSION_GAP_MS:
        return False
    pct = _progress_pct(row["progress_ms"], row["duration_ms"] or current.get("duration_ms"))
    if current.get("saw_at_or_above_threshold") and pct is not None and pct <= RESTART_PROGRESS_PCT:
        return False
    # Progress monotonicity (skip for pure terminal history/scrobble without progress).
    if row["progress_ms"] is not None and current.get("max_progress_ms") is not None:
        tol = _rewind_tolerance_ms(row["duration_ms"] or current.get("duration_ms"))
        if int(row["progress_ms"]) + tol < int(current["max_progress_ms"]):
            kind = str(row["source_event_kind"])
            if kind not in {"history_played", "plex_scrobble", "manual_scrobble"}:
                return False
    # Client handoff
    if (
        row["client_key"]
        and current.get("primary_client_key")
        and str(row["client_key"]) != str(current["primary_client_key"])
        and gap > CLIENT_HANDOFF_GAP_MS
    ):
        return False
    # Near-duplicate scrobbles
    if str(row["source_event_kind"]) in {"plex_scrobble", "history_played"}:
        if gap <= SCROBBLE_DEDUPE_WINDOW_MS:
            return True
    return True


def _derive_completion(
    current: Dict[str, Any], events: Sequence[Any]
) -> Optional[Dict[str, Any]]:
    last = events[-1]
    kinds = current.get("kinds") or set()
    completed_at = int(current.get("ended_at_ms") or last["occurred_at_ms"])
    evidence_id = str(last["id"])

    if (
        "manual_unscrobble" in kinds
        and "manual_scrobble" in kinds
        and not (kinds & {"history_played", "plex_scrobble"})
        and not current.get("saw_at_or_above_threshold")
    ):
        return None

    if "manual_scrobble" in kinds:
        return {
            "completed_at_ms": completed_at,
            "confidence": "plex_event_only",
            "basis": "manual_scrobble",
            "evidence_event_id": evidence_id,
        }

    if (
        current.get("user_id")
        and current.get("saw_below_threshold")
        and current.get("saw_at_or_above_threshold")
    ):
        return {
            "completed_at_ms": int(current.get("crossing_at_ms") or completed_at),
            "confidence": "certain",
            "basis": "observed_threshold_crossing",
            "evidence_event_id": str(current.get("crossing_event_id") or evidence_id),
        }

    max_pct = _progress_pct(current.get("max_progress_ms"), current.get("duration_ms"))
    terminal_kinds = kinds & {"session_stop", "plex_scrobble", "history_played"}
    if max_pct is not None and max_pct >= COMPLETION_THRESHOLD_PCT and terminal_kinds:
        return {
            "completed_at_ms": completed_at,
            "confidence": "likely",
            "basis": "terminal_near_complete",
            "evidence_event_id": evidence_id,
        }

    if "history_played" in kinds and current.get("has_progress"):
        return {
            "completed_at_ms": completed_at,
            "confidence": "likely",
            "basis": "history_linked_progress",
            "evidence_event_id": evidence_id,
        }

    if kinds & {"history_played", "plex_scrobble"}:
        return {
            "completed_at_ms": completed_at,
            "confidence": "plex_event_only",
            "basis": "plex_played_event",
            "evidence_event_id": evidence_id,
        }

    return None


def _is_implausible_recompletion(
    current: Dict[str, Any],
    completion: Dict[str, Any],
    prior: Dict[str, Any],
) -> bool:
    if completion["confidence"] != "plex_event_only":
        return False
    start_pct = _progress_pct(current.get("start_progress_ms"), current.get("duration_ms"))
    if start_pct is not None and start_pct <= RESTART_PROGRESS_PCT:
        return False
    elapsed = int(completion["completed_at_ms"]) - int(prior["completed_at_ms"])
    duration = current.get("duration_ms") or prior.get("duration_ms") or 0
    floor = max(IMPLAUSIBLE_RECOMPLETE_MS, int(float(duration) * 0.75))
    return elapsed < floor


def correlate_after_ingest(
    db: Database,
    *,
    user_ids: Optional[Sequence[str]] = None,
    source_user_keys: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Rebuild derivations for affected users (or full ledger when unspecified)."""
    if not user_ids and not source_user_keys:
        return rebuild_watch_derivations(db)
    totals = {"sessions": 0, "completions": 0, "events": 0}
    for uid in user_ids or ():
        if not uid:
            continue
        part = rebuild_watch_derivations(db, user_id=str(uid))
        totals["sessions"] += int(part.get("sessions") or 0)
        totals["completions"] += int(part.get("completions") or 0)
        totals["events"] += int(part.get("events") or 0)
    for source_key in source_user_keys or ():
        if not source_key:
            continue
        part = rebuild_watch_derivations(db, source_user_key=str(source_key))
        totals["sessions"] += int(part.get("sessions") or 0)
        totals["completions"] += int(part.get("completions") or 0)
        totals["events"] += int(part.get("events") or 0)
    return totals
