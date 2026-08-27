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

from projectionist.connectors.plex import PlexClient, PlexOnDeckItem
from projectionist.library.db import Database
from projectionist.library.holidays import (
    SEASONAL_FALLBACKS as _SEASONAL_FALLBACK_ROWS,
    compose_rail_items,
    resolve_seasonal_context,
)
from projectionist.library.query import row_to_query_item

DEFAULT_FEED_LIMIT = 12
MAX_FEED_LIMIT = 48
MAX_PAGE_LIMIT = 100
REVISIT_DEFAULT_LIMIT = 20
REVISIT_IDLE_DAYS = 60
MILESTONE_AGES = (5, 10, 15, 20, 25, 30, 40, 50, 75)
DIRECTOR_MIN_TITLES = 3
GENRE_MIN_TITLES = 4

# Legacy label/months/terms shape for callers that still unpack SEASONAL_FALLBACKS.
SEASONAL_FALLBACKS = tuple(
    (label, months, terms) for _scope_id, label, months, terms in _SEASONAL_FALLBACK_ROWS
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


def _is_anniversary_rail_mode(mode: str, label: str) -> bool:
    """True when a seasonal snapshot/rail is an anniversary shelf (not holiday keywords)."""
    mode_l = str(mode or "").strip().lower()
    if mode_l in {"weekend_anniversary", "holiday_anniversary"}:
        return True
    label_l = str(label or "").casefold()
    return "anniversar" in label_l or "on this day" in label_l


def _revalidate_anniversary_snapshot_items(
    db: Database,
    items: Sequence[Mapping[str, Any]],
    selected_day: date,
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    """Drop poisoned anniversary snapshot rows that lack a real month+day match.

    Watched-anniversary rows (``anniversary_text`` starts with \"Watched\") are kept.
    Release rows must join a library item whose release/air date matches
    ``selected_day``'s month+day. Year-only or wrong-day junk is discarded so a
    stale snapshot cannot serve an alphabetical library dump.
    """
    capped = _cap_limit(limit)
    ids: List[int] = []
    for item in items:
        try:
            ids.append(int(item["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    by_id = db.get_library_items_by_ids(ids)
    kept: List[Dict[str, Any]] = []
    for item in items:
        try:
            item_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(item.get("anniversary_text") or "")
        if text.casefold().startswith("watched"):
            kept.append(dict(item))
        else:
            lib = by_id.get(item_id)
            if lib is None:
                continue
            release = _parse_iso_date(_release_iso(lib))
            if release is None:
                continue
            if release.month == selected_day.month and release.day == selected_day.day:
                kept.append(dict(item))
        if len(kept) >= capped:
            break
    return kept


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


def _holiday_observances(db: Database) -> List[Dict[str, Any]]:
    """Load enabled+disabled observances from SQLite (seeds on first read)."""
    try:
        return db.list_holiday_observances(include_disabled=True)
    except Exception:  # noqa: BLE001
        # Pre-migration or bare test doubles — resolve from built-in seeds.
        from projectionist.library.holidays import DEFAULT_OBSERVANCES

        return [
            {
                **seed,
                "enabled": True,
                "is_builtin": True,
                "search_terms": list(seed["search_terms"]),
            }
            for seed in DEFAULT_OBSERVANCES
        ]


def _seasonal_context(
    db: Database, today: date, *, require_schedule_publish: bool = False
) -> Dict[str, Any]:
    ctx = resolve_seasonal_context(
        _holiday_observances(db),
        today,
        require_schedule_publish=require_schedule_publish,
    )
    return {
        "scope_id": ctx.scope_id,
        "label": ctx.label,
        "terms": ctx.terms,
        "mode": ctx.mode,
        "grounding_date": ctx.grounding_date.isoformat() if ctx.grounding_date else None,
        "pre_shoulder_days": ctx.pre_shoulder_days,
        "post_shoulder_days": ctx.post_shoulder_days,
        "schedule_publish": ctx.schedule_publish,
    }


def _match_seasonal_rows(
    rows: Sequence[Mapping[str, Any]], terms: Sequence[str]
) -> List[Mapping[str, Any]]:
    matches: List[Mapping[str, Any]] = []
    for row in rows:
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
    return matches


def _apply_rail_curation(
    db: Database,
    *,
    scope_id: str,
    matches: Sequence[Mapping[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    """pins → includes ∪ matches − excludes; year-sort the unpinned tail."""
    try:
        curation = db.holiday_rail_curation_maps(scope_id)
    except Exception:  # noqa: BLE001
        curation = {"pins": [], "includes": [], "excludes": []}
    pin_ids = list(curation.get("pins") or [])
    include_ids = list(curation.get("includes") or [])
    exclude_ids = list(curation.get("excludes") or [])
    if not pin_ids and not include_ids and not exclude_ids:
        return _sort_rail_items(matches, limit)

    needed_ids = list(dict.fromkeys([*pin_ids, *include_ids]))
    by_id = db.get_library_items_by_ids(needed_ids)
    pin_rows = [by_id[item_id] for item_id in pin_ids if item_id in by_id]
    include_rows = [by_id[item_id] for item_id in include_ids if item_id in by_id]

    def _feed(row: Mapping[str, Any], **extra: Any) -> Dict[str, Any]:
        return _feed_item(row, **extra)

    return compose_rail_items(
        pins=pin_rows,
        includes=include_rows,
        matches=matches,
        excludes=exclude_ids,
        limit=limit,
        feed_item_fn=_feed,
        sort_unpinned_fn=_sort_rail_items,
    )


def feed_seasonal_spotlight(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    today: Optional[date] = None,
    prefer_snapshot: bool = True,
) -> Dict[str, Any]:
    """Holiday-near matching with a modest, explicit season fallback.

    Observances + asymmetric shoulders come from the Admin holiday store.
    Owner rail curation: pins (front) → includes ∪ keyword matches − excludes.
    On weekends (and when a holiday window is active), prefer titles surfaced by
    the anniversary scanner when available — no calendar connector required.
    """
    selected_day = today or date.today()
    capped = _cap_limit(limit)
    context = _seasonal_context(db, selected_day)
    label = str(context["label"])
    terms = tuple(context["terms"] or ())
    mode = str(context["mode"])
    scope_id = str(context["scope_id"])
    is_weekend = selected_day.weekday() >= 5

    # B2: prefer today's scheduled snapshot when present (stable through the day).
    if prefer_snapshot:
        try:
            snapshot = db.get_seasonal_rail_snapshot(selected_day.isoformat())
        except Exception:  # noqa: BLE001
            snapshot = None
        if snapshot and isinstance(snapshot.get("items"), list) and snapshot["items"]:
            snap_label = str(snapshot.get("label") or label)
            snap_mode = str(snapshot.get("mode") or mode)
            raw_items = list(snapshot["items"])
            # Anniversary snapshots can be poisoned by a stale year-only scanner;
            # re-validate against library release dates before serving.
            if _is_anniversary_rail_mode(snap_mode, snap_label):
                items = _revalidate_anniversary_snapshot_items(
                    db, raw_items, selected_day, limit=capped
                )
                if not items:
                    # Fall through to live computation — do not return alpha dump.
                    pass
                else:
                    return {
                        "feed": "seasonal-spotlight",
                        "date": selected_day.isoformat(),
                        "label": snap_label,
                        "mode": snap_mode,
                        "scope_id": str(snapshot.get("scope_id") or scope_id),
                        "grounding_date": context.get("grounding_date"),
                        "pre_shoulder_days": context.get("pre_shoulder_days"),
                        "post_shoulder_days": context.get("post_shoulder_days"),
                        "items": items,
                        "total": len(items),
                        "note": None,
                        "from_schedule": True,
                    }
            else:
                items = raw_items[:capped]
                return {
                    "feed": "seasonal-spotlight",
                    "date": selected_day.isoformat(),
                    "label": snap_label,
                    "mode": snap_mode,
                    "scope_id": str(snapshot.get("scope_id") or scope_id),
                    "grounding_date": context.get("grounding_date"),
                    "pre_shoulder_days": context.get("pre_shoulder_days"),
                    "post_shoulder_days": context.get("post_shoulder_days"),
                    "items": items,
                    "total": len(items),
                    "note": None,
                    "from_schedule": True,
                }

    anniversary_items: List[Mapping[str, Any]] = []
    if is_weekend or mode == "holiday":
        try:
            with db.connect() as conn:
                has = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_anniversaries'"
                ).fetchone()
                if has:
                    rows = conn.execute(
                        """
                        SELECT li.*, a.anniversary_type, a.anniversary_text
                        FROM daily_anniversaries a
                        JOIN library_items li ON li.id = a.item_id
                        WHERE a.scanned_date = ?
                        ORDER BY a.id ASC
                        LIMIT ?
                        """,
                        (selected_day.isoformat(), max(capped * 4, 48)),
                    ).fetchall()
                    # Re-validate release anniversaries against real month+day so a
                    # stale scanner table (year-only false positives) cannot fill the rail.
                    kept: List[Mapping[str, Any]] = []
                    for row in rows:
                        ann_type = str(row["anniversary_type"] or "")
                        if ann_type == "watched_anniversary":
                            kept.append(row)
                            continue
                        if ann_type != "release_anniversary":
                            continue
                        release = _parse_iso_date(_release_iso(row))
                        if release is None:
                            continue
                        if release.month == selected_day.month and release.day == selected_day.day:
                            kept.append(row)
                        if len(kept) >= capped:
                            break
                    anniversary_items = kept
        except Exception:  # noqa: BLE001
            anniversary_items = []

    if anniversary_items:
        items = [_feed_item(row) for row in anniversary_items[:capped]]
        for item, row in zip(items, anniversary_items[:capped]):
            try:
                item["anniversary_text"] = str(row["anniversary_text"] or "")
            except (TypeError, KeyError, IndexError):
                pass
        weekend_label = label
        if is_weekend and mode != "holiday":
            weekend_label = "Weekend anniversaries"
            mode = "weekend_anniversary"
        elif mode == "holiday":
            weekend_label = f"{label} · On this day"
            mode = "holiday_anniversary"
        return {
            "feed": "seasonal-spotlight",
            "date": selected_day.isoformat(),
            "label": weekend_label,
            "mode": mode,
            "scope_id": scope_id,
            "grounding_date": context.get("grounding_date"),
            "pre_shoulder_days": context.get("pre_shoulder_days"),
            "post_shoulder_days": context.get("post_shoulder_days"),
            "items": items,
            "total": len(items),
            "note": None,
            "from_schedule": False,
        }

    matches = _match_seasonal_rows(db.all_library_items(), terms)
    items = _apply_rail_curation(db, scope_id=scope_id, matches=matches, limit=capped)
    if is_weekend and mode == "season":
        label = f"Weekend · {label}"
        mode = "weekend"
    return {
        "feed": "seasonal-spotlight",
        "date": selected_day.isoformat(),
        "label": label,
        "mode": mode,
        "scope_id": scope_id,
        "grounding_date": context.get("grounding_date"),
        "pre_shoulder_days": context.get("pre_shoulder_days"),
        "post_shoulder_days": context.get("post_shoulder_days"),
        "items": items,
        "total": len(matches),
        "note": None if items else f"No {label.lower()} matches in your library yet.",
        "from_schedule": False,
    }


def build_seasonal_rail_snapshot(
    db: Database, *, today: Optional[date] = None, limit: int = DEFAULT_FEED_LIMIT
) -> Dict[str, Any]:
    """Materialize today's seasonal rail for the B2 schedule task / Admin preview."""
    selected_day = today or date.today()
    payload = feed_seasonal_spotlight(
        db, limit=limit, today=selected_day, prefer_snapshot=False
    )
    snapshot = db.save_seasonal_rail_snapshot(
        snapshot_date=selected_day.isoformat(),
        scope_id=str(payload.get("scope_id") or ""),
        label=str(payload.get("label") or ""),
        mode=str(payload.get("mode") or ""),
        items=list(payload.get("items") or []),
    )
    return {"status": "completed", "snapshot": snapshot, "payload": payload}


def preview_holiday_rail(
    db: Database, scope_id: str, *, limit: int = DEFAULT_FEED_LIMIT
) -> Dict[str, Any]:
    """Admin preview for one observance or season scope (ignores active window)."""
    capped = _cap_limit(limit)
    obs = None
    try:
        obs = db.get_holiday_observance(scope_id)
    except Exception:  # noqa: BLE001
        obs = None
    if obs is not None:
        label = str(obs["name"])
        terms = tuple(obs.get("search_terms") or ())
        grounding = obs.get("grounding_date")
        mode = "holiday"
        pre = obs.get("pre_shoulder_days")
        post = obs.get("post_shoulder_days")
    elif scope_id.startswith("season:"):
        label = "Seasonal picks"
        terms: tuple[str, ...] = ()
        grounding = None
        mode = "season"
        pre = None
        post = None
        for sid, lab, _months, t in _SEASONAL_FALLBACK_ROWS:
            if sid == scope_id:
                label = lab
                terms = t
                break
    else:
        raise KeyError("Holiday not found")

    matches = _match_seasonal_rows(db.all_library_items(), terms)
    items = _apply_rail_curation(db, scope_id=scope_id, matches=matches, limit=capped)
    try:
        curation = db.list_holiday_rail_titles(scope_id)
    except Exception:  # noqa: BLE001
        curation = []
    return {
        "scope_id": scope_id,
        "label": label,
        "mode": mode,
        "grounding_date": grounding,
        "pre_shoulder_days": pre,
        "post_shoulder_days": post,
        "items": items,
        "curation": curation,
        "match_count": len(matches),
        "note": None if items else "Add a favorite or loosen filter terms.",
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


def feed_trending(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    offset: int = 0,
    media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Popular owned titles by TMDB ``vote_average`` (movies by default)."""
    capped = _cap_limit(limit, max_limit=MAX_PAGE_LIMIT)
    off = _cap_offset(offset)
    media_filter = _normalize_media_type(media_type) or "movie"
    where_parts = ["vote_average IS NOT NULL", "vote_average > 0"]
    params: List[Any] = []
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
            ORDER BY vote_average DESC, title ASC
            LIMIT ? OFFSET ?
            """,
            tuple(params) + (capped, off),
        ).fetchall()
    items = [_feed_item(row) for row in rows]
    note = None
    if not items:
        note = (
            "No rated titles in the library yet — run library sync or metadata "
            "enrichment for vote_average."
        )
    return {
        "feed": "trending",
        "items": items,
        "total": total,
        "offset": off,
        "limit": capped,
        "has_more": off + len(items) < total,
        "media_type": media_filter,
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
    seed_genres = []
    if "genres" in seed.keys() and seed["genres"]:
        raw_seed_genres = seed["genres"]
        if isinstance(raw_seed_genres, list):
            seed_genres = [str(g) for g in raw_seed_genres if g]
        elif isinstance(raw_seed_genres, str):
            try:
                parsed = json.loads(raw_seed_genres)
            except (TypeError, json.JSONDecodeError):
                parsed = []
            if isinstance(parsed, list):
                seed_genres = [str(g) for g in parsed if g]
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
        # Exact inverse of surprise_score = cosine × (1 − overlap); never invent.
        if score > 0:
            item["metadata_overlap"] = max(0.0, min(1.0, 1.0 - (surprise / score)))
        else:
            item["metadata_overlap"] = None
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
            "genres": seed_genres,
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
