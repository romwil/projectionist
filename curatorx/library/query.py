"""Structured library queries: filters, pagination, aggregates, overview."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

from curatorx.config_store import Settings
from curatorx.library.db import ACTIVE_CONTEXT_CONFIG_KEY, DEFAULT_CONTEXT_HASH, Database
from curatorx.library.embeddings import embed_text, semantic_search
from curatorx.library.facets import library_facet_catalog

MAX_QUERY_LIMIT = 50
DEFAULT_QUERY_LIMIT = 25
OVERVIEW_CACHE_KEY = "library_overview"

SortField = Literal[
    "title",
    "year",
    "view_count",
    "file_size",
    "vote_average",
    "runtime_minutes",
    "added_at",
    "last_viewed_at",
    "unwatched_episode_count",
]
GroupBy = Literal[
    "decade",
    "year",
    "genre",
    "media_type",
    "director",
    "actor",
    "keyword",
    "content_rating",
    "country",
    "language",
    "runtime_bucket",
    "decade_genre",
]


@dataclass
class LibraryFilters:
    media_type: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    genres: List[str] = field(default_factory=list)
    directors: List[str] = field(default_factory=list)
    cast: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    motifs: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    content_ratings: List[str] = field(default_factory=list)
    collection_name: Optional[str] = None
    original_language: Optional[str] = None
    query: Optional[str] = None
    fts_query: Optional[str] = None
    semantic_query: Optional[str] = None
    # Plot Lab: hybrid = motif ∪ keyword ∪ live plot-text per token (AND across tokens).
    # motifs = pure library_facets motif AND (legacy motif walls).
    plot_match_mode: Literal["hybrid", "motifs"] = "hybrid"
    unwatched_only: bool = False
    min_view_count: Optional[int] = None
    max_view_count: Optional[int] = None
    stale_days: Optional[int] = None
    added_from: Optional[int] = None
    added_to: Optional[int] = None
    recently_added_days: Optional[int] = None
    last_viewed_from: Optional[int] = None
    last_viewed_to: Optional[int] = None
    runtime_min: Optional[int] = None
    runtime_max: Optional[int] = None
    vote_min: Optional[float] = None
    vote_max: Optional[float] = None
    file_size_min: Optional[int] = None
    file_size_max: Optional[int] = None
    in_radarr: Optional[bool] = None
    in_sonarr: Optional[bool] = None
    missing_tmdb_id: bool = False
    min_unwatched_episodes: Optional[int] = None
    max_unwatched_episodes: Optional[int] = None
    in_progress_only: bool = False
    sort: SortField = "title"
    offset: int = 0
    limit: int = DEFAULT_QUERY_LIMIT

    def normalized_limit(self) -> int:
        return min(max(1, int(self.limit or DEFAULT_QUERY_LIMIT)), MAX_QUERY_LIMIT)

    def normalized_offset(self) -> int:
        return max(0, int(self.offset or 0))


def _parse_csv_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def filters_from_mapping(data: Mapping[str, Any]) -> LibraryFilters:
    sort = str(data.get("sort") or "title").strip().lower()
    allowed_sort = {
        "title",
        "year",
        "view_count",
        "file_size",
        "vote_average",
        "runtime_minutes",
        "added_at",
        "last_viewed_at",
        "unwatched_episode_count",
    }
    if sort not in allowed_sort:
        sort = "title"

    in_radarr = data.get("in_radarr")
    in_sonarr = data.get("in_sonarr")

    added_from = _parse_timestamp(data.get("added_from"))
    added_to = _parse_timestamp(data.get("added_to"), end_of_day=True)
    recently_added_days = _optional_int(data.get("recently_added_days"))
    if recently_added_days is not None:
        cutoff = int(time.time()) - recently_added_days * 86400
        added_from = max(added_from, cutoff) if added_from is not None else cutoff

    plot_match_mode_raw = str(data.get("plot_match_mode") or "hybrid").strip().lower()
    plot_match_mode: Literal["hybrid", "motifs"] = (
        "motifs" if plot_match_mode_raw in {"motifs", "motif", "pure"} else "hybrid"
    )

    return LibraryFilters(
        media_type=str(data["media_type"]).strip() if data.get("media_type") else None,
        year_from=_optional_int(data.get("year_from")),
        year_to=_optional_int(data.get("year_to")),
        genres=_parse_csv_list(data.get("genres")),
        directors=_parse_csv_list(data.get("directors")),
        cast=_parse_csv_list(data.get("cast")),
        keywords=_parse_csv_list(data.get("keywords")),
        motifs=_parse_csv_list(data.get("motifs")),
        themes=_parse_csv_list(data.get("themes")),
        countries=_parse_csv_list(data.get("countries")),
        content_ratings=_parse_csv_list(data.get("content_ratings")),
        collection_name=str(data["collection_name"]).strip() if data.get("collection_name") else None,
        original_language=str(data["original_language"]).strip() if data.get("original_language") else None,
        query=str(data["query"]).strip() if data.get("query") else None,
        fts_query=str(data["fts_query"]).strip() if data.get("fts_query") else None,
        semantic_query=str(data["semantic_query"]).strip() if data.get("semantic_query") else None,
        plot_match_mode=plot_match_mode,
        unwatched_only=bool(data.get("unwatched_only")),
        min_view_count=_optional_int(data.get("min_view_count")),
        max_view_count=_optional_int(data.get("max_view_count")),
        stale_days=_optional_int(data.get("stale_days")),
        added_from=added_from,
        added_to=added_to,
        recently_added_days=recently_added_days,
        last_viewed_from=_parse_timestamp(data.get("last_viewed_from")),
        last_viewed_to=_parse_timestamp(data.get("last_viewed_to"), end_of_day=True),
        runtime_min=_optional_int(data.get("runtime_min")),
        runtime_max=_optional_int(data.get("runtime_max")),
        vote_min=_optional_float(data.get("vote_min")),
        vote_max=_optional_float(data.get("vote_max")),
        file_size_min=_optional_int(data.get("file_size_min")),
        file_size_max=_optional_int(data.get("file_size_max")),
        in_radarr=bool(in_radarr) if in_radarr is not None else None,
        in_sonarr=bool(in_sonarr) if in_sonarr is not None else None,
        missing_tmdb_id=bool(data.get("missing_tmdb_id")),
        min_unwatched_episodes=_optional_int(data.get("min_unwatched_episodes")),
        max_unwatched_episodes=_optional_int(data.get("max_unwatched_episodes")),
        in_progress_only=bool(data.get("in_progress_only")),
        sort=sort,  # type: ignore[arg-type]
        offset=int(data.get("offset") or 0),
        limit=int(data.get("limit") or DEFAULT_QUERY_LIMIT),
    )


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any, *, end_of_day: bool = False) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        if len(text) == 10:
            dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59)
            return int(dt.timestamp())
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def _parse_json_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(g) for g in parsed]
        return []
    return []


def build_facet_match_details(
    filters: LibraryFilters,
    item: Mapping[str, Any],
) -> tuple[str, List[str]]:
    """Build recommendation_reason and facet_matches from active query filters."""
    matches: List[str] = []

    if filters.genres:
        item_genres = {str(g).lower() for g in (item.get("genres") or [])}
        for genre in filters.genres:
            needle = genre.lower()
            if needle in item_genres or any(needle in g for g in item_genres):
                matches.append(f"Genre: {genre}")

    for facet_label, filter_values, item_key in (
        ("Director", filters.directors, "directors"),
        ("Cast", filters.cast, "cast"),
        ("Keyword", filters.keywords, "keywords"),
    ):
        if not filter_values:
            continue
        item_values = [str(v).lower() for v in (item.get(item_key) or [])]
        for value in filter_values:
            needle = value.lower()
            if any(needle in entry for entry in item_values):
                matches.append(f"{facet_label}: {value}")

    if filters.countries:
        item_countries = {str(c).lower() for c in (item.get("countries") or [])}
        for country in filters.countries:
            needle = country.lower()
            if needle in item_countries or any(needle in c for c in item_countries):
                matches.append(f"Country: {country}")

    if filters.year_from is not None or filters.year_to is not None:
        year = item.get("year")
        if year is not None:
            year_from = filters.year_from if filters.year_from is not None else year
            year_to = filters.year_to if filters.year_to is not None else year
            if year_from <= int(year) <= year_to:
                if filters.year_from is not None and filters.year_to is not None:
                    matches.append(f"Year: {filters.year_from}–{filters.year_to}")
                elif filters.year_from is not None:
                    matches.append(f"Year: {filters.year_from}+")
                else:
                    matches.append(f"Year: ≤{filters.year_to}")

    if filters.unwatched_only and int(item.get("view_count") or 0) == 0:
        matches.append("Unwatched")
    if filters.in_progress_only:
        total_eps = int(item.get("total_episode_count") or 0)
        unwatched_eps = int(item.get("unwatched_episode_count") or 0)
        if total_eps > 0 and 0 < unwatched_eps < total_eps:
            matches.append("In progress")
    if filters.semantic_query:
        matches.append(f"Mood: {filters.semantic_query}")
    if filters.query:
        matches.append(f"Title/summary: {filters.query}")
    if filters.fts_query:
        matches.append(f"Full-text: {filters.fts_query}")
    if filters.motifs:
        for motif in filters.motifs:
            matches.append(f"Motif: {motif}")
    if filters.themes:
        for theme in filters.themes:
            matches.append(f"Theme: {theme}")

    if matches:
        reason = "Matches your query — " + "; ".join(matches[:4])
        if len(matches) > 4:
            reason += f" (+{len(matches) - 4} more)"
        return reason, matches
    return "In your library", []


def row_to_query_item(row: Mapping[str, Any]) -> Dict[str, Any]:
    keys = row.keys()
    total_eps = int(row["total_episode_count"] or 0) if "total_episode_count" in keys else 0
    unwatched_eps = int(row["unwatched_episode_count"] or 0) if "unwatched_episode_count" in keys else 0
    return {
        "id": int(row["id"]),
        "title": str(row["title"]),
        "year": int(row["year"]) if row["year"] is not None else None,
        "media_type": str(row["media_type"]),
        "genres": _parse_json_list(row["genres"]),
        "directors": _parse_json_list(row["directors"]) if "directors" in keys else [],
        "cast": _parse_json_list(row["cast"]) if "cast" in keys else [],
        "keywords": _parse_json_list(row["keywords"]) if "keywords" in keys else [],
        "view_count": int(row["view_count"] or 0),
        "added_at": int(row["added_at"]) if "added_at" in keys and row["added_at"] is not None else None,
        "last_viewed_at": int(row["last_viewed_at"]) if "last_viewed_at" in keys and row["last_viewed_at"] is not None else None,
        "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
        "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
        "rating_key": str(row["rating_key"] or ""),
        "file_size": int(row["file_size"] or 0) if "file_size" in keys else 0,
        "poster_url": str(row["poster_url"] or "") if "poster_url" in keys else "",
        "backdrop_url": str(row["backdrop_url"] or "") if "backdrop_url" in keys else "",
        "runtime_minutes": int(row["runtime_minutes"]) if "runtime_minutes" in keys and row["runtime_minutes"] is not None else None,
        "vote_average": float(row["vote_average"]) if "vote_average" in keys and row["vote_average"] is not None else None,
        "content_rating": str(row["content_rating"] or "") if "content_rating" in keys else "",
        "original_language": str(row["original_language"] or "") if "original_language" in keys else "",
        "countries": _parse_json_list(row["countries"]) if "countries" in keys else [],
        "collection_name": str(row["collection_name"] or "") if "collection_name" in keys else "",
        "unwatched_episode_count": unwatched_eps,
        "total_episode_count": total_eps,
        "in_radarr": bool(row["in_radarr"]) if "in_radarr" in keys else False,
        "in_sonarr": bool(row["in_sonarr"]) if "in_sonarr" in keys else False,
    }


def _facet_subquery(facet_type: str, values: List[str]) -> Tuple[str, List[Any]]:
    clauses = []
    params: List[Any] = []
    for value in values:
        clauses.append("(facet_type = ? AND lower(facet_value) LIKE ?)")
        params.extend([facet_type, f"%{value.lower()}%"])
    sql = f"id IN (SELECT item_id FROM library_facets WHERE {' OR '.join(clauses)})"
    return sql, params


def _plot_signal_subquery(token: str) -> Tuple[str, List[Any]]:
    """Match one Plot Lab token via motif/keyword/theme facet OR live plot text."""
    needle = f"%{token.lower()}%"
    sql = (
        "id IN ("
        "SELECT item_id FROM library_facets "
        "WHERE (facet_type = 'motif' OR facet_type = 'keyword' OR facet_type = 'theme') "
        "AND lower(facet_value) LIKE ? "
        "UNION "
        "SELECT id FROM library_items WHERE "
        "lower(COALESCE(summary, '')) LIKE ? "
        "OR lower(COALESCE(tmdb_overview, '')) LIKE ? "
        "OR lower(COALESCE(tagline, '')) LIKE ? "
        "OR lower(COALESCE(long_synopsis, '')) LIKE ? "
        "OR lower(COALESCE(llm_logline, '')) LIKE ? "
        "OR lower(COALESCE(keywords, '')) LIKE ?"
        ")"
    )
    # Note: keep keyword JSON LIKE as a cheap fallback when facets lag sync.
    return sql, [needle, needle, needle, needle, needle, needle, needle]


def _effective_added_from(filters: LibraryFilters) -> Optional[int]:
    added_from = filters.added_from
    if filters.recently_added_days is not None:
        cutoff = int(time.time()) - filters.recently_added_days * 86400
        added_from = max(added_from, cutoff) if added_from is not None else cutoff
    return added_from


def _build_where(filters: LibraryFilters) -> Tuple[str, List[Any]]:
    clauses: List[str] = ["1=1"]
    params: List[Any] = []

    if filters.media_type:
        clauses.append("media_type = ?")
        params.append(filters.media_type)
    if filters.year_from is not None:
        clauses.append("year >= ?")
        params.append(filters.year_from)
    if filters.year_to is not None:
        clauses.append("year <= ?")
        params.append(filters.year_to)
    if filters.query:
        pattern = f"%{filters.query.lower()}%"
        clauses.append("(lower(title) LIKE ? OR lower(summary) LIKE ?)")
        params.extend([pattern, pattern])
    if filters.fts_query:
        clauses.append(
            "id IN (SELECT item_id FROM library_fts WHERE library_fts MATCH ?)"
        )
        params.append(filters.fts_query)
    if filters.unwatched_only:
        clauses.append("(view_count IS NULL OR view_count = 0)")
    if filters.min_view_count is not None:
        clauses.append("view_count >= ?")
        params.append(filters.min_view_count)
    if filters.max_view_count is not None:
        clauses.append("view_count <= ?")
        params.append(filters.max_view_count)
    if filters.stale_days is not None:
        cutoff = int(time.time()) - filters.stale_days * 86400
        clauses.append("(last_viewed_at IS NULL OR last_viewed_at < ?)")
        params.append(cutoff)
    added_from = _effective_added_from(filters)
    if added_from is not None:
        clauses.append("added_at >= ?")
        params.append(added_from)
    if filters.added_to is not None:
        clauses.append("added_at <= ?")
        params.append(filters.added_to)
    if filters.last_viewed_from is not None:
        clauses.append("last_viewed_at >= ?")
        params.append(filters.last_viewed_from)
    if filters.last_viewed_to is not None:
        clauses.append("last_viewed_at <= ?")
        params.append(filters.last_viewed_to)
    if filters.genres:
        genre_clauses = []
        for genre in filters.genres:
            genre_clauses.append("lower(genres) LIKE ?")
            params.append(f"%{genre.lower()}%")
        clauses.append(f"({' OR '.join(genre_clauses)})")
    if filters.directors:
        facet_sql, facet_params = _facet_subquery("director", filters.directors)
        clauses.append(facet_sql)
        params.extend(facet_params)
    if filters.cast:
        facet_sql, facet_params = _facet_subquery("actor", filters.cast)
        clauses.append(facet_sql)
        params.extend(facet_params)
    if filters.keywords:
        # Multiple keywords are AND (each tag must match) for tag browse filters.
        for keyword in filters.keywords:
            facet_sql, facet_params = _facet_subquery("keyword", [keyword])
            clauses.append(facet_sql)
            params.extend(facet_params)
    if filters.collection_name:
        clauses.append("lower(collection_name) = ?")
        params.append(filters.collection_name.lower())
    if filters.motifs:
        # Multiple tokens are AND. Hybrid (default) unions motif ∪ keyword ∪ plot text
        # per token so sparse motif facets do not brick Plot Lab intersections.
        if filters.plot_match_mode == "motifs":
            for motif in filters.motifs:
                facet_sql, facet_params = _facet_subquery("motif", [motif])
                clauses.append(facet_sql)
                params.extend(facet_params)
        else:
            for motif in filters.motifs:
                signal_sql, signal_params = _plot_signal_subquery(motif)
                clauses.append(signal_sql)
                params.extend(signal_params)
    if filters.themes:
        for theme in filters.themes:
            facet_sql, facet_params = _facet_subquery("theme", [theme])
            clauses.append(facet_sql)
            params.extend(facet_params)
    if filters.countries:
        country_clauses = []
        for country in filters.countries:
            country_clauses.append("lower(countries) LIKE ?")
            params.append(f"%{country.lower()}%")
        clauses.append(f"({' OR '.join(country_clauses)})")
    if filters.original_language:
        clauses.append("lower(original_language) = ?")
        params.append(filters.original_language.lower())
    if filters.content_ratings:
        rating_clauses = []
        for rating in filters.content_ratings:
            rating_clauses.append("lower(content_rating) LIKE ?")
            params.append(f"%{rating.lower()}%")
        clauses.append(f"({' OR '.join(rating_clauses)})")
    if filters.runtime_min is not None:
        clauses.append("runtime_minutes >= ?")
        params.append(filters.runtime_min)
    if filters.runtime_max is not None:
        clauses.append("runtime_minutes <= ?")
        params.append(filters.runtime_max)
    if filters.vote_min is not None:
        clauses.append("vote_average >= ?")
        params.append(filters.vote_min)
    if filters.vote_max is not None:
        clauses.append("vote_average <= ?")
        params.append(filters.vote_max)
    if filters.file_size_min is not None:
        clauses.append("file_size >= ?")
        params.append(filters.file_size_min)
    if filters.file_size_max is not None:
        clauses.append("file_size <= ?")
        params.append(filters.file_size_max)
    if filters.in_radarr is not None:
        clauses.append("in_radarr = ?")
        params.append(int(filters.in_radarr))
    if filters.in_sonarr is not None:
        clauses.append("in_sonarr = ?")
        params.append(int(filters.in_sonarr))
    if filters.missing_tmdb_id:
        clauses.append("tmdb_id IS NULL")
    if filters.min_unwatched_episodes is not None:
        clauses.append("unwatched_episode_count >= ?")
        params.append(filters.min_unwatched_episodes)
    if filters.max_unwatched_episodes is not None:
        clauses.append("unwatched_episode_count <= ?")
        params.append(filters.max_unwatched_episodes)
    if filters.in_progress_only:
        clauses.append(
            "total_episode_count > 0 AND unwatched_episode_count > 0 "
            "AND unwatched_episode_count < total_episode_count"
        )

    return " AND ".join(clauses), params


def _sort_clause(sort: SortField) -> str:
    mapping = {
        "year": "year IS NULL, year DESC, title ASC",
        "view_count": "view_count DESC, title ASC",
        "file_size": "file_size DESC, title ASC",
        "vote_average": "vote_average IS NULL, vote_average DESC, title ASC",
        "runtime_minutes": "runtime_minutes IS NULL, runtime_minutes ASC, title ASC",
        "added_at": "added_at IS NULL, added_at DESC, title ASC",
        "last_viewed_at": "last_viewed_at IS NULL, last_viewed_at DESC, title ASC",
        "unwatched_episode_count": "unwatched_episode_count DESC, title ASC",
    }
    return mapping.get(sort, "title ASC")


def _fetch_rows(
    db: Database,
    where_sql: str,
    params: List[Any],
    *,
    sort_sql: str,
    limit: int,
    offset: int,
    item_ids: Optional[Sequence[int]] = None,
) -> Tuple[int, List[Any]]:
    id_filter = ""
    id_params: List[Any] = []
    if item_ids is not None:
        if not item_ids:
            return 0, []
        placeholders = ",".join("?" for _ in item_ids)
        id_filter = f" AND id IN ({placeholders})"
        id_params = list(item_ids)

    with db.connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM library_items WHERE {where_sql}{id_filter}",
            [*params, *id_params],
        ).fetchone()["cnt"]
        rows = conn.execute(
            f"""
            SELECT * FROM library_items
            WHERE {where_sql}{id_filter}
            ORDER BY {sort_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, *id_params, limit, offset],
        ).fetchall()
    return int(total), list(rows)


async def query_library_async(
    db: Database,
    filters: LibraryFilters,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    where_sql, params = _build_where(filters)
    limit = filters.normalized_limit()
    offset = filters.normalized_offset()
    sort_sql = _sort_clause(filters.sort)

    semantic_ids: Optional[List[int]] = None
    if filters.semantic_query and settings is not None:
        vector = await embed_text(filters.semantic_query, settings)
        with db.connect() as conn:
            candidate_rows = conn.execute(
                f"SELECT id FROM library_items WHERE {where_sql}",
                params,
            ).fetchall()
        candidate_ids = {int(r["id"]) for r in candidate_rows}
        hits = semantic_search(
            db,
            vector,
            limit=max(limit * 4, 100),
            media_type=filters.media_type,
            candidate_ids=candidate_ids,
        )
        semantic_ids = [item_id for item_id, _score in hits]
        if not semantic_ids:
            return {
                "total_matched": 0,
                "returned": 0,
                "offset": offset,
                "has_more": False,
                "items": [],
                "search_mode": "semantic",
            }
        total_matched = len(semantic_ids)
        page_ids = semantic_ids[offset : offset + limit]
        with db.connect() as conn:
            placeholders = ",".join("?" for _ in page_ids)
            rows = conn.execute(
                f"SELECT * FROM library_items WHERE id IN ({placeholders})",
                page_ids,
            ).fetchall()
        row_by_id = {int(r["id"]): r for r in rows}
        ordered_rows = [row_by_id[item_id] for item_id in page_ids if item_id in row_by_id]
        items = [row_to_query_item(row) for row in ordered_rows]
        if filters.motifs:
            attach_motif_why(db, items, filters.motifs)
        returned = len(items)
        return {
            "total_matched": total_matched,
            "returned": returned,
            "offset": offset,
            "has_more": offset + returned < total_matched,
            "items": items,
            "search_mode": "semantic",
        }

    total_matched, rows = _fetch_rows(
        db,
        where_sql,
        params,
        sort_sql=sort_sql,
        limit=limit,
        offset=offset,
    )
    items = [row_to_query_item(row) for row in rows]
    if filters.motifs:
        attach_motif_why(db, items, filters.motifs)
    returned = len(items)
    payload = {
        "total_matched": total_matched,
        "returned": returned,
        "offset": offset,
        "has_more": offset + returned < total_matched,
        "items": items,
    }
    if filters.fts_query:
        payload["search_mode"] = "fts"
    elif filters.semantic_query:
        payload["search_mode"] = "semantic_unavailable"
    return payload


def _excerpt_around(text: str, needle: str, *, radius: int = 72) -> str:
    """Return a short plot window centered on the first case-insensitive needle hit."""
    body = " ".join(str(text or "").split())
    token = str(needle or "").strip()
    if not body or not token:
        return ""
    lower = body.lower()
    idx = lower.find(token.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(body), idx + len(token) + radius)
    excerpt = body[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(body):
        excerpt = excerpt + "…"
    return excerpt


def _token_in_values(needle: str, values: Sequence[str]) -> bool:
    target = needle.lower()
    return any(target == value or target in value for value in values)


def _layer_label(layer: str) -> str:
    return {
        "motif": "plot motif",
        "keyword": "keyword",
        "theme": "theme",
        "plot_text": "plot text",
    }.get(layer, layer)


def build_motif_why(
    selected_motifs: List[str],
    item_motif_values: List[str],
    *,
    plot_text: str = "",
    item_keyword_values: Optional[Sequence[str]] = None,
    item_theme_values: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Explain why a title appears for the selected Plot Lab tokens.

    Layers (any may match in hybrid mode):
    - ``motif`` — ``library_facets`` motif value
    - ``keyword`` — ``library_facets`` / item keyword value
    - ``theme`` — controlled theme facet (keyword→theme map)
    - ``plot_text`` — live summary/overview/tagline/long_synopsis/logline excerpt
    """
    selected = [str(m).strip() for m in (selected_motifs or []) if str(m).strip()]
    owned = [str(v).strip().lower() for v in (item_motif_values or []) if str(v).strip()]
    keywords = [
        str(v).strip().lower() for v in (item_keyword_values or []) if str(v).strip()
    ]
    themes = [
        str(v).strip().lower() for v in (item_theme_values or []) if str(v).strip()
    ]
    plot_lower = str(plot_text or "").lower()
    matched: List[str] = []
    missed: List[str] = []
    match_layers: List[Dict[str, Any]] = []

    for motif in selected:
        needle = motif.lower()
        layers: List[str] = []
        if _token_in_values(needle, owned):
            layers.append("motif")
        if _token_in_values(needle, keywords):
            layers.append("keyword")
        if _token_in_values(needle, themes):
            layers.append("theme")
        if needle and needle in plot_lower:
            layers.append("plot_text")
        if layers:
            matched.append(motif)
            match_layers.append({"motif": motif, "layers": layers})
        else:
            missed.append(motif)

    excerpts: List[Dict[str, str]] = []
    for motif in matched:
        excerpt = _excerpt_around(plot_text, motif)
        if excerpt:
            excerpts.append({"motif": motif, "excerpt": excerpt})

    if not selected:
        summary = "No motifs selected."
    elif not matched:
        summary = "Selected motifs are not attached to this title’s plot signals."
    else:
        parts: List[str] = []
        for entry in match_layers:
            labels = [_layer_label(layer) for layer in entry["layers"]]
            joined_layers = " + ".join(labels)
            parts.append(f"“{entry['motif']}” ({joined_layers})")
        if len(matched) == len(selected):
            if len(matched) == 1:
                summary = f"Selected because {parts[0]}."
            else:
                summary = "Selected because " + "; ".join(parts) + "."
        else:
            summary = "Matches " + "; ".join(parts) + " among the selected motifs."

    return {
        "matched_motifs": matched,
        "missed_motifs": missed,
        "match_layers": match_layers,
        "excerpts": excerpts,
        "summary": summary,
    }


def attach_motif_why(
    db: Database,
    items: List[Dict[str, Any]],
    selected_motifs: List[str],
) -> None:
    """Mutate query items in place with motif match explanations."""
    selected = [str(m).strip() for m in (selected_motifs or []) if str(m).strip()]
    if not selected or not items:
        return
    ids = [int(item["id"]) for item in items if item.get("id") is not None]
    motifs_by_id = db.facet_values_for_items(ids, "motif")
    keywords_by_id = db.facet_values_for_items(ids, "keyword")
    themes_by_id = db.facet_values_for_items(ids, "theme")
    plots_by_id = db.plot_text_for_items(ids)
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue
        key = int(item_id)
        why = build_motif_why(
            selected,
            motifs_by_id.get(key) or [],
            plot_text=plots_by_id.get(key) or "",
            item_keyword_values=keywords_by_id.get(key) or [],
            item_theme_values=themes_by_id.get(key) or [],
        )
        item["matched_motifs"] = why["matched_motifs"]
        item["missed_motifs"] = why["missed_motifs"]
        item["match_layers"] = why["match_layers"]
        item["motif_excerpts"] = why["excerpts"]
        item["motif_why"] = why["summary"]


def query_library(db: Database, filters: LibraryFilters) -> Dict[str, Any]:
    where_sql, params = _build_where(filters)
    limit = filters.normalized_limit()
    offset = filters.normalized_offset()
    sort_sql = _sort_clause(filters.sort)
    total_matched, rows = _fetch_rows(
        db,
        where_sql,
        params,
        sort_sql=sort_sql,
        limit=limit,
        offset=offset,
    )
    items = [row_to_query_item(row) for row in rows]
    if filters.motifs:
        attach_motif_why(db, items, filters.motifs)
    returned = len(items)
    payload = {
        "total_matched": total_matched,
        "returned": returned,
        "offset": offset,
        "has_more": offset + returned < total_matched,
        "items": items,
    }
    if filters.semantic_query:
        payload["hint"] = "semantic_query requires async query path with LLM settings"
    return payload


def aggregate_library(
    db: Database,
    group_by: GroupBy,
    filters: Optional[LibraryFilters] = None,
    *,
    top_examples: int = 3,
) -> Dict[str, Any]:
    base_filters = filters or LibraryFilters(limit=MAX_QUERY_LIMIT)
    where_sql, params = _build_where(base_filters)

    handlers = {
        "media_type": lambda: _aggregate_media_type(db, where_sql, params),
        "year": lambda: _aggregate_year(db, where_sql, params, top_examples),
        "decade": lambda: _aggregate_decade(db, where_sql, params, top_examples),
        "genre": lambda: _aggregate_genre(db, where_sql, params, top_examples),
        "director": lambda: _aggregate_facet(db, where_sql, params, "director", top_examples),
        "actor": lambda: _aggregate_facet(db, where_sql, params, "actor", top_examples),
        "keyword": lambda: _aggregate_facet(db, where_sql, params, "keyword", top_examples),
        "country": lambda: _aggregate_country(db, where_sql, params, top_examples),
        "language": lambda: _aggregate_language(db, where_sql, params, top_examples),
        "content_rating": lambda: _aggregate_content_rating(db, where_sql, params, top_examples),
        "runtime_bucket": lambda: _aggregate_runtime_bucket(db, where_sql, params),
        "decade_genre": lambda: _aggregate_decade_genre(db, where_sql, params),
    }
    handler = handlers.get(group_by)
    if handler is None:
        raise ValueError(f"Unknown group_by: {group_by}")
    return handler()


def _aggregate_media_type(db: Database, where_sql: str, params: List[Any]) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT media_type, COUNT(*) AS cnt
            FROM library_items
            WHERE {where_sql}
            GROUP BY media_type
            ORDER BY cnt DESC
            """,
            params,
        ).fetchall()
    buckets = [{"media_type": str(r["media_type"]), "count": int(r["cnt"])} for r in rows]
    return {"group_by": "media_type", "total_matched": sum(b["count"] for b in buckets), "buckets": buckets}


def _aggregate_year(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT year, COUNT(*) AS cnt
            FROM library_items
            WHERE {where_sql} AND year IS NOT NULL
            GROUP BY year
            ORDER BY year ASC
            """,
            params,
        ).fetchall()
    buckets = []
    for row in rows:
        year = int(row["year"])
        bucket: Dict[str, Any] = {"year": year, "count": int(row["cnt"])}
        if top_examples > 0:
            bucket["examples"] = _top_examples_for_year(db, where_sql, params, year, top_examples)
        buckets.append(bucket)
    return {"group_by": "year", "total_matched": sum(b["count"] for b in buckets), "buckets": buckets}


def _aggregate_decade(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT (year / 10) * 10 AS decade_start, COUNT(*) AS cnt
            FROM library_items
            WHERE {where_sql} AND year IS NOT NULL
            GROUP BY decade_start
            ORDER BY decade_start ASC
            """,
            params,
        ).fetchall()
    buckets = []
    for row in rows:
        decade_start = int(row["decade_start"])
        bucket: Dict[str, Any] = {
            "decade": f"{decade_start}s",
            "decade_start": decade_start,
            "decade_end": decade_start + 9,
            "count": int(row["cnt"]),
        }
        if top_examples > 0:
            bucket["examples"] = _top_examples_for_decade(
                db, where_sql, params, decade_start, top_examples
            )
        buckets.append(bucket)
    return {"group_by": "decade", "total_matched": sum(b["count"] for b in buckets), "buckets": buckets}


def _top_examples_for_year(
    db: Database,
    where_sql: str,
    params: List[Any],
    year: int,
    limit: int,
) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT title, year, media_type FROM library_items
            WHERE {where_sql} AND year = ?
            ORDER BY title ASC
            LIMIT ?
            """,
            [*params, year, limit],
        ).fetchall()
    return [{"title": str(r["title"]), "year": int(r["year"]), "media_type": str(r["media_type"])} for r in rows]


def _top_examples_for_decade(
    db: Database,
    where_sql: str,
    params: List[Any],
    decade_start: int,
    limit: int,
) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT title, year, media_type FROM library_items
            WHERE {where_sql} AND year >= ? AND year <= ?
            ORDER BY title ASC
            LIMIT ?
            """,
            [*params, decade_start, decade_start + 9, limit],
        ).fetchall()
    return [
        {
            "title": str(r["title"]),
            "year": int(r["year"]) if r["year"] is not None else None,
            "media_type": str(r["media_type"]),
        }
        for r in rows
    ]


def _aggregate_genre(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT id, title, year, media_type, genres FROM library_items WHERE {where_sql}",
            params,
        ).fetchall()

    genre_counts: Dict[str, int] = {}
    genre_examples: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        for genre in _parse_json_list(row["genres"]):
            key = genre.strip()
            if not key:
                continue
            genre_counts[key] = genre_counts.get(key, 0) + 1
            if top_examples > 0:
                examples = genre_examples.setdefault(key, [])
                if len(examples) < top_examples:
                    examples.append(
                        {
                            "title": str(row["title"]),
                            "year": int(row["year"]) if row["year"] is not None else None,
                            "media_type": str(row["media_type"]),
                        }
                    )

    buckets = [
        {
            "genre": genre,
            "count": count,
            **({"examples": genre_examples.get(genre, [])} if top_examples > 0 else {}),
        }
        for genre, count in sorted(genre_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "group_by": "genre",
        "total_matched": sum(genre_counts.values()),
        "buckets": buckets,
    }


def _aggregate_country(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    del top_examples
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT countries FROM library_items WHERE {where_sql}",
            params,
        ).fetchall()
    counts: Dict[str, int] = {}
    for row in rows:
        for country in _parse_json_list(row["countries"]):
            key = country.strip()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    buckets = [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "group_by": "country",
        "total_matched": sum(counts.values()),
        "buckets": buckets[:50],
    }


def _aggregate_language(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    del top_examples
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT original_language FROM library_items
            WHERE {where_sql} AND original_language IS NOT NULL AND original_language != ''
            """,
            params,
        ).fetchall()
    counts: Dict[str, int] = {}
    for row in rows:
        value = str(row["original_language"] or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    buckets = [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "group_by": "language",
        "total_matched": sum(counts.values()),
        "buckets": buckets[:50],
    }


def _aggregate_facet(
    db: Database,
    where_sql: str,
    params: List[Any],
    facet_type: str,
    top_examples: int,
) -> Dict[str, Any]:
    del top_examples
    with db.connect() as conn:
        item_rows = conn.execute(
            f"SELECT id FROM library_items WHERE {where_sql}",
            params,
        ).fetchall()
    allowed_ids = {int(r["id"]) for r in item_rows}
    with db.connect() as conn:
        facet_rows = conn.execute(
            """
            SELECT item_id, facet_value FROM library_facets
            WHERE facet_type = ?
            """,
            (facet_type,),
        ).fetchall()
    counts: Dict[str, int] = {}
    for row in facet_rows:
        if int(row["item_id"]) not in allowed_ids:
            continue
        value = str(row["facet_value"])
        counts[value] = counts.get(value, 0) + 1
    buckets = [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "group_by": facet_type,
        "total_matched": sum(counts.values()),
        "buckets": buckets[:50],
    }


def _aggregate_content_rating(
    db: Database,
    where_sql: str,
    params: List[Any],
    top_examples: int,
) -> Dict[str, Any]:
    del top_examples
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT content_rating, COUNT(*) AS cnt
            FROM library_items
            WHERE {where_sql} AND content_rating IS NOT NULL AND content_rating != ''
            GROUP BY content_rating
            ORDER BY cnt DESC
            """,
            params,
        ).fetchall()
    buckets = [{"content_rating": str(r["content_rating"]), "count": int(r["cnt"])} for r in rows]
    return {"group_by": "content_rating", "total_matched": sum(b["count"] for b in buckets), "buckets": buckets}


def _aggregate_runtime_bucket(db: Database, where_sql: str, params: List[Any]) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                CASE
                    WHEN runtime_minutes IS NULL THEN 'unknown'
                    WHEN runtime_minutes < 90 THEN 'short'
                    WHEN runtime_minutes < 120 THEN 'medium'
                    WHEN runtime_minutes < 180 THEN 'long'
                    ELSE 'epic'
                END AS bucket,
                COUNT(*) AS cnt
            FROM library_items
            WHERE {where_sql}
            GROUP BY bucket
            ORDER BY cnt DESC
            """,
            params,
        ).fetchall()
    buckets = [{"bucket": str(r["bucket"]), "count": int(r["cnt"])} for r in rows]
    return {"group_by": "runtime_bucket", "total_matched": sum(b["count"] for b in buckets), "buckets": buckets}


def _aggregate_decade_genre(db: Database, where_sql: str, params: List[Any]) -> Dict[str, Any]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT year, genres FROM library_items WHERE {where_sql} AND year IS NOT NULL",
            params,
        ).fetchall()
    matrix: Dict[str, Dict[str, int]] = {}
    for row in rows:
        decade = f"{(int(row['year']) // 10) * 10}s"
        decade_map = matrix.setdefault(decade, {})
        for genre in _parse_json_list(row["genres"]):
            if not genre:
                continue
            decade_map[genre] = decade_map.get(genre, 0) + 1
    buckets = [
        {"decade": decade, "genres": genres}
        for decade, genres in sorted(matrix.items())
    ]
    return {"group_by": "decade_genre", "buckets": buckets}


def _top_genre_for_media_type(db: Database, media_type: str) -> Optional[Dict[str, Any]]:
    genre_agg = aggregate_library(
        db,
        "genre",
        LibraryFilters(media_type=media_type, limit=MAX_QUERY_LIMIT),
        top_examples=0,
    )
    buckets = genre_agg.get("buckets") or []
    if not buckets:
        return None
    top = buckets[0]
    return {"genre": top["genre"], "count": int(top["count"])}


def _media_type_overview(
    *,
    count: int,
    total_runtime_minutes: Optional[float],
    top_genre: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "count": int(count),
        "top_genre": top_genre,
        "total_runtime_minutes": (
            int(round(float(total_runtime_minutes))) if total_runtime_minutes else None
        ),
    }


def compute_library_overview(db: Database) -> Dict[str, Any]:
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS cnt FROM library_items").fetchone()["cnt"]
        movies = conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'movie'"
        ).fetchone()["cnt"]
        shows = conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'show'"
        ).fetchone()["cnt"]
        decade_rows = conn.execute(
            """
            SELECT (year / 10) * 10 AS decade_start, COUNT(*) AS cnt
            FROM library_items
            WHERE year IS NOT NULL
            GROUP BY decade_start
            ORDER BY decade_start ASC
            """
        ).fetchall()
        avg_runtime = conn.execute(
            "SELECT AVG(runtime_minutes) AS avg_runtime FROM library_items WHERE runtime_minutes IS NOT NULL"
        ).fetchone()["avg_runtime"]
        total_runtime = conn.execute(
            "SELECT SUM(runtime_minutes) AS total_runtime FROM library_items WHERE runtime_minutes IS NOT NULL"
        ).fetchone()["total_runtime"]
        movies_total_runtime = conn.execute(
            """
            SELECT SUM(runtime_minutes) AS total_runtime FROM library_items
            WHERE media_type = 'movie' AND runtime_minutes IS NOT NULL
            """
        ).fetchone()["total_runtime"]
        shows_total_runtime = conn.execute(
            """
            SELECT SUM(runtime_minutes) AS total_runtime FROM library_items
            WHERE media_type = 'show' AND runtime_minutes IS NOT NULL
            """
        ).fetchone()["total_runtime"]
        unwatched_movies = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = 'movie' AND (view_count IS NULL OR view_count = 0)
            """
        ).fetchone()["cnt"]
        in_progress_shows = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = 'show' AND total_episode_count > 0
              AND unwatched_episode_count > 0
              AND unwatched_episode_count < total_episode_count
            """
        ).fetchone()["cnt"]

    decades = [
        {
            "decade": f"{int(r['decade_start'])}s",
            "decade_start": int(r["decade_start"]),
            "count": int(r["cnt"]),
        }
        for r in decade_rows
    ]
    genre_agg = aggregate_library(db, "genre", LibraryFilters(limit=MAX_QUERY_LIMIT), top_examples=0)
    top_genres = [
        {"genre": b["genre"], "count": b["count"]}
        for b in genre_agg.get("buckets", [])[:10]
    ]
    movies_top_genre = _top_genre_for_media_type(db, "movie")
    shows_top_genre = _top_genre_for_media_type(db, "show")
    director_catalog = library_facet_catalog(db, "director", limit=10)
    top_directors = director_catalog.get("facets", [])
    country_catalog = library_facet_catalog(db, "country", limit=10)
    top_countries = country_catalog.get("facets", [])
    language_catalog = library_facet_catalog(db, "language", limit=10)
    top_languages = language_catalog.get("facets", [])
    return {
        "total": int(total),
        "movies": int(movies),
        "shows": int(shows),
        "decades": decades,
        "top_genres": top_genres,
        "top_directors": top_directors,
        "top_countries": top_countries,
        "top_languages": top_languages,
        "avg_runtime_minutes": round(float(avg_runtime), 1) if avg_runtime else None,
        "total_runtime_minutes": int(round(float(total_runtime))) if total_runtime else None,
        "by_media_type": {
            "movie": _media_type_overview(
                count=int(movies),
                total_runtime_minutes=movies_total_runtime,
                top_genre=movies_top_genre,
            ),
            "show": _media_type_overview(
                count=int(shows),
                total_runtime_minutes=shows_total_runtime,
                top_genre=shows_top_genre,
            ),
        },
        "unwatched_movies": int(unwatched_movies),
        "in_progress_shows": int(in_progress_shows),
        "generated_at": time.time(),
    }


def refresh_library_overview_cache(db: Database) -> Dict[str, Any]:
    overview = compute_library_overview(db)
    db.set_sync_state(OVERVIEW_CACHE_KEY, json.dumps(overview))
    return overview


def library_overview(db: Database, *, use_cache: bool = True) -> Dict[str, Any]:
    if use_cache:
        raw = db.get_sync_state(OVERVIEW_CACHE_KEY)
        if raw:
            try:
                cached = json.loads(raw)
                # Soft-refresh when older caches predate per-type pulse fields.
                if isinstance(cached, dict) and "by_media_type" in cached:
                    return cached
            except json.JSONDecodeError:
                pass
    return refresh_library_overview_cache(db)


def format_overview_for_prompt(overview: Mapping[str, Any]) -> str:
    lines = [
        f"Library inventory: {overview.get('total', 0)} titles "
        f"({overview.get('movies', 0)} movies, {overview.get('shows', 0)} shows)."
    ]
    decades = overview.get("decades") or []
    if decades:
        decade_parts = [f"{d.get('decade', '?')}: {d.get('count', 0)}" for d in decades[:12]]
        lines.append("By decade: " + ", ".join(decade_parts) + ".")
    top_genres = overview.get("top_genres") or []
    if top_genres:
        genre_parts = [f"{g.get('genre', '?')} ({g.get('count', 0)})" for g in top_genres[:8]]
        lines.append("Top genres: " + ", ".join(genre_parts) + ".")
    top_directors = overview.get("top_directors") or []
    if top_directors:
        director_parts = [f"{d.get('value', '?')} ({d.get('count', 0)})" for d in top_directors[:6]]
        lines.append("Top directors: " + ", ".join(director_parts) + ".")
    if overview.get("avg_runtime_minutes"):
        lines.append(f"Avg runtime: {overview['avg_runtime_minutes']} min.")
    if overview.get("in_progress_shows"):
        lines.append(f"Shows in progress: {overview['in_progress_shows']}.")
    lines.append(
        "Query cookbook: owned inventory → query_library/summarize_library/search_library; "
        "exact external title lookup → search_tmdb; "
        "director/actor filmography → query_library(directors/cast) or get_facet_catalog; "
        "mood/theme in owned library → query_library(keywords/semantic_query); tonight picks → what_to_watch_tonight or runtime_max + unwatched_only; "
        "recently added → sort=added_at desc or recently_added_days; never-watched new adds → unwatched_only + recently_added_days; "
        "purge candidates → sort=file_size desc + stale_days or unwatched_only; "
        "missing from Radarr/Sonarr → in_radarr=false (movies) or in_sonarr=false (shows); "
        "TV progress → query_tv_episodes/summarize_tv_progress; "
        "gaps/hidden gems to add → find_collection_gaps/recommend_hidden_gems (never query_library)."
    )
    return " ".join(lines)


def compute_knowledge_coverage(db: Database) -> Dict[str, Any]:
    """Library knowledge-depth coverage for Admin / Explore (Phase D UI consumes this).

    Returns percentages and averages for overview text, motifs, keywords, neighbors,
    and optional LLM loglines so sparsity is visible without LLM spend.
    """
    with db.connect() as conn:
        total = int(
            conn.execute("SELECT COUNT(*) AS cnt FROM library_items").fetchone()["cnt"]
        )
        if total <= 0:
            return {
                "total_titles": 0,
                "with_overview_pct": 0.0,
                "with_motifs_pct": 0.0,
                "with_keywords_pct": 0.0,
                "with_themes_pct": 0.0,
                "with_neighbors_pct": 0.0,
                "with_loglines_pct": 0.0,
                "avg_motifs_per_title": 0.0,
                "avg_keywords_per_title": 0.0,
                "avg_themes_per_title": 0.0,
                "neighbor_edges": 0,
                "motif_rows": 0,
                "keyword_rows": 0,
                "theme_rows": 0,
                "logline_count": 0,
            }

        cols = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
        overview_expr = "TRIM(COALESCE(summary, '')) != ''"
        if "tmdb_overview" in cols:
            overview_expr = (
                f"({overview_expr} OR TRIM(COALESCE(tmdb_overview, '')) != '')"
            )
        with_overview = int(
            conn.execute(
                f"SELECT COUNT(*) AS cnt FROM library_items WHERE {overview_expr}"
            ).fetchone()["cnt"]
        )

        logline_count = 0
        if "llm_logline" in cols:
            logline_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS cnt FROM library_items "
                    "WHERE TRIM(COALESCE(llm_logline, '')) != ''"
                ).fetchone()["cnt"]
            )

        synopsis_count = 0
        has_synopsis_col = "long_synopsis" in cols
        if has_synopsis_col:
            synopsis_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS cnt FROM library_items "
                    "WHERE TRIM(COALESCE(long_synopsis, '')) != ''"
                ).fetchone()["cnt"]
            )

        motif_row = conn.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT item_id) AS titles
            FROM library_facets
            WHERE facet_type = 'motif'
            """
        ).fetchone()
        motif_rows = int(motif_row["rows"] or 0)
        motif_titles = int(motif_row["titles"] or 0)

        keyword_row = conn.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT item_id) AS titles
            FROM library_facets
            WHERE facet_type = 'keyword'
            """
        ).fetchone()
        keyword_rows = int(keyword_row["rows"] or 0)
        keyword_titles = int(keyword_row["titles"] or 0)

        theme_row = conn.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT item_id) AS titles
            FROM library_facets
            WHERE facet_type = 'theme'
            """
        ).fetchone()
        theme_rows = int(theme_row["rows"] or 0)
        theme_titles = int(theme_row["titles"] or 0)

        neighbor_row = conn.execute(
            """
            SELECT COUNT(*) AS edges,
                   COUNT(DISTINCT item_id) AS seeds
            FROM item_neighbors
            """
        ).fetchone()
        neighbor_edges = int(neighbor_row["edges"] or 0)
        neighbor_seeds = int(neighbor_row["seeds"] or 0)

    def _pct(count: int) -> float:
        return round((count / total) * 100.0, 1)

    result = {
        "total_titles": total,
        "with_overview_pct": _pct(with_overview),
        "with_motifs_pct": _pct(motif_titles),
        "with_keywords_pct": _pct(keyword_titles),
        "with_themes_pct": _pct(theme_titles),
        "with_neighbors_pct": _pct(neighbor_seeds),
        "with_loglines_pct": _pct(logline_count),
        "avg_motifs_per_title": round(motif_rows / total, 2),
        "avg_keywords_per_title": round(keyword_rows / total, 2),
        "avg_themes_per_title": round(theme_rows / total, 2),
        "neighbor_edges": neighbor_edges,
        "motif_rows": motif_rows,
        "keyword_rows": keyword_rows,
        "theme_rows": theme_rows,
        "logline_count": logline_count,
    }
    # Phase C may add long_synopsis — only expose when the column exists.
    if has_synopsis_col:
        result["with_synopsis_pct"] = _pct(synopsis_count)
        result["synopsis_count"] = synopsis_count
    return result


def maybe_set_audit_context_label(db: Database, filters: LibraryFilters) -> None:
    """Update active derived context label when user is exploring a decade slice."""
    if filters.year_from is None and filters.year_to is None:
        return
    year_from = filters.year_from
    year_to = filters.year_to
    if year_from is not None and year_to is not None and year_to - year_from <= 12:
        decade = (year_from // 10) * 10
        label = f"{decade}s Collection Audit"
    elif year_from is not None:
        label = f"From {year_from} Collection Audit"
    elif year_to is not None:
        label = f"Through {year_to} Collection Audit"
    else:
        return
    context_hash = db.get_config(ACTIVE_CONTEXT_CONFIG_KEY, DEFAULT_CONTEXT_HASH) or DEFAULT_CONTEXT_HASH
    db.update_derived_context_label(context_hash, label)
