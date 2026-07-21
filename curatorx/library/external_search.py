"""Shared external (TMDB) title search + card/item mapping.

This is the single source of truth for turning a TMDB query into de-duped,
ownership/queue-flagged :class:`TitleCard` results. Both the agent chat tool
(``search_tmdb``) and the ``GET /api/search/external`` HTTP endpoint call
:func:`external_tmdb_search`, so their behavior stays identical and DRY.

The helper functions below (title matching, ranking, card/item mapping,
external-id enrichment, queue flagging) used to live inside
``curatorx.agent.tools``; they are re-exported there to preserve the existing
import surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.models.recommendation import sanitize_recommendation_reason
from curatorx.models.schemas import TitleCard


def _normalize_title_key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _titles_roughly_match(expected: str, actual: str) -> bool:
    """True when expected title aligns with actual (exact or containment)."""
    left = _normalize_title_key(expected)
    right = _normalize_title_key(actual)
    if not left or not right:
        return True
    if left == right:
        return True
    if left in right or right in left:
        return True
    # Token overlap for minor punctuation differences.
    left_tokens = {t for t in left.replace(":", " ").replace("-", " ").split() if t}
    right_tokens = {t for t in right.replace(":", " ").replace("-", " ").split() if t}
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
    return overlap >= 0.6


def _tmdb_result_year(item: Mapping[str, Any]) -> Optional[int]:
    date = item.get("release_date") or item.get("first_air_date") or ""
    if not date:
        return None
    try:
        return int(str(date)[:4])
    except ValueError:
        return None


def _rank_tmdb_search_results(
    results: List[Mapping[str, Any]],
    *,
    year: Optional[int],
    title: Optional[str] = None,
) -> List[Mapping[str, Any]]:
    """Order/filter TMDB search hits.

    When ``year`` is set, keep only that release year so one recommendation
    (e.g. Mandy 2018) does not expand into every same-name hit.

    When both ``title`` and ``year`` are set, exact title matches are preferred
    so that "Munich (2005)" pins Spielberg's film and not every same-year title
    containing "Munich" (e.g. "Munich Mambo").

    When only ``title`` is set, exact title matches are ranked ahead of partial
    hits so agents do not recommend unrelated IDs from a noisy search page.
    """
    ordered = [item for item in results if isinstance(item, Mapping)]
    normalised = title.strip().casefold() if title else ""
    if year is None:
        if not normalised:
            return ordered
        exact = [
            item
            for item in ordered
            if str(item.get("title") or item.get("name") or "").strip().casefold() == normalised
        ]
        if exact:
            return exact + [item for item in ordered if item not in exact]
        close = [
            item
            for item in ordered
            if _titles_roughly_match(normalised, str(item.get("title") or item.get("name") or ""))
        ]
        if close:
            return close
        return ordered
    year_matched = [item for item in ordered if _tmdb_result_year(item) == year]
    if normalised and year_matched:
        exact = [
            item
            for item in year_matched
            if str(item.get("title") or item.get("name") or "").strip().casefold() == normalised
        ]
        if exact:
            return exact
    return year_matched


def _tmdb_search_item_to_tool_item(item: Mapping[str, Any], media_type: str) -> Dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "")
    overview = str(item.get("overview") or "")
    payload: Dict[str, Any] = {
        "title": title,
        "year": _tmdb_result_year(item),
        "media_type": media_type,
        "tmdb_id": int(item.get("id") or 0),
        "overview": overview[:200] if overview else "",
        "in_library": False,
    }
    if media_type == "show":
        external = item.get("external_ids") or {}
        if external.get("tvdb_id"):
            payload["tvdb_id"] = int(external["tvdb_id"])
    return payload


def _tmdb_card(item: Mapping[str, Any], media_type: str, tmdb: TMDBClient, *, reason: str = "") -> TitleCard:
    poster = tmdb.poster_url(item.get("poster_path"))
    backdrop = tmdb.backdrop_url(item.get("backdrop_path"))
    title = item.get("title") or item.get("name") or ""
    year = None
    date = item.get("release_date") or item.get("first_air_date") or ""
    if date:
        year = int(str(date)[:4])
    tvdb_id = None
    if media_type == "show":
        external = item.get("external_ids") or {}
        if external.get("tvdb_id"):
            tvdb_id = int(external["tvdb_id"])
    return TitleCard(
        media_type=media_type,  # type: ignore[arg-type]
        title=str(title),
        year=year,
        tmdb_id=int(item.get("id") or 0),
        tvdb_id=tvdb_id,
        poster_url=poster,
        backdrop_url=backdrop,
        overview=str(item.get("overview") or ""),
        rating=float(item.get("vote_average") or 0) or None,
        recommendation_reason=sanitize_recommendation_reason(reason),
        in_library=False,
    )


def _enrich_show_external_ids(item: Mapping[str, Any], tmdb: TMDBClient) -> Mapping[str, Any]:
    if item.get("external_ids"):
        return item
    tmdb_id = int(item.get("id") or 0)
    if not tmdb_id:
        return item
    try:
        details = tmdb.tv_details(tmdb_id)
    except RuntimeError:
        return item
    return {**item, "external_ids": details.get("external_ids") or {}}


def _apply_queue_flags(db: Database, card: TitleCard) -> TitleCard:
    if card.media_type == "movie" and card.tmdb_id:
        if db.is_arr_queued(media_type="movie", tmdb_id=card.tmdb_id):
            card.in_radarr = True
    if card.media_type == "show":
        if card.tvdb_id and db.is_arr_queued(media_type="show", tvdb_id=card.tvdb_id):
            card.in_sonarr = True
        elif card.tmdb_id and db.is_arr_queued(media_type="show", tmdb_id=card.tmdb_id):
            card.in_sonarr = True
    return card


# --- Shared search service -------------------------------------------------

# Structured error kinds so HTTP and chat callers can present errors in the
# way that suits each surface without re-deriving the message strings.
ERROR_NOT_CONFIGURED = "not_configured"
ERROR_BAD_ID = "bad_id"
ERROR_MISSING_QUERY = "missing_query"
ERROR_NOT_FOUND = "not_found"
ERROR_MISMATCH = "mismatch"
ERROR_TMDB = "tmdb_error"


@dataclass
class ExternalSearchResult:
    """Outcome of an external TMDB search.

    ``cards`` includes every result (owned titles keep ``in_library=True`` so
    callers can badge/suppress them); ``items`` is the tool-item projection with
    ``in_library``/``in_radarr``/``in_sonarr``/``already_queued`` flags.
    """

    cards: List[TitleCard] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)
    total_matched: int = 0
    error: Optional[str] = None
    error_kind: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def external_tmdb_search(
    db: Database,
    settings: Settings,
    *,
    media_type: str = "movie",
    title: str = "",
    tmdb_id: Optional[int] = None,
    year: Optional[int] = None,
    limit: int = 10,
    reason: str = "",
) -> ExternalSearchResult:
    """Search TMDB for titles and map them to de-duped, flagged cards/items.

    Ownership and Radarr/Sonarr-queue flags are applied against the local
    library so callers can suppress or badge titles already owned/queued.
    """
    if not settings.tmdb_api_key:
        return ExternalSearchResult(
            error="TMDB API key not configured", error_kind=ERROR_NOT_CONFIGURED
        )

    title = str(title or "").strip()
    pinned_tmdb_id = int(tmdb_id) if tmdb_id is not None else None
    if pinned_tmdb_id is not None and pinned_tmdb_id <= 0:
        return ExternalSearchResult(
            error="tmdb_id must be a positive integer", error_kind=ERROR_BAD_ID
        )
    if not title and pinned_tmdb_id is None:
        return ExternalSearchResult(
            error="title or tmdb_id is required", error_kind=ERROR_MISSING_QUERY
        )

    year_int = int(year) if year is not None else None
    limit = min(int(limit or 10), 20)
    reason = sanitize_recommendation_reason(reason)

    tmdb = TMDBClient(settings.tmdb_api_key)
    results: List[Mapping[str, Any]] = []
    total_matched = 0
    if pinned_tmdb_id is not None:
        try:
            details = (
                tmdb.movie_details(pinned_tmdb_id)
                if media_type == "movie"
                else tmdb.tv_details(pinned_tmdb_id)
            )
        except RuntimeError as error:
            return ExternalSearchResult(error=str(error), error_kind=ERROR_TMDB)
        if not isinstance(details, Mapping) or not int(details.get("id") or 0):
            return ExternalSearchResult(
                error=f"TMDB {media_type} {pinned_tmdb_id} not found",
                error_kind=ERROR_NOT_FOUND,
            )
        actual_title = str(details.get("title") or details.get("name") or "")
        if title and not _titles_roughly_match(title, actual_title):
            return ExternalSearchResult(
                error=(
                    f"tmdb_id {pinned_tmdb_id} resolves to '{actual_title}', "
                    f"which does not match requested title '{title}'. "
                    "Re-search by title+year instead of inventing ids."
                ),
                error_kind=ERROR_MISMATCH,
            )
        results = [details]
        total_matched = 1
    else:
        if media_type == "movie":
            page = tmdb.search_movie_page(title, year=year_int)
        else:
            page = tmdb.search_tv_page(title)
        raw_results = page.get("results", [])
        if not isinstance(raw_results, list):
            raw_results = []
        total_matched = int(page.get("total_results") or len(raw_results))
        results = _rank_tmdb_search_results(raw_results, year=year_int, title=title)
        if year_int is not None:
            # Year pin: honest count is filtered matches, not unscoped TMDB total.
            total_matched = len(results)

    owned = db.owned_tmdb_ids(media_type)
    queued = db.queued_tmdb_ids(media_type)
    cards: List[TitleCard] = []
    items: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        result_tmdb_id = int(item.get("id") or 0)
        if result_tmdb_id <= 0:
            continue
        if media_type == "show":
            item = _enrich_show_external_ids(item, tmdb)
        card = _apply_queue_flags(db, _tmdb_card(item, media_type, tmdb, reason=reason))
        card.in_library = result_tmdb_id in owned
        if result_tmdb_id in queued and media_type == "movie":
            card.in_radarr = True
        cards.append(card)
        tool_item = _tmdb_search_item_to_tool_item(item, media_type)
        tool_item["in_library"] = card.in_library
        tool_item["in_radarr"] = bool(card.in_radarr)
        tool_item["in_sonarr"] = bool(card.in_sonarr)
        tool_item["already_queued"] = bool(
            card.in_radarr or card.in_sonarr or result_tmdb_id in queued
        )
        if reason:
            tool_item["recommendation_reason"] = reason
        items.append(tool_item)
        if len(items) >= limit:
            break

    return ExternalSearchResult(cards=cards, items=items, total_matched=total_matched)
