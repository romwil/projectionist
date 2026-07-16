"""Library search helpers."""

from __future__ import annotations

import json
from typing import List, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.query import filters_from_mapping, query_library, query_library_async
from curatorx.models.schemas import TitleCard


def row_to_title_card(row, *, reason: str = "", facet_matches: Optional[List[str]] = None) -> TitleCard:
    genres = json.loads(row["genres"]) if row["genres"] else []
    return TitleCard(
        media_type=row["media_type"],
        title=row["title"],
        year=row["year"],
        tmdb_id=row["tmdb_id"],
        tvdb_id=row["tvdb_id"],
        rating_key=row["rating_key"],
        poster_url=row["poster_url"] or "",
        backdrop_url=row["backdrop_url"] or "",
        overview=row["summary"] or "",
        genres=genres,
        in_library=True,
        in_radarr=bool(row["in_radarr"]),
        in_sonarr=bool(row["in_sonarr"]),
        recommendation_reason=reason,
        facet_matches=list(facet_matches or []),
        runtime_minutes=int(row["runtime_minutes"]) if "runtime_minutes" in row.keys() and row["runtime_minutes"] else None,
        total_episode_count=int(row["total_episode_count"])
        if "total_episode_count" in row.keys() and row["total_episode_count"]
        else None,
        unwatched_episode_count=int(row["unwatched_episode_count"])
        if "unwatched_episode_count" in row.keys() and row["unwatched_episode_count"] is not None
        else None,
    )


def _cards_from_query_result(
    db: Database,
    result: dict,
    *,
    reason: str,
    facet_matches: Optional[List[str]] = None,
    limit: int,
) -> List[TitleCard]:
    cards: List[TitleCard] = []
    for item in result.get("items", []):
        row = db.library_item_by_id(int(item["id"])) if item.get("id") else None
        if row is None:
            continue
        cards.append(row_to_title_card(row, reason=reason, facet_matches=facet_matches))
        if len(cards) >= limit:
            break
    return cards


def looks_like_facet_tag_query(query: str) -> bool:
    """Heuristic: short multi-word / genre-like phrases often map to keyword facets."""
    cleaned = " ".join(str(query or "").strip().split())
    if not cleaned:
        return False
    # Avoid treating long plot sentences as tags.
    if len(cleaned) > 48 or cleaned.count(" ") > 4:
        return False
    return True


async def search_library(
    db: Database,
    settings: Settings,
    query: str,
    *,
    media_type: Optional[str] = None,
    limit: int = 12,
) -> List[TitleCard]:
    """Search the library, preferring keyword/facet and text matches over semantic noise.

    Tag-style queries (e.g. \"found footage\") should hit ``library_facets`` first.
    Semantic search runs only when keyword and title/summary matches are empty.
    """
    cleaned = " ".join(str(query or "").strip().split())
    if not cleaned:
        return []

    capped = min(max(1, int(limit or 12)), 48)

    # 1) Exact-ish keyword / facet match — highest precision for tag asks.
    if looks_like_facet_tag_query(cleaned):
        keyword_result = query_library(
            db,
            filters_from_mapping(
                {
                    "keywords": [cleaned],
                    "media_type": media_type,
                    "limit": capped,
                    "sort": "title",
                }
            ),
        )
        if keyword_result.get("total_matched", 0) > 0:
            return _cards_from_query_result(
                db,
                keyword_result,
                reason="Library match (keyword)",
                facet_matches=[f"Keyword: {cleaned}"],
                limit=capped,
            )

    # 2) Title / summary substring match.
    text_result = query_library(
        db,
        filters_from_mapping(
            {
                "query": cleaned,
                "media_type": media_type,
                "limit": capped,
                "sort": "title",
            }
        ),
    )
    if text_result.get("total_matched", 0) > 0:
        return _cards_from_query_result(
            db,
            text_result,
            reason="Library match (text)",
            limit=capped,
        )

    # 3) Semantic fallback only when structured matches came up empty.
    filters = filters_from_mapping(
        {
            "semantic_query": cleaned,
            "media_type": media_type,
            "limit": capped,
        }
    )
    result = await query_library_async(db, filters, settings)
    mode = result.get("search_mode", "semantic")
    return _cards_from_query_result(
        db,
        result,
        reason=f"Library match ({mode})",
        limit=capped,
    )
