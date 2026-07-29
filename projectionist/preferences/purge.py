"""Purge candidate analysis."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.connectors.tautulli import TautulliClient
from projectionist.library.db import Database
from projectionist.models.schemas import TitleCard


def _taste_penalty(db: Database, genres_json: str) -> float:
    genres = json.loads(genres_json) if genres_json else []
    facts = db.preference_facts(limit=100)
    score = 0.5
    for fact in facts:
        text = str(fact["text"]).lower()
        weight = float(fact["weight"] or 1.0)
        for genre in genres:
            if genre.lower() in text:
                score += 0.1 * weight
    return max(0.0, min(1.0, score))


def _build_candidates(
    db: Database,
    settings: Settings,
    *,
    limit: int = 12,
    min_file_size: int = 500_000_000,
    exclude_rating_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Core purge logic returning rich dicts with purge metadata."""
    tautulli_stats: dict[str, dict] = {}
    if settings.tautulli_url and settings.tautulli_api_key:
        try:
            client = TautulliClient(settings.tautulli_url, settings.tautulli_api_key)
            for section in client.get_libraries():
                if section.get("section_type") not in ("movie", "show"):
                    continue
                for item in client.get_library_media_info(int(section["section_id"]), length=5000):
                    key = str(item.get("rating_key") or "")
                    if key:
                        tautulli_stats[key] = item
        except RuntimeError:
            pass

    now = time.time()
    dismissed_keys = db.dismissed_purge_keys()
    excluded = {str(k) for k in (exclude_rating_keys or set()) if str(k).strip()}
    candidates: List[tuple[float, Dict[str, Any]]] = []
    for row in db.all_library_items():
        file_size = int(row["file_size"] or 0)
        if file_size < min_file_size:
            continue
        rating_key = str(row["rating_key"] or "")
        if rating_key in dismissed_keys or rating_key in excluded:
            continue
        view_count = int(row["view_count"] or 0)
        last_viewed = row["last_viewed_at"]
        media_type = str(row["media_type"] or "movie")
        # Shows: prefer episode progress over coarse show-level play count.
        if media_type == "show":
            total_eps = int(row["total_episode_count"] or 0)
            unwatched_eps = int(row["unwatched_episode_count"] or 0)
            if total_eps > 0:
                watched_eps = max(0, total_eps - unwatched_eps)
                if watched_eps > 2:
                    continue
                view_count = max(view_count, watched_eps)
        stats = tautulli_stats.get(rating_key, {})
        if stats:
            view_count = max(view_count, int(stats.get("play_count") or 0))
        taste = _taste_penalty(db, row["genres"])
        stale_years = 0.0
        if last_viewed:
            stale_years = (now - int(last_viewed)) / (365.25 * 24 * 3600)
        elif view_count == 0:
            stale_years = 5.0

        purge_score = (file_size / 1_000_000_000) * (1.1 - taste) + stale_years * 0.5
        if view_count > 2:
            continue
        reason = f"{file_size / 1_000_000_000:.1f} GB, {view_count} plays, {taste:.0%} taste match"
        if stale_years >= 1:
            reason += f", stale {stale_years:.0f}y"
        if media_type == "show":
            total_eps = int(row["total_episode_count"] or 0)
            if total_eps:
                reason += f", {total_eps} eps"

        last_watched_str: Optional[str] = None
        if last_viewed:
            try:
                from datetime import datetime, timezone
                last_watched_str = datetime.fromtimestamp(int(last_viewed), tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        entry: Dict[str, Any] = {
            "media_type": media_type,
            "title": row["title"],
            "year": row["year"],
            "tmdb_id": row["tmdb_id"],
            "tvdb_id": row["tvdb_id"],
            "rating_key": rating_key,
            "poster_url": row["poster_url"] or "",
            "backdrop_url": row["backdrop_url"] or "",
            "genres": json.loads(row["genres"]) if row["genres"] else [],
            "in_library": True,
            "file_size": file_size,
            "last_watched": last_watched_str,
            "taste_match": round(taste * 100, 1),
            "purge_score": round(purge_score, 2),
            "reason": reason,
            "recommendation_reason": reason,
            "card_kind": "purge",
            "total_episode_count": int(row["total_episode_count"] or 0)
            if media_type == "show"
            else None,
            "unwatched_episode_count": int(row["unwatched_episode_count"] or 0)
            if media_type == "show"
            else None,
        }
        candidates.append((purge_score, entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in candidates[:limit]]


def suggest_purge_candidates(
    db: Database,
    settings: Settings,
    *,
    limit: int = 12,
    min_file_size: int = 500_000_000,
    exclude_rating_keys: Optional[set[str]] = None,
) -> List[TitleCard]:
    """Return purge candidates as TitleCard objects (for MCP/chat compatibility)."""
    rich = _build_candidates(
        db,
        settings,
        limit=limit,
        min_file_size=min_file_size,
        exclude_rating_keys=exclude_rating_keys,
    )
    cards: List[TitleCard] = []
    for entry in rich:
        cards.append(TitleCard(
            media_type=entry["media_type"],
            title=entry["title"],
            year=entry.get("year"),
            tmdb_id=entry.get("tmdb_id"),
            tvdb_id=entry.get("tvdb_id"),
            rating_key=entry.get("rating_key"),
            poster_url=entry.get("poster_url", ""),
            backdrop_url=entry.get("backdrop_url", ""),
            genres=entry.get("genres", []),
            in_library=True,
            recommendation_reason=entry.get("recommendation_reason", ""),
            card_kind="purge",
        ))
    return cards


def suggest_purge_candidates_rich(
    db: Database,
    settings: Settings,
    *,
    limit: int = 12,
    min_file_size: int = 500_000_000,
    exclude_rating_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Return purge candidates with full purge metadata for the dashboard."""
    return _build_candidates(
        db,
        settings,
        limit=limit,
        min_file_size=min_file_size,
        exclude_rating_keys=exclude_rating_keys,
    )


def enrich_purge_candidate_rows(
    db: Database,
    settings: Settings,
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Refresh size / last-watched for presentation; prefer *arr sizeOnDisk when set."""
    if not items:
        return []

    enriched: List[Dict[str, Any]] = []
    radarr_sizes: Dict[int, int] = {}
    sonarr_sizes: Dict[int, int] = {}

    need_radarr = any(
        str(item.get("media_type") or "") == "movie" and item.get("tmdb_id") for item in items
    )
    need_sonarr = any(
        str(item.get("media_type") or "") == "show"
        and (item.get("tvdb_id") or item.get("tmdb_id"))
        for item in items
    )
    if need_radarr and settings.radarr_url and settings.radarr_api_key:
        try:
            from projectionist.connectors.radarr import RadarrClient

            client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
            for movie in client.movies():
                if movie.tmdb_id and movie.file_size:
                    radarr_sizes[int(movie.tmdb_id)] = int(movie.file_size)
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            pass
    if need_sonarr and settings.sonarr_url and settings.sonarr_api_key:
        try:
            from projectionist.connectors.sonarr import SonarrClient

            client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
            for series in client.series_list():
                if series.tvdb_id and series.total_file_size:
                    sonarr_sizes[int(series.tvdb_id)] = int(series.total_file_size)
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            pass

    for item in items:
        row_dict = dict(item)
        key = str(item.get("rating_key") or "").strip()
        row = db.library_item_by_rating_key(key) if key else None
        if row is not None:
            file_size = int(row["file_size"] or 0)
            last_viewed = row["last_viewed_at"]
            media_type = str(row["media_type"] or row_dict.get("media_type") or "movie")
            row_dict["file_size"] = file_size
            row_dict["media_type"] = media_type
            row_dict["title"] = row["title"] or row_dict.get("title")
            row_dict["year"] = row["year"] if row["year"] is not None else row_dict.get("year")
            row_dict["tmdb_id"] = row["tmdb_id"] if row["tmdb_id"] is not None else row_dict.get("tmdb_id")
            row_dict["tvdb_id"] = row["tvdb_id"] if row["tvdb_id"] is not None else row_dict.get("tvdb_id")
            if media_type == "show":
                row_dict["total_episode_count"] = int(row["total_episode_count"] or 0)
                row_dict["unwatched_episode_count"] = int(row["unwatched_episode_count"] or 0)
            last_watched_str: Optional[str] = None
            if last_viewed:
                try:
                    from datetime import datetime, timezone

                    last_watched_str = datetime.fromtimestamp(
                        int(last_viewed), tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    pass
            row_dict["last_watched"] = last_watched_str

        media_type = str(row_dict.get("media_type") or "movie")
        if media_type == "movie" and row_dict.get("tmdb_id") is not None:
            arr_size = radarr_sizes.get(int(row_dict["tmdb_id"]))
            if arr_size:
                row_dict["file_size"] = arr_size
        elif media_type == "show" and row_dict.get("tvdb_id") is not None:
            arr_size = sonarr_sizes.get(int(row_dict["tvdb_id"]))
            if arr_size:
                row_dict["file_size"] = arr_size

        file_size = int(row_dict.get("file_size") or 0)
        taste = row_dict.get("taste_match")
        view_hint = row_dict.get("reason") or ""
        if file_size:
            # Keep reason readable after size refresh.
            gb = file_size / 1_000_000_000
            if "GB" in str(view_hint):
                # Replace leading size token if present.
                parts = str(view_hint).split(", ", 1)
                rest = parts[1] if len(parts) > 1 else view_hint
                row_dict["reason"] = f"{gb:.1f} GB, {rest}" if parts else f"{gb:.1f} GB"
            elif not view_hint:
                taste_pct = f"{float(taste):.0f}%" if taste is not None else "?"
                row_dict["reason"] = f"{gb:.1f} GB, taste {taste_pct}"
            row_dict["recommendation_reason"] = row_dict.get("reason") or ""
        enriched.append(row_dict)
    return enriched
