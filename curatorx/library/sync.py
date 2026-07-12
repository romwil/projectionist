"""Library sync from Plex with TMDB enrichment."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, List, NamedTuple, Optional, Set

from curatorx.config_store import Settings
from curatorx.connectors.fanart import FanartClient
from curatorx.connectors.plex import PlexClient
from curatorx.connectors.radarr import RadarrClient
from curatorx.connectors.sonarr import SonarrClient
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.library.embeddings import rebuild_embeddings
from curatorx.library.episodes import sync_tv_episodes
from curatorx.library.facets import rebuild_library_facets, rebuild_library_fts
from curatorx.library.query import refresh_library_overview_cache
from curatorx.reviews.store import scan_for_rating_prompts
from curatorx.web.job_progress import format_count_message

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, int, int, str], None]]

DEFAULT_LIBRARY_ENRICH_WORKERS = 6
MAX_LIBRARY_ENRICH_WORKERS = 16
# Commit enriched rows in batches to cut SQLite write contention with the HTTP API.
DEFAULT_LIBRARY_UPSERT_BATCH_SIZE = 50


class _EnrichOutcome(NamedTuple):
    status: str  # ok | skip | error
    row: Optional[dict] = None
    title: str = ""
    media_type: str = ""
    error: Optional[Exception] = None


def _resolve_enrich_workers(settings: Settings) -> int:
    try:
        raw = getattr(settings, "library_enrich_workers", None)
        workers = int(raw if raw is not None else DEFAULT_LIBRARY_ENRICH_WORKERS)
    except (TypeError, ValueError):
        workers = DEFAULT_LIBRARY_ENRICH_WORKERS
    return max(1, min(workers, MAX_LIBRARY_ENRICH_WORKERS))


def _enrich_plex_item(
    item: Any,
    plex: PlexClient,
    tmdb: Optional[TMDBClient],
    fanart: Optional[FanartClient],
    radarr_tmdb: Set[int],
    sonarr_tvdb: Set[int],
) -> _EnrichOutcome:
    """Build an enriched library row for one Plex item (network I/O only)."""
    title = str(getattr(item, "title", "") or "")
    media_type = str(getattr(item, "media_type", "") or "")
    rating_key = str(getattr(item, "rating_key", None) or "").strip()
    if not rating_key:
        return _EnrichOutcome(status="skip", title=title, media_type=media_type)
    try:
        tmdb_id = getattr(item, "tmdb_id", None)
        tvdb_id = getattr(item, "tvdb_id", None)
        in_radarr = bool(tmdb_id and int(tmdb_id) in radarr_tmdb)
        in_sonarr = bool(tvdb_id and int(tvdb_id) in sonarr_tvdb)
        row = _row_from_plex_item(
            item,
            plex,
            tmdb,
            fanart,
            in_radarr=in_radarr,
            in_sonarr=in_sonarr,
        )
        row["rating_key"] = rating_key
        return _EnrichOutcome(status="ok", row=row, title=title, media_type=media_type)
    except Exception as error:  # noqa: BLE001 — per-item isolation for sync
        return _EnrichOutcome(
            status="error",
            title=title,
            media_type=media_type,
            error=error,
        )


class _PhaseClock:
    """INFO-level phase start/end timing without spam."""

    def __init__(self) -> None:
        self._name: Optional[str] = None
        self._started: Optional[float] = None

    def begin(self, name: str) -> None:
        self.finish()
        self._name = name
        self._started = time.time()
        logger.info("Library sync: starting %s", name)

    def finish(self, *, extra: str = "") -> None:
        if not self._name or self._started is None:
            return
        elapsed = time.time() - self._started
        suffix = f" — {extra}" if extra else ""
        logger.info("Library sync: finished %s in %.1fs%s", self._name, elapsed, suffix)
        self._name = None
        self._started = None


def _emit(
    progress: ProgressCallback,
    phase: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress:
        progress(phase, current, total, message)


def _runtime_minutes_from_ms(duration_ms: Optional[int]) -> Optional[int]:
    if not duration_ms:
        return None
    return int(duration_ms / 60000)


def _countries_from_tmdb(details: dict) -> List[str]:
    countries = [
        str(c.get("name") or "").strip()
        for c in (details.get("production_countries") or [])
        if c.get("name")
    ]
    if countries:
        return countries
    return [
        str(code or "").strip()
        for code in (details.get("origin_country") or [])
        if str(code or "").strip()
    ]


def _apply_tmdb_enrichment(
    row: dict,
    details: dict,
    *,
    media_type: str,
    tmdb_client: Optional[TMDBClient] = None,
) -> None:
    if not details:
        return
    if not row.get("poster_url") and details.get("poster_path") and tmdb_client:
        row["poster_url"] = tmdb_client.poster_url(details.get("poster_path"))
    if not row.get("backdrop_url") and details.get("backdrop_path") and tmdb_client:
        row["backdrop_url"] = tmdb_client.backdrop_url(details.get("backdrop_path"))

    vote = details.get("vote_average")
    if vote is not None:
        row["vote_average"] = float(vote)

    language = str(details.get("original_language") or "").strip()
    if language:
        row["original_language"] = language

    countries = _countries_from_tmdb(details)
    if countries:
        row["countries"] = countries

    keywords_payload = details.get("keywords") or {}
    keyword_list = keywords_payload.get("keywords") or keywords_payload.get("results") or []
    keywords = [k.get("name", "") for k in keyword_list if k.get("name")]
    if keywords:
        row["keywords"] = keywords

    credits = details.get("credits") or {}
    if not row.get("cast"):
        row["cast"] = [c.get("name", "") for c in credits.get("cast", [])[:8] if c.get("name")]
    if not row.get("directors"):
        if media_type == "movie":
            row["directors"] = [
                c.get("name", "") for c in credits.get("crew", []) if c.get("job") == "Director"
            ]
        else:
            row["directors"] = [
                c.get("name", "") for c in credits.get("crew", []) if c.get("job") in {"Director", "Creator"}
            ]

    if media_type == "movie":
        runtime = details.get("runtime")
        if runtime:
            row["runtime_minutes"] = int(runtime)
    else:
        runtimes = details.get("episode_run_time") or []
        if runtimes:
            row["runtime_minutes"] = int(runtimes[0])


def _row_from_plex_item(
    item,
    plex: PlexClient,
    tmdb: Optional[TMDBClient],
    fanart: Optional[FanartClient],
    *,
    in_radarr: bool,
    in_sonarr: bool,
) -> dict:
    poster = plex.thumb_url(item.thumb)
    backdrop = plex.thumb_url(item.art)
    keywords: list[str] = []
    tmdb_id = int(item.tmdb_id) if item.tmdb_id else None
    tvdb_id = int(item.tvdb_id) if item.tvdb_id else None
    runtime_minutes = _runtime_minutes_from_ms(item.duration_ms)
    countries: list[str] = []
    vote_average = None
    original_language = ""

    item_cast = item.cast
    item_directors = item.directors

    if tmdb and tmdb_id:
        try:
            if item.media_type == "movie":
                details = tmdb.movie_details(tmdb_id)
            else:
                details = tmdb.tv_details(tmdb_id)
            if details.get("poster_path"):
                poster = tmdb.poster_url(details["poster_path"])
            if details.get("backdrop_path"):
                backdrop = tmdb.backdrop_url(details["backdrop_path"])
            keywords = [
                k.get("name", "")
                for k in (details.get("keywords") or {}).get("keywords", [])
                if k.get("name")
            ]
            vote_average = float(details.get("vote_average") or 0) or None
            original_language = str(details.get("original_language") or "")
            countries = _countries_from_tmdb(details)
            if item.media_type == "movie" and details.get("runtime"):
                runtime_minutes = int(details["runtime"])
            elif item.media_type == "show":
                runtimes = details.get("episode_run_time") or []
                if runtimes:
                    runtime_minutes = int(runtimes[0])
            row_stub = {
                "cast": item.cast,
                "directors": item.directors,
                "keywords": keywords,
                "poster_url": poster,
                "backdrop_url": backdrop,
                "vote_average": vote_average,
                "original_language": original_language,
                "countries": countries,
                "runtime_minutes": runtime_minutes,
            }
            _apply_tmdb_enrichment(row_stub, details, media_type=item.media_type, tmdb_client=tmdb)
            keywords = row_stub.get("keywords") or keywords
            poster = row_stub.get("poster_url") or poster
            backdrop = row_stub.get("backdrop_url") or backdrop
            vote_average = row_stub.get("vote_average", vote_average)
            original_language = row_stub.get("original_language", original_language)
            countries = row_stub.get("countries") or countries
            runtime_minutes = row_stub.get("runtime_minutes", runtime_minutes)
            item_cast = row_stub.get("cast") or item.cast
            item_directors = row_stub.get("directors") or item.directors
        except RuntimeError as error:
            logger.debug(
                "TMDB enrichment skipped %s tmdb_id=%s: %s",
                item.media_type,
                tmdb_id,
                error,
            )

    if fanart and tmdb_id and item.media_type == "movie":
        try:
            art = fanart.movie(tmdb_id)
            if not poster:
                poster = fanart.best_poster(art)
            if not backdrop:
                backdrop = fanart.best_backdrop(art)
        except RuntimeError as error:
            logger.debug("Fanart movie enrichment skipped tmdb_id=%s: %s", tmdb_id, error)
    elif fanart and tvdb_id and item.media_type == "show":
        try:
            art = fanart.tv(tvdb_id)
            if not poster:
                poster = fanart.best_poster(art)
            if not backdrop:
                backdrop = fanart.best_backdrop(art)
        except RuntimeError as error:
            logger.debug("Fanart TV enrichment skipped tvdb_id=%s: %s", tvdb_id, error)

    return {
        "rating_key": item.rating_key,
        "media_type": item.media_type,
        "title": item.title,
        "year": item.year,
        "summary": item.summary,
        "genres": item.genres,
        "cast": item_cast,
        "directors": item_directors,
        "keywords": keywords,
        "tmdb_id": tmdb_id,
        "tvdb_id": tvdb_id,
        "imdb_id": item.imdb_id,
        "poster_url": poster,
        "backdrop_url": backdrop,
        "view_count": item.view_count,
        "added_at": item.added_at,
        "last_viewed_at": item.last_viewed_at,
        "file_size": item.file_size,
        "in_radarr": in_radarr,
        "in_sonarr": in_sonarr,
        "runtime_minutes": runtime_minutes,
        "content_rating": item.content_rating,
        "vote_average": vote_average,
        "original_language": original_language,
        "countries": countries,
        "season_count": item.season_count,
        "leaf_count": item.leaf_count,
        "viewed_leaf_count": item.viewed_leaf_count,
        "view_offset_ms": item.view_offset_ms,
        "duration_ms": item.duration_ms,
        "plex_user_rating_stars": item.user_rating_stars,
    }


async def sync_library(
    db: Database,
    settings: Settings,
    *,
    progress: ProgressCallback = None,
) -> dict:
    if not settings.plex_url or not settings.plex_token:
        raise RuntimeError("Plex is not configured")

    clock = _PhaseClock()
    logger.info("Library sync starting")
    clock.begin("preparing")
    _emit(progress, "preparing", 0, 1, "Connecting to Plex…")

    plex = PlexClient(
        settings.plex_url,
        settings.plex_token,
        movie_section=settings.plex_movie_section or None,
        tv_section=settings.plex_tv_section or None,
    )
    tmdb = TMDBClient(settings.tmdb_api_key) if settings.tmdb_api_key else None
    fanart = FanartClient(settings.fanart_api_key) if settings.fanart_api_key else None

    radarr_tmdb: set[int] = set()
    sonarr_tvdb: set[int] = set()
    if settings.radarr_url and settings.radarr_api_key:
        _emit(progress, "preparing", 0, 1, "Loading Radarr index…")
        radarr_tmdb = {m.tmdb_id for m in RadarrClient(settings.radarr_url, settings.radarr_api_key).movies()}
        logger.info("Library sync: Radarr index loaded (%s movies)", len(radarr_tmdb))
    if settings.sonarr_url and settings.sonarr_api_key:
        _emit(progress, "preparing", 0, 1, "Loading Sonarr index…")
        sonarr_tvdb = {s.tvdb_id for s in SonarrClient(settings.sonarr_url, settings.sonarr_api_key).series_list()}
        logger.info("Library sync: Sonarr index loaded (%s shows)", len(sonarr_tvdb))

    _emit(progress, "preparing", 1, 1, "Ready to scan Plex")
    clock.finish()

    page_size = max(50, int(settings.tv_page_size or 500))

    clock.begin("scanning movies")
    _emit(progress, "movies", 0, 1, "Scanning Plex movies…")

    def movie_progress(current: int, total: int, message: str) -> None:
        _emit(progress, "movies", current, total, message)

    movies = plex.movie_items(page_size=page_size, progress_callback=movie_progress)
    _emit(
        progress,
        "movies",
        max(len(movies), 1),
        max(len(movies), 1),
        format_count_message("Scanning movies", len(movies), len(movies), unit="movies", done=True),
    )
    clock.finish(extra=f"{len(movies)} movies")

    clock.begin("scanning TV")
    _emit(progress, "tv", 0, 1, "Scanning Plex TV shows…")

    def tv_progress(current: int, total: int, message: str) -> None:
        _emit(progress, "tv", current, total, message)

    shows = plex.show_items(page_size=page_size, progress_callback=tv_progress)
    _emit(
        progress,
        "tv",
        max(len(shows), 1),
        max(len(shows), 1),
        format_count_message("Scanning shows", len(shows), len(shows), unit="shows", done=True),
    )
    clock.finish(extra=f"{len(shows)} shows")

    plex_items = movies + shows
    enrich_total = max(len(plex_items), 1)
    enrich_workers = _resolve_enrich_workers(settings)
    clock.begin("enriching metadata")
    logger.info("Library sync: enriching metadata with %s workers", enrich_workers)
    _emit(progress, "enriching", 0, enrich_total, "Enriching metadata…")

    count = 0
    skipped_no_rating_key = 0
    last_enrich_log = 0.0
    completed = 0
    pending_rows: list[dict] = []

    def _emit_enrich_progress(index: int) -> None:
        nonlocal last_enrich_log
        now = time.time()
        should_emit = index == 1 or index == enrich_total or index % 25 == 0 or (now - last_enrich_log) >= 3.0
        if not should_emit:
            return
        message = format_count_message("Enriching metadata", index, enrich_total, unit="titles")
        _emit(progress, "enriching", index, enrich_total, message)
        if now - last_enrich_log >= 3.0 or index == enrich_total:
            logger.info(
                "Library sync: enriching metadata — %s of %s titles",
                index,
                enrich_total,
            )
            last_enrich_log = now

    def _flush_pending_rows() -> None:
        if not pending_rows:
            return
        db.upsert_library_items(pending_rows)
        pending_rows.clear()

    with ThreadPoolExecutor(max_workers=enrich_workers) as pool:
        futures = [
            pool.submit(
                _enrich_plex_item,
                item,
                plex,
                tmdb,
                fanart,
                radarr_tmdb,
                sonarr_tvdb,
            )
            for item in plex_items
        ]
        for future in as_completed(futures):
            completed += 1
            try:
                outcome = future.result()
            except Exception as error:  # noqa: BLE001 — keep sync alive
                logger.exception("Library sync: unexpected enrich worker failure: %s", error)
                _emit_enrich_progress(completed)
                continue

            if outcome.status == "skip":
                skipped_no_rating_key += 1
                logger.debug(
                    "Skipping Plex item without rating_key title=%r media_type=%s",
                    outcome.title,
                    outcome.media_type,
                )
            elif outcome.status == "error":
                logger.warning(
                    "Library sync: enrichment failed title=%r media_type=%s: %s",
                    outcome.title,
                    outcome.media_type,
                    outcome.error,
                )
            elif outcome.row is not None:
                pending_rows.append(outcome.row)
                count += 1
                if len(pending_rows) >= DEFAULT_LIBRARY_UPSERT_BATCH_SIZE:
                    _flush_pending_rows()

            _emit_enrich_progress(completed)

    _flush_pending_rows()
    clock.finish(extra=f"{count} titles saved")
    with db.connect() as conn:
        items_with_tmdb = conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_items WHERE tmdb_id IS NOT NULL"
        ).fetchone()["cnt"]
        items_with_countries = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE countries IS NOT NULL AND countries != '' AND countries != '[]'
            """
        ).fetchone()["cnt"]
        items_with_language = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE original_language IS NOT NULL AND original_language != ''
            """
        ).fetchone()["cnt"]
    logger.info(
        "Library metadata coverage after sync: tmdb_id=%s countries=%s original_language=%s (of %s items)",
        items_with_tmdb,
        items_with_countries,
        items_with_language,
        count,
    )
    if count and items_with_tmdb == 0:
        logger.warning(
            "No library items have tmdb_id — country/language enrichment requires Plex includeGuids "
            "and a TMDB API key; verify Plex metadata is matched (not local:// only)."
        )
    elif count and items_with_countries == 0 and tmdb is not None:
        logger.warning(
            "No library items have countries after sync despite TMDB client — check TMDB API key and enrichment errors."
        )
    if skipped_no_rating_key:
        logger.warning(
            "Skipped %s Plex items without rating_key during library sync",
            skipped_no_rating_key,
        )

    clock.begin("building indexes")
    _emit(progress, "indexing", 0, 1, "Building search facets…")
    facet_count = rebuild_library_facets(db, progress=progress)
    _emit(progress, "indexing", 0, 1, "Building search index…")
    fts_count = rebuild_library_fts(db, progress=progress)
    _emit(progress, "indexing", 1, 1, "Search indexes ready")
    clock.finish(extra=f"facets={facet_count} fts={fts_count}")

    clock.begin("syncing episodes")
    _emit(progress, "episodes", 0, 1, "Syncing TV episodes…")
    episode_stats = sync_tv_episodes(
        db,
        plex,
        progress=progress,
        plex_shows=shows,
        workers=enrich_workers,
    )
    clock.finish(
        extra=(
            f"shows={episode_stats.get('shows_synced')} "
            f"skipped_unchanged={episode_stats.get('shows_skipped_unchanged', 0)} "
            f"episodes={episode_stats.get('episodes_synced')}"
        )
    )

    clock.begin("finishing")
    _emit(progress, "finishing", 0, 1, "Building recommendations…")
    embedded = await rebuild_embeddings(db, settings, progress=progress)
    refresh_library_overview_cache(db)
    rating_prompts = scan_for_rating_prompts(db, settings)
    _emit(progress, "finishing", 1, 1, "Wrapping up…")
    clock.finish(extra=f"embeddings={embedded} rating_prompts={rating_prompts}")

    db.set_sync_state(
        "last_sync",
        json.dumps(
            {
                "items": count,
                "movies": len(movies),
                "shows": len(shows),
                "embeddings": embedded,
                "facets": facet_count,
                "fts": fts_count,
                "episodes": episode_stats,
                "rating_prompts": rating_prompts,
                "timestamp": time.time(),
            }
        ),
    )

    logger.info(
        "Library sync complete — %s movies, %s shows, %s titles indexed",
        len(movies),
        len(shows),
        count,
    )
    return {
        "items_synced": count,
        "movies": len(movies),
        "shows": len(shows),
        "embeddings": embedded,
        "facets": facet_count,
        "fts": fts_count,
        "episodes": episode_stats,
        "rating_prompts": rating_prompts,
    }
