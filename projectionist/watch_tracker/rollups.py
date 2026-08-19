"""Year-scoped per-user rollups from watch_completions (never household aggregates)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from projectionist.library.db import Database
from projectionist.watch_tracker.models import TitleRollup, YearRollup

# Soft floor so YIR does not tease empty years.
MIN_COMPLETIONS_FOR_YIR = 3
PEAK_MONTH_TITLE_LIMIT = 8


def year_bounds_ms(year: int) -> tuple[int, int]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


_IN_CHUNK = 400
_CAST_CAP = 4


def _parse_json_list(raw: Any) -> List[str]:
    if not raw:
        return []
    parsed: Any = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _chunked(keys: Iterable[str], size: int = _IN_CHUNK) -> Iterable[List[str]]:
    batch: List[str] = []
    for key in keys:
        cleaned = str(key or "").strip()
        if not cleaned:
            continue
        batch.append(cleaned)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _prefetch_library_meta(
    db: Database,
    *,
    movie_keys: Sequence[str],
    episode_keys: Sequence[str],
    show_keys: Sequence[str],
) -> Dict[str, Dict[str, Any]]:
    """Batch-load library rows so the year rollup does not N+1."""
    movies: Dict[str, Dict[str, Any]] = {}
    episodes: Dict[str, Dict[str, Any]] = {}
    shows: Dict[str, Dict[str, Any]] = {}
    item_keys = list({*movie_keys, *show_keys})
    with db.connect() as conn:
        for chunk in _chunked(item_keys):
            placeholders = ",".join("?" * len(chunk))
            for row in conn.execute(
                f"""
                SELECT rating_key, title, year, poster_url, genres, directors, "cast", runtime_minutes
                FROM library_items
                WHERE rating_key IN ({placeholders})
                """,
                chunk,
            ).fetchall():
                key = str(row["rating_key"] or "").strip()
                payload = {
                    "title": str(row["title"] or "Untitled"),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "poster_url": row["poster_url"],
                    "genres": _parse_json_list(row["genres"]),
                    "directors": _parse_json_list(row["directors"]),
                    "cast": _parse_json_list(row["cast"])[:_CAST_CAP],
                    "runtime_minutes": int(row["runtime_minutes"])
                    if row["runtime_minutes"] is not None
                    else None,
                }
                movies[key] = payload
                shows[key] = payload
        for chunk in _chunked(episode_keys):
            placeholders = ",".join("?" * len(chunk))
            for row in conn.execute(
                f"""
                SELECT e.rating_key AS episode_key, e.title AS episode_title,
                       e.season_number, e.episode_number, e.runtime_minutes,
                       i.rating_key AS show_rating_key, i.title AS show_title,
                       i.year, i.poster_url, i.genres, i.directors, i."cast"
                FROM library_episodes e
                LEFT JOIN library_items i ON i.id = e.show_item_id
                WHERE e.rating_key IN ({placeholders})
                """,
                chunk,
            ).fetchall():
                show_key = str(row["show_rating_key"] or "").strip() or None
                episodes[str(row["episode_key"] or "").strip()] = {
                    "episode_title": str(row["episode_title"] or "").strip(),
                    "season_number": row["season_number"],
                    "episode_number": row["episode_number"],
                    "runtime_minutes": int(row["runtime_minutes"])
                    if row["runtime_minutes"] is not None
                    else None,
                    "parent_rating_key": show_key,
                    "title": str(row["show_title"] or "Show").strip(),
                    "year": int(row["year"]) if row["year"] is not None else None,
                    "poster_url": row["poster_url"],
                    "genres": _parse_json_list(row["genres"]),
                    "directors": _parse_json_list(row["directors"]),
                    "cast": _parse_json_list(row["cast"])[:_CAST_CAP],
                }
    return {"movies": movies, "episodes": episodes, "shows": shows}


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


def _empty_bucket(
    *,
    rating_key: str,
    media_type: str,
    parent_rating_key: Optional[str],
    title: str,
    year: Optional[int],
    poster_url: Optional[str],
    completed_at: int,
) -> Dict[str, Any]:
    return {
        "rating_key": rating_key,
        "media_type": media_type,
        "parent_rating_key": parent_rating_key,
        "title": title,
        "year": year,
        "poster_url": poster_url,
        "completions": 0,
        "confidence": {"certain": 0, "likely": 0, "plex_event_only": 0},
        "last_completed_at_ms": completed_at,
        "days": set(),
    }


def _touch_bucket(bucket: Dict[str, Any], *, conf: str, completed_at: int, day: str) -> None:
    bucket["completions"] += 1
    bucket["confidence"][conf] += 1
    bucket["last_completed_at_ms"] = max(bucket["last_completed_at_ms"], completed_at)
    days: Set[str] = bucket["days"]
    days.add(day)


def build_year_rollup(db: Database, *, user_id: str, year: int) -> YearRollup:
    """Aggregate accepted completions for one user in one calendar year (UTC)."""
    uid = str(user_id or "").strip()
    start_ms, end_ms = year_bounds_ms(int(year))
    confidence = {"certain": 0, "likely": 0, "plex_event_only": 0}
    monthly = {m: 0 for m in range(1, 13)}
    # month -> title_key -> bucket (movies + shows, not individual episodes)
    monthly_titles: Dict[int, Dict[str, Dict[str, Any]]] = {m: {} for m in range(1, 13)}

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

    movie_keys = [
        str(row["rating_key"]) for row in rows if str(row["media_type"]) == "movie"
    ]
    episode_keys = [
        str(row["rating_key"]) for row in rows if str(row["media_type"]) != "movie"
    ]
    show_keys = [
        str(row["parent_rating_key"] or "")
        for row in rows
        if str(row["media_type"]) != "movie" and row["parent_rating_key"]
    ]
    library = _prefetch_library_meta(
        db, movie_keys=movie_keys, episode_keys=episode_keys, show_keys=show_keys
    )
    movie_meta = library["movies"]
    episode_meta = library["episodes"]
    show_meta = library["shows"]

    movie_completions = 0
    episode_completions = 0
    unique_titles: set[str] = set()
    unique_episodes: set[str] = set()
    sittings = 0
    first_at: Optional[int] = None
    last_at: Optional[int] = None
    by_movie: Dict[str, Dict[str, Any]] = {}
    by_show: Dict[str, Dict[str, Any]] = {}
    movie_genre_counts: Counter[str] = Counter()
    tv_genre_counts: Counter[str] = Counter()
    weekday_counts: Counter[int] = Counter()
    director_counts: Counter[str] = Counter()
    actor_counts: Counter[str] = Counter()
    movie_decade_counts: Counter[int] = Counter()
    catalog_minutes = 0
    catalog_minutes_coverage = 0

    for row in rows:
        conf = str(row["confidence"] or "plex_event_only")
        if conf not in confidence:
            conf = "plex_event_only"
        confidence[conf] += 1
        completed_at = int(row["completed_at_ms"])
        first_at = completed_at if first_at is None else min(first_at, completed_at)
        last_at = completed_at if last_at is None else max(last_at, completed_at)
        dt = datetime.fromtimestamp(completed_at / 1000.0, tz=timezone.utc)
        month = int(dt.month)
        day = dt.strftime("%Y-%m-%d")
        weekday_counts[int(dt.weekday())] += 1
        monthly[month] = monthly.get(month, 0) + 1
        sittings += int(row["sittings"] or 1)
        media_type = str(row["media_type"])
        rating_key = str(row["rating_key"])
        parent = row["parent_rating_key"]
        if media_type == "movie":
            meta = movie_meta.get(rating_key) or _library_title(db, rating_key, "movie")
            runtime = meta.get("runtime_minutes")
            if runtime:
                catalog_minutes += int(runtime)
                catalog_minutes_coverage += 1
            for genre in meta.get("genres") or []:
                movie_genre_counts[str(genre)] += 1
            for director in meta.get("directors") or []:
                director_counts[str(director)] += 1
            for actor in meta.get("cast") or []:
                actor_counts[str(actor)] += 1
            year_val = meta.get("year")
            if year_val is not None:
                movie_decade_counts[(int(year_val) // 10) * 10] += 1
            movie_completions += 1
            unique_titles.add(rating_key)
            bucket = by_movie.setdefault(
                rating_key,
                _empty_bucket(
                    rating_key=rating_key,
                    media_type="movie",
                    parent_rating_key=None,
                    title=str(meta.get("title") or "Untitled"),
                    year=meta.get("year"),
                    poster_url=meta.get("poster_url"),
                    completed_at=completed_at,
                ),
            )
            _touch_bucket(bucket, conf=conf, completed_at=completed_at, day=day)
            month_bucket = monthly_titles[month].setdefault(
                f"movie:{rating_key}",
                _empty_bucket(
                    rating_key=rating_key,
                    media_type="movie",
                    parent_rating_key=None,
                    title=str(meta.get("title") or "Untitled"),
                    year=meta.get("year"),
                    poster_url=meta.get("poster_url"),
                    completed_at=completed_at,
                ),
            )
            _touch_bucket(month_bucket, conf=conf, completed_at=completed_at, day=day)
        else:
            ep = episode_meta.get(rating_key) or {}
            show_key = str(parent or ep.get("parent_rating_key") or rating_key)
            show = show_meta.get(show_key) or {}
            runtime = ep.get("runtime_minutes")
            if runtime:
                catalog_minutes += int(runtime)
                catalog_minutes_coverage += 1
            genres = ep.get("genres") or show.get("genres") or []
            for genre in genres:
                tv_genre_counts[str(genre)] += 1
            episode_completions += 1
            unique_episodes.add(rating_key)
            unique_titles.add(show_key)
            title = str(show.get("title") or ep.get("title") or "Show")
            year_val = show.get("year") if show.get("year") is not None else ep.get("year")
            poster = show.get("poster_url") if show else ep.get("poster_url")
            if not show and not ep:
                fallback = _library_title(db, rating_key, "episode")
                title = str(fallback.get("title") or "Show").split(" — ")[0]
                year_val = fallback.get("year")
                poster = fallback.get("poster_url")
                show_key = str(fallback.get("parent_rating_key") or show_key)
            bucket = by_show.setdefault(
                show_key,
                _empty_bucket(
                    rating_key=show_key,
                    media_type="episode",
                    parent_rating_key=show_key,
                    title=title,
                    year=year_val,
                    poster_url=poster,
                    completed_at=completed_at,
                ),
            )
            _touch_bucket(bucket, conf=conf, completed_at=completed_at, day=day)
            month_bucket = monthly_titles[month].setdefault(
                f"show:{show_key}",
                _empty_bucket(
                    rating_key=show_key,
                    media_type="episode",
                    parent_rating_key=show_key,
                    title=title,
                    year=year_val,
                    poster_url=poster,
                    completed_at=completed_at,
                ),
            )
            _touch_bucket(month_bucket, conf=conf, completed_at=completed_at, day=day)

    def _to_title(d: Dict[str, Any]) -> TitleRollup:
        days = d.get("days") or set()
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
            distinct_days=max(1, len(days)),
        )

    def _rank_key(d: Dict[str, Any]) -> tuple:
        # Prefer true multi-day rewatches over same-day completion noise.
        return (-len(d.get("days") or ()), -int(d["completions"]), -int(d["last_completed_at_ms"]))

    top_movies = sorted(by_movie.values(), key=_rank_key)[:8]
    top_shows = sorted(by_show.values(), key=_rank_key)[:8]

    peak = peak_month(monthly)
    peak_titles: list[TitleRollup] = []
    if peak:
        peak_m, _ = peak
        peak_titles = [
            _to_title(d)
            for d in sorted(monthly_titles.get(peak_m, {}).values(), key=_rank_key)[
                :PEAK_MONTH_TITLE_LIMIT
            ]
        ]

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
        peak_month_titles=peak_titles,
        first_completion_at_ms=first_at,
        last_completion_at_ms=last_at,
        has_enough_data=total >= MIN_COMPLETIONS_FOR_YIR,
        unique_movies=len(by_movie),
        unique_shows=len(by_show),
        catalog_minutes=catalog_minutes,
        catalog_minutes_coverage=catalog_minutes_coverage,
        movie_genre_counts=dict(movie_genre_counts),
        tv_genre_counts=dict(tv_genre_counts),
        weekday_counts=dict(weekday_counts),
        director_counts=dict(director_counts),
        actor_counts=dict(actor_counts),
        movie_decade_counts=dict(movie_decade_counts),
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
