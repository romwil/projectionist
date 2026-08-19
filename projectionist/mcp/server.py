"""MCP stdio / HTTP server exposing CuratorX library query tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from projectionist.config_store import Settings, load_merged_settings
from projectionist.library.db import Database
from projectionist.library.episodes import query_episodes, summarize_tv_progress
from projectionist.library.facets import ensure_library_facet_index, library_facet_catalog
from projectionist.library.query import (
    aggregate_library,
    filters_from_mapping,
    library_overview,
    query_library,
    query_library_async,
)
from projectionist.library.titles import get_title_detail
from projectionist.mcp.mode import (
    audience_for_mode,
    full_confirm_scope_enabled,
    get_mcp_mode,
    resolve_stdio_mcp_mode,
    set_mcp_mode,
)
from projectionist.privacy import sanitize
from projectionist.web.jobs import _resolve_db_path

mcp = FastMCP(
    "Projectionist Library",
    instructions=(
        "Query the user's Plex library indexed by Projectionist. "
        "Use library_query for paginated owned-title browse with rich filters; "
        "library_aggregate for counts; library_facet_catalog for top directors/actors; "
        "library_tv_episodes and library_tv_progress for TV episode-level queries. "
        "Full MCP mode can propose confirm-gated *arr changes; confirming them over "
        "MCP requires a key scoped for active curation, otherwise a human confirms "
        "on the authenticated Projectionist web plane."
    ),
)


def _database() -> Database:
    data_dir = Path(os.environ.get("DATA_DIR", "/config"))
    db = Database(_resolve_db_path(data_dir))
    ensure_library_facet_index(db)
    return db


def _settings() -> Settings:
    return load_merged_settings(Path(os.environ.get("DATA_DIR", "/config")))


def _emit(payload: Any) -> str:
    """Serialize tool results with audience sanitization (never live X-Plex-Token)."""
    cleaned = sanitize(payload, audience=audience_for_mode(), settings=_settings())
    return json.dumps(cleaned)


def _require_full_mode() -> Optional[str]:
    if get_mcp_mode() != "full":
        return json.dumps(
            {
                "error": "This tool requires full MCP mode (PROJECTIONIST_MCP_FULL_API_KEY / PROJECTIONIST_MCP_MODE=full).",
            }
        )
    return None


def _filter_mapping(**kwargs: Any) -> dict[str, Any]:
    bool_keys = {"unwatched_only", "in_progress_only", "missing_tmdb_id"}
    return {
        key: value
        for key, value in kwargs.items()
        if value is not None or key in bool_keys
    }


def _public_tmdb_item(item: dict[str, Any]) -> dict[str, Any]:
    """Trim TMDB search hits for privacy mode (no raw poster_path fan-out needed)."""
    from projectionist.connectors.tmdb import TMDBClient

    settings = _settings()
    poster_size = getattr(settings, "mcp_tmdb_poster_size", "w500") or "w500"
    backdrop_size = getattr(settings, "mcp_tmdb_backdrop_size", "w1280") or "w1280"
    media = "show" if item.get("media_type") == "tv" or "first_air_date" in item else "movie"
    title = str(item.get("title") or item.get("name") or "")
    year_raw = item.get("release_date") or item.get("first_air_date") or ""
    year = None
    if isinstance(year_raw, str) and len(year_raw) >= 4 and year_raw[:4].isdigit():
        year = int(year_raw[:4])
    tmdb = TMDBClient("")  # URL helpers only
    poster = tmdb.poster_url(item.get("poster_path"), size=poster_size)
    backdrop = tmdb.backdrop_url(item.get("backdrop_path"), size=backdrop_size)
    return {
        "tmdb_id": int(item.get("id") or 0) or None,
        "title": title,
        "year": year,
        "media_type": media,
        "overview": str(item.get("overview") or "")[:480],
        "vote_average": item.get("vote_average"),
        "poster_url": poster,
        "backdrop_url": backdrop,
    }


@mcp.tool()
def library_query(
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    cast: Optional[str] = None,
    keywords: Optional[str] = None,
    countries: Optional[str] = None,
    content_ratings: Optional[str] = None,
    original_language: Optional[str] = None,
    query: Optional[str] = None,
    fts_query: Optional[str] = None,
    semantic_query: Optional[str] = None,
    unwatched_only: bool = False,
    min_view_count: Optional[int] = None,
    max_view_count: Optional[int] = None,
    stale_days: Optional[int] = None,
    recently_added_days: Optional[int] = None,
    added_from: Optional[str] = None,
    added_to: Optional[str] = None,
    last_viewed_from: Optional[str] = None,
    last_viewed_to: Optional[str] = None,
    runtime_min: Optional[int] = None,
    runtime_max: Optional[int] = None,
    vote_min: Optional[float] = None,
    vote_max: Optional[float] = None,
    file_size_min: Optional[int] = None,
    file_size_max: Optional[int] = None,
    in_radarr: Optional[bool] = None,
    in_sonarr: Optional[bool] = None,
    missing_tmdb_id: bool = False,
    in_progress_only: bool = False,
    sort: str = "title",
    offset: int = 0,
    limit: int = 25,
) -> str:
    """Browse owned library titles with filters and pagination."""
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            year_from=year_from,
            year_to=year_to,
            genres=genres,
            directors=directors,
            cast=cast,
            keywords=keywords,
            countries=countries,
            content_ratings=content_ratings,
            original_language=original_language,
            query=query,
            fts_query=fts_query,
            semantic_query=semantic_query,
            unwatched_only=unwatched_only,
            min_view_count=min_view_count,
            max_view_count=max_view_count,
            stale_days=stale_days,
            recently_added_days=recently_added_days,
            added_from=added_from,
            added_to=added_to,
            last_viewed_from=last_viewed_from,
            last_viewed_to=last_viewed_to,
            runtime_min=runtime_min,
            runtime_max=runtime_max,
            vote_min=vote_min,
            vote_max=vote_max,
            file_size_min=file_size_min,
            file_size_max=file_size_max,
            in_radarr=in_radarr,
            in_sonarr=in_sonarr,
            missing_tmdb_id=missing_tmdb_id,
            in_progress_only=in_progress_only,
            sort=sort,
            offset=offset,
            limit=limit,
        )
    )
    if filters.semantic_query:
        result = asyncio.run(query_library_async(_database(), filters, _settings()))
    else:
        result = query_library(_database(), filters)
    return _emit(result)


@mcp.tool()
def library_aggregate(
    group_by: str,
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    keywords: Optional[str] = None,
) -> str:
    """Aggregate owned library counts by decade, genre, director, etc."""
    normalized = group_by.strip().lower()
    allowed = {
        "decade",
        "year",
        "genre",
        "media_type",
        "director",
        "actor",
        "keyword",
        "country",
        "language",
        "content_rating",
        "runtime_bucket",
        "decade_genre",
    }
    if normalized not in allowed:
        return _emit({"error": f"group_by must be one of: {', '.join(sorted(allowed))}"})
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            year_from=year_from,
            year_to=year_to,
            genres=genres,
            directors=directors,
            keywords=keywords,
        )
    )
    return _emit(aggregate_library(_database(), normalized, filters))  # type: ignore[arg-type]


@mcp.tool()
def library_facet_catalog_tool(facet_type: str, limit: int = 50) -> str:
    """List top directors, actors, keywords, countries, or languages in the library."""
    try:
        return _emit(library_facet_catalog(_database(), facet_type, limit=limit))
    except ValueError as exc:
        return _emit({"error": str(exc)})


@mcp.tool()
def library_tv_episodes(
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    season: Optional[int] = None,
    unwatched_only: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> str:
    """Browse episodes for an owned TV show."""
    return _emit(
        query_episodes(
            _database(),
            show=show,
            show_id=show_id,
            season=season,
            unwatched_only=unwatched_only,
            offset=offset,
            limit=limit,
        )
    )


@mcp.tool()
def library_tv_progress(
    group_by: str = "show",
    in_progress_only: bool = False,
    limit: int = 25,
) -> str:
    """Summarize TV watch completion by show or season."""
    try:
        return _emit(
            summarize_tv_progress(
                _database(),
                group_by=group_by,
                in_progress_only=in_progress_only,
                limit=limit,
            )
        )
    except ValueError as exc:
        return _emit({"error": str(exc)})


@mcp.tool()
def library_overview_tool() -> str:
    """Compact library inventory: totals, decades, genres, directors, TV progress."""
    return _emit(library_overview(_database()))


@mcp.tool()
def library_title_detail(
    media_type: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
) -> str:
    """Fetch rich metadata for one title in or outside the library."""
    # Privacy mode: do not accept/lookup by rating_key (Plex infrastructure id).
    if get_mcp_mode() != "full" and rating_key:
        return _emit({"error": "rating_key lookups require full MCP mode; use tmdb_id or tvdb_id"})
    kwargs: dict[str, Any] = {"media_type": media_type}
    if rating_key and get_mcp_mode() == "full":
        kwargs["rating_key"] = rating_key
    elif tvdb_id is not None:
        kwargs["tvdb_id"] = tvdb_id
    elif tmdb_id is not None:
        kwargs["tmdb_id"] = tmdb_id
    else:
        return _emit({"error": "Provide tmdb_id, tvdb_id, or rating_key (full mode)"})
    detail = get_title_detail(_database(), _settings(), **kwargs)
    return _emit(detail.model_dump())


@mcp.tool()
def what_to_watch_tonight(
    media_type: Optional[str] = "movie",
    query: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Suggest owned titles worth watching now (unwatched / in-progress bias). Full MCP only."""
    denied = _require_full_mode()
    if denied:
        return denied
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            query=query or "watch tonight",
            unwatched_only=False,
            in_progress_only=False,
            sort="title",
            limit=limit,
        )
    )
    result = query_library(_database(), filters)
    return _emit(result)


def _sample_owned_library_payload(
    media_type: Optional[str] = "movie",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Owned-inventory sample (not TMDB missing-title discover)."""
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            year_from=year_from,
            year_to=year_to,
            genres=genres,
            sort="title",
            limit=limit,
        )
    )
    overview = library_overview(_database())
    sample = query_library(_database(), filters)
    return _emit({"overview": overview, "sample_owned": sample})


@mcp.tool()
def sample_owned_library(
    media_type: Optional[str] = "movie",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Sample owned library inventory for a slice (overview + owned titles).

    This is NOT TMDB missing-title discovery — use discover_missing_titles for gaps.
    """
    return _sample_owned_library_payload(
        media_type=media_type,
        year_from=year_from,
        year_to=year_to,
        genres=genres,
        limit=limit,
    )


@mcp.tool(name="find_collection_gaps")
def find_collection_gaps(
    media_type: Optional[str] = "movie",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Deprecated alias of sample_owned_library (owned inventory only).

    Prefer sample_owned_library for owned slices, or discover_missing_titles for
    real TMDB titles missing from the library. Kept for one release for clients
    still calling find_collection_gaps.
    """
    return _sample_owned_library_payload(
        media_type=media_type,
        year_from=year_from,
        year_to=year_to,
        genres=genres,
        limit=limit,
    )


@mcp.tool()
def discover_missing_titles(
    media_type: str = "movie",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    without_genres: Optional[str] = None,
    keywords: Optional[str] = None,
    without_keywords: Optional[str] = None,
    companies: Optional[str] = None,
    tv_type: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Privacy-safe TMDB titles missing from the library (real collection gaps).

    Shares agent find_collection_gaps filters (genres, negatives, years, tv_type,
    query). Returns title/year/media_type/poster CDN URLs with in_library=false.
    """
    from projectionist.agent.tools import ToolRegistry
    from projectionist.library.db import DEFAULT_LENS_ID

    settings = _settings()
    if not settings.tmdb_api_key:
        return _emit({"error": "TMDB API key is not configured"})

    args: dict[str, Any] = {"media_type": media_type}
    if year_from is not None:
        args["year_from"] = year_from
    if year_to is not None:
        args["year_to"] = year_to
    if genres:
        args["genres"] = genres
    if without_genres:
        args["without_genres"] = without_genres
    if keywords:
        args["keywords"] = keywords
    if without_keywords:
        args["without_keywords"] = without_keywords
    if companies:
        args["companies"] = companies
    if tv_type:
        args["tv_type"] = tv_type
    if query:
        args["query"] = query

    registry = ToolRegistry(_database(), settings, DEFAULT_LENS_ID)
    raw = asyncio.run(registry.execute("find_collection_gaps", args))
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _emit({"error": "Gap discovery failed", "detail": str(raw)[:240]})
    if not isinstance(payload, dict):
        return _emit({"error": "Gap discovery returned unexpected payload"})
    if payload.get("error"):
        return _emit({"error": payload["error"]})

    capped = max(1, min(int(limit or 12), 25))
    items_out: list[dict[str, Any]] = []
    # Prefer TitleCard posters (CDN URLs); fall back to tool JSON items.
    cards = list(getattr(registry, "cards", None) or [])
    if cards:
        for card in cards[:capped]:
            items_out.append(
                {
                    "title": str(getattr(card, "title", "") or ""),
                    "year": getattr(card, "year", None),
                    "media_type": str(getattr(card, "media_type", None) or media_type),
                    "tmdb_id": getattr(card, "tmdb_id", None),
                    "poster_url": str(getattr(card, "poster_url", "") or "") or None,
                    "in_library": False,
                }
            )
    else:
        for item in list(payload.get("items") or [])[:capped]:
            if not isinstance(item, dict):
                continue
            items_out.append(
                {
                    "title": str(item.get("title") or ""),
                    "year": item.get("year"),
                    "media_type": str(item.get("media_type") or media_type),
                    "tmdb_id": item.get("tmdb_id"),
                    "poster_url": item.get("poster_url") or None,
                    "in_library": False,
                }
            )
    return _emit(
        {
            "total_matched": int(payload.get("total_matched") or len(items_out)),
            "returned": len(items_out),
            "items": items_out,
            "genres_resolved": payload.get("genres_resolved") or [],
            "genres_unresolved": payload.get("genres_unresolved") or [],
            "genres_candidates": payload.get("genres_candidates") or [],
            "keywords_resolved": payload.get("keywords_resolved") or [],
            "keywords_unresolved": payload.get("keywords_unresolved") or [],
            "companies_resolved": payload.get("companies_resolved") or [],
            "companies_unresolved": payload.get("companies_unresolved") or [],
            "note": payload.get("note"),
        }
    )


@mcp.tool()
def recommend_hidden_gems(
    media_type: Optional[str] = "movie",
    limit: int = 12,
) -> str:
    """Surface lower-view-count owned titles (hidden gems). Full MCP only — affinity-biased."""
    denied = _require_full_mode()
    if denied:
        return denied
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            max_view_count=1,
            sort="vote",
            limit=limit,
        )
    )
    return _emit(query_library(_database(), filters))


@mcp.tool()
def suggest_purge_candidates_tool(limit: int = 12) -> str:
    """Suggest rarely watched / low-affinity owned titles for purge review. Full MCP only."""
    denied = _require_full_mode()
    if denied:
        return denied
    from projectionist.preferences.purge import suggest_purge_candidates

    cards = suggest_purge_candidates(_database(), _settings(), limit=min(max(1, limit), 25))
    return _emit({"count": len(cards), "items": [c.model_dump() for c in cards]})


@mcp.tool()
def analyze_watch_patterns(limit: int = 25) -> str:
    """High-level watch pattern snapshot from library overview + progress. Full MCP only."""
    denied = _require_full_mode()
    if denied:
        return denied
    overview = library_overview(_database())
    progress = summarize_tv_progress(_database(), group_by="show", in_progress_only=True, limit=limit)
    return _emit({"overview": overview, "in_progress_tv": progress})


@mcp.tool()
def list_watchlist_pins(limit: int = 50) -> str:
    """List household watchlist pins. Full MCP only (personal affinity sidecar)."""
    denied = _require_full_mode()
    if denied:
        return denied
    items = _database().list_watchlist_pins()[: max(1, min(limit, 200))]
    return _emit({"items": items, "count": len(items)})


@mcp.tool()
def upcoming_premieres(limit: int = 20) -> str:
    """Best-effort recently added library titles (proxy for newly available / premiere-like)."""
    filters = filters_from_mapping(
        _filter_mapping(recently_added_days=30, sort="added_at", limit=limit)
    )
    return _emit(query_library(_database(), filters))


@mcp.tool()
def search_tmdb_proxy(query: str, media_type: Optional[str] = "movie", limit: int = 10) -> str:
    """Search TMDB when configured (read-only discovery outside the owned library)."""
    from projectionist.connectors.tmdb import TMDBClient

    settings = _settings()
    if not settings.tmdb_api_key:
        return _emit({"error": "TMDB API key is not configured"})
    client = TMDBClient(settings.tmdb_api_key)
    capped = max(1, min(int(limit or 10), 25))
    if media_type == "show":
        results = client.search_tv(query)[:capped]
    else:
        results = client.search_movie(query)[:capped]
    # Always emit trimmed public TMDB fields (CDN posters only, no API key leakage).
    items = [_public_tmdb_item(dict(item)) for item in results if isinstance(item, dict)]
    return _emit({"items": items, "count": len(items)})


# --- Full-mode confirm-gated *arr tools -------------------------------------------------


@mcp.tool()
def propose_add_radarr(tmdb_id: int, title: str = "") -> str:
    """Full mode: queue a Radarr add for confirmation (returns pending_token)."""
    denied = _require_full_mode()
    if denied:
        return denied
    from projectionist.agent.tools import check_radarr_already_exists, mark_in_radarr
    from projectionist.config_store import (
        radarr_add_configuration_error,
        resolve_radarr_root_folder,
        validate_arr_root_folder,
    )
    from projectionist.connectors.radarr import RadarrClient

    settings = _settings()
    config_error = radarr_add_configuration_error(settings)
    if config_error:
        return _emit({"error": config_error})
    client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    root_error = validate_arr_root_folder(
        "Radarr",
        resolve_radarr_root_folder(settings),
        client.root_folders(),
    )
    if root_error:
        return _emit({"error": root_error})
    if _database().is_acquisition_excluded(media_type="movie", tmdb_id=int(tmdb_id)):
        return _emit(
            {
                "error": (
                    f"{title or 'This title'} was removed with an acquisition "
                    "exclusion and will not be re-added"
                )
            }
        )
    existing = check_radarr_already_exists(client, int(tmdb_id), title=title)
    if existing:
        mark_in_radarr(_database(), int(tmdb_id), title=title)
        return _emit(existing)
    token = uuid.uuid4().hex
    payload = {"action": "add_radarr", "tmdb_id": int(tmdb_id), "title": title}
    _database().save_pending_action(token, "add_radarr", payload, user_id=None)
    return _emit(
        {
            "pending_token": token,
            "confirmation_token": token,
            "summary": f"Add to Radarr: {title or tmdb_id}",
            "message": (
                "Confirm with confirm_pending_action if this key is scoped for "
                "active curation; otherwise a human confirms it in the Projectionist "
                "web UI status dock (or POST /api/actions/confirm)."
            ),
        }
    )


@mcp.tool()
def propose_add_sonarr(tvdb_id: int, title: str = "") -> str:
    """Full mode: queue a Sonarr add for confirmation (returns pending_token)."""
    denied = _require_full_mode()
    if denied:
        return denied
    from projectionist.agent.tools import check_sonarr_already_exists, mark_in_sonarr
    from projectionist.config_store import (
        resolve_sonarr_root_folder,
        sonarr_add_configuration_error,
        validate_arr_root_folder,
    )
    from projectionist.connectors.sonarr import SonarrClient

    settings = _settings()
    config_error = sonarr_add_configuration_error(settings)
    if config_error:
        return _emit({"error": config_error})
    client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    root_error = validate_arr_root_folder(
        "Sonarr",
        resolve_sonarr_root_folder(settings),
        client.root_folders(),
    )
    if root_error:
        return _emit({"error": root_error})
    if _database().is_acquisition_excluded(media_type="show", tvdb_id=int(tvdb_id)):
        return _emit(
            {
                "error": (
                    f"{title or 'This title'} was removed with an acquisition "
                    "exclusion and will not be re-added"
                )
            }
        )
    existing = check_sonarr_already_exists(client, int(tvdb_id), title=title)
    if existing:
        mark_in_sonarr(_database(), int(tvdb_id), title=title)
        return _emit(existing)
    token = uuid.uuid4().hex
    payload = {"action": "add_sonarr", "tvdb_id": int(tvdb_id), "title": title}
    _database().save_pending_action(token, "add_sonarr", payload, user_id=None)
    return _emit(
        {
            "pending_token": token,
            "confirmation_token": token,
            "summary": f"Add to Sonarr: {title or tvdb_id}",
            "message": (
                "Confirm with confirm_pending_action if this key is scoped for "
                "active curation; otherwise a human confirms it in the Projectionist "
                "web UI status dock (or POST /api/actions/confirm)."
            ),
        }
    )


@mcp.tool()
def propose_remove_arr(
    media_type: str = "movie",
    title: str = "",
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    arr_id: Optional[int] = None,
    delete_files: bool = False,
) -> str:
    """Full mode: queue an *arr remove for confirmation (returns pending_token)."""
    denied = _require_full_mode()
    if denied:
        return denied
    from projectionist.agent.tools import resolve_arr_removal_target
    from projectionist.connectors.arr_errors import ArrTitleNotFoundError

    try:
        resolved = resolve_arr_removal_target(
            _settings(),
            media_type=media_type,
            arr_id=int(arr_id) if arr_id is not None else None,
            tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
            tvdb_id=int(tvdb_id) if tvdb_id is not None else None,
            title=title,
        )
    except ArrTitleNotFoundError as error:
        return _emit({"error": str(error)})
    token = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "action": "remove_arr",
        "media_type": media_type,
        "arr_id": resolved["arr_id"],
        "title": resolved.get("title") or title,
        "delete_files": bool(delete_files),
    }
    if resolved.get("tmdb_id") is not None:
        payload["tmdb_id"] = resolved["tmdb_id"]
    if resolved.get("tvdb_id") is not None:
        payload["tvdb_id"] = resolved["tvdb_id"]
    _database().save_pending_action(token, "remove_arr", payload, user_id=None)
    return _emit(
        {
            "pending_token": token,
            "confirmation_token": token,
            "summary": f"Remove from *arr: {payload['title']}",
            "arr_id": resolved["arr_id"],
            "message": (
                "Confirm with confirm_pending_action if this key is scoped for "
                "active curation; otherwise a human confirms it in the Projectionist "
                "web UI status dock (or POST /api/actions/confirm)."
            ),
        }
    )


@mcp.tool()
def confirm_pending_action(token: str, confirmed: bool = True) -> str:
    """Full mode: confirm or cancel a pending *arr propose token.

    Confirming (executing) a fleet mutation requires the full key to carry the
    active-curation scope, chosen at key creation (``mcp_full_confirm_enabled``
    setting, or ``PROJECTIONIST_MCP_FULL_CONFIRM`` for stdio/CA). A key without
    that scope may propose and cancel, but cannot self-confirm — a human
    confirms it on the authenticated web plane instead (review finding H3).
    Cancelling is always allowed and leaves nothing to execute.
    """
    denied = _require_full_mode()
    if denied:
        return denied

    if not confirmed:
        try:
            popped = _database().pop_pending_action(token)
        except Exception as error:  # noqa: BLE001
            return _emit({"error": str(error)})
        return _emit({"cancelled": True, "found": popped is not None})

    if not full_confirm_scope_enabled():
        return _emit(
            {
                "error": "This MCP key is not scoped for active curation.",
                "requires_human_confirmation": True,
                "pending_token": token,
                "message": (
                    "This full key can propose and cancel but not self-confirm. "
                    "Confirm this token in the Projectionist web UI status dock or "
                    "via POST /api/actions/confirm as an authenticated owner, or "
                    "issue a full key with the active-curation scope "
                    "(mcp_full_confirm_enabled / PROJECTIONIST_MCP_FULL_CONFIRM)."
                ),
            }
        )

    async def _run() -> dict[str, Any]:
        from projectionist.agent.tools import execute_confirmed_action

        result = await execute_confirmed_action(_database(), _settings(), token, user_id=None)
        return {"ok": True, **result}

    try:
        return _emit(asyncio.run(_run()))
    except Exception as error:  # noqa: BLE001
        return _emit({"error": str(error)})


def main() -> None:
    from projectionist.config_store import load_dotenv_file
    from projectionist.envcompat import skip_dotenv
    from projectionist.logging_config import configure_logging

    if not skip_dotenv():
        load_dotenv_file()
    configure_logging()
    mode = resolve_stdio_mcp_mode()
    set_mcp_mode(mode)
    logging.getLogger(__name__).info("CuratorX MCP server starting mode=%s", mode)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
