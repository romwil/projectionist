"""Purge candidate analysis."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.connectors.tautulli import TautulliClient
from curatorx.library.db import Database
from curatorx.models.schemas import TitleCard


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
    candidates: List[tuple[float, Dict[str, Any]]] = []
    for row in db.all_library_items():
        file_size = int(row["file_size"] or 0)
        if file_size < min_file_size:
            continue
        view_count = int(row["view_count"] or 0)
        last_viewed = row["last_viewed_at"]
        stats = tautulli_stats.get(str(row["rating_key"]), {})
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

        last_watched_str: Optional[str] = None
        if last_viewed:
            try:
                from datetime import datetime, timezone
                last_watched_str = datetime.fromtimestamp(int(last_viewed), tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        entry: Dict[str, Any] = {
            "media_type": row["media_type"],
            "title": row["title"],
            "year": row["year"],
            "tmdb_id": row["tmdb_id"],
            "tvdb_id": row["tvdb_id"],
            "rating_key": row["rating_key"],
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
) -> List[TitleCard]:
    """Return purge candidates as TitleCard objects (for MCP/chat compatibility)."""
    rich = _build_candidates(db, settings, limit=limit, min_file_size=min_file_size)
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
) -> List[Dict[str, Any]]:
    """Return purge candidates with full purge metadata for the dashboard."""
    return _build_candidates(db, settings, limit=limit, min_file_size=min_file_size)
