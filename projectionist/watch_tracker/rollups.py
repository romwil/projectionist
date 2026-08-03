"""Year-scoped per-user rollups from watch_completions (never household aggregates)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from projectionist.library.db import Database
from projectionist.watch_tracker.models import TitleRollup, YearRollup

# Soft floor so YIR does not tease empty years.
MIN_COMPLETIONS_FOR_YIR = 3


def year_bounds_ms(year: int) -> tuple[int, int]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _library_title(db: Database, rating_key: str, media_type: str) -> Dict[str, Any]:
    with db.connect() as conn:
        if media_type == "episode":
            row = conn.execute(
                """
                SELECT e.title AS episode_title, e.season_number, e.episode_number,
                       i.title AS show_title, i.year, i.poster_url, i.rating_key AS show_rating_key
                FROM library_episodes e
                LEFT JOIN library_items i ON i.id = e.show_item_id
                WHERE e.rating_key = ?
                """,
                (rating_key,),
            ).fetchone()
            if row:
                show = str(row["show_title"] or "Show").strip()
                ep = str(row["episode_title"] or "").strip()
                sn = row["season_number"]
                en = row["episode_number"]
                label = show
                if sn is not None and en is not None:
                    label = f"{show} — S{int(sn):02d}E{int(en):02d}"
                    if ep:
                        label = f"{label}: {ep}"
                return {
                    "title": label,
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "poster_url": row["poster_url"],
                    "parent_rating_key": row["show_rating_key"],
                }
        row = conn.execute(
            """
            SELECT title, year, poster_url FROM library_items WHERE rating_key = ?
            """,
            (rating_key,),
        ).fetchone()
    if row is None:
        return {"title": "Untitled", "year": None, "poster_url": None, "parent_rating_key": None}
    return {
        "title": str(row["title"] or "Untitled"),
        "year": int(row["year"]) if row["year"] is not None else None,
        "poster_url": row["poster_url"],
        "parent_rating_key": None,
    }


def build_year_rollup(db: Database, *, user_id: str, year: int) -> YearRollup:
    """Aggregate accepted completions for one user in one calendar year (UTC)."""
    uid = str(user_id or "").strip()
    start_ms, end_ms = year_bounds_ms(int(year))
    confidence = {"certain": 0, "likely": 0, "plex_event_only": 0}
    monthly = {m: 0 for m in range(1, 13)}

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.*, s.event_count AS sittings
            FROM watch_completions c
            LEFT JOIN watch_sessions s ON s.id = c.session_id
            WHERE c.user_id = ?
              AND c.superseded_by_completion_id IS NULL
              AND c.completed_at_ms >= ?
              AND c.completed_at_ms < ?
            ORDER BY c.completed_at_ms ASC
            """,
            (uid, start_ms, end_ms),
        ).fetchall()

    movie_completions = 0
    episode_completions = 0
    unique_titles: set[str] = set()
    unique_episodes: set[str] = set()
    sittings = 0
    first_at: Optional[int] = None
    last_at: Optional[int] = None
    by_movie: Dict[str, Dict[str, Any]] = {}
    by_show: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        conf = str(row["confidence"] or "plex_event_only")
        if conf not in confidence:
            conf = "plex_event_only"
        confidence[conf] += 1
        completed_at = int(row["completed_at_ms"])
        first_at = completed_at if first_at is None else min(first_at, completed_at)
        last_at = completed_at if last_at is None else max(last_at, completed_at)
        dt = datetime.fromtimestamp(completed_at / 1000.0, tz=timezone.utc)
        monthly[int(dt.month)] = monthly.get(int(dt.month), 0) + 1
        sittings += int(row["sittings"] or 1)
        media_type = str(row["media_type"])
        rating_key = str(row["rating_key"])
        parent = row["parent_rating_key"]
        meta = _library_title(db, rating_key, media_type)
        if media_type == "movie":
            movie_completions += 1
            unique_titles.add(rating_key)
            bucket = by_movie.setdefault(
                rating_key,
                {
                    "rating_key": rating_key,
                    "media_type": "movie",
                    "parent_rating_key": None,
                    "title": meta["title"],
                    "year": meta["year"],
                    "poster_url": meta["poster_url"],
                    "completions": 0,
                    "confidence": {"certain": 0, "likely": 0, "plex_event_only": 0},
                    "last_completed_at_ms": completed_at,
                },
            )
            bucket["completions"] += 1
            bucket["confidence"][conf] += 1
            bucket["last_completed_at_ms"] = max(bucket["last_completed_at_ms"], completed_at)
        else:
            episode_completions += 1
            unique_episodes.add(rating_key)
            show_key = str(parent or meta.get("parent_rating_key") or rating_key)
            unique_titles.add(show_key)
            # Prefer show title from library_items
            with db.connect() as conn:
                show_row = conn.execute(
                    "SELECT title, year, poster_url FROM library_items WHERE rating_key = ?",
                    (show_key,),
                ).fetchone()
            title = str(show_row["title"]) if show_row else str(meta["title"]).split(" — ")[0]
            year_val = int(show_row["year"]) if show_row and show_row["year"] is not None else meta["year"]
            poster = show_row["poster_url"] if show_row else meta["poster_url"]
            bucket = by_show.setdefault(
                show_key,
                {
                    "rating_key": show_key,
                    "media_type": "episode",
                    "parent_rating_key": show_key,
                    "title": title,
                    "year": year_val,
                    "poster_url": poster,
                    "completions": 0,
                    "confidence": {"certain": 0, "likely": 0, "plex_event_only": 0},
                    "last_completed_at_ms": completed_at,
                },
            )
            bucket["completions"] += 1
            bucket["confidence"][conf] += 1
            bucket["last_completed_at_ms"] = max(bucket["last_completed_at_ms"], completed_at)

    def _to_title(d: Dict[str, Any]) -> TitleRollup:
        return TitleRollup(
            rating_key=d["rating_key"],
            media_type=d["media_type"],
            parent_rating_key=d.get("parent_rating_key"),
            title=d["title"],
            year=d.get("year"),
            poster_url=d.get("poster_url"),
            completions=int(d["completions"]),
            confidence=dict(d["confidence"]),
            last_completed_at_ms=int(d["last_completed_at_ms"]),
        )

    top_movies = sorted(by_movie.values(), key=lambda d: (-d["completions"], -d["last_completed_at_ms"]))[:8]
    top_shows = sorted(by_show.values(), key=lambda d: (-d["completions"], -d["last_completed_at_ms"]))[:8]
    total = len(rows)
    return YearRollup(
        user_id=uid,
        year=int(year),
        completion_count=total,
        movie_completions=movie_completions,
        episode_completions=episode_completions,
        unique_titles=len(unique_titles),
        unique_episodes=len(unique_episodes),
        sittings_observed=sittings,
        confidence=confidence,
        top_movies=[_to_title(d) for d in top_movies],
        top_shows=[_to_title(d) for d in top_shows],
        monthly_counts=monthly,
        first_completion_at_ms=first_at,
        last_completion_at_ms=last_at,
        has_enough_data=total >= MIN_COMPLETIONS_FOR_YIR,
    )


def month_label(month: int) -> str:
    names = (
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    if month < 1 or month > 12:
        return "that month"
    return names[month]


def peak_month(monthly_counts: Dict[int, int]) -> Optional[tuple[int, int]]:
    if not monthly_counts:
        return None
    best = max(monthly_counts.items(), key=lambda kv: (kv[1], -kv[0]))
    if best[1] <= 0:
        return None
    return best
