"""Explore hub feed helpers — recently added, recent releases, on-this-day, revisit,
continue-watching.

Honest empties: recent-releases returns ``[]`` when no ``release_date`` /
``first_air_date`` rows exist. On-this-day prefers calendar month-day matches
from those dates; when none exist it falls back to the legacy milestone-year
anniversaries behavior used by ``GET /api/library/anniversaries``.
Revisit These samples partially watched TV idle for 60+ days.
Continue Watching prefers live Plex on-deck reads, then local in-progress rows.
"""

from __future__ import annotations

import json
import time
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from curatorx.connectors.plex import PlexClient, PlexOnDeckItem
from curatorx.library.db import Database
from curatorx.library.query import row_to_query_item

DEFAULT_FEED_LIMIT = 12
MAX_FEED_LIMIT = 48
MAX_PAGE_LIMIT = 100
REVISIT_DEFAULT_LIMIT = 20
REVISIT_IDLE_DAYS = 60
MILESTONE_AGES = (5, 10, 15, 20, 25, 30, 40, 50, 75)
DIRECTOR_MIN_TITLES = 3
GENRE_MIN_TITLES = 4
HOLIDAY_WINDOW_DAYS = 7

# Keep this small, explicit calendar editable in one place. Movable observances
# are calculated in ``_holiday_candidates`` rather than guessed from prose.
FIXED_HOLIDAYS = (
    ("New Year's Day", 1, 1, ("new year", "party", "celebration", "fresh start")),
    ("Groundhog Day", 2, 2, ("groundhog", "winter", "repetition", "small town")),
    ("Valentine's Day", 2, 14, ("romance", "love", "dating", "valentine")),
    ("St. Patrick's Day", 3, 17, ("ireland", "irish", "green", "pub")),
    ("Pi Day", 3, 14, ("math", "science", "pie", "genius")),
    ("Earth Day", 4, 22, ("nature", "environment", "earth", "wildlife")),
    ("May Day", 5, 1, ("spring", "garden", "flower", "festival")),
    ("Independence Day", 7, 4, ("america", "independence", "summer", "fireworks")),
    ("Día de los Muertos", 11, 2, ("afterlife", "spirit", "family", "mexico")),
    ("Halloween", 10, 31, ("horror", "haunted", "ghost", "witch", "monster")),
    ("Winter Solstice", 12, 21, ("winter", "snow", "holiday", "christmas")),
    ("Christmas", 12, 25, ("christmas", "holiday", "winter", "family")),
)
SEASONAL_FALLBACKS = (
    ("Winter nights", (12, 1, 2), ("winter", "snow", "holiday", "christmas")),
    ("Spring awakenings", (3, 4, 5), ("spring", "nature", "garden", "coming of age")),
    ("Summer comfort", (6, 7, 8), ("summer", "road trip", "beach", "vacation")),
    ("Autumn gothic", (9, 10, 11), ("autumn", "fall", "gothic", "mystery", "horror")),
)


def _cap_limit(
    limit: Optional[int],
    *,
    default: int = DEFAULT_FEED_LIMIT,
    max_limit: int = MAX_FEED_LIMIT,
) -> int:
    return min(max(1, int(limit if limit is not None else default)), max_limit)


def _cap_offset(offset: Optional[int]) -> int:
    return max(0, int(offset if offset is not None else 0))


def _normalize_media_type(media_type: Optional[str]) -> Optional[str]:
    normalized = str(media_type or "").strip().lower()
    if normalized in {"movie", "movies"}:
        return "movie"
    if normalized in {"show", "shows", "tv"}:
        return "show"
    return None


def _cap_days(days: Optional[int], *, default: int = 30) -> int:
    return min(max(1, int(days if days is not None else default)), 3650)


def _recent_releases_where_sql(
    earliest_iso: str,
    today_iso: str,
    *,
    media_type: Optional[str] = None,
) -> tuple[str, tuple[Any, ...]]:
    """Shared WHERE clause for recent-releases count + page queries."""
    media_filter = _normalize_media_type(media_type)
    params: List[Any] = []
    if media_filter == "movie":
        return (
            """
            (release_date IS NOT NULL AND release_date != ''
             AND release_date >= ? AND release_date <= ?)
            """,
            (earliest_iso, today_iso),
        )
    if media_filter == "show":
        return (
            """
            (first_air_date IS NOT NULL AND first_air_date != ''
             AND first_air_date >= ? AND first_air_date <= ?)
            """,
            (earliest_iso, today_iso),
        )
    params = (
        earliest_iso,
        today_iso,
        earliest_iso,
        today_iso,
        earliest_iso,
        today_iso,
        earliest_iso,
        today_iso,
    )
    return (
        """
        (
            (media_type = 'movie'
             AND release_date IS NOT NULL AND release_date != ''
             AND release_date >= ? AND release_date <= ?)
            OR
            (media_type = 'show'
             AND first_air_date IS NOT NULL AND first_air_date != ''
             AND first_air_date >= ? AND first_air_date <= ?)
            OR
            (media_type NOT IN ('movie', 'show')
             AND (
               (release_date IS NOT NULL AND release_date != ''
                AND release_date >= ? AND release_date <= ?)
               OR
               (first_air_date IS NOT NULL AND first_air_date != ''
                AND first_air_date >= ? AND first_air_date <= ?)
             ))
        )
        """,
        params,
    )


def _parse_iso_date(raw: Any) -> Optional[date]:
    text = str(raw or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _release_iso(row: Mapping[str, Any]) -> str:
    keys = row.keys()
    media = str(row["media_type"] or "")
    if media == "show" and "first_air_date" in keys and row["first_air_date"]:
        return str(row["first_air_date"])[:10]
    if "release_date" in keys and row["release_date"]:
        return str(row["release_date"])[:10]
    if "first_air_date" in keys and row["first_air_date"]:
        return str(row["first_air_date"])[:10]
    return ""


def _feed_item(row: Mapping[str, Any], **extra: Any) -> Dict[str, Any]:
    item = row_to_query_item(row)
    release = _release_iso(row)
    if release:
        item["release_date"] = release
    if "collection_name" in row.keys() and row["collection_name"]:
        item["collection_name"] = str(row["collection_name"])
    if "tmdb_collection_id" in row.keys() and row["tmdb_collection_id"] is not None:
        item["tmdb_collection_id"] = int(row["tmdb_collection_id"])
    item.update(extra)
    return item


def _json_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(value).strip() for value in raw if str(value).strip()]
    try:
        decoded = json.loads(str(raw or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(value).strip() for value in decoded if str(value).strip()] if isinstance(decoded, list) else []


def _daily_choice(values: Sequence[str], today: date) -> Optional[str]:
    """Stable daily rotation without database state or request-time randomness."""
    ordered = sorted(set(values), key=str.casefold)
    return ordered[today.toordinal() % len(ordered)] if ordered else None


def _sort_rail_items(rows: Sequence[Mapping[str, Any]], limit: int) -> List[Dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -(int(row["year"]) if row["year"] is not None else 0),
            str(row["title"] or "").casefold(),
        ),
    )
    return [_feed_item(row) for row in ordered[:limit]]


def feed_director_spotlight(
    db: Database, *, limit: int = DEFAULT_FEED_LIMIT, today: Optional[date] = None
) -> Dict[str, Any]:
    """Daily rotating filmography rail, only when a director has real depth."""
    selected_day = today or date.today()
    rows = db.all_library_items()
    by_director: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        for director in _json_list(row["directors"]):
            by_director.setdefault(director, []).append(row)
    candidates = [
        name for name, titles in by_director.items() if len(titles) >= DIRECTOR_MIN_TITLES
    ]
    director = _daily_choice(candidates, selected_day)
    if not director:
        return {
            "feed": "director-spotlight", "date": selected_day.isoformat(), "items": [],
            "total": 0, "note": f"Add director credits to show this rail (needs {DIRECTOR_MIN_TITLES} titles per director).",
        }
    items = _sort_rail_items(by_director[director], _cap_limit(limit))
    return {
        "feed": "director-spotlight", "date": selected_day.isoformat(), "director": director,
        "items": items, "total": len(by_director[director]), "note": None,
    }


def feed_genre_spotlight(
    db: Database, *, limit: int = DEFAULT_FEED_LIMIT, today: Optional[date] = None
) -> Dict[str, Any]:
    """Daily rotating genre rail with enough owned titles to feel intentional."""
    selected_day = today or date.today()
    rows = db.all_library_items()
    by_genre: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        for genre in _json_list(row["genres"]):
            by_genre.setdefault(genre, []).append(row)
    candidates = [name for name, titles in by_genre.items() if len(titles) >= GENRE_MIN_TITLES]
    genre = _daily_choice(candidates, selected_day)
    if not genre:
        return {
            "feed": "genre-spotlight", "date": selected_day.isoformat(), "items": [],
            "total": 0, "note": f"Add genre metadata to show this rail (needs {GENRE_MIN_TITLES} titles per genre).",
        }
    items = _sort_rail_items(by_genre[genre], _cap_limit(limit))
    return {
        "feed": "genre-spotlight", "date": selected_day.isoformat(), "genre": genre,
        "items": items, "total": len(by_genre[genre]), "note": None,
    }


def _holiday_candidates(today: date) -> List[tuple[str, date, tuple[str, ...]]]:
    """Return the maintained fixed and movable holiday calendar for this year."""
    candidates = [
        (name, date(today.year, month, day), terms)
        for name, month, day, terms in FIXED_HOLIDAYS
    ]
    april_first = date(today.year, 4, 1)
    arbor_day = date(today.year, 4, 1 + ((4 - april_first.weekday()) % 7) + 21)
    candidates.append(("Arbor Day", arbor_day, ("tree", "forest", "nature", "environment", "garden")))
    september_first = date(today.year, 9, 1)
    labor_day = date(today.year, 9, 1 + ((0 - september_first.weekday()) % 7))
    candidates.append(("Labor Day", labor_day, ("work", "road trip", "summer", "family")))
    november_first = date(today.year, 11, 1)
    thanksgiving = date(today.year, 11, 1 + ((3 - november_first.weekday()) % 7) + 21)
    candidates.append(("Thanksgiving", thanksgiving, ("family", "food", "home", "thanksgiving")))
    return candidates


def _seasonal_context(today: date) -> tuple[str, tuple[str, ...], str]:
    nearest = min(_holiday_candidates(today), key=lambda entry: abs((entry[1] - today).days))
    if abs((nearest[1] - today).days) <= HOLIDAY_WINDOW_DAYS:
        return nearest[0], nearest[2], "holiday"
    for label, months, terms in SEASONAL_FALLBACKS:
        if today.month in months:
            return label, terms, "season"
    return "Seasonal picks", (), "season"


def feed_seasonal_spotlight(
    db: Database, *, limit: int = DEFAULT_FEED_LIMIT, today: Optional[date] = None
) -> Dict[str, Any]:
    """Holiday-near matching with a modest, explicit season fallback."""
    selected_day = today or date.today()
    label, terms, mode = _seasonal_context(selected_day)
    matches: List[Mapping[str, Any]] = []
    for row in db.all_library_items():
        haystack = " ".join(
            [
                str(row["title"] or ""),
                str(row["summary"] or ""),
                " ".join(_json_list(row["genres"])),
                " ".join(_json_list(row["keywords"])),
            ]
        ).casefold()
        if any(term.casefold() in haystack for term in terms):
            matches.append(row)
    items = _sort_rail_items(matches, _cap_limit(limit))
    return {
        "feed": "seasonal-spotlight", "date": selected_day.isoformat(), "label": label,
        "mode": mode, "items": items, "total": len(matches),
        "note": None if items else f"No {label.lower()} matches in your library yet.",
    }


def feed_recently_added(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    days: int = 30,
    offset: int = 0,
    media_type: Optional[str] = None,
) -> Dict[str, Any]:
    capped = _cap_limit(limit, max_limit=MAX_PAGE_LIMIT)
    off = _cap_offset(offset)
    window = _cap_days(days)
    cutoff = int(time.time()) - window * 86400
    media_filter = _normalize_media_type(media_type)
    where_parts = ["added_at IS NOT NULL", "added_at >= ?"]
    params: List[Any] = [cutoff]
    if media_filter:
        where_parts.append("media_type = ?")
        params.append(media_filter)
    where_sql = " AND ".join(where_parts)
    with db.connect() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM library_items WHERE {where_sql}",
            tuple(params),
        ).fetchone()
        total = int(count_row["cnt"] or 0)
        rows = conn.execute(
            f"""
            SELECT *
            FROM library_items
            WHERE {where_sql}
            ORDER BY added_at DESC, title ASC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (capped, off),
        ).fetchall()
    items = [_feed_item(row) for row in rows]
    note = None
    if not items:
        note = (
            "No titles added in this window — or library sync has not recorded "
            "added_at yet."
        )
    return {
        "feed": "recently-added",
        "days": window,
        "items": items,
        "total": total,
        "offset": off,
        "limit": capped,
        "has_more": off + len(items) < total,
        "media_type": media_filter,
        "note": note,
    }


def feed_revisit_these(
    db: Database,
    *,
    limit: int = REVISIT_DEFAULT_LIMIT,
    idle_days: int = REVISIT_IDLE_DAYS,
) -> Dict[str, Any]:
    """Random sample of partially watched TV idle for ``idle_days``+.

    Selection:
    - ``media_type = 'show'``
    - some but not all episodes watched
    - last activity (``last_viewed_at`` or ``last_episode_watched_at``) older
      than ``idle_days`` (default 60 / ~2 months)
    - ``ORDER BY RANDOM()`` capped at ``limit`` (default 20)
    """
    capped = _cap_limit(limit, default=REVISIT_DEFAULT_LIMIT, max_limit=REVISIT_DEFAULT_LIMIT)
    window = _cap_days(idle_days, default=REVISIT_IDLE_DAYS)
    cutoff = int(time.time()) - window * 86400
    where_sql = """
        media_type = 'show'
        AND total_episode_count > 0
        AND unwatched_episode_count > 0
        AND unwatched_episode_count < total_episode_count
        AND COALESCE(last_viewed_at, last_episode_watched_at) IS NOT NULL
        AND COALESCE(last_viewed_at, last_episode_watched_at) > 0
        AND COALESCE(last_viewed_at, last_episode_watched_at) < ?
    """
    with db.connect() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM library_items WHERE {where_sql}",
            (cutoff,),
        ).fetchone()
        total = int(count_row["cnt"] or 0)
        rows = conn.execute(
            f"""
            SELECT *
            FROM library_items
            WHERE {where_sql}
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (cutoff, capped),
        ).fetchall()

    items = [_feed_item(row) for row in rows]
    note = None
    if not items:
        note = (
            "No partially watched shows idle for over two months — "
            "or episode progress has not been synced yet."
        )
    return {
        "feed": "revisit-these",
        "idle_days": window,
        "items": items,
        "total": total,
        "limit": capped,
        "note": note,
    }


def feed_recent_releases(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    days: int = 90,
    offset: int = 0,
    media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Titles whose release/first-air date falls within the last ``days``.

    Returns an honest empty list when the library has no enriched dates.
    """
    capped = _cap_limit(limit, max_limit=MAX_PAGE_LIMIT)
    off = _cap_offset(offset)
    window = _cap_days(days, default=90)
    today = date.today()
    earliest = date.fromordinal(max(date.min.toordinal(), today.toordinal() - window))
    earliest_iso = earliest.isoformat()
    today_iso = today.isoformat()
    media_filter = _normalize_media_type(media_type)

    with db.connect() as conn:
        dated = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE (release_date IS NOT NULL AND release_date != '')
               OR (first_air_date IS NOT NULL AND first_air_date != '')
            """
        ).fetchone()
        has_dates = int(dated["cnt"] or 0) > 0
        if not has_dates:
            return {
                "feed": "recent-releases",
                "days": window,
                "items": [],
                "total": 0,
                "offset": off,
                "limit": capped,
                "has_more": False,
                "media_type": media_filter,
                "note": (
                    "No release_date/first_air_date enriched yet — run library sync "
                    "or metadata_enrichment."
                ),
            }
        where_sql, where_params = _recent_releases_where_sql(
            earliest_iso,
            today_iso,
            media_type=media_filter,
        )
        count_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM library_items WHERE {where_sql}",
            where_params,
        ).fetchone()
        total = int(count_row["cnt"] or 0)
        rows = conn.execute(
            f"""
            SELECT *
            FROM library_items
            WHERE {where_sql}
            ORDER BY COALESCE(
                NULLIF(CASE WHEN media_type = 'show' THEN first_air_date ELSE release_date END, ''),
                NULLIF(release_date, ''),
                NULLIF(first_air_date, '')
            ) DESC, title ASC
            LIMIT ? OFFSET ?
            """,
            where_params + (capped, off),
        ).fetchall()

    items = [_feed_item(row) for row in rows]
    note = None
    if not items:
        note = f"No library titles released in the last {window} days."
    return {
        "feed": "recent-releases",
        "days": window,
        "items": items,
        "total": total,
        "offset": off,
        "limit": capped,
        "has_more": off + len(items) < total,
        "media_type": media_filter,
        "note": note,
    }


def _calendar_on_this_day(
    rows: Sequence[Mapping[str, Any]],
    today: date,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        release = _parse_iso_date(_release_iso(row))
        if release is None:
            continue
        if release.month != today.month or release.day != today.day:
            continue
        if release.year == today.year:
            context = "Released today"
            age = 0
        else:
            age = today.year - release.year
            context = f"Released {age} year{'s' if age != 1 else ''} ago today"
        items.append(
            _feed_item(
                row,
                anniversary_context=context,
                anniversary_type="release_anniversary",
                anniversary_years=age,
            )
        )
        if len(items) >= limit:
            break
    items.sort(
        key=lambda item: (
            -(item.get("anniversary_years") or 0),
            str(item.get("title") or ""),
        )
    )
    return items[:limit]


def _milestone_fallback(
    rows: Sequence[Mapping[str, Any]],
    today: date,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    milestone_years = {today.year - age for age in MILESTONE_AGES}
    items: List[Dict[str, Any]] = []
    for row in rows:
        year = row["year"] if "year" in row.keys() else None
        if year is None:
            continue
        try:
            year_i = int(year)
        except (TypeError, ValueError):
            continue
        if year_i not in milestone_years:
            continue
        age = today.year - year_i
        context = f"Released {age} year{'s' if age != 1 else ''} ago"
        last_viewed = row["last_viewed_at"] if "last_viewed_at" in row.keys() else None
        if last_viewed:
            try:
                months_ago = max(1, int((time.time() - int(last_viewed)) / (30 * 86400)))
                context += f" · Last watched {months_ago} month{'s' if months_ago != 1 else ''} ago"
            except (TypeError, ValueError, OSError):
                pass
        items.append(
            _feed_item(
                row,
                anniversary_context=context,
                anniversary_type="milestone_year",
                anniversary_years=age,
            )
        )
    items.sort(key=lambda item: (item.get("anniversary_years") or 0, str(item.get("title") or "")))
    return items[:limit]


def feed_on_this_day(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    month: Optional[int] = None,
    day: Optional[int] = None,
) -> Dict[str, Any]:
    """Date-aware On This Day with milestone-year fallback.

    When ``release_date`` / ``first_air_date`` month-day matches exist, those
    win (``mode=calendar``). Otherwise falls back to milestone release years
    (5/10/15/…), matching ``GET /api/library/anniversaries`` (``mode=milestone_fallback``).
    """
    capped = _cap_limit(limit)
    today = date.today()
    if month is not None and day is not None:
        try:
            today = date(today.year, int(month), int(day))
        except ValueError:
            pass

    rows = list(db.all_library_items())
    calendar_items = _calendar_on_this_day(rows, today, limit=capped)
    if calendar_items:
        return {
            "feed": "on-this-day",
            "date": today.isoformat(),
            "mode": "calendar",
            "items": calendar_items,
            "total": len(calendar_items),
            "note": None,
        }

    fallback = _milestone_fallback(rows, today, limit=capped)
    note = None
    if not fallback:
        note = (
            "No calendar release anniversaries or milestone years for today. "
            "Enrich release dates for date-aware On This Day."
        )
    elif not any(_release_iso(r) for r in rows):
        note = (
            "Using milestone-year fallback (same idea as /api/library/anniversaries) "
            "because release/first_air dates are not enriched yet."
        )
    else:
        note = (
            "No titles share today's month-day on release/first_air; "
            "showing milestone-year fallback."
        )
    return {
        "feed": "on-this-day",
        "date": today.isoformat(),
        "mode": "milestone_fallback",
        "items": fallback,
        "total": len(fallback),
        "note": note,
    }


def neighbors_payload(
    db: Database,
    item_id: int,
    *,
    mode: str = "similar",
    limit: int = DEFAULT_FEED_LIMIT,
) -> Dict[str, Any]:
    """Cached plot neighbors for Explore / Plot Lab (by library item id)."""
    capped = _cap_limit(limit)
    normalized = str(mode or "similar").strip().lower()
    if normalized not in {"similar", "surprising"}:
        normalized = "similar"
    seed = db.library_item_by_id(int(item_id))
    if seed is None:
        return {
            "item_id": int(item_id),
            "mode": normalized,
            "items": [],
            "total": 0,
            "note": "Library item not found",
        }
    neighbor_rows = db.get_neighbors(int(item_id), mode=normalized, limit=capped)
    items: List[Dict[str, Any]] = []
    for neighbor in neighbor_rows:
        item = _feed_item(neighbor)
        # Prefer neighbor_id as the related title's library id.
        nid = int(neighbor["neighbor_id"]) if "neighbor_id" in neighbor.keys() else int(neighbor["id"])
        item["id"] = nid
        item["neighbor_id"] = nid
        score = float(neighbor["score"] or 0)
        surprise = float(neighbor["surprise_score"] or 0) if "surprise_score" in neighbor.keys() else 0.0
        item["score"] = score
        item["surprise_score"] = surprise
        item["match_score"] = surprise if normalized == "surprising" else score
        item["overview"] = str(neighbor["summary"] or "") if "summary" in neighbor.keys() else ""
        item["in_library"] = True
        items.append(item)
    return {
        "item_id": int(item_id),
        "seed": {
            "id": int(seed["id"]),
            "title": str(seed["title"]),
            "year": seed["year"],
            "media_type": str(seed["media_type"]),
        },
        "mode": normalized,
        "items": items,
        "total": len(items),
        "note": (
            None
            if items
            else "Empty — plot_neighbors cache not built yet for this title."
        ),
    }


def _continue_watching_resume_label(
    *,
    media_type: str,
    view_offset_ms: Optional[int],
    duration_ms: Optional[int],
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    episode_title: str = "",
) -> str:
    parts: List[str] = []
    if media_type == "episode" or season_number is not None or episode_number is not None:
        if season_number is not None and episode_number is not None:
            parts.append(f"S{int(season_number)}E{int(episode_number)}")
        elif episode_title:
            parts.append(episode_title)
    offset = int(view_offset_ms or 0)
    duration = int(duration_ms or 0)
    if offset > 0 and duration > 0:
        pct = min(99, max(1, int(round(100 * offset / duration))))
        parts.append(f"{pct}% watched")
    elif offset > 0:
        mins = max(1, int(round(offset / 60000)))
        parts.append(f"Resume at {mins}m")
    else:
        parts.append("Resume")
    return " · ".join(parts)


def _library_row_for_on_deck(db: Database, entry: "PlexOnDeckItem"):
    """Resolve an on-deck Plex entry to a CuratorX library row."""
    if entry.media_type == "episode":
        if entry.show_rating_key:
            row = db.library_item_by_rating_key(entry.show_rating_key)
            if row is not None:
                return row, "show"
        # Fall back to episode key (rare — usually not indexed as library_items).
        row = db.library_item_by_rating_key(entry.rating_key)
        if row is not None:
            return row, str(row["media_type"] or "show")
        return None, "show"
    row = db.library_item_by_rating_key(entry.rating_key)
    if row is not None:
        return row, str(row["media_type"] or "movie")
    return None, "movie"


def _items_from_plex_on_deck(
    db: Database,
    on_deck: Sequence["PlexOnDeckItem"],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for entry in on_deck:
        row, resolved_type = _library_row_for_on_deck(db, entry)
        if row is None:
            continue
        key = str(row["rating_key"] or "")
        if not key or key in seen:
            continue
        seen.add(key)
        play_key = entry.rating_key  # episode or movie play target
        resume = _continue_watching_resume_label(
            media_type=entry.media_type,
            view_offset_ms=entry.view_offset_ms,
            duration_ms=entry.duration_ms,
            season_number=entry.season_number,
            episode_number=entry.episode_number,
            episode_title=entry.title if entry.media_type == "episode" else "",
        )
        extra: Dict[str, Any] = {
            "in_library": True,
            "card_kind": "continue_watching",
            "resume_label": resume,
            "view_offset_ms": entry.view_offset_ms,
            "duration_ms": entry.duration_ms or (
                int(row["duration_ms"]) if "duration_ms" in row.keys() and row["duration_ms"] is not None else None
            ),
            "play_rating_key": play_key,
            "watch_state": "partial",
        }
        if entry.media_type == "episode":
            extra["continue_episode_title"] = entry.title
            extra["continue_season"] = entry.season_number
            extra["continue_episode"] = entry.episode_number
            if resolved_type == "show":
                # Prefer show poster/title for the rail while Play targets the episode.
                pass
        item = _feed_item(row, **extra)
        # Ensure Play uses the in-progress media (episode) when distinct from show.
        if play_key and play_key != key:
            item["play_rating_key"] = play_key
        items.append(item)
        if len(items) >= limit:
            break
    return items


def _local_continue_watching(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    """Fallback: local in-progress movies + partially watched shows."""
    items: List[Dict[str, Any]] = []
    with db.connect() as conn:
        movie_rows = conn.execute(
            """
            SELECT *
            FROM library_items
            WHERE media_type = 'movie'
              AND COALESCE(view_count, 0) = 0
              AND view_offset_ms IS NOT NULL
              AND view_offset_ms > 0
            ORDER BY COALESCE(last_viewed_at, 0) DESC, title ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for row in movie_rows:
            resume = _continue_watching_resume_label(
                media_type="movie",
                view_offset_ms=int(row["view_offset_ms"] or 0) if "view_offset_ms" in row.keys() else None,
                duration_ms=int(row["duration_ms"] or 0) if "duration_ms" in row.keys() and row["duration_ms"] is not None else None,
            )
            items.append(
                _feed_item(
                    row,
                    in_library=True,
                    card_kind="continue_watching",
                    resume_label=resume,
                    watch_state="partial",
                    play_rating_key=str(row["rating_key"] or ""),
                )
            )
        remaining = max(0, limit - len(items))
        if remaining:
            show_rows = conn.execute(
                """
                SELECT *
                FROM library_items
                WHERE media_type = 'show'
                  AND total_episode_count > 0
                  AND unwatched_episode_count > 0
                  AND unwatched_episode_count < total_episode_count
                ORDER BY COALESCE(last_viewed_at, last_episode_watched_at, 0) DESC, title ASC
                LIMIT ?
                """,
                (remaining,),
            ).fetchall()
            for row in show_rows:
                items.append(
                    _feed_item(
                        row,
                        in_library=True,
                        card_kind="continue_watching",
                        resume_label="Resume",
                        watch_state="partial",
                        play_rating_key=str(row["rating_key"] or ""),
                    )
                )
    return items


def feed_continue_watching(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    plex_client: Optional["PlexClient"] = None,
) -> Dict[str, Any]:
    """Continue Watching rail — Plex on-deck when available, else local progress.

    This is **not** live session / now-playing polling. On-deck is Plex's
    in-progress shelf (``/library/onDeck``).
    """
    capped = _cap_limit(limit)
    source = "local"
    items: List[Dict[str, Any]] = []
    plex_error = None
    if plex_client is not None:
        try:
            on_deck = plex_client.on_deck(limit=capped)
            items = _items_from_plex_on_deck(db, on_deck, limit=capped)
            source = "plex_on_deck"
        except Exception as error:  # noqa: BLE001 — degrade to local
            plex_error = str(error)
            items = []
    if not items:
        items = _local_continue_watching(db, limit=capped)
        source = "local" if not plex_error else "local_after_plex_error"
    note = None
    if not items:
        note = (
            "Nothing in progress — start something in Plex, or wait for watch "
            "progress to sync."
        )
    return {
        "feed": "continue-watching",
        "source": source,
        "items": items,
        "total": len(items),
        "limit": capped,
        "note": note,
        "plex_error": plex_error,
    }
