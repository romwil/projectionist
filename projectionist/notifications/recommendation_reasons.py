"""Reasons a person would recognize for an inbox recommendation.

Seeds come from real household evidence (completions, sessions, terminal watch
events, watchlist pins) — not raw view_count alone. Peers must share a named
link (explainable neighbor, shared crew, or collection). The resulting
explanation kind is ``watched_bridge`` when a seed exists; cosine proximity
alone is never a reason.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.library.db import Database
from projectionist.library.plot_kinship import (
    build_explanation,
    parse_plot_link_json,
    plot_blob,
    specific_plot_link,
)

_CREW_JOBS = ("director", "writer", "screenplay", "creator")
_ITEM_COLUMNS = """
    id, title, year, media_type, tmdb_id, tvdb_id, rating_key, poster_url,
    summary, tmdb_overview, tagline, long_synopsis, llm_logline,
    genres, keywords, tmdb_collection_id, collection_name, view_count
"""
_SEED_SOURCES_WATCH = ("completion", "session", "watch_event", "library_view")
_SEED_SOURCES_SAVED = ("watchlist",)


def _as_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return row
    keys = row.keys() if hasattr(row, "keys") else []
    return {key: row[key] for key in keys}


def _labels(value: Any) -> set[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = []
        raw = parsed if isinstance(parsed, list) else []
    else:
        raw = []
    return {str(label).strip().casefold() for label in raw if str(label).strip()}


def _title_label(row: Mapping[str, Any]) -> str:
    title = str(row.get("title") or "Untitled").strip() or "Untitled"
    year = row.get("year")
    return f"{title} ({year})" if year else title


def _finish(sentence: str) -> str:
    text = " ".join(str(sentence or "").split())
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text


def _table_exists(conn: Any, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _merge_seed(
    by_id: Dict[int, Dict[str, Any]],
    row: Mapping[str, Any],
    *,
    seed_source: str,
    seed_at: float,
) -> None:
    try:
        item_id = int(row["id"])
    except (TypeError, ValueError, KeyError):
        return
    if item_id <= 0:
        return
    existing = by_id.get(item_id)
    # Prefer completions over sessions/events/views; prefer earlier-listed sources.
    priority = {
        "completion": 0,
        "session": 1,
        "watch_event": 2,
        "watchlist": 3,
        "library_view": 4,
    }
    if existing is not None:
        if priority.get(existing.get("seed_source"), 99) <= priority.get(seed_source, 99):
            # Keep better source; bump recency if this row is newer.
            if float(existing.get("seed_at") or 0) < float(seed_at or 0):
                existing["seed_at"] = float(seed_at or 0)
            return
    payload = _as_dict(row)
    payload["seed_source"] = seed_source
    payload["seed_at"] = float(seed_at or 0)
    by_id[item_id] = payload


def _join_library_on_rating_keys(conn: Any, rating_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    keys = [str(key).strip() for key in rating_keys if str(key or "").strip()]
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS}
        FROM library_items
        WHERE rating_key IN ({placeholders})
        """,
        tuple(keys),
    ).fetchall()
    return {str(row["rating_key"]): _as_dict(row) for row in rows}


def _load_completion_seeds(
    conn: Any,
    *,
    user_id: Optional[str],
    household: bool,
    limit: int,
) -> List[Tuple[Dict[str, Any], float]]:
    if not _table_exists(conn, "watch_completions"):
        return []
    if household:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, completed_at_ms
            FROM watch_completions
            WHERE superseded_by_completion_id IS NULL
            ORDER BY completed_at_ms DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    elif user_id:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, completed_at_ms
            FROM watch_completions
            WHERE superseded_by_completion_id IS NULL
              AND user_id = ?
            ORDER BY completed_at_ms DESC
            LIMIT ?
            """,
            (user_id, limit * 3),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, completed_at_ms
            FROM watch_completions
            WHERE superseded_by_completion_id IS NULL
              AND user_id IS NULL
            ORDER BY completed_at_ms DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    lookup_keys: List[str] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        if media == "episode" and parent:
            lookup_keys.append(parent)
        elif key:
            lookup_keys.append(key)
    by_key = _join_library_on_rating_keys(conn, lookup_keys)
    out: List[Tuple[Dict[str, Any], float]] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        lib_key = parent if media == "episode" and parent else key
        item = by_key.get(lib_key)
        if item is None:
            continue
        try:
            at_ms = float(row["completed_at_ms"] or 0)
        except (TypeError, ValueError):
            at_ms = 0.0
        out.append((item, at_ms / 1000.0 if at_ms > 1e12 else at_ms))
        if len(out) >= limit:
            break
    return out


def _load_session_seeds(
    conn: Any,
    *,
    user_id: Optional[str],
    household: bool,
    limit: int,
) -> List[Tuple[Dict[str, Any], float]]:
    if not _table_exists(conn, "watch_sessions"):
        return []
    if household:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type,
                   COALESCE(ended_at_ms, started_at_ms) AS seed_ms
            FROM watch_sessions
            ORDER BY COALESCE(ended_at_ms, started_at_ms) DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    elif user_id:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type,
                   COALESCE(ended_at_ms, started_at_ms) AS seed_ms
            FROM watch_sessions
            WHERE user_id = ?
            ORDER BY COALESCE(ended_at_ms, started_at_ms) DESC
            LIMIT ?
            """,
            (user_id, limit * 3),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type,
                   COALESCE(ended_at_ms, started_at_ms) AS seed_ms
            FROM watch_sessions
            WHERE user_id IS NULL
            ORDER BY COALESCE(ended_at_ms, started_at_ms) DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    lookup_keys: List[str] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        if media == "episode" and parent:
            lookup_keys.append(parent)
        elif key:
            lookup_keys.append(key)
    by_key = _join_library_on_rating_keys(conn, lookup_keys)
    out: List[Tuple[Dict[str, Any], float]] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        lib_key = parent if media == "episode" and parent else key
        item = by_key.get(lib_key)
        if item is None:
            continue
        try:
            at_ms = float(row["seed_ms"] or 0)
        except (TypeError, ValueError):
            at_ms = 0.0
        out.append((item, at_ms / 1000.0 if at_ms > 1e12 else at_ms))
        if len(out) >= limit:
            break
    return out


def _load_terminal_event_seeds(
    conn: Any,
    *,
    user_id: Optional[str],
    household: bool,
    limit: int,
) -> List[Tuple[Dict[str, Any], float]]:
    if not _table_exists(conn, "watch_events"):
        return []
    if household:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, occurred_at_ms
            FROM watch_events
            WHERE terminal = 1
              AND duplicate_of_event_id IS NULL
            ORDER BY occurred_at_ms DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    elif user_id:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, occurred_at_ms
            FROM watch_events
            WHERE terminal = 1
              AND duplicate_of_event_id IS NULL
              AND user_id = ?
            ORDER BY occurred_at_ms DESC
            LIMIT ?
            """,
            (user_id, limit * 3),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT rating_key, parent_rating_key, media_type, occurred_at_ms
            FROM watch_events
            WHERE terminal = 1
              AND duplicate_of_event_id IS NULL
              AND user_id IS NULL
            ORDER BY occurred_at_ms DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    lookup_keys: List[str] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        if media == "episode" and parent:
            lookup_keys.append(parent)
        elif key:
            lookup_keys.append(key)
    by_key = _join_library_on_rating_keys(conn, lookup_keys)
    out: List[Tuple[Dict[str, Any], float]] = []
    for row in rows:
        media = str(row["media_type"] or "")
        parent = str(row["parent_rating_key"] or "").strip()
        key = str(row["rating_key"] or "").strip()
        lib_key = parent if media == "episode" and parent else key
        item = by_key.get(lib_key)
        if item is None:
            continue
        try:
            at_ms = float(row["occurred_at_ms"] or 0)
        except (TypeError, ValueError):
            at_ms = 0.0
        out.append((item, at_ms / 1000.0 if at_ms > 1e12 else at_ms))
        if len(out) >= limit:
            break
    return out


def _load_watchlist_seeds(
    conn: Any,
    *,
    user_id: Optional[str],
    household: bool,
    limit: int,
) -> List[Tuple[Dict[str, Any], float]]:
    if not _table_exists(conn, "watchlist_pins"):
        return []
    cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(watchlist_pins)").fetchall()}
    has_plex = "plex_rating_key" in cols
    plex_select = "plex_rating_key," if has_plex else "NULL AS plex_rating_key,"
    if household:
        pins = conn.execute(
            f"""
            SELECT tmdb_id, tvdb_id, media_type, title, created_at, {plex_select}
                   user_id
            FROM watchlist_pins
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    elif user_id:
        pins = conn.execute(
            f"""
            SELECT tmdb_id, tvdb_id, media_type, title, created_at, {plex_select}
                   user_id
            FROM watchlist_pins
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit * 3),
        ).fetchall()
    else:
        pins = conn.execute(
            f"""
            SELECT tmdb_id, tvdb_id, media_type, title, created_at, {plex_select}
                   user_id
            FROM watchlist_pins
            WHERE user_id IS NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()
    out: List[Tuple[Dict[str, Any], float]] = []
    for pin in pins:
        item = None
        plex_key = str(pin["plex_rating_key"] or "").strip() if has_plex else ""
        if plex_key:
            item = conn.execute(
                f"SELECT {_ITEM_COLUMNS} FROM library_items WHERE rating_key = ? LIMIT 1",
                (plex_key,),
            ).fetchone()
        if item is None and pin["tmdb_id"] is not None:
            item = conn.execute(
                f"""
                SELECT {_ITEM_COLUMNS}
                FROM library_items
                WHERE tmdb_id = ? AND media_type = ?
                LIMIT 1
                """,
                (int(pin["tmdb_id"]), str(pin["media_type"] or "movie")),
            ).fetchone()
        if item is None:
            continue
        try:
            created = float(pin["created_at"] or 0)
        except (TypeError, ValueError):
            created = 0.0
        out.append((_as_dict(item), created))
        if len(out) >= limit:
            break
    return out


def _load_library_view_seeds(conn: Any, *, limit: int) -> List[Tuple[Dict[str, Any], float]]:
    """Legacy Plex view_count / last_viewed_at — last resort only."""
    rows = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS}, last_viewed_at
        FROM library_items
        WHERE COALESCE(view_count, 0) > 0
           OR last_viewed_at IS NOT NULL
        ORDER BY COALESCE(last_viewed_at, 0) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out: List[Tuple[Dict[str, Any], float]] = []
    for row in rows:
        payload = _as_dict(row)
        try:
            at = float(payload.pop("last_viewed_at", None) or 0)
        except (TypeError, ValueError):
            at = 0.0
            payload.pop("last_viewed_at", None)
        out.append((payload, at))
    return out


def _collect_seeds_for_scope(
    db: Database,
    *,
    user_id: Optional[str],
    household: bool,
    limit: int,
) -> Dict[int, Dict[str, Any]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    capped = max(1, min(int(limit or 24), 40))
    try:
        with db.connect() as conn:
            for item, at in _load_completion_seeds(
                conn, user_id=user_id, household=household, limit=capped
            ):
                _merge_seed(by_id, item, seed_source="completion", seed_at=at)
            if len(by_id) < capped:
                for item, at in _load_session_seeds(
                    conn, user_id=user_id, household=household, limit=capped
                ):
                    _merge_seed(by_id, item, seed_source="session", seed_at=at)
            if len(by_id) < capped:
                for item, at in _load_terminal_event_seeds(
                    conn, user_id=user_id, household=household, limit=capped
                ):
                    _merge_seed(by_id, item, seed_source="watch_event", seed_at=at)
            for item, at in _load_watchlist_seeds(
                conn, user_id=user_id, household=household, limit=capped
            ):
                _merge_seed(by_id, item, seed_source="watchlist", seed_at=at)
            # Legacy library views only when no stronger watch evidence exists.
            if not any(
                row.get("seed_source") in _SEED_SOURCES_WATCH for row in by_id.values()
            ):
                for item, at in _load_library_view_seeds(conn, limit=capped):
                    _merge_seed(by_id, item, seed_source="library_view", seed_at=at)
    except Exception:  # noqa: BLE001
        return {}
    return by_id


def watched_library_rows(
    db: Database,
    *,
    limit: int = 24,
    user_id: Optional[str] = None,
    multi_user_enabled: bool = False,
) -> List[Dict[str, Any]]:
    """Household (or member) seed titles for inbox bridges, newest first.

    Prefer ``watch_completions``, then recent ``watch_sessions``, then terminal
    ``watch_events``, plus ``watchlist_pins``. Fall back to library view_count
    only when no ledger evidence exists. When ``multi_user_enabled``, prefer the
    acting member's evidence, then fall back to the whole household.
    """
    capped = max(1, min(int(limit or 24), 40))
    by_id: Dict[int, Dict[str, Any]] = {}
    if multi_user_enabled and user_id:
        by_id.update(
            _collect_seeds_for_scope(
                db, user_id=str(user_id), household=False, limit=capped
            )
        )
        if len(by_id) < capped:
            for item_id, row in _collect_seeds_for_scope(
                db, user_id=None, household=True, limit=capped
            ).items():
                if item_id not in by_id:
                    by_id[item_id] = row
    else:
        by_id.update(
            _collect_seeds_for_scope(db, user_id=None, household=True, limit=capped)
        )
    ordered = sorted(
        by_id.values(),
        key=lambda row: float(row.get("seed_at") or 0),
        reverse=True,
    )
    return ordered[:capped]


def _load_items(db: Database, item_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    ids = [int(item_id) for item_id in item_ids if int(item_id) > 0]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    try:
        with db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_ITEM_COLUMNS}
                FROM library_items
                WHERE id IN ({placeholders})
                """,
                tuple(ids),
            ).fetchall()
    except Exception:  # noqa: BLE001
        return {}
    return {int(row["id"]): _as_dict(row) for row in rows}


def _shared_creator(db: Database, left_id: int, right_id: int) -> Optional[str]:
    jobs = ",".join("?" for _ in _CREW_JOBS)
    try:
        with db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT p.name AS name
                FROM credits a
                JOIN credits b
                  ON b.person_id = a.person_id AND b.item_id = ?
                JOIN people p ON p.id = a.person_id
                WHERE a.item_id = ?
                  AND (
                    a.department IN ('Directing', 'Writing')
                    OR lower(COALESCE(a.job, '')) IN ({jobs})
                  )
                  AND (
                    b.department IN ('Directing', 'Writing')
                    OR lower(COALESCE(b.job, '')) IN ({jobs})
                  )
                ORDER BY p.name ASC
                LIMIT 1
                """,
                (int(right_id), int(left_id), *_CREW_JOBS, *_CREW_JOBS),
            ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if row is None:
        return None
    name = str(row["name"] or "").strip()
    return name or None


def _seed_verb(seed: Mapping[str, Any]) -> str:
    source = str(seed.get("seed_source") or "").strip()
    if source == "completion":
        return "finished"
    if source in _SEED_SOURCES_SAVED:
        return "pinned"
    return "watched"


def _inner_link(
    db: Database,
    candidate: Mapping[str, Any],
    seed: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Named link between candidate and seed — never cosine alone."""
    try:
        candidate_id = int(candidate.get("id") or 0)
        seed_id = int(seed.get("id") or 0)
    except (TypeError, ValueError):
        return None
    if candidate_id <= 0 or seed_id <= 0 or candidate_id == seed_id:
        return None

    # Prefer materialized explainable neighbor plot link when present.
    try:
        neighbors = db.get_neighbors(seed_id, limit=24, explainable_only=True) or []
    except Exception:  # noqa: BLE001
        neighbors = []
    for neighbor in neighbors:
        try:
            if int(neighbor["neighbor_id"]) != candidate_id:
                continue
        except (TypeError, ValueError, KeyError):
            continue
        stored = parse_plot_link_json(neighbor["plot_link_json"] if "plot_link_json" in neighbor.keys() else None)
        if stored and stored.get("sentence"):
            return {
                "link_kind": "plot_link",
                "sentence": str(stored["sentence"]),
                "terms": list(stored.get("terms") or []),
            }

    shelf = _labels(candidate.get("genres")) | _labels(candidate.get("keywords"))
    shelf |= _labels(seed.get("genres")) | _labels(seed.get("keywords"))
    link = specific_plot_link(
        seed_text=plot_blob(seed),
        peer_text=plot_blob(candidate),
        shelf_labels=shelf,
    )
    if link and link.get("sentence"):
        return {
            "link_kind": "plot_link",
            "sentence": str(link["sentence"]),
            "terms": list(link.get("terms") or []),
        }

    creator = _shared_creator(db, candidate_id, seed_id)
    if creator:
        return {
            "link_kind": "shared_crew",
            "sentence": f"{creator} worked on both",
            "terms": [creator],
        }

    try:
        candidate_collection = int(candidate.get("tmdb_collection_id") or 0)
        seed_collection = int(seed.get("tmdb_collection_id") or 0)
    except (TypeError, ValueError):
        candidate_collection = 0
        seed_collection = 0
    collection = str(
        candidate.get("collection_name") or seed.get("collection_name") or ""
    ).strip()
    if (
        candidate_collection > 0
        and candidate_collection == seed_collection
        and collection
    ):
        return {
            "link_kind": "collection",
            "sentence": f"both are part of {collection}",
            "terms": [collection],
        }
    return None


def bridge_between(
    db: Database,
    candidate: Mapping[str, Any],
    seed: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Explanation object ``kind=watched_bridge`` naming seed + peer link, or None."""
    try:
        candidate_id = int(candidate.get("id") or 0)
        seed_id = int(seed.get("id") or 0)
    except (TypeError, ValueError):
        return None
    if candidate_id <= 0 or seed_id <= 0 or candidate_id == seed_id:
        return None

    inner = _inner_link(db, candidate, seed)
    if not inner:
        return None

    seed_label = _title_label(seed)
    candidate_label = _title_label(candidate)
    verb = _seed_verb(seed)
    link_sentence = str(inner.get("sentence") or "").strip()
    if not link_sentence:
        return None
    # "Both stories turn on X." → keep as clause after em dash.
    clause = link_sentence[0].lower() + link_sentence[1:] if link_sentence else ""
    if clause.endswith("."):
        clause = clause[:-1]
    sentence = _finish(f"You {verb} {seed_label}; {candidate_label} — {clause}")
    return build_explanation(
        kind="watched_bridge",
        sentence=sentence,
        terms=[str(term) for term in (inner.get("terms") or [])],
        seed_ids=[seed_id],
        peer_id=candidate_id,
        evidence={
            "seed_source": str(seed.get("seed_source") or ""),
            "link_kind": str(inner.get("link_kind") or ""),
            "seed_title": str(seed.get("title") or ""),
        },
    )


def reason_between(db: Database, candidate: Mapping[str, Any], watched: Mapping[str, Any]) -> str:
    """One complete sentence naming the link, or "" when there is none."""
    explanation = bridge_between(db, candidate, watched)
    if not explanation:
        return ""
    return str(explanation.get("sentence") or "")


def specific_reason(
    db: Database,
    candidate: Mapping[str, Any],
    watched_rows: Sequence[Mapping[str, Any]],
) -> str:
    """First recognizable link from ``candidate`` back to something watched."""
    explanation = specific_bridge(db, candidate, watched_rows)
    if not explanation:
        return ""
    return str(explanation.get("sentence") or "")


def specific_bridge(
    db: Database,
    candidate: Mapping[str, Any],
    seed_rows: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """First ``watched_bridge`` explanation from ``candidate`` back to a seed."""
    for seed in seed_rows:
        explanation = bridge_between(db, candidate, seed)
        if explanation and explanation.get("sentence"):
            return explanation
    return None


def _candidate_ids(db: Database, seed_ids: Sequence[int]) -> List[int]:
    found: List[int] = []
    seen = {int(seed_id) for seed_id in seed_ids}

    def _add(item_id: int) -> None:
        if item_id <= 0 or item_id in seen:
            return
        seen.add(item_id)
        found.append(item_id)

    for seed_id in seed_ids:
        try:
            neighbors = db.get_neighbors(int(seed_id), limit=8, explainable_only=True) or []
        except Exception:  # noqa: BLE001
            neighbors = []
        for neighbor in neighbors:
            try:
                if int(neighbor["view_count"] or 0) > 0:
                    continue
                _add(int(neighbor["neighbor_id"]))
            except (TypeError, ValueError, KeyError, IndexError):
                continue
        try:
            with db.connect() as conn:
                seed = conn.execute(
                    """
                    SELECT tmdb_collection_id
                    FROM library_items
                    WHERE id = ?
                    """,
                    (int(seed_id),),
                ).fetchone()
                collection_id = int(seed["tmdb_collection_id"] or 0) if seed else 0
                if collection_id > 0:
                    for row in conn.execute(
                        """
                        SELECT id
                        FROM library_items
                        WHERE tmdb_collection_id = ?
                          AND id != ?
                          AND COALESCE(view_count, 0) = 0
                        LIMIT 8
                        """,
                        (collection_id, int(seed_id)),
                    ):
                        _add(int(row["id"]))
                for row in conn.execute(
                    """
                    SELECT DISTINCT o.item_id AS id
                    FROM credits c
                    JOIN credits o
                      ON o.person_id = c.person_id AND o.item_id != c.item_id
                    JOIN library_items li ON li.id = o.item_id
                    WHERE c.item_id = ?
                      AND COALESCE(li.view_count, 0) = 0
                      AND (
                        c.department IN ('Directing', 'Writing')
                        OR lower(COALESCE(c.job, '')) IN ('director', 'writer', 'screenplay', 'creator')
                      )
                    LIMIT 8
                    """,
                    (int(seed_id),),
                ):
                    _add(int(row["id"]))
        except Exception:  # noqa: BLE001
            continue
        if len(found) >= 40:
            break
    return found[:40]


def _pick_from_row(
    row: Mapping[str, Any],
    *,
    why: str,
    seed_title: Optional[str] = None,
    explanation: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    year = row.get("year")
    try:
        year_int: Optional[int] = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_int = None
    tmdb = row.get("tmdb_id")
    tvdb = row.get("tvdb_id")
    try:
        tmdb_id = int(tmdb) if tmdb is not None else None
    except (TypeError, ValueError):
        tmdb_id = None
    try:
        tvdb_id = int(tvdb) if tvdb is not None else None
    except (TypeError, ValueError):
        tvdb_id = None
    return {
        "id": int(row["id"]),
        "title": str(row.get("title") or "Untitled").strip() or "Untitled",
        "year": year_int,
        "media_type": str(row.get("media_type") or "movie"),
        "tmdb_id": tmdb_id,
        "tvdb_id": tvdb_id,
        "rating_key": str(row.get("rating_key") or "") or None,
        "poster_url": str(row.get("poster_url") or "") or None,
        "why": why,
        "seed_title": seed_title,
        "cluster": None,
        "explanation": dict(explanation) if explanation else None,
    }


def list_linked_unwatched(
    db: Database,
    *,
    limit: int = 12,
    watched_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    user_id: Optional[str] = None,
    multi_user_enabled: bool = False,
) -> List[Dict[str, Any]]:
    """Unwatched titles with named ``watched_bridge`` explanations (inbox refusal rules).

    Same seed ledger, explainable-only candidates, and ``bridge_between`` gate as
    ``pick_linked_unwatched`` — returns up to ``limit`` distinct peers, or [] when
    there is no honest why (never cosine-only filler).
    """
    capped = max(1, min(int(limit or 12), 50))
    watched = (
        list(watched_rows)
        if watched_rows is not None
        else watched_library_rows(
            db, user_id=user_id, multi_user_enabled=multi_user_enabled
        )
    )
    if not watched:
        return []
    seed_ids = []
    for row in watched[:8]:
        try:
            seed_ids.append(int(row["id"]))
        except (TypeError, ValueError, KeyError):
            continue
    if not seed_ids:
        return []
    candidate_ids = _candidate_ids(db, seed_ids)
    loaded = _load_items(db, candidate_ids)
    picks: List[Dict[str, Any]] = []
    for item_id in candidate_ids:
        if len(picks) >= capped:
            break
        row = loaded.get(item_id)
        if row is None:
            continue
        try:
            if int(row.get("view_count") or 0) > 0:
                continue
        except (TypeError, ValueError):
            continue
        explanation = specific_bridge(db, row, watched)
        if not explanation:
            continue
        seed_title = None
        evidence = explanation.get("evidence") if isinstance(explanation.get("evidence"), dict) else {}
        if evidence:
            seed_title = str(evidence.get("seed_title") or "") or None
        picks.append(
            _pick_from_row(
                row,
                why=str(explanation.get("sentence") or ""),
                seed_title=seed_title,
                explanation=explanation,
            )
        )
    if picks:
        return picks
    # Seeds existed but no named peer — prioritize enrichment for those seeds.
    try:
        from projectionist.telemetry.kinship_miss import schedule_kinship_miss

        for seed_id in seed_ids[:8]:
            schedule_kinship_miss(
                item_id=int(seed_id),
                reason="bridge_zero_peers",
                context_source="recommendation_bridge",
            )
    except Exception:  # noqa: BLE001 — never break inbox / explore / nudge picks
        pass
    return []


def pick_linked_unwatched(
    db: Database,
    *,
    watched_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    user_id: Optional[str] = None,
    multi_user_enabled: bool = False,
) -> Optional[Dict[str, Any]]:
    """First unwatched title with a named ``watched_bridge`` to household evidence."""
    picks = list_linked_unwatched(
        db,
        limit=1,
        watched_rows=watched_rows,
        user_id=user_id,
        multi_user_enabled=multi_user_enabled,
    )
    return picks[0] if picks else None


def library_row_for_ref(db: Database, item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve a digest title back to its library row."""
    rating_key = str(item.get("rating_key") or item.get("plex_rating_key") or "").strip()
    tmdb = item.get("tmdb_id")
    try:
        with db.connect() as conn:
            row = None
            if rating_key:
                row = conn.execute(
                    f"SELECT {_ITEM_COLUMNS} FROM library_items WHERE rating_key = ? LIMIT 1",
                    (rating_key,),
                ).fetchone()
            if row is None and tmdb is not None and str(tmdb).strip() != "":
                row = conn.execute(
                    f"SELECT {_ITEM_COLUMNS} FROM library_items WHERE tmdb_id = ? LIMIT 1",
                    (int(tmdb),),
                ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if row is None:
        return None
    return _as_dict(row)
