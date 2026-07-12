"""TV episode sync and query helpers."""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from curatorx.connectors.plex import PlexClient, PlexEpisode, PlexLibraryItem, PlexSeason
from curatorx.library.db import Database

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, int, int, str], None]]

DEFAULT_EPISODE_WORKERS = 6
MAX_EPISODE_WORKERS = 16


def _resolve_episode_workers(workers: Optional[int]) -> int:
    try:
        value = int(workers if workers is not None else DEFAULT_EPISODE_WORKERS)
    except (TypeError, ValueError):
        value = DEFAULT_EPISODE_WORKERS
    return max(1, min(value, MAX_EPISODE_WORKERS))


def _normalize_show_title(title: str) -> str:
    normalized = str(title or "").strip().lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _show_rating_key(show: Mapping[str, Any]) -> str:
    value = show["rating_key"] if "rating_key" in show.keys() else None
    return str(value or "").strip()


def _show_field(show: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if key in show.keys():
        return show[key]
    return default


def _build_plex_show_lookups(
    plex_shows: Sequence[PlexLibraryItem],
) -> Tuple[
    Dict[str, PlexLibraryItem],
    Dict[str, PlexLibraryItem],
    Dict[Tuple[str, Optional[int]], PlexLibraryItem],
]:
    by_tmdb: Dict[str, PlexLibraryItem] = {}
    by_tvdb: Dict[str, PlexLibraryItem] = {}
    by_title_year: Dict[Tuple[str, Optional[int]], PlexLibraryItem] = {}

    for item in plex_shows:
        rating_key = str(item.rating_key or "").strip()
        if not rating_key:
            continue

        tmdb_id = str(item.tmdb_id or "").strip()
        if tmdb_id and tmdb_id not in by_tmdb:
            by_tmdb[tmdb_id] = item

        tvdb_id = str(item.tvdb_id or "").strip()
        if tvdb_id and tvdb_id not in by_tvdb:
            by_tvdb[tvdb_id] = item

        title_key = (_normalize_show_title(item.title), item.year)
        if title_key not in by_title_year:
            by_title_year[title_key] = item

    return by_tmdb, by_tvdb, by_title_year


def _match_plex_show(
    show: Mapping[str, Any],
    *,
    by_tmdb: Mapping[str, PlexLibraryItem],
    by_tvdb: Mapping[str, PlexLibraryItem],
    by_title_year: Mapping[Tuple[str, Optional[int]], PlexLibraryItem],
) -> Optional[PlexLibraryItem]:
    existing_key = _show_rating_key(show)
    if existing_key:
        return None

    tmdb_id = _show_field(show, "tmdb_id")
    if tmdb_id is not None:
        match = by_tmdb.get(str(tmdb_id).strip())
        if match:
            return match

    tvdb_id = _show_field(show, "tvdb_id")
    if tvdb_id is not None:
        match = by_tvdb.get(str(tvdb_id).strip())
        if match:
            return match

    title = _normalize_show_title(str(_show_field(show, "title") or ""))
    if not title:
        return None

    year = _show_field(show, "year")
    year_value = int(year) if year is not None else None
    match = by_title_year.get((title, year_value))
    if match:
        return match

    if year_value is None:
        for (candidate_title, _), candidate in by_title_year.items():
            if candidate_title == title:
                return candidate

    return None


def backfill_show_rating_keys(
    db: Database,
    plex: PlexClient,
    *,
    plex_shows: Optional[Sequence[PlexLibraryItem]] = None,
) -> Dict[str, int]:
    shows = db.library_shows()
    missing = [show for show in shows if not _show_rating_key(show)]
    if not missing:
        return {"backfilled": 0, "unmatchable": 0, "conflicts": 0}

    catalog = list(plex_shows) if plex_shows is not None else plex.show_items()
    by_tmdb, by_tvdb, by_title_year = _build_plex_show_lookups(catalog)

    backfilled = 0
    unmatchable = 0
    conflicts = 0

    for show in missing:
        show_id = int(show["id"])
        match = _match_plex_show(
            show,
            by_tmdb=by_tmdb,
            by_tvdb=by_tvdb,
            by_title_year=by_title_year,
        )
        if match is None:
            unmatchable += 1
            logger.debug(
                "No Plex match for show without rating_key show_id=%s title=%r year=%s tmdb_id=%s",
                show_id,
                show["title"],
                _show_field(show, "year"),
                _show_field(show, "tmdb_id"),
            )
            continue

        rating_key = str(match.rating_key or "").strip()
        if not rating_key:
            unmatchable += 1
            continue

        if db.update_library_item_rating_key(show_id, rating_key):
            backfilled += 1
            logger.debug(
                "Backfilled Plex rating_key show_id=%s title=%r rating_key=%s",
                show_id,
                show["title"],
                rating_key,
            )
        else:
            conflicts += 1
            logger.debug(
                "Could not backfill rating_key due to conflict show_id=%s title=%r rating_key=%s",
                show_id,
                show["title"],
                rating_key,
            )

    if backfilled:
        logger.info("Backfilled Plex rating_key for %s shows before episode sync", backfilled)
    if unmatchable:
        logger.info(
            "Could not match %s shows to Plex during rating_key backfill",
            unmatchable,
        )
    if conflicts:
        logger.info(
            "Skipped rating_key backfill for %s shows due to existing rating_key conflicts",
            conflicts,
        )

    return {"backfilled": backfilled, "unmatchable": unmatchable, "conflicts": conflicts}


def _log_episode_sync_sample(shows: Sequence[Mapping[str, Any]]) -> None:
    sample = []
    for show in shows[:3]:
        rating_key = _show_rating_key(show)
        sample.append(
            {
                "show_id": int(show["id"]),
                "title": str(show["title"]),
                "rating_key": rating_key or None,
                "has_rating_key": bool(rating_key),
                "tmdb_id": _show_field(show, "tmdb_id"),
                "tvdb_id": _show_field(show, "tvdb_id"),
            }
        )
    with_key = sum(1 for show in shows if _show_rating_key(show))
    logger.info(
        "Episode sync sample (first %s shows)=%s with_rating_key=%s without_rating_key=%s",
        len(sample),
        sample,
        with_key,
        len(shows) - with_key,
    )


def _episode_row(
    show_id: int,
    episode: PlexEpisode,
    *,
    default_season_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    episode_key = str(episode.rating_key or "").strip()
    if not episode_key:
        return None
    return {
        "show_item_id": show_id,
        "rating_key": episode_key,
        "season_number": episode.season_number
        if episode.season_number is not None
        else default_season_number,
        "episode_number": episode.episode_number,
        "title": episode.title,
        "runtime_minutes": episode.runtime_minutes,
        "view_count": episode.view_count,
        "last_viewed_at": episode.last_viewed_at,
        "file_size": episode.file_size,
        "aired_at": episode.aired_at,
        "view_offset_ms": episode.view_offset_ms,
        "duration_ms": episode.duration_ms,
        "plex_user_rating_stars": episode.user_rating_stars,
    }


def _rows_from_plex_episodes(
    show_id: int,
    episodes: Sequence[PlexEpisode],
    *,
    default_season_number: Optional[int] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for episode in episodes:
        row = _episode_row(show_id, episode, default_season_number=default_season_number)
        if row is not None:
            rows.append(row)
    return rows


def _upsert_episodes_for_show(
    db: Database,
    show_id: int,
    episodes: Sequence[PlexEpisode],
    *,
    default_season_number: Optional[int] = None,
) -> int:
    rows = _rows_from_plex_episodes(
        show_id,
        episodes,
        default_season_number=default_season_number,
    )
    if not rows:
        return 0
    return db.upsert_library_episodes(rows)


def _show_episodes_unchanged(db: Database, show: Mapping[str, Any]) -> bool:
    """Skip re-fetch when stored episode/view counts match Plex leaf counts."""
    leaf_raw = _show_field(show, "leaf_count")
    if leaf_raw is None:
        return False
    try:
        leaf_count = int(leaf_raw)
    except (TypeError, ValueError):
        return False

    viewed_raw = _show_field(show, "viewed_leaf_count")
    viewed_leaf: Optional[int]
    if viewed_raw is None:
        viewed_leaf = None
    else:
        try:
            viewed_leaf = int(viewed_raw)
        except (TypeError, ValueError):
            viewed_leaf = None

    total, viewed = db.show_episode_view_counts(int(show["id"]))
    if leaf_count == 0 and total == 0:
        return True
    if total == 0 or total != leaf_count:
        return False
    if viewed_leaf is None:
        return True
    return viewed == viewed_leaf


class _ShowEpisodeFetch(NamedTuple):
    show_id: int
    title: str
    rating_key: str
    rows: List[Dict[str, Any]]
    skipped_empty_seasons: int = 0
    failed_season_fetches: int = 0
    failed_show_fetch: bool = False
    used_all_leaves: bool = False


def _fetch_show_episodes(
    plex: PlexClient,
    *,
    show_id: int,
    title: str,
    rating_key: str,
) -> _ShowEpisodeFetch:
    """Network I/O only: prefer one allLeaves request, fall back to seasons."""
    skipped_empty_seasons = 0
    failed_season_fetches = 0
    all_leaves_error: Optional[str] = None

    try:
        all_leaves = plex.show_all_episodes(rating_key)
    except (RuntimeError, ValueError) as error:
        all_leaves = []
        all_leaves_error = str(error)
        logger.debug(
            "Failed allLeaves fetch show_id=%s title=%r rating_key=%s: %s",
            show_id,
            title,
            rating_key,
            error,
        )
    else:
        rows = _rows_from_plex_episodes(show_id, all_leaves)
        if rows:
            return _ShowEpisodeFetch(
                show_id=show_id,
                title=title,
                rating_key=rating_key,
                rows=rows,
                used_all_leaves=True,
            )

    seasons: List[PlexSeason] = []
    seasons_fetch_error: Optional[str] = None
    try:
        seasons = plex.show_seasons(rating_key)
    except (RuntimeError, ValueError) as error:
        seasons_fetch_error = str(error)
        logger.debug(
            "Failed to fetch seasons show_id=%s title=%r rating_key=%s: %s",
            show_id,
            title,
            rating_key,
            error,
        )

    rows: List[Dict[str, Any]] = []
    for season in seasons:
        season_key = str(season.rating_key or "").strip()
        if not season_key:
            skipped_empty_seasons += 1
            logger.debug(
                "Skipping season without Plex rating_key show_id=%s season=%s title=%r",
                show_id,
                season.season_number,
                season.title,
            )
            continue
        try:
            episodes = plex.season_episodes(season_key)
        except (RuntimeError, ValueError) as error:
            failed_season_fetches += 1
            logger.debug(
                "Failed to fetch episodes show_id=%s season=%s rating_key=%s: %s",
                show_id,
                season.season_number,
                season_key,
                error,
            )
            continue
        rows.extend(
            _rows_from_plex_episodes(
                show_id,
                episodes,
                default_season_number=season.season_number,
            )
        )

    failed_show_fetch = False
    if not rows and (seasons_fetch_error or all_leaves_error):
        failed_show_fetch = True
        logger.debug(
            "Failed to fetch episodes for show show_id=%s title=%r rating_key=%s "
            "seasons_error=%s allLeaves_error=%s",
            show_id,
            title,
            rating_key,
            seasons_fetch_error,
            all_leaves_error,
        )
    elif not rows and not seasons:
        logger.info(
            "No Plex seasons or episodes for show_id=%s title=%r rating_key=%s "
            "(empty show or check Plex flattenSeasons setting)",
            show_id,
            title,
            rating_key,
        )

    return _ShowEpisodeFetch(
        show_id=show_id,
        title=title,
        rating_key=rating_key,
        rows=rows,
        skipped_empty_seasons=skipped_empty_seasons,
        failed_season_fetches=failed_season_fetches,
        failed_show_fetch=failed_show_fetch,
        used_all_leaves=False,
    )


def sync_tv_episodes(
    db: Database,
    plex: PlexClient,
    *,
    progress: ProgressCallback = None,
    plex_shows: Optional[Sequence[PlexLibraryItem]] = None,
    workers: Optional[int] = None,
) -> Dict[str, int]:
    backfill_stats = backfill_show_rating_keys(db, plex, plex_shows=plex_shows)
    shows = db.library_shows()
    total = len(shows)
    episode_workers = _resolve_episode_workers(workers)
    episodes_synced = 0
    shows_synced = 0
    shows_skipped_unchanged = 0
    unmatchable_shows = int(backfill_stats["unmatchable"]) + int(backfill_stats["conflicts"])
    skipped_empty_seasons = 0
    failed_show_fetches = 0
    failed_season_fetches = 0
    all_leaves_fallbacks = 0
    logger.info(
        "Episode sync starting show_count=%s workers=%s",
        total,
        episode_workers,
    )
    _log_episode_sync_sample(shows)

    completed = 0
    last_progress_log = 0.0

    def _emit_progress(message: str) -> None:
        nonlocal last_progress_log
        if not progress:
            return
        now = time.time()
        should_emit = (
            completed == 1
            or completed == total
            or completed % 25 == 0
            or (now - last_progress_log) >= 3.0
        )
        if not should_emit:
            return
        progress("episodes", completed, max(total, 1), message)
        if now - last_progress_log >= 3.0 or completed == total:
            logger.info(
                "Episode sync: %s of %s shows (%s)",
                completed,
                total,
                message,
            )
            last_progress_log = now

    fetch_jobs: List[Tuple[int, str, str]] = []
    for show in shows:
        show_id = int(show["id"])
        title = str(show["title"])
        rating_key = _show_rating_key(show)
        if not rating_key:
            logger.debug(
                "Skipping episode sync for unmatchable show show_id=%s title=%r",
                show_id,
                title,
            )
            completed += 1
            _emit_progress(f"Skipping {title}")
            continue

        if _show_episodes_unchanged(db, show):
            shows_skipped_unchanged += 1
            shows_synced += 1
            completed += 1
            _emit_progress(f"Unchanged {title}")
            continue

        fetch_jobs.append((show_id, title, rating_key))

    with ThreadPoolExecutor(max_workers=episode_workers) as pool:
        futures = [
            pool.submit(
                _fetch_show_episodes,
                plex,
                show_id=show_id,
                title=title,
                rating_key=rating_key,
            )
            for show_id, title, rating_key in fetch_jobs
        ]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 — keep sync alive
                failed_show_fetches += 1
                completed += 1
                logger.exception("Episode sync: unexpected worker failure: %s", error)
                _emit_progress("Episode fetch failed")
                continue

            # Serial writer: one show delete+upsert+rollup per commit.
            synced = db.replace_library_episodes_for_show(result.show_id, result.rows)
            episodes_synced += synced
            shows_synced += 1
            skipped_empty_seasons += result.skipped_empty_seasons
            failed_season_fetches += result.failed_season_fetches
            if result.failed_show_fetch:
                failed_show_fetches += 1
            if result.used_all_leaves:
                all_leaves_fallbacks += 1
            completed += 1
            _emit_progress(f"Syncing {result.title}")

    if unmatchable_shows:
        logger.info(
            "Skipped episode sync for %s unmatchable shows without Plex rating_key",
            unmatchable_shows,
        )
    if shows_skipped_unchanged:
        logger.info(
            "Skipped episode re-fetch for %s unchanged shows (leaf/view counts match)",
            shows_skipped_unchanged,
        )
    if skipped_empty_seasons:
        logger.info(
            "Skipped %s seasons without Plex rating_key during episode sync",
            skipped_empty_seasons,
        )
    if failed_show_fetches:
        logger.warning(
            "Failed to fetch seasons for %s shows during episode sync",
            failed_show_fetches,
        )
    if failed_season_fetches:
        logger.warning(
            "Failed to fetch episodes for %s seasons during episode sync",
            failed_season_fetches,
        )
    if all_leaves_fallbacks:
        logger.info(
            "Fetched episodes via Plex allLeaves for %s shows",
            all_leaves_fallbacks,
        )

    return {
        "shows_synced": shows_synced,
        "shows_skipped_unchanged": shows_skipped_unchanged,
        "episodes_synced": episodes_synced,
        "backfilled_rating_key": int(backfill_stats["backfilled"]),
        "unmatchable_shows": unmatchable_shows,
        "skipped_no_rating_key": unmatchable_shows,
        "skipped_empty_seasons": skipped_empty_seasons,
        "failed_show_fetches": failed_show_fetches,
        "failed_season_fetches": failed_season_fetches,
        "all_leaves_fallbacks": all_leaves_fallbacks,
    }


def _resolve_show(db: Database, show: Optional[str] = None, show_id: Optional[int] = None):
    if show_id is not None:
        return db.library_item_by_id(int(show_id))
    if show:
        return db.library_item_by_title(str(show), media_type="show")
    return None


def query_episodes(
    db: Database,
    *,
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    season: Optional[int] = None,
    unwatched_only: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> Dict[str, Any]:
    show_row = _resolve_show(db, show=show, show_id=show_id)
    if show_row is None:
        return {"error": "Show not found", "total_matched": 0, "returned": 0, "items": []}

    clauses = ["show_item_id = ?"]
    params: List[Any] = [int(show_row["id"])]
    if season is not None:
        clauses.append("season_number = ?")
        params.append(int(season))
    if unwatched_only:
        clauses.append("(view_count IS NULL OR view_count = 0)")

    where_sql = " AND ".join(clauses)
    capped_limit = min(max(1, limit), 50)
    capped_offset = max(0, offset)

    with db.connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM library_episodes WHERE {where_sql}",
            params,
        ).fetchone()["cnt"]
        rows = conn.execute(
            f"""
            SELECT * FROM library_episodes
            WHERE {where_sql}
            ORDER BY season_number ASC, episode_number ASC
            LIMIT ? OFFSET ?
            """,
            [*params, capped_limit, capped_offset],
        ).fetchall()

    items = [
        {
            "show_title": str(show_row["title"]),
            "season_number": int(r["season_number"]) if r["season_number"] is not None else None,
            "episode_number": int(r["episode_number"]) if r["episode_number"] is not None else None,
            "title": str(r["title"] or ""),
            "runtime_minutes": int(r["runtime_minutes"]) if r["runtime_minutes"] is not None else None,
            "view_count": int(r["view_count"] or 0),
            "unwatched": int(r["view_count"] or 0) == 0,
        }
        for r in rows
    ]
    returned = len(items)
    total_matched = int(total)
    return {
        "show_title": str(show_row["title"]),
        "total_matched": total_matched,
        "returned": returned,
        "offset": capped_offset,
        "has_more": capped_offset + returned < total_matched,
        "items": items,
    }


def summarize_tv_progress(
    db: Database,
    *,
    group_by: str = "show",
    in_progress_only: bool = False,
    limit: int = 25,
) -> Dict[str, Any]:
    normalized = group_by.strip().lower()
    if normalized not in {"show", "season"}:
        raise ValueError("group_by must be show or season")

    capped = min(max(1, limit), 50)
    if normalized == "show":
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, total_episode_count, unwatched_episode_count,
                       viewed_leaf_count, leaf_count
                FROM library_items
                WHERE media_type = 'show' AND total_episode_count > 0
                ORDER BY title ASC
                """
            ).fetchall()

        buckets: List[Dict[str, Any]] = []
        for row in rows:
            total_eps = int(row["total_episode_count"] or 0)
            unwatched = int(row["unwatched_episode_count"] or 0)
            watched = max(0, total_eps - unwatched)
            completion = round((watched / total_eps) * 100, 1) if total_eps else 0.0
            if in_progress_only and (completion <= 0 or completion >= 100):
                continue
            buckets.append(
                {
                    "show_title": str(row["title"]),
                    "total_episodes": total_eps,
                    "watched_episodes": watched,
                    "unwatched_episodes": unwatched,
                    "completion_percent": completion,
                }
            )
        buckets.sort(key=lambda item: (-item["completion_percent"], item["show_title"]))
        buckets = buckets[:capped]
        return {"group_by": "show", "buckets": buckets, "returned": len(buckets)}

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT li.title AS show_title, le.season_number,
                   COUNT(*) AS total,
                   SUM(CASE WHEN le.view_count IS NULL OR le.view_count = 0 THEN 1 ELSE 0 END) AS unwatched
            FROM library_episodes le
            JOIN library_items li ON li.id = le.show_item_id
            GROUP BY le.show_item_id, le.season_number
            ORDER BY li.title ASC, le.season_number ASC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()

    buckets = []
    for row in rows:
        total_eps = int(row["total"])
        unwatched = int(row["unwatched"])
        watched = max(0, total_eps - unwatched)
        completion = round((watched / total_eps) * 100, 1) if total_eps else 0.0
        if in_progress_only and (completion <= 0 or completion >= 100):
            continue
        buckets.append(
            {
                "show_title": str(row["show_title"]),
                "season_number": int(row["season_number"]) if row["season_number"] is not None else None,
                "total_episodes": total_eps,
                "watched_episodes": watched,
                "unwatched_episodes": unwatched,
                "completion_percent": completion,
            }
        )
    return {"group_by": "season", "buckets": buckets, "returned": len(buckets)}
