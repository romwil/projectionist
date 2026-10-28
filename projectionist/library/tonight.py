"""Shared tonight concierge payload (MCP + in-app agent).

TN-01: ``what_to_watch_tonight`` is For you — ``list_linked_unwatched``.
TN-02: sibling ``continue`` from TV progress / paused episodes, not ``watched_bridge``.
XC-03: playable claims require ``in_library`` derived from a ``rating_key``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.db import Database
from projectionist.library.episodes import summarize_tv_progress
from projectionist.notifications.recommendation_reasons import list_linked_unwatched

TONIGHT_EMPTY_NOTE = "No named link to something you finished — not a cosine guess."
DEFAULT_TONIGHT_LIMIT = 8
MAX_TONIGHT_LIMIT = 8
_FETCH_HEADROOM = 50


def _cap_tonight_limit(limit: Any) -> int:
    try:
        value = int(limit if limit is not None else DEFAULT_TONIGHT_LIMIT)
    except (TypeError, ValueError):
        value = DEFAULT_TONIGHT_LIMIT
    return max(1, min(value, MAX_TONIGHT_LIMIT))


def _as_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return row
    keys = row.keys() if hasattr(row, "keys") else []
    return {key: row[key] for key in keys}


def _rating_key(value: Any) -> str:
    return str(value or "").strip()


def _availability(rating_key: Any) -> tuple[bool, bool]:
    """Playable only when a library ``rating_key`` exists (XC-03)."""
    present = bool(_rating_key(rating_key))
    return present, present


def _row_int(row: Mapping[str, Any], key: str) -> Optional[int]:
    if key not in row or row[key] is None:
        return None
    try:
        return int(row[key])
    except (TypeError, ValueError):
        return None


def _paused_minutes(view_offset_ms: Optional[int]) -> Optional[int]:
    if not view_offset_ms or view_offset_ms <= 0:
        return None
    return max(1, int(round(view_offset_ms / 60_000)))


def _continue_sentence(
    title: str,
    *,
    season: Optional[int],
    episode: Optional[int],
    view_offset_ms: Optional[int],
) -> str:
    se = ""
    if season is not None and episode is not None:
        se = f" S{int(season)}E{int(episode)}"
    paused = ""
    minutes = _paused_minutes(view_offset_ms)
    if minutes is not None:
        unit = "minute" if minutes == 1 else "minutes"
        paused = f" (paused {minutes} {unit} in)"
    return f"Finish {title}{se}{paused}."


def _youth_ok(row: Mapping[str, Any], youth_max_rating: Optional[str]) -> bool:
    if not youth_max_rating:
        return True
    from projectionist.youth.rating_gate import content_rating_allowed

    return content_rating_allowed(row.get("content_rating"), max_rating=youth_max_rating)


def _runtimes_by_id(db: Database, item_ids: Sequence[int]) -> Dict[int, Optional[int]]:
    ids = [int(item_id) for item_id in item_ids if item_id]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT id, runtime_minutes FROM library_items WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    out: Dict[int, Optional[int]] = {}
    for row in rows:
        payload = _as_dict(row)
        out[int(payload["id"])] = _row_int(payload, "runtime_minutes")
    return out


def _continue_item(
    *,
    title: str,
    year: Any,
    media_type: str,
    rating_key: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    episode_title: str = "",
    view_offset_ms: Optional[int] = None,
    show_rating_key: str = "",
) -> Dict[str, Any]:
    play_key = _rating_key(rating_key) or _rating_key(show_rating_key)
    in_library, playable = _availability(play_key)
    item: Dict[str, Any] = {
        "title": title,
        "year": int(year) if year is not None else None,
        "media_type": media_type,
        "in_library": in_library,
        "playable": playable,
        "kind": "continue",
        "sentence": _continue_sentence(
            title, season=season, episode=episode, view_offset_ms=view_offset_ms
        ),
    }
    if play_key:
        item["rating_key"] = play_key
    if season is not None:
        item["season"] = int(season)
    if episode is not None:
        item["episode"] = int(episode)
    if episode_title:
        item["episode_title"] = episode_title
    if show_rating_key:
        item["show_rating_key"] = show_rating_key
    return item


def list_tonight_continue(
    db: Database,
    *,
    limit: int = DEFAULT_TONIGHT_LIMIT,
    youth_max_rating: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """In-progress TV (and paused movies) for tonight ``continue``, never watched_bridge."""
    capped = _cap_tonight_limit(limit)
    items: List[Dict[str, Any]] = []
    seen_show_keys: set[str] = set()

    with db.connect() as conn:
        paused_eps = conn.execute(
            """
            SELECT
                le.rating_key AS episode_rating_key,
                le.season_number,
                le.episode_number,
                le.title AS episode_title,
                le.view_offset_ms,
                li.title AS show_title,
                li.year,
                li.rating_key AS show_rating_key,
                li.content_rating
            FROM library_episodes le
            JOIN library_items li ON li.id = le.show_item_id
            WHERE COALESCE(le.view_offset_ms, 0) > 0
              AND COALESCE(le.view_count, 0) = 0
            ORDER BY COALESCE(le.last_viewed_at, 0) DESC, li.title ASC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()

    for raw in paused_eps:
        row = _as_dict(raw)
        if not _youth_ok(row, youth_max_rating):
            continue
        show_key = _rating_key(row.get("show_rating_key"))
        if show_key and show_key in seen_show_keys:
            continue
        if show_key:
            seen_show_keys.add(show_key)
        items.append(
            _continue_item(
                title=str(row.get("show_title") or "").strip() or "Untitled",
                year=row.get("year"),
                media_type="show",
                rating_key=_rating_key(row.get("episode_rating_key")),
                season=_row_int(row, "season_number"),
                episode=_row_int(row, "episode_number"),
                episode_title=str(row.get("episode_title") or "").strip(),
                view_offset_ms=_row_int(row, "view_offset_ms"),
                show_rating_key=show_key,
            )
        )
        if len(items) >= capped:
            return items

    progress = summarize_tv_progress(
        db, group_by="show", in_progress_only=True, limit=capped
    )
    show_titles = [
        str(bucket.get("show_title") or "").strip()
        for bucket in (progress.get("buckets") or [])
        if str(bucket.get("show_title") or "").strip()
    ]
    if show_titles:
        placeholders = ",".join("?" for _ in show_titles)
        with db.connect() as conn:
            show_rows = conn.execute(
                f"""
                SELECT id, title, year, rating_key, content_rating
                FROM library_items
                WHERE media_type = 'show' AND title IN ({placeholders})
                """,
                show_titles,
            ).fetchall()
        by_title = {str(_as_dict(row).get("title") or ""): _as_dict(row) for row in show_rows}
        for title in show_titles:
            if len(items) >= capped:
                break
            show = by_title.get(title)
            if show is None or not _youth_ok(show, youth_max_rating):
                continue
            show_key = _rating_key(show.get("rating_key"))
            if show_key and show_key in seen_show_keys:
                continue
            if show_key:
                seen_show_keys.add(show_key)
            # Show-level resume only. Do not invent the next unwatched episode
            # (season-0 specials / skipped episodes are not on-deck).
            items.append(
                _continue_item(
                    title=title,
                    year=show.get("year"),
                    media_type="show",
                    rating_key=show_key,
                    show_rating_key=show_key,
                )
            )

    if len(items) >= capped:
        return items[:capped]

    remaining = capped - len(items)
    with db.connect() as conn:
        paused_movies = conn.execute(
            """
            SELECT rating_key, title, year, media_type, view_offset_ms, content_rating
            FROM library_items
            WHERE media_type = 'movie'
              AND COALESCE(view_count, 0) = 0
              AND COALESCE(view_offset_ms, 0) > 0
            ORDER BY COALESCE(last_viewed_at, 0) DESC, title ASC
            LIMIT ?
            """,
            (remaining,),
        ).fetchall()
    for raw in paused_movies:
        row = _as_dict(raw)
        if not _youth_ok(row, youth_max_rating):
            continue
        key = _rating_key(row.get("rating_key"))
        if key and key in seen_show_keys:
            continue
        if key:
            seen_show_keys.add(key)
        items.append(
            _continue_item(
                title=str(row.get("title") or "").strip() or "Untitled",
                year=row.get("year"),
                media_type="movie",
                rating_key=key,
                view_offset_ms=_row_int(row, "view_offset_ms"),
            )
        )
        if len(items) >= capped:
            break
    return items[:capped]


def _bridge_item(pick: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    explanation = pick.get("explanation")
    if not isinstance(explanation, dict) or explanation.get("kind") != "watched_bridge":
        return None
    key = _rating_key(pick.get("rating_key"))
    in_library, playable = _availability(key)
    if not in_library:
        return None
    item: Dict[str, Any] = {
        "title": str(pick.get("title") or "").strip() or "Untitled",
        "year": pick.get("year"),
        "media_type": str(pick.get("media_type") or "movie"),
        "in_library": True,
        "playable": playable,
        "rating_key": key,
        "explanation": dict(explanation),
    }
    if pick.get("id") is not None:
        item["id"] = pick["id"]
    if pick.get("tmdb_id") is not None:
        item["tmdb_id"] = pick["tmdb_id"]
    if pick.get("poster_url"):
        item["poster_url"] = pick["poster_url"]
    if pick.get("content_rating"):
        item["content_rating"] = pick["content_rating"]
    why = str(explanation.get("sentence") or pick.get("why") or "").strip()
    if why:
        item["why"] = why
    return item


def build_tonight_watch(
    db: Database,
    *,
    limit: int = DEFAULT_TONIGHT_LIMIT,
    media_type: Optional[str] = None,
    runtime_max: Optional[int] = None,
    youth_max_rating: Optional[str] = None,
    user_id: Optional[str] = None,
    multi_user_enabled: bool = False,
) -> Dict[str, Any]:
    """For you watched_bridge picks plus a sibling continue list."""
    capped = _cap_tonight_limit(limit)
    wanted_type = str(media_type or "").strip().lower() or None
    if wanted_type not in {"movie", "show"}:
        wanted_type = None
    try:
        runtime_cap = int(runtime_max) if runtime_max is not None else None
    except (TypeError, ValueError):
        runtime_cap = None
    if runtime_cap is not None and runtime_cap <= 0:
        runtime_cap = None

    picks = list_linked_unwatched(
        db,
        limit=_FETCH_HEADROOM,
        user_id=user_id,
        multi_user_enabled=multi_user_enabled,
        youth_max_rating=youth_max_rating,
    )
    continue_items = list_tonight_continue(
        db, limit=capped, youth_max_rating=youth_max_rating
    )
    continue_keys = {
        _rating_key(item.get("show_rating_key")) or _rating_key(item.get("rating_key"))
        for item in continue_items
    }
    continue_keys.discard("")

    runtime_needed = runtime_cap is not None
    runtimes = _runtimes_by_id(
        db,
        [int(pick["id"]) for pick in picks if pick.get("id") is not None],
    ) if runtime_needed else {}

    items: List[Dict[str, Any]] = []
    for pick in picks:
        if not isinstance(pick, dict):
            continue
        if wanted_type and str(pick.get("media_type") or "") != wanted_type:
            continue
        if runtime_needed:
            item_id = pick.get("id")
            runtime = runtimes.get(int(item_id)) if item_id is not None else None
            if runtime is None or runtime > runtime_cap:
                continue
        key = _rating_key(pick.get("rating_key"))
        if key and key in continue_keys:
            continue
        item = _bridge_item(pick)
        if item is None:
            continue
        items.append(item)
        if len(items) >= capped:
            break

    empty = not items
    return {
        "mode": "watched_bridge",
        "empty": empty,
        "note": TONIGHT_EMPTY_NOTE if empty else None,
        "items": items,
        "continue": continue_items,
    }
