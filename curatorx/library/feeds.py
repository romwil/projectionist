"""Explore hub feed helpers — recently added, recent releases, on-this-day.

Honest empties: recent-releases returns ``[]`` when no ``release_date`` /
``first_air_date`` rows exist. On-this-day prefers calendar month-day matches
from those dates; when none exist it falls back to the legacy milestone-year
anniversaries behavior used by ``GET /api/library/anniversaries``.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from curatorx.library.db import Database
from curatorx.library.query import row_to_query_item

DEFAULT_FEED_LIMIT = 12
MAX_FEED_LIMIT = 48
MILESTONE_AGES = (5, 10, 15, 20, 25, 30, 40, 50, 75)


def _cap_limit(limit: Optional[int], *, default: int = DEFAULT_FEED_LIMIT) -> int:
    return min(max(1, int(limit if limit is not None else default)), MAX_FEED_LIMIT)


def _cap_days(days: Optional[int], *, default: int = 30) -> int:
    return min(max(1, int(days if days is not None else default)), 3650)


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


def feed_recently_added(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    days: int = 30,
) -> Dict[str, Any]:
    capped = _cap_limit(limit)
    window = _cap_days(days)
    cutoff = int(time.time()) - window * 86400
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM library_items
            WHERE added_at IS NOT NULL AND added_at >= ?
            ORDER BY added_at DESC, title ASC
            LIMIT ?
            """,
            (cutoff, capped),
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
        "total": len(items),
        "note": note,
    }


def feed_recent_releases(
    db: Database,
    *,
    limit: int = DEFAULT_FEED_LIMIT,
    days: int = 90,
) -> Dict[str, Any]:
    """Titles whose release/first-air date falls within the last ``days``.

    Returns an honest empty list when the library has no enriched dates.
    """
    capped = _cap_limit(limit)
    window = _cap_days(days, default=90)
    today = date.today()
    earliest = date.fromordinal(max(date.min.toordinal(), today.toordinal() - window))
    earliest_iso = earliest.isoformat()
    today_iso = today.isoformat()

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
                "note": (
                    "No release_date/first_air_date enriched yet — run library sync "
                    "or metadata_enrichment."
                ),
            }
        rows = conn.execute(
            """
            SELECT *
            FROM library_items
            WHERE (
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
            ORDER BY COALESCE(
                NULLIF(CASE WHEN media_type = 'show' THEN first_air_date ELSE release_date END, ''),
                NULLIF(release_date, ''),
                NULLIF(first_air_date, '')
            ) DESC, title ASC
            LIMIT ?
            """,
            (
                earliest_iso,
                today_iso,
                earliest_iso,
                today_iso,
                earliest_iso,
                today_iso,
                earliest_iso,
                today_iso,
                capped,
            ),
        ).fetchall()

    items = [_feed_item(row) for row in rows]
    note = None
    if not items:
        note = f"No library titles released in the last {window} days."
    return {
        "feed": "recent-releases",
        "days": window,
        "items": items,
        "total": len(items),
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
