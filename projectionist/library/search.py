"""Library search helpers."""

from __future__ import annotations

import json
import re
from typing import List, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.library.embeddings import semantic_embedding_search_available
from projectionist.library.query import filters_from_mapping, query_library, query_library_async
from projectionist.library.play_counts import effective_view_count
from projectionist.models.schemas import TitleCard


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
        content_rating=(
            str(row["content_rating"] or "") if "content_rating" in row.keys() else ""
        ),
        recommendation_reason=reason,
        facet_matches=list(facet_matches or []),
        runtime_minutes=int(row["runtime_minutes"]) if "runtime_minutes" in row.keys() and row["runtime_minutes"] else None,
        view_count=effective_view_count(row),
        view_offset_ms=(
            int(row["view_offset_ms"])
            if "view_offset_ms" in row.keys() and row["view_offset_ms"] is not None
            else None
        ),
        duration_ms=(
            int(row["duration_ms"])
            if "duration_ms" in row.keys() and row["duration_ms"] is not None
            else None
        ),
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


def _normalize_search_query(query: str) -> str:
    """Collapse whitespace and strip a single layer of wrapping quotes."""
    cleaned = " ".join(str(query or "").strip().split())
    if len(cleaned) >= 2 and cleaned[0] in {"'", '"', "\u201c", "\u2018"} and cleaned[-1] in {
        "'",
        '"',
        "\u201d",
        "\u2019",
    }:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _strip_token_punct(token: str) -> str:
    return str(token or "").strip("\"'“”‘’").strip()


_TITLE_CANDIDATE_STOPWORDS = {
    "a",
    "about",
    "any",
    "can",
    "could",
    "do",
    "drive",
    "episode",
    "film",
    "films",
    "for",
    "get",
    "hard",
    "hbo",
    "how",
    "i",
    "is",
    "it",
    "know",
    "library",
    "me",
    "more",
    "movie",
    "movies",
    "netflix",
    "of",
    "on",
    "plex",
    "please",
    "search",
    "season",
    "series",
    "show",
    "shows",
    "space",
    "tell",
    "the",
    "this",
    "tv",
    "watch",
    "watching",
    "what",
    "with",
    "worth",
    "you",
}


def _title_candidates(query: str) -> List[str]:
    """Extract conservative title-like candidates from conversational lookup text."""
    tokens = re.findall(r"[\w']+", str(query or "").casefold())
    meaningful = [
        cleaned
        for token in tokens
        if (cleaned := _strip_token_punct(token))
        and cleaned not in _TITLE_CANDIDATE_STOPWORDS
        and not re.fullmatch(r"\d{4}", cleaned)
    ]
    if not meaningful:
        return []
    # Prefer short title-like tokens before the noisy joined phrase so a quoted
    # single-word title ("Industry") is not lost behind ambient words.
    singles = list(dict.fromkeys(meaningful))
    joined = " ".join(meaningful)
    if joined in singles or meaningful == tokens:
        return singles
    return [*singles, joined]


def _title_match_queries(cleaned: str) -> List[str]:
    """Queries used to detect exact/near-exact title presence."""
    queries = [cleaned, *_title_candidates(cleaned)]
    # Drop long conversational joins from exact-match probes.
    return list(
        dict.fromkeys(q for q in queries if q and (q == cleaned or " " not in q or len(q) <= 48))
    )


def _is_exact_title_match(title: str, query: str) -> bool:
    left = _normalize_search_query(title).casefold()
    right = _normalize_search_query(query).casefold()
    if not left or not right:
        return False
    if left == right:
        return True
    # Allow "Industry (2020)" style probes against title "Industry".
    year_suffix = re.fullmatch(r"(.+?)\s*\((\d{4})\)\s*", right)
    if year_suffix and left == year_suffix.group(1).strip():
        return True
    return False


def exact_title_cards(cards: Sequence[TitleCard], query: str) -> List[TitleCard]:
    """Return cards whose title exactly matches the query or a short title probe."""
    cleaned = _normalize_search_query(query)
    probes = _title_match_queries(cleaned)
    exact: List[TitleCard] = []
    seen: set[str] = set()
    for card in cards:
        if not any(_is_exact_title_match(card.title, probe) for probe in probes):
            continue
        key = f"{card.media_type}:{card.rating_key or card.tmdb_id or card.title}:{card.year or ''}"
        if key in seen:
            continue
        seen.add(key)
        exact.append(card)
    return exact


def _rank_cards_for_query(cards: Sequence[TitleCard], cleaned: str) -> List[TitleCard]:
    """Prefer exact title hits over summary/keyword substring noise."""
    probes = _title_match_queries(cleaned)
    exact: List[TitleCard] = []
    titled: List[TitleCard] = []
    rest: List[TitleCard] = []
    for card in cards:
        title = (card.title or "").casefold()
        if any(_is_exact_title_match(card.title, probe) for probe in probes):
            exact.append(card)
        elif any(probe and probe.casefold() in title for probe in probes):
            titled.append(card)
        else:
            rest.append(card)
    return [*exact, *titled, *rest]


async def _text_search_cards(
    db: Database,
    *,
    query: str,
    media_type: Optional[str],
    limit: int,
    reason: str,
) -> List[TitleCard]:
    result = await run_db(
        query_library,
        db,
        filters_from_mapping(
            {
                "query": query,
                "media_type": media_type,
                "limit": limit,
                "sort": "title",
            }
        ),
    )
    if result.get("total_matched", 0) <= 0:
        return []
    return _cards_from_query_result(db, result, reason=reason, limit=limit)


async def search_library(
    db: Database,
    settings: Settings,
    query: str,
    *,
    media_type: Optional[str] = None,
    limit: int = 12,
) -> List[TitleCard]:
    """Search the library, preferring title presence over keyword-facet noise.

    Tag-style queries (e.g. \"found footage\") still hit ``library_facets`` when
    there is no exact/near-exact title match. Short/common titles such as
    \"Industry\" must not be swallowed by unrelated keyword facets.
    Semantic search runs only when keyword and title/summary matches are empty.
    """
    cleaned = _normalize_search_query(query)
    if not cleaned:
        return []

    capped = min(max(1, int(limit or 12)), 48)
    # Pull a wider text window so exact titles are not truncated away by
    # alphabetical summary matches before ranking.
    fetch_limit = min(48, max(capped, 24))

    # 1) Title / summary substring match (and conversational candidates).
    text_cards = await _text_search_cards(
        db,
        query=cleaned,
        media_type=media_type,
        limit=fetch_limit,
        reason="Library match (text)",
    )
    if not text_cards:
        # Chat often passes the whole sentence; retry cleaned title candidates
        # so “Simpsley” / quoted “Industry” are not lost behind filler words.
        for candidate in _title_candidates(cleaned):
            if candidate.casefold() == cleaned.casefold():
                continue
            text_cards = await _text_search_cards(
                db,
                query=candidate,
                media_type=media_type,
                limit=fetch_limit,
                reason="Library match (title extracted from conversation)",
            )
            if text_cards:
                break

    if text_cards:
        ranked = _rank_cards_for_query(text_cards, cleaned)
        exact = exact_title_cards(ranked, cleaned)
        if exact:
            # Presence-critical: never let keyword facets hide an owned title.
            exact_keys = {
                f"{card.media_type}:{card.rating_key or card.tmdb_id or card.title}:{card.year or ''}"
                for card in exact
            }
            remainder = [
                card
                for card in ranked
                if f"{card.media_type}:{card.rating_key or card.tmdb_id or card.title}:{card.year or ''}"
                not in exact_keys
            ]
            return [*exact, *remainder][:capped]

    # 2) Keyword / facet match — only when no exact title presence was found.
    if looks_like_facet_tag_query(cleaned):
        keyword_result = await run_db(
            query_library,
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

    if text_cards:
        return _rank_cards_for_query(text_cards, cleaned)[:capped]

    # 3) Semantic fallback only when structured matches came up empty. An
    # Anthropic chat endpoint is not an embeddings endpoint, so it needs an
    # explicitly configured OpenAI-compatible embedding URL.
    if not semantic_embedding_search_available(settings):
        return []
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
