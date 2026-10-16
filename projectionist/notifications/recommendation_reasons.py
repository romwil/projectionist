"""Reasons a person would recognize for an inbox recommendation.

A recent watch, a new arrival, or an embedding neighbor is not a reason.
The only accepted links are the ones the library graph can name: a specific
plot subject (``specific_plot_link``), a shared director or writer, or a
shared franchise. Callers omit the title when this returns nothing.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.db import Database
from projectionist.library.plot_kinship import plot_blob, specific_plot_link

_CREW_JOBS = ("director", "writer", "screenplay", "creator")
_ITEM_COLUMNS = """
    id, title, year, media_type, tmdb_id, tvdb_id, rating_key, poster_url,
    summary, tmdb_overview, tagline, long_synopsis, llm_logline,
    genres, keywords, tmdb_collection_id, collection_name, view_count
"""


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


def watched_library_rows(db: Database, *, limit: int = 24) -> List[Dict[str, Any]]:
    """Titles this household has actually started, newest first."""
    capped = max(1, min(int(limit or 24), 40))
    try:
        with db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {_ITEM_COLUMNS}
                FROM library_items
                WHERE COALESCE(view_count, 0) > 0
                   OR last_viewed_at IS NOT NULL
                ORDER BY COALESCE(last_viewed_at, 0) DESC, id DESC
                LIMIT ?
                """,
                (capped,),
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [_as_dict(row) for row in rows]


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


def reason_between(db: Database, candidate: Mapping[str, Any], watched: Mapping[str, Any]) -> str:
    """One complete sentence naming the link, or "" when there is none."""
    try:
        candidate_id = int(candidate.get("id") or 0)
        watched_id = int(watched.get("id") or 0)
    except (TypeError, ValueError):
        return ""
    if candidate_id <= 0 or watched_id <= 0 or candidate_id == watched_id:
        return ""

    shelf = _labels(candidate.get("genres")) | _labels(candidate.get("keywords"))
    shelf |= _labels(watched.get("genres")) | _labels(watched.get("keywords"))
    link = specific_plot_link(
        seed_text=plot_blob(watched),
        peer_text=plot_blob(candidate),
        shelf_labels=shelf,
    )
    candidate_label = _title_label(candidate)
    watched_label = _title_label(watched)
    if link and link.get("sentence"):
        story = str(link["sentence"]).strip()
        if story:
            bridge = story[0].lower() + story[1:]
            return _finish(f"{candidate_label} follows {watched_label} because {bridge}")

    creator = _shared_creator(db, candidate_id, watched_id)
    if creator:
        return _finish(
            f"{candidate_label} follows {watched_label} because {creator} worked on both"
        )

    try:
        candidate_collection = int(candidate.get("tmdb_collection_id") or 0)
        watched_collection = int(watched.get("tmdb_collection_id") or 0)
    except (TypeError, ValueError):
        candidate_collection = 0
        watched_collection = 0
    collection = str(
        candidate.get("collection_name") or watched.get("collection_name") or ""
    ).strip()
    if (
        candidate_collection > 0
        and candidate_collection == watched_collection
        and collection
    ):
        return _finish(
            f"{candidate_label} follows {watched_label} because both are part of {collection}"
        )
    return ""


def specific_reason(
    db: Database,
    candidate: Mapping[str, Any],
    watched_rows: Sequence[Mapping[str, Any]],
) -> str:
    """First recognizable link from ``candidate`` back to something watched."""
    for watched in watched_rows:
        sentence = reason_between(db, candidate, watched)
        if sentence:
            return sentence
    return ""


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
            neighbors = db.get_neighbors(int(seed_id), limit=8) or []
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


def _pick_from_row(row: Mapping[str, Any], *, why: str) -> Dict[str, Any]:
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
        "seed_title": None,
        "cluster": None,
    }


def pick_linked_unwatched(
    db: Database,
    *,
    watched_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """First unwatched title with a named link to something already watched."""
    watched = list(watched_rows) if watched_rows is not None else watched_library_rows(db)
    if not watched:
        return None
    seed_ids = []
    for row in watched[:8]:
        try:
            seed_ids.append(int(row["id"]))
        except (TypeError, ValueError, KeyError):
            continue
    if not seed_ids:
        return None
    candidate_ids = _candidate_ids(db, seed_ids)
    loaded = _load_items(db, candidate_ids)
    for item_id in candidate_ids:
        row = loaded.get(item_id)
        if row is None:
            continue
        try:
            if int(row.get("view_count") or 0) > 0:
                continue
        except (TypeError, ValueError):
            continue
        why = specific_reason(db, row, watched)
        if why:
            return _pick_from_row(row, why=why)
    return None


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
