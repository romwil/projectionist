"""Title detail assembly."""

from __future__ import annotations

import json
from typing import Optional

from curatorx.config_store import Settings
from curatorx.connectors.fanart import FanartClient
from curatorx.connectors.plex import cached_machine_identifier, plex_watch_url
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.models.schemas import TitleDetail
from curatorx.preferences.purge import suggest_purge_candidates


def get_title_detail(
    db: Database,
    settings: Settings,
    *,
    media_type: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
) -> TitleDetail:
    row = None
    if rating_key:
        for item in db.all_library_items():
            if item["rating_key"] == rating_key:
                row = item
                break
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

    resolved_tmdb_id = detail.tmdb_id
    if settings.tmdb_api_key and resolved_tmdb_id:
        tmdb = TMDBClient(settings.tmdb_api_key)
        try:
            if media_type == "movie":
                meta = tmdb.movie_details(resolved_tmdb_id)
                detail.title = detail.title or str(meta.get("title") or "")
                detail.overview = detail.overview or str(meta.get("overview") or "")
                detail.rating = float(meta.get("vote_average") or 0) or None
                if not detail.poster_url:
                    detail.poster_url = tmdb.poster_url(meta.get("poster_path"))
                if not detail.backdrop_url:
                    detail.backdrop_url = tmdb.backdrop_url(meta.get("backdrop_path"))
                detail.runtime_minutes = int((meta.get("runtime") or 0) or 0) or None
                credits = meta.get("credits") or {}
                if not detail.cast:
                    detail.cast = [c.get("name", "") for c in credits.get("cast", [])[:8]]
                if not detail.directors:
                    detail.directors = [
                        c.get("name", "") for c in credits.get("crew", []) if c.get("job") == "Director"
                    ]
                keywords = (meta.get("keywords") or {}).get("keywords") or []
                detail.keywords = detail.keywords or [k.get("name", "") for k in keywords if k.get("name")]
                trailer_key = TMDBClient.youtube_trailer_key(meta)
                detail.trailer_youtube_key = trailer_key if isinstance(trailer_key, str) else ""
            else:
                meta = tmdb.tv_details(resolved_tmdb_id)
                detail.title = detail.title or str(meta.get("name") or "")
                detail.overview = detail.overview or str(meta.get("overview") or "")
                detail.rating = float(meta.get("vote_average") or 0) or None
                if not detail.poster_url:
                    detail.poster_url = tmdb.poster_url(meta.get("poster_path"))
                if not detail.backdrop_url:
                    detail.backdrop_url = tmdb.backdrop_url(meta.get("backdrop_path"))
                external = meta.get("external_ids") or {}
                if external.get("tvdb_id"):
                    detail.tvdb_id = int(external["tvdb_id"])
                trailer_key = TMDBClient.youtube_trailer_key(meta)
                detail.trailer_youtube_key = trailer_key if isinstance(trailer_key, str) else ""
        except RuntimeError:
            pass

    if settings.fanart_api_key and resolved_tmdb_id and media_type == "movie":
        art = FanartClient(settings.fanart_api_key).movie(resolved_tmdb_id)
        if not detail.poster_url:
            detail.poster_url = FanartClient(settings.fanart_api_key).best_poster(art)

    if row:
        purge_cards = suggest_purge_candidates(db, settings, limit=100)
        for card in purge_cards:
            if card.rating_key == row["rating_key"]:
                detail.purge_reason = card.recommendation_reason
                detail.purge_score = 0.8
                break

    if detail.in_library and detail.rating_key:
        machine_id = cached_machine_identifier(settings.plex_url, settings.plex_token)
        detail.plex_machine_id = machine_id
        detail.plex_watch_url = plex_watch_url(machine_id, detail.rating_key)

    return detail
