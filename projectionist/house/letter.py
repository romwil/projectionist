"""Compose the owner house letter — prose, not dashboard tiles."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from projectionist.library.db import Database
from projectionist.library.health import STALE_ADD_DAYS

DEAD_WEIGHT_LIMIT = 6
LETTER_TITLE = "A letter about the house"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def format_hours(ms: int) -> str:
    hours = max(0, int(ms or 0)) / 3_600_000.0
    if hours <= 0:
        return "no timed hours"
    if hours < 1:
        return "less than an hour"
    if hours < 10:
        return f"{hours:.1f} hours"
    return f"{int(round(hours))} hours"


def format_bytes(size: int) -> str:
    value = max(0, int(size or 0))
    if value <= 0:
        return "an unknown amount of disk"
    units = (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024))
    for label, step in units:
        if value >= step:
            amount = value / step
            if amount >= 10:
                return f"{int(round(amount))} {label}"
            return f"{amount:.1f} {label}"
    return f"{value} bytes"


def _title_label(row: Dict[str, Any]) -> str:
    title = str(row.get("title") or "Untitled").strip() or "Untitled"
    year = row.get("year")
    return f"{title} ({year})" if year else title


def gather_house_stats(db: Database, *, now: Optional[float] = None) -> Dict[str, Any]:
    """Unwatched hours, dead weight, and disk — the letter's facts."""
    ts = time.time() if now is None else float(now)
    stale_cutoff = ts - STALE_ADD_DAYS * 86400
    with db.connect() as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN view_count IS NULL OR view_count = 0 THEN 1 ELSE 0 END) AS unwatched,
              COALESCE(SUM(COALESCE(file_size, 0)), 0) AS bytes_on_disk,
              COALESCE(SUM(CASE WHEN media_type = 'movie' THEN COALESCE(file_size, 0) ELSE 0 END), 0) AS movie_bytes,
              COALESCE(SUM(CASE WHEN media_type = 'show' THEN COALESCE(file_size, 0) ELSE 0 END), 0) AS show_bytes
            FROM library_items
            """
        ).fetchone()
        unwatched_ms = conn.execute(
            """
            SELECT COALESCE(SUM(duration_ms), 0) AS ms
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND duration_ms IS NOT NULL
              AND duration_ms > 0
            """
        ).fetchone()
        episode_ms = None
        try:
            episode_ms = conn.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) AS ms
                FROM library_episodes
                WHERE (view_count IS NULL OR view_count = 0)
                  AND duration_ms IS NOT NULL
                  AND duration_ms > 0
                """
            ).fetchone()
        except Exception:  # noqa: BLE001 — older fixtures may lack the table
            episode_ms = None
        dead_rows = conn.execute(
            """
            SELECT id, title, year, media_type, file_size, added_at, rating_key, tmdb_id
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND added_at IS NOT NULL
              AND added_at < ?
            ORDER BY COALESCE(file_size, 0) DESC, title ASC
            LIMIT ?
            """,
            (stale_cutoff, DEAD_WEIGHT_LIMIT),
        ).fetchall()
        dead_summary = conn.execute(
            """
            SELECT
              COUNT(*) AS cnt,
              COALESCE(SUM(COALESCE(file_size, 0)), 0) AS bytes_on_disk
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND added_at IS NOT NULL
              AND added_at < ?
            """,
            (stale_cutoff,),
        ).fetchone()

    total = _as_int(totals["total"] if totals else 0)
    unwatched = _as_int(totals["unwatched"] if totals else 0)
    disk_bytes = _as_int(totals["bytes_on_disk"] if totals else 0)
    movie_bytes = _as_int(totals["movie_bytes"] if totals else 0)
    show_bytes = _as_int(totals["show_bytes"] if totals else 0)
    movie_ms = _as_int(unwatched_ms["ms"] if unwatched_ms else 0)
    show_episode_ms = _as_int(episode_ms["ms"] if episode_ms else 0)
    unwatched_ms_total = movie_ms + show_episode_ms
    dead_count = _as_int(dead_summary["cnt"] if dead_summary else 0)
    dead_bytes = _as_int(dead_summary["bytes_on_disk"] if dead_summary else 0)

    dead_weight: List[Dict[str, Any]] = []
    for row in dead_rows or []:
        dead_weight.append(
            {
                "id": _as_int(row["id"]),
                "title": str(row["title"] or "Untitled"),
                "year": _as_int(row["year"]) if row["year"] is not None else None,
                "media_type": str(row["media_type"] or "movie"),
                "file_size": _as_int(row["file_size"]),
                "added_at": float(row["added_at"]) if row["added_at"] else None,
                "rating_key": str(row["rating_key"]) if row["rating_key"] else None,
                "tmdb_id": _as_int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
                "label": _title_label(
                    {
                        "title": row["title"],
                        "year": row["year"],
                    }
                ),
            }
        )

    unwatched_pct = round((unwatched / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "unwatched_count": unwatched,
        "unwatched_pct": unwatched_pct,
        "unwatched_ms": unwatched_ms_total,
        "unwatched_hours_label": format_hours(unwatched_ms_total),
        "disk_bytes": disk_bytes,
        "disk_label": format_bytes(disk_bytes),
        "movie_bytes": movie_bytes,
        "show_bytes": show_bytes,
        "movie_disk_label": format_bytes(movie_bytes),
        "show_disk_label": format_bytes(show_bytes),
        "stale_add_days": STALE_ADD_DAYS,
        "dead_weight_count": dead_count,
        "dead_weight_bytes": dead_bytes,
        "dead_weight_label": format_bytes(dead_bytes) if dead_bytes else "no sized files yet",
        "dead_weight": dead_weight,
        "generated_at": ts,
    }


def _paragraphs_for(stats: Dict[str, Any]) -> List[Dict[str, str]]:
    total = int(stats.get("total") or 0)
    if total <= 0:
        return [
            {
                "kind": "empty",
                "text": (
                    "The house is quiet. There is no library index yet, so I cannot tell you "
                    "about unwatched hours or disk. Sync from Admin → Libraries when you are "
                    "ready. I will write again after that."
                ),
            }
        ]

    unwatched = int(stats.get("unwatched_count") or 0)
    hours = str(stats.get("unwatched_hours_label") or "no timed hours")
    pct = stats.get("unwatched_pct")
    if unwatched <= 0:
        watch_text = (
            "Every title on the shelves has been sat with at least once. That is rare. "
            "The house is not waiting — it is ready for a rewatch or a gift."
        )
    elif hours == "no timed hours":
        watch_text = (
            f"There are {unwatched} titles nobody has sat with yet"
            f"{f' — about {pct}% of the shelves' if total else ''}. "
            "I do not have runtimes for them yet, so I will not invent hours."
        )
    else:
        watch_text = (
            f"There are {hours} of film and television that have never been sat with — "
            f"{unwatched} title{'s' if unwatched != 1 else ''}"
            f"{f', about {pct}% of the shelves' if total else ''}. "
            "That is not a failure. It is inventory waiting for a night."
        )

    dead_count = int(stats.get("dead_weight_count") or 0)
    stale_days = int(stats.get("stale_add_days") or STALE_ADD_DAYS)
    heaviest = (stats.get("dead_weight") or [None])[0]
    if dead_count <= 0:
        dead_text = (
            f"Nothing has sat unwatched for more than {stale_days} days with weight on disk. "
            "The house is not carrying dead weight right now."
        )
    else:
        heaviest_bit = ""
        if isinstance(heaviest, dict) and heaviest.get("label"):
            size = format_bytes(int(heaviest.get("file_size") or 0))
            if int(heaviest.get("file_size") or 0) > 0:
                heaviest_bit = f" The heaviest is {heaviest['label']} at {size}."
            else:
                heaviest_bit = f" The longest-sitting is {heaviest['label']}."
        dead_text = (
            f"{dead_count} title{'s' if dead_count != 1 else ''} have been here more than "
            f"{stale_days} days with no play, taking {stats.get('dead_weight_label')}.{heaviest_bit} "
            "I will not send a fleet at them. If you want the house lighter, open Health "
            "and confirm each one."
        )

    disk_bytes = int(stats.get("disk_bytes") or 0)
    if disk_bytes <= 0:
        disk_text = (
            "I cannot see file sizes yet, so I will not guess at disk. After the next sync "
            "I can tell you what the movies and shows actually weigh."
        )
    else:
        disk_text = (
            f"The disks hold {stats.get('disk_label')}. Movies take "
            f"{stats.get('movie_disk_label')}; shows take {stats.get('show_disk_label')}."
        )

    close = (
        "When you are ready, the seasonal preview and the gift queue are below. "
        "Nothing publishes, and nobody is gifted, until you say so."
    )
    return [
        {"kind": "hours", "text": watch_text},
        {"kind": "dead_weight", "text": dead_text},
        {"kind": "disk", "text": disk_text},
        {"kind": "close", "text": close},
    ]


def compose_house_letter(db: Database, *, now: Optional[float] = None) -> Dict[str, Any]:
    """Owner letter: unwatched hours, dead weight, disk — story, not tiles."""
    stats = gather_house_stats(db, now=now)
    paragraphs = _paragraphs_for(stats)
    body = "\n\n".join(item["text"] for item in paragraphs)
    return {
        "title": LETTER_TITLE,
        "salutation": "Dear owner,",
        "signoff": "— your curator",
        "body": body,
        "paragraphs": paragraphs,
        "stats": stats,
        "generated_at": stats["generated_at"],
    }
