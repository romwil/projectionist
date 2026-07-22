"""Title detail assembly."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.fanart import FanartClient
from curatorx.connectors.plex import cached_machine_identifier, plex_watch_url
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.models.schemas import CreditPerson, PlotKnowledge, TitleDetail

logger = logging.getLogger(__name__)

# Keep title detail interactive: enrichment is optional and must not block for long.
_TITLE_DETAIL_TMDB_TIMEOUT = 5
_TITLE_DETAIL_FANART_TIMEOUT = 3
_TITLE_DETAIL_PLEX_TIMEOUT = 2


def _credit_from_db_row(row) -> CreditPerson:
    tmdb_id = row["tmdb_person_id"]
    person_id = row["person_id"]
    return CreditPerson(
        name=str(row["name"] or "").strip(),
        tmdb_person_id=int(tmdb_id) if tmdb_id is not None else None,
        person_id=int(person_id) if person_id is not None else None,
        department=str(row["department"] or ""),
        job=str(row["job"] or ""),
        character=str(row["character"] or ""),
        profile_url=str(row["profile_url"] or ""),
        billing_order=int(row["billing_order"] or 0),
    )


def _credits_from_tmdb(
    credits_payload: Mapping[str, Any],
    *,
    tmdb: TMDBClient,
    cast_limit: int = 12,
) -> List[CreditPerson]:
    """Map TMDB credits.cast / directors into CreditPerson rows."""
    people: List[CreditPerson] = []
    seen: set[tuple[Optional[int], str, str, str]] = set()

    cast = credits_payload.get("cast") or []
    if isinstance(cast, list):
        for index, entry in enumerate(cast[:cast_limit]):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            tmdb_person_id = entry.get("id")
            try:
                resolved_id = int(tmdb_person_id) if tmdb_person_id is not None else None
            except (TypeError, ValueError):
                resolved_id = None
            character = str(entry.get("character") or "")
            key = (resolved_id, name, "Acting", character)
            if key in seen:
                continue
            seen.add(key)
            order = entry.get("order")
            try:
                billing = int(order) if order is not None else index
            except (TypeError, ValueError):
                billing = index
            people.append(
                CreditPerson(
                    name=name,
                    tmdb_person_id=resolved_id,
                    department="Acting",
                    job="Actor",
                    character=character,
                    profile_url=tmdb.profile_url(entry.get("profile_path")),
                    billing_order=billing,
                )
            )

    crew = credits_payload.get("crew") or []
    if isinstance(crew, list):
        for entry in crew:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("job") or "") != "Director":
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            tmdb_person_id = entry.get("id")
            try:
                resolved_id = int(tmdb_person_id) if tmdb_person_id is not None else None
            except (TypeError, ValueError):
                resolved_id = None
            key = (resolved_id, name, "Directing", "Director")
            if key in seen:
                continue
            seen.add(key)
            people.append(
                CreditPerson(
                    name=name,
                    tmdb_person_id=resolved_id,
                    department="Directing",
                    job="Director",
                    character="",
                    profile_url=tmdb.profile_url(entry.get("profile_path")),
                    billing_order=0,
                )
            )

    people.sort(key=lambda p: (0 if p.job == "Director" else 1, p.billing_order, p.name))
    return people


def _keyword_names_from_tmdb(meta: Mapping[str, Any]) -> List[str]:
    keywords_block = meta.get("keywords") or {}
    if not isinstance(keywords_block, dict):
        return []
    # Movies use "keywords"; TV uses "results".
    raw = keywords_block.get("keywords") or keywords_block.get("results") or []
    if not isinstance(raw, list):
        return []
    names: List[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _apply_tmdb_credit_strings(detail: TitleDetail, credits_payload: Mapping[str, Any]) -> None:
    cast = credits_payload.get("cast") or []
    if not detail.cast and isinstance(cast, list):
        detail.cast = [
            str(c.get("name") or "").strip()
            for c in cast[:8]
            if isinstance(c, dict) and str(c.get("name") or "").strip()
        ]
    crew = credits_payload.get("crew") or []
    if not detail.directors and isinstance(crew, list):
        detail.directors = [
            str(c.get("name") or "").strip()
            for c in crew
            if isinstance(c, dict)
            and str(c.get("job") or "") == "Director"
            and str(c.get("name") or "").strip()
        ]


def _needs_tmdb_enrichment(detail: TitleDetail) -> bool:
    """True when local data is incomplete enough to justify a TMDB round-trip."""
    if not detail.title or not detail.overview:
        return True
    if not detail.poster_url or not detail.backdrop_url:
        return True
    if detail.rating is None or detail.runtime_minutes is None:
        return True
    if not detail.trailer_youtube_key:
        return True
    if not detail.credits and not detail.cast and not detail.directors:
        return True
    if not detail.keywords:
        return True
    if detail.media_type == "movie" and not detail.release_date:
        return True
    if detail.media_type == "show" and not detail.first_air_date:
        return True
    if not detail.content_rating:
        return True
    return False


def _apply_tmdb_movie_meta(detail: TitleDetail, meta: Mapping[str, Any], tmdb: TMDBClient) -> None:
    detail.title = detail.title or str(meta.get("title") or "")
    detail.overview = detail.overview or str(meta.get("overview") or "")
    if detail.rating is None:
        detail.rating = float(meta.get("vote_average") or 0) or None
    if not detail.poster_url:
        detail.poster_url = tmdb.poster_url(meta.get("poster_path"))
    if not detail.backdrop_url:
        detail.backdrop_url = tmdb.backdrop_url(meta.get("backdrop_path"))
    if detail.runtime_minutes is None:
        detail.runtime_minutes = int((meta.get("runtime") or 0) or 0) or None
    if not detail.release_date:
        detail.release_date = str(meta.get("release_date") or "")[:10]
    if not detail.collection_name:
        collection = meta.get("belongs_to_collection") or {}
        if isinstance(collection, dict):
            detail.collection_name = str(collection.get("name") or "")
    if not detail.original_language:
        detail.original_language = str(meta.get("original_language") or "")
    if not detail.content_rating:
        detail.content_rating = TMDBClient.us_content_rating(meta)
    if not detail.countries:
        countries = meta.get("production_countries") or []
        if isinstance(countries, list):
            detail.countries = [
                str(c.get("iso_3166_1") or c.get("name") or "").strip()
                for c in countries
                if isinstance(c, dict) and str(c.get("iso_3166_1") or c.get("name") or "").strip()
            ]
    if not detail.status:
        detail.status = str(meta.get("status") or "")
    credits = meta.get("credits") or {}
    if isinstance(credits, dict):
        _apply_tmdb_credit_strings(detail, credits)
        if not detail.credits:
            detail.credits = _credits_from_tmdb(credits, tmdb=tmdb)
    detail.keywords = detail.keywords or _keyword_names_from_tmdb(meta)
    if not detail.trailer_youtube_key:
        trailer_key = TMDBClient.youtube_trailer_key(meta)
        detail.trailer_youtube_key = trailer_key if isinstance(trailer_key, str) else ""


def _apply_tmdb_tv_meta(detail: TitleDetail, meta: Mapping[str, Any], tmdb: TMDBClient) -> None:
    detail.title = detail.title or str(meta.get("name") or "")
    detail.overview = detail.overview or str(meta.get("overview") or "")
    if detail.rating is None:
        detail.rating = float(meta.get("vote_average") or 0) or None
    if not detail.poster_url:
        detail.poster_url = tmdb.poster_url(meta.get("poster_path"))
    if not detail.backdrop_url:
        detail.backdrop_url = tmdb.backdrop_url(meta.get("backdrop_path"))
    if not detail.first_air_date:
        detail.first_air_date = str(meta.get("first_air_date") or "")[:10]
    if not detail.original_language:
        detail.original_language = str(meta.get("original_language") or "")
    if not detail.content_rating:
        detail.content_rating = TMDBClient.us_content_rating(meta)
    if not detail.status:
        detail.status = str(meta.get("status") or "")
    if not detail.countries:
        countries = meta.get("origin_country") or []
        if isinstance(countries, list):
            detail.countries = [str(c).strip() for c in countries if str(c).strip()]
    external = meta.get("external_ids") or {}
    if external.get("tvdb_id") and not detail.tvdb_id:
        detail.tvdb_id = int(external["tvdb_id"])
    credits = meta.get("credits") or {}
    if isinstance(credits, dict):
        _apply_tmdb_credit_strings(detail, credits)
        if not detail.credits:
            detail.credits = _credits_from_tmdb(credits, tmdb=tmdb)
    detail.keywords = detail.keywords or _keyword_names_from_tmdb(meta)
    if not detail.trailer_youtube_key:
        trailer_key = TMDBClient.youtube_trailer_key(meta)
        detail.trailer_youtube_key = trailer_key if isinstance(trailer_key, str) else ""


def _plot_knowledge_for_item(db: Database, row, item_id: int) -> PlotKnowledge:
    """Cheap per-title plot-depth snapshot for title detail (feature-detects columns)."""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    summary = str(row["summary"] or "").strip() if "summary" in keys else ""
    overview = (
        str(row["tmdb_overview"] or "").strip() if "tmdb_overview" in keys else ""
    )
    tagline = str(row["tagline"] or "").strip() if "tagline" in keys else ""
    logline = str(row["llm_logline"] or "").strip() if "llm_logline" in keys else ""
    synopsis_supported = "long_synopsis" in keys
    synopsis = (
        str(row["long_synopsis"] or "").strip() if synopsis_supported else ""
    )
    motifs = db.facet_values_for_items([item_id], "motif").get(item_id, [])
    themes = db.facet_values_for_items([item_id], "theme").get(item_id, [])
    neighbor_count = 0
    with db.connect() as conn:
        neighbor_count = int(
            conn.execute(
                "SELECT COUNT(*) AS cnt FROM item_neighbors WHERE item_id = ?",
                (int(item_id),),
            ).fetchone()["cnt"]
            or 0
        )
    return PlotKnowledge(
        has_overview=bool(summary or overview),
        has_tagline=bool(tagline),
        has_logline=bool(logline),
        has_synopsis=bool(synopsis),
        synopsis_supported=synopsis_supported,
        motifs=motifs[:24],
        themes=themes[:24],
        neighbor_count=neighbor_count,
    )


def get_title_detail(
    db: Database,
    settings: Settings,
    *,
    media_type: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
    enrich: bool = True,
) -> TitleDetail:
    """Assemble title detail from the local library, optionally enriching via TMDB/Fanart.

    ``enrich=False`` returns local DB fields only (plus a cheap cached Plex watch URL).
    Use that for first paint; pass ``enrich=True`` for trailer/rating/runtime fill-in.
    Never runs full-library purge scoring on this path.
    """
    row = None
    if rating_key:
        row = db.library_item_by_rating_key(rating_key)
    if row is None and tmdb_id:
        row = db.library_item_by_tmdb(tmdb_id, media_type)
    if row is None and tvdb_id:
        row = db.library_item_by_tvdb(tvdb_id)

    detail = TitleDetail(
        media_type=media_type,  # type: ignore[arg-type]
        title="",
        in_library=row is not None,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        rating_key=rating_key,
    )

    if row:
        detail.title = row["title"]
        detail.year = row["year"]
        detail.tmdb_id = row["tmdb_id"] or tmdb_id
        detail.tvdb_id = row["tvdb_id"] or tvdb_id
        detail.rating_key = row["rating_key"] or rating_key
        detail.poster_url = row["poster_url"] or ""
        detail.backdrop_url = row["backdrop_url"] or ""
        detail.overview = row["summary"] or ""
        detail.genres = json.loads(row["genres"]) if row["genres"] else []
        detail.cast = json.loads(row["cast"]) if row["cast"] else []
        detail.directors = json.loads(row["directors"]) if row["directors"] else []
        detail.keywords = json.loads(row["keywords"]) if row["keywords"] else []
        detail.file_size_bytes = int(row["file_size"] or 0)
        detail.view_count = int(row["view_count"] or 0)
        detail.last_viewed_at = row["last_viewed_at"]
        detail.in_radarr = bool(row["in_radarr"])
        detail.in_sonarr = bool(row["in_sonarr"])
        keys = row.keys()
        if "release_date" in keys and row["release_date"]:
            detail.release_date = str(row["release_date"])[:10]
        if "first_air_date" in keys and row["first_air_date"]:
            detail.first_air_date = str(row["first_air_date"])[:10]
        if "collection_name" in keys and row["collection_name"]:
            detail.collection_name = str(row["collection_name"] or "")
        if "content_rating" in keys and row["content_rating"]:
            detail.content_rating = str(row["content_rating"] or "")
        if "original_language" in keys and row["original_language"]:
            detail.original_language = str(row["original_language"] or "")
        if "status" in keys and row["status"]:
            detail.status = str(row["status"] or "")
        if "countries" in keys and row["countries"]:
            try:
                detail.countries = json.loads(row["countries"]) if isinstance(row["countries"], str) else list(row["countries"] or [])
            except json.JSONDecodeError:
                detail.countries = []
        if "runtime_minutes" in keys and row["runtime_minutes"] and detail.runtime_minutes is None:
            detail.runtime_minutes = int(row["runtime_minutes"])
        if "vote_average" in keys and row["vote_average"] is not None and detail.rating is None:
            detail.rating = float(row["vote_average"])
        if "total_episode_count" in keys and row["total_episode_count"] is not None:
            try:
                detail.total_episode_count = int(row["total_episode_count"])
            except (TypeError, ValueError):
                pass
        if "unwatched_episode_count" in keys and row["unwatched_episode_count"] is not None:
            try:
                detail.unwatched_episode_count = int(row["unwatched_episode_count"])
            except (TypeError, ValueError):
                pass
        try:
            item_id = int(row["id"])
        except (TypeError, ValueError, KeyError):
            item_id = None
        if item_id is not None:
            detail.credits = [
                _credit_from_db_row(credit_row)
                for credit_row in db.list_credits_for_item(item_id)
                if str(credit_row["name"] or "").strip()
            ]
            detail.plot_knowledge = _plot_knowledge_for_item(db, row, item_id)

    resolved_tmdb_id = detail.tmdb_id
    if (
        enrich
        and settings.tmdb_api_key
        and resolved_tmdb_id
        and _needs_tmdb_enrichment(detail)
    ):
        tmdb = TMDBClient(settings.tmdb_api_key, timeout=_TITLE_DETAIL_TMDB_TIMEOUT)
        try:
            if media_type == "movie":
                _apply_tmdb_movie_meta(detail, tmdb.movie_details(resolved_tmdb_id), tmdb)
            else:
                _apply_tmdb_tv_meta(detail, tmdb.tv_details(resolved_tmdb_id), tmdb)
        except RuntimeError as exc:
            logger.info("TMDB enrichment skipped for %s/%s: %s", media_type, resolved_tmdb_id, exc)

    if (
        enrich
        and settings.fanart_api_key
        and resolved_tmdb_id
        and media_type == "movie"
        and not detail.poster_url
    ):
        try:
            fanart = FanartClient(settings.fanart_api_key, timeout=_TITLE_DETAIL_FANART_TIMEOUT)
            art = fanart.movie(resolved_tmdb_id)
            detail.poster_url = fanart.best_poster(art)
        except RuntimeError as exc:
            logger.info("Fanart enrichment skipped for movie/%s: %s", resolved_tmdb_id, exc)

    if detail.in_library and detail.rating_key:
        machine_id = cached_machine_identifier(
            settings.plex_url,
            settings.plex_token,
            timeout=_TITLE_DETAIL_PLEX_TIMEOUT,
        )
        detail.plex_machine_id = machine_id
        detail.plex_watch_url = plex_watch_url(machine_id, detail.rating_key)

    return detail
