"""Replace one-title Live cycles with the station recipe's library.

A channel imported from Tunarr can be a single rating key that loops forever
even when the show or collection has more to play. The guide reads
``live_lineup.json``; rebuilding here rewrites that cycle so the next read
does not keep serving the loop.

Quarter-hour flex pads stay: a title that ends off :00/:15/:30/:45 holds with
filler until the next boundary, then the next library title starts. A title
airs again only after the rest of the cycle, unless the library really has
one playable item.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from projectionist.live_channels.filters import normalize_craft_filters
from projectionist.live_channels.filler import pad_lineup_with_flex
from projectionist.live_channels.publish import (
    pad_flex_max_ms,
    recipe_from_station_meta,
    station_meta_row,
)
from projectionist.live_channels.recipes import (
    MediaScope,
    ProgrammingMode,
    normalize_media_scope,
    normalize_programming_mode,
)

_ONLY_ONE_NOTE = (
    "This station has only one playable item in the library, so the guide repeats it."
)
_FILL_CAP = 1000
_MIN_DURATION_MS = 60_000


def rebuild_single_title_cycles(
    doc: Dict[str, Any],
    settings: Any = None,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Expand channels whose cycle is one rating key. Mutates ``doc``.

    Channels that already rotate through more than one title are left alone.
    Returns which channels changed and which still have a single library item.
    """
    channels = doc.get("channels") if isinstance(doc.get("channels"), dict) else None
    report: Dict[str, Any] = {"changed": False, "channels": [], "only_one_playable": []}
    if not channels:
        return report

    single_ids = [
        cid
        for cid, channel in channels.items()
        if isinstance(channel, Mapping) and _is_single_title(channel)
    ]
    if not single_ids:
        return report

    root = Path(data_dir) if data_dir is not None else None
    conn = _open_library(root) if root is not None else None
    if conn is None:
        return report

    try:
        ordered = sorted(single_ids, key=lambda cid: (_channel_number(channels[cid]), str(cid)))
        standing = _standing_keys(channels)
        used_first: Set[str] = set()
        for cid in ordered:
            channel = channels[cid]
            if not isinstance(channel, dict):
                continue
            own = set(_unique_content_keys(channel))
            blocked = (standing - own) | used_first
            outcome = _rebuild_channel(conn, settings, cid, channel, blocked_first=blocked)
            report["channels"].append(outcome)
            if outcome.get("changed"):
                report["changed"] = True
            if outcome.get("only_one_playable"):
                report["only_one_playable"].append(
                    {
                        "id": cid,
                        "name": channel.get("name"),
                        "rating_key": outcome.get("rating_key") or "",
                        "note": _ONLY_ONE_NOTE,
                    }
                )
            else:
                first = _first_content_key(channel)
                if first:
                    used_first.add(first)
                    standing.discard(first)
    finally:
        conn.close()
    return report


def _rebuild_channel(
    conn: sqlite3.Connection,
    settings: Any,
    channel_id: str,
    channel: Dict[str, Any],
    *,
    blocked_first: Set[str],
) -> Dict[str, Any]:
    before = list(_unique_content_keys(channel))
    pool = _pool_for_channel(conn, settings, channel_id, channel)
    outcome: Dict[str, Any] = {
        "id": channel_id,
        "name": channel.get("name"),
        "before": before,
        "after": before,
        "changed": False,
        "only_one_playable": False,
    }
    if len(pool) <= 1:
        if len(pool) == 1:
            outcome["only_one_playable"] = True
            outcome["rating_key"] = pool[0]["plex_rating_key"]
            outcome["after"] = [pool[0]["plex_rating_key"]]
            try:
                start_ms = int(channel.get("start_time_ms") or 0)
            except (TypeError, ValueError):
                start_ms = 0
            items = _items_with_quarter_hour_flex(
                pool,
                start_time_ms=start_ms,
                max_flex_ms=pad_flex_max_ms(settings),
            )
            if items != list(channel.get("items") or []) or channel.get("library_repeat_note") != _ONLY_ONE_NOTE:
                channel["items"] = items
                channel["library_repeat_note"] = _ONLY_ONE_NOTE
                outcome["changed"] = True
        return outcome

    mode = _programming_mode(settings, channel_id)
    ordered = list(pool)
    if mode == ProgrammingMode.SHUFFLE:
        random.Random(str(channel_id)).shuffle(ordered)
    ordered = _rotate_off_blocked(ordered, blocked_first)
    try:
        start_ms = int(channel.get("start_time_ms") or 0)
    except (TypeError, ValueError):
        start_ms = 0
    items = _items_with_quarter_hour_flex(
        ordered,
        start_time_ms=start_ms,
        max_flex_ms=pad_flex_max_ms(settings),
    )
    after = _unique_content_keys({"items": items})
    outcome["after"] = after
    if items != list(channel.get("items") or []) or channel.get("library_repeat_note"):
        channel["items"] = items
        channel.pop("library_repeat_note", None)
        outcome["changed"] = True
    return outcome


def _pool_for_channel(
    conn: sqlite3.Connection,
    settings: Any,
    channel_id: str,
    channel: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    recipe = recipe_from_station_meta(
        settings,
        channel_id,
        name=str(channel.get("name") or ""),
        number=_channel_number(channel) or 100,
    )
    if recipe is None:
        return []
    meta = station_meta_row(settings, channel_id)
    show = _find_show(conn, recipe, meta)
    scope = normalize_media_scope(getattr(recipe, "media_scope", None))
    source = str(getattr(recipe, "source", "") or "").strip().lower()
    if show is not None and (source == "show" or scope == MediaScope.TV.value or not _movie_recipe(recipe)):
        return _episodes_for_show(conn, int(show["id"]), str(show["title"] or ""))
    if source == "collection" or str(getattr(recipe, "collection_id", "") or "").strip() or str(
        getattr(recipe, "collection_title", "") or ""
    ).strip():
        movies = _collection_movies(conn, recipe)
        if movies:
            return movies
    if scope == MediaScope.TV.value:
        return []
    return _filtered_movies(conn, recipe)


def _movie_recipe(recipe: Any) -> bool:
    filters = normalize_craft_filters(getattr(recipe, "craft_filters", None))
    return bool(
        str(getattr(recipe, "collection_id", "") or "").strip()
        or str(getattr(recipe, "collection_title", "") or "").strip()
        or not filters.is_empty()
        or str(getattr(recipe, "motif", "") or "").strip()
    )


def _programming_mode(settings: Any, channel_id: str) -> ProgrammingMode:
    row = station_meta_row(settings, channel_id)
    source = str(row.get("source") or "").strip().lower()
    default = (
        ProgrammingMode.SEQUENTIAL
        if source in {"collection", "show"}
        else ProgrammingMode.SHUFFLE
    )
    raw = str(row.get("programming_mode") or "").strip()
    if raw:
        return normalize_programming_mode(raw, default=default)
    return default


def _find_show(
    conn: sqlite3.Connection,
    recipe: Any,
    meta: Mapping[str, Any],
) -> Optional[sqlite3.Row]:
    keys: List[str] = []
    for key in list(getattr(recipe, "item_rating_keys", ()) or ()) + [
        meta.get("show_plex_key")
    ]:
        text = str(key or "").strip()
        if text and text not in keys:
            keys.append(text)
    for key in keys:
        show = _show_by_rating_key(conn, key)
        if show is not None:
            return show
        episode = _episode_row(conn, key)
        if episode is not None:
            show = _show_by_id(conn, int(episode["show_item_id"]))
            if show is not None:
                return show
    titles: List[str] = []
    for raw in list(getattr(recipe, "item_hints", ()) or ()) + [
        getattr(recipe, "collection_title", "")
    ]:
        text = str(raw or "").strip()
        if text and text.casefold() not in {t.casefold() for t in titles}:
            titles.append(text)
    for title in titles:
        show = _show_by_title(conn, title)
        if show is not None:
            return show
    return None


def _episodes_for_show(
    conn: sqlite3.Connection,
    show_id: int,
    show_title: str,
) -> List[Dict[str, Any]]:
    cols = _columns(conn, "library_episodes")
    duration_sql = "duration_ms" if "duration_ms" in cols else "NULL"
    rows = conn.execute(
        f"""
        SELECT rating_key, season_number, episode_number, title, runtime_minutes,
               {duration_sql} AS duration_ms
        FROM library_episodes
        WHERE show_item_id = ?
        ORDER BY COALESCE(season_number, 0), COALESCE(episode_number, 0), id
        LIMIT ?
        """,
        (show_id, _FILL_CAP),
    ).fetchall()
    show = _show_by_id(conn, show_id)
    year = show["year"] if show is not None and "year" in show.keys() else None
    rating = ""
    summary = ""
    if show is not None:
        if "content_rating" in show.keys():
            rating = str(show["content_rating"] or "")
        if "summary" in show.keys():
            summary = str(show["summary"] or "")
    programs: List[Dict[str, Any]] = []
    for row in rows:
        duration = _duration_ms(row["duration_ms"], row["runtime_minutes"])
        key = str(row["rating_key"] or "").strip()
        if not key or duration < _MIN_DURATION_MS:
            continue
        programs.append(
            {
                "plex_rating_key": key,
                "title": str(row["title"] or "").strip() or "Untitled",
                "show_title": show_title,
                "season": row["season_number"],
                "episode": row["episode_number"],
                "year": year,
                "overview": summary,
                "content_rating": rating,
                "media_type": "episode",
                "duration_ms": duration,
            }
        )
    return programs


def _collection_movies(conn: sqlite3.Connection, recipe: Any) -> List[Dict[str, Any]]:
    cols = _columns(conn, "library_items")
    title = str(getattr(recipe, "collection_title", "") or "").strip()
    cid = str(getattr(recipe, "collection_id", "") or "").strip()
    clauses: List[str] = []
    params: List[Any] = []
    if title and "collection_name" in cols:
        clauses.append("lower(collection_name) = ?")
        params.append(title.casefold())
    if cid.isdigit() and "tmdb_collection_id" in cols:
        clauses.append("tmdb_collection_id = ?")
        params.append(int(cid))
    keys = [
        str(key).strip()
        for key in (getattr(recipe, "item_rating_keys", ()) or ())
        if str(key).strip()
    ]
    if len(keys) > 1:
        marks = ",".join("?" for _ in keys)
        clauses.append(f"rating_key IN ({marks})")
        params.extend(keys)
    if not clauses:
        return []
    where = " OR ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT * FROM library_items
        WHERE media_type = 'movie' AND ({where})
        ORDER BY COALESCE(year, 0), title, rating_key
        LIMIT ?
        """,
        (*params, _FILL_CAP),
    ).fetchall()
    return [_movie_program(row) for row in rows if _movie_program(row)]


def _filtered_movies(conn: sqlite3.Connection, recipe: Any) -> List[Dict[str, Any]]:
    filters = normalize_craft_filters(getattr(recipe, "craft_filters", None))
    motif = str(getattr(recipe, "motif", "") or "").strip()
    if filters.is_empty() and not motif:
        return []
    cols = _columns(conn, "library_items")
    year_sql = []
    params: List[Any] = []
    if filters.year_from is not None:
        year_sql.append("year >= ?")
        params.append(int(filters.year_from))
    if filters.year_to is not None:
        year_sql.append("year <= ?")
        params.append(int(filters.year_to))
    where_year = (" AND " + " AND ".join(year_sql)) if year_sql else ""
    rows = conn.execute(
        f"""
        SELECT * FROM library_items
        WHERE media_type = 'movie'
          AND rating_key IS NOT NULL AND rating_key != ''
          {where_year}
        ORDER BY COALESCE(year, 0), title, rating_key
        LIMIT ?
        """,
        (*params, 5000),
    ).fetchall()
    if not rows:
        return []
    facet_index = _facet_index(conn, [int(row["id"]) for row in rows])
    wanted_genres = {g.casefold() for g in filters.genres}
    wanted_themes = {t.casefold() for t in filters.themes}
    wanted_motifs = {m.casefold() for m in filters.motifs}
    if motif:
        wanted_motifs.add(motif.casefold())
    wanted_ratings = {r.casefold() for r in filters.content_ratings}
    matched: List[Dict[str, Any]] = []
    for row in rows:
        if wanted_genres and not wanted_genres.issubset(_text_set(row, "genres")):
            continue
        facets = facet_index.get(int(row["id"]), {})
        if wanted_themes and not wanted_themes.issubset(facets.get("theme", set())):
            continue
        if wanted_motifs and not wanted_motifs.issubset(facets.get("motif", set())):
            continue
        if wanted_ratings and "content_rating" in cols:
            if str(row["content_rating"] or "").strip().casefold() not in wanted_ratings:
                continue
        program = _movie_program(row)
        if program:
            matched.append(program)
        if len(matched) >= _FILL_CAP:
            break
    return matched


def _movie_program(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    key = str(row["rating_key"] or "").strip()
    duration = _duration_ms(
        row["duration_ms"] if "duration_ms" in row.keys() else None,
        row["runtime_minutes"] if "runtime_minutes" in row.keys() else None,
    )
    if not key or duration < _MIN_DURATION_MS:
        return None
    summary = str(row["summary"] or "") if "summary" in row.keys() else ""
    rating = str(row["content_rating"] or "") if "content_rating" in row.keys() else ""
    return {
        "plex_rating_key": key,
        "title": str(row["title"] or "").strip() or "Untitled",
        "show_title": "",
        "season": None,
        "episode": None,
        "year": row["year"] if "year" in row.keys() else None,
        "overview": summary,
        "content_rating": rating,
        "media_type": "movie",
        "duration_ms": duration,
    }


def _items_with_quarter_hour_flex(
    programs: Sequence[Mapping[str, Any]],
    *,
    start_time_ms: int,
    max_flex_ms: int,
) -> List[Dict[str, Any]]:
    by_key = {str(row["plex_rating_key"]): row for row in programs}
    lineup = [
        {
            "type": "content",
            "id": str(row["plex_rating_key"]),
            "duration": int(row["duration_ms"]),
        }
        for row in programs
    ]
    padded = pad_lineup_with_flex(
        lineup,
        max_flex_ms=max_flex_ms,
        start_time_ms=start_time_ms,
    )
    stored: List[Dict[str, Any]] = []
    for row in padded:
        if str(row.get("type") or "") == "flex":
            stored.append({"type": "flex", "duration_ms": int(row["duration"])})
            continue
        program = by_key.get(str(row.get("id") or ""))
        if program is None:
            continue
        stored.append(
            {
                "type": "content",
                "duration_ms": int(row.get("duration") or program["duration_ms"]),
                "program_id": str(program["plex_rating_key"]),
                "title": program["title"],
                "show_title": program["show_title"],
                "season": program["season"],
                "episode": program["episode"],
                "year": program["year"],
                "overview": program["overview"],
                "content_rating": program["content_rating"],
                "media_type": program["media_type"],
                "plex_rating_key": program["plex_rating_key"],
            }
        )
    return stored


def _rotate_off_blocked(
    programs: Sequence[Mapping[str, Any]],
    blocked_first: Set[str],
) -> List[Mapping[str, Any]]:
    rows = list(programs)
    if len(rows) < 2 or not blocked_first:
        return rows
    for shift in range(len(rows)):
        rotated = rows[shift:] + rows[:shift]
        if str(rotated[0].get("plex_rating_key") or "") not in blocked_first:
            return rotated
    return rows


def _facet_index(
    conn: sqlite3.Connection,
    item_ids: Sequence[int],
) -> Dict[int, Dict[str, Set[str]]]:
    if not item_ids or not _table_exists(conn, "library_facets"):
        return {}
    found: Dict[int, Dict[str, Set[str]]] = {}
    step = 400
    for start in range(0, len(item_ids), step):
        chunk = item_ids[start : start + step]
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT item_id, facet_type, facet_value
            FROM library_facets
            WHERE item_id IN ({marks})
              AND facet_type IN ('theme', 'motif')
            """,
            list(chunk),
        ).fetchall()
        for row in rows:
            bucket = found.setdefault(int(row["item_id"]), {})
            kind = str(row["facet_type"] or "")
            bucket.setdefault(kind, set()).add(str(row["facet_value"] or "").casefold())
    return found


def _text_set(row: sqlite3.Row, column: str) -> Set[str]:
    if column not in row.keys():
        return set()
    raw = row[column]
    values: List[Any]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in raw.split(",") if part.strip()]
        values = parsed if isinstance(parsed, list) else []
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _show_by_rating_key(conn: sqlite3.Connection, rating_key: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM library_items
        WHERE rating_key = ? AND media_type = 'show'
        """,
        (rating_key,),
    ).fetchone()


def _show_by_id(conn: sqlite3.Connection, show_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM library_items WHERE id = ? AND media_type = 'show'",
        (show_id,),
    ).fetchone()


def _show_by_title(conn: sqlite3.Connection, title: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM library_items
        WHERE media_type = 'show' AND lower(title) = lower(?)
        """,
        (title,),
    ).fetchone()


def _episode_row(conn: sqlite3.Connection, rating_key: str) -> Optional[sqlite3.Row]:
    if not _table_exists(conn, "library_episodes"):
        return None
    return conn.execute(
        "SELECT * FROM library_episodes WHERE rating_key = ?",
        (rating_key,),
    ).fetchone()


def _open_library(data_dir: Path) -> Optional[sqlite3.Connection]:
    path = Path(data_dir) / "projectionist.db"
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    conn.row_factory = sqlite3.Row
    if not _table_exists(conn, "library_items"):
        conn.close()
        return None
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _duration_ms(duration_ms: Any, runtime_minutes: Any) -> int:
    try:
        exact = int(duration_ms or 0)
    except (TypeError, ValueError):
        exact = 0
    if exact >= _MIN_DURATION_MS:
        return exact
    try:
        minutes = int(runtime_minutes or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return 0
    return minutes * 60 * 1000


def _is_single_title(channel: Mapping[str, Any]) -> bool:
    return len(_unique_content_keys(channel)) <= 1


def _unique_content_keys(channel: Mapping[str, Any]) -> List[str]:
    seen: List[str] = []
    for item in _content_items(channel):
        key = str(item.get("plex_rating_key") or item.get("program_id") or "").strip()
        if key and key not in seen:
            seen.append(key)
    return seen


def _content_items(channel: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    items = channel.get("items") if isinstance(channel.get("items"), list) else []
    return [
        item
        for item in items
        if isinstance(item, Mapping) and str(item.get("type") or "content").lower() == "content"
    ]


def _first_content_key(channel: Mapping[str, Any]) -> str:
    for item in _content_items(channel):
        key = str(item.get("plex_rating_key") or "").strip()
        if key:
            return key
    return ""


def _standing_keys(channels: Mapping[str, Any]) -> Set[str]:
    standing: Set[str] = set()
    for channel in channels.values():
        if not isinstance(channel, Mapping):
            continue
        keys = _unique_content_keys(channel)
        if len(keys) == 1:
            standing.add(keys[0])
    return standing


def _channel_number(channel: Mapping[str, Any]) -> int:
    try:
        return int(channel.get("number") or 0)
    except (TypeError, ValueError):
        return 0
