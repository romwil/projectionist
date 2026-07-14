"""MCP stdio server exposing CuratorX library query tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from curatorx.config_store import Settings, load_merged_settings
from curatorx.library.db import Database
from curatorx.library.episodes import query_episodes, summarize_tv_progress
from curatorx.library.facets import ensure_library_facet_index, library_facet_catalog
from curatorx.library.query import (
    aggregate_library,
    filters_from_mapping,
    library_overview,
    query_library,
    query_library_async,
)
from curatorx.library.titles import get_title_detail
from curatorx.web.jobs import _resolve_db_path

mcp = FastMCP(
    "CuratorX Library",
    instructions=(
        "Query the user's Plex library indexed by CuratorX. "
        "Use library_query for paginated owned-title browse with rich filters; "
        "library_aggregate for counts; library_facet_catalog for top directors/actors; "
        "library_tv_episodes and library_tv_progress for TV episode-level queries."
    ),
)


def _database() -> Database:
    data_dir = Path(os.environ.get("DATA_DIR", "/config"))
    db = Database(_resolve_db_path(data_dir))
    ensure_library_facet_index(db)
    return db


def _settings() -> Settings:
    return load_merged_settings(Path(os.environ.get("DATA_DIR", "/config")))


def _filter_mapping(**kwargs: Any) -> dict[str, Any]:
    bool_keys = {"unwatched_only", "in_progress_only", "missing_tmdb_id"}
    return {
        key: value
        for key, value in kwargs.items()
        if value is not None or key in bool_keys
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
    return json.dumps(result)


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
        return json.dumps({"error": f"group_by must be one of: {', '.join(sorted(allowed))}"})
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
    return json.dumps(aggregate_library(_database(), normalized, filters))  # type: ignore[arg-type]


@mcp.tool()
def library_facet_catalog_tool(facet_type: str, limit: int = 50) -> str:
    """List top directors, actors, keywords, countries, or languages in the library."""
    try:
        return json.dumps(library_facet_catalog(_database(), facet_type, limit=limit))
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


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
    return json.dumps(
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
        return json.dumps(
            summarize_tv_progress(
                _database(),
                group_by=group_by,
                in_progress_only=in_progress_only,
                limit=limit,
            )
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def library_overview_tool() -> str:
    """Compact library inventory: totals, decades, genres, directors, TV progress."""
    return json.dumps(library_overview(_database()))


@mcp.tool()
def library_title_detail(
    media_type: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
) -> str:
    """Fetch rich metadata for one title in or outside the library."""
    kwargs: dict[str, Any] = {"media_type": media_type}
    if rating_key:
        kwargs["rating_key"] = rating_key
    elif tvdb_id is not None:
        kwargs["tvdb_id"] = tvdb_id
    elif tmdb_id is not None:
        kwargs["tmdb_id"] = tmdb_id
    else:
        return json.dumps({"error": "Provide tmdb_id, tvdb_id, or rating_key"})
    detail = get_title_detail(_database(), _settings(), **kwargs)
    return json.dumps(detail.model_dump())



@mcp.tool()
def what_to_watch_tonight(
    media_type: Optional[str] = "movie",
    query: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Suggest owned titles worth watching now (unwatched / in-progress bias)."""
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
    return json.dumps(result)


@mcp.tool()
def find_collection_gaps(
    media_type: Optional[str] = "movie",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Summarize owned inventory slices useful for spotting collection gaps."""
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
    return json.dumps({"overview": overview, "sample_owned": sample})


@mcp.tool()
def recommend_hidden_gems(
    media_type: Optional[str] = "movie",
    limit: int = 12,
) -> str:
    """Surface lower-view-count owned titles (hidden gems in the library)."""
    filters = filters_from_mapping(
        _filter_mapping(
            media_type=media_type,
            max_view_count=1,
            sort="vote",
            limit=limit,
        )
    )
    return json.dumps(query_library(_database(), filters))


@mcp.tool()
def suggest_purge_candidates_tool(limit: int = 12) -> str:
    """Suggest rarely watched / low-affinity owned titles for purge review."""
    from curatorx.preferences.purge import suggest_purge_candidates

    cards = suggest_purge_candidates(_database(), _settings(), limit=min(max(1, limit), 25))
    return json.dumps({"count": len(cards), "items": [c.model_dump() for c in cards]})


@mcp.tool()
def analyze_watch_patterns(limit: int = 25) -> str:
    """High-level watch pattern snapshot from library overview + progress."""
    overview = library_overview(_database())
    progress = summarize_tv_progress(_database(), group_by="show", in_progress_only=True, limit=limit)
    return json.dumps({"overview": overview, "in_progress_tv": progress})


@mcp.tool()
def list_watchlist_pins(limit: int = 50) -> str:
    """List household watchlist pins (shared library sidecar; no per-user MCP auth yet)."""
    items = _database().list_watchlist_pins()[: max(1, min(limit, 200))]
    return json.dumps({"items": items, "count": len(items)})


@mcp.tool()
def upcoming_premieres(limit: int = 20) -> str:
    """Best-effort recently added library titles (proxy for newly available / premiere-like)."""
    filters = filters_from_mapping(
        _filter_mapping(recently_added_days=30, sort="added_at", limit=limit)
    )
    return json.dumps(query_library(_database(), filters))


@mcp.tool()
def search_tmdb_proxy(query: str, media_type: Optional[str] = "movie", limit: int = 10) -> str:
    """Search TMDB when configured (read-only discovery outside the owned library)."""
    from curatorx.connectors.tmdb import TmdbClient

    settings = _settings()
    if not settings.tmdb_api_key:
        return json.dumps({"error": "TMDB API key is not configured"})
    client = TmdbClient(settings.tmdb_api_key)
    if media_type == "show":
        results = client.search_tv(query)[:limit]
    else:
        results = client.search_movie(query)[:limit]
    return json.dumps({"items": results, "count": len(results)})



def main() -> None:
    from curatorx.config_store import load_dotenv_file
    from curatorx.logging_config import configure_logging

    if os.environ.get("CURATORX_SKIP_DOTENV") != "1":
        load_dotenv_file()
    configure_logging()
    logging.getLogger(__name__).info("CuratorX MCP server starting")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
