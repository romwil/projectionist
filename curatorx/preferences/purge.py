"""Purge candidate analysis."""

from __future__ import annotations

import json
import time
from typing import List, Optional

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


def suggest_purge_candidates(
    db: Database,
    settings: Settings,
    *,
    limit: int = 12,
    min_file_size: int = 500_000_000,
) -> List[TitleCard]:
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
    candidates: List[tuple[float, TitleCard]] = []
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
        card = TitleCard(
            media_type=row["media_type"],
            title=row["title"],
            year=row["year"],
            tmdb_id=row["tmdb_id"],
            tvdb_id=row["tvdb_id"],
            rating_key=row["rating_key"],
            poster_url=row["poster_url"] or "",
            backdrop_url=row["backdrop_url"] or "",
            overview=row["summary"] or "",
            genres=json.loads(row["genres"]) if row["genres"] else [],
            in_library=True,
            in_radarr=bool(row["in_radarr"]),
            in_sonarr=bool(row["in_sonarr"]),
            recommendation_reason=reason,
            card_kind="purge",
        )
        candidates.append((purge_score, card))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in candidates[:limit]]
