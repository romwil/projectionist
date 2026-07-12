"""Write personal review star ratings back to Plex."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.plex import PlexClient
from curatorx.library.db import Database

logger = logging.getLogger(__name__)


def sync_reviews_to_plex_enabled(settings: Settings) -> bool:
    return bool(settings.sync_reviews_to_plex)


def _plex_client(settings: Settings) -> PlexClient:
    return PlexClient(
        settings.plex_url,
        settings.plex_token,
        movie_section=settings.plex_movie_section or None,
        tv_section=settings.plex_tv_section or None,
    )


def get_stored_plex_user_rating_stars(db: Database, rating_key: str) -> Optional[float]:
    key = str(rating_key or "").strip()
    if not key:
        return None
    with db.connect() as conn:
        item_cols = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
        if "plex_user_rating_stars" in item_cols:
            row = conn.execute(
                "SELECT plex_user_rating_stars FROM library_items WHERE rating_key = ?",
                (key,),
            ).fetchone()
            if row is not None and row["plex_user_rating_stars"] is not None:
                return float(row["plex_user_rating_stars"])
        episode_cols = {row[1] for row in conn.execute("PRAGMA table_info(library_episodes)")}
        if "plex_user_rating_stars" in episode_cols:
            row = conn.execute(
                "SELECT plex_user_rating_stars FROM library_episodes WHERE rating_key = ?",
                (key,),
            ).fetchone()
            if row is not None and row["plex_user_rating_stars"] is not None:
                return float(row["plex_user_rating_stars"])
    return None


def cache_plex_user_rating_stars(db: Database, rating_key: str, stars: float | int) -> None:
    """Update local library cache immediately after a successful Plex rating write."""
    key = str(rating_key or "").strip()
    if not key:
        return
    now = time.time()
    stars_value = float(stars)
    with db.connect() as conn:
        item_cols = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
        if "plex_user_rating_stars" in item_cols:
            conn.execute(
                """
                UPDATE library_items
                SET plex_user_rating_stars = ?, updated_at = ?
                WHERE rating_key = ?
                """,
                (stars_value, now, key),
            )
        episode_cols = {row[1] for row in conn.execute("PRAGMA table_info(library_episodes)")}
        if "plex_user_rating_stars" in episode_cols:
            conn.execute(
                """
                UPDATE library_episodes
                SET plex_user_rating_stars = ?
                WHERE rating_key = ?
                """,
                (stars_value, key),
            )


def lookup_plex_user_rating_stars(
    db: Database,
    settings: Settings,
    rating_key: str,
) -> Optional[float]:
    stored = get_stored_plex_user_rating_stars(db, rating_key)
    if stored is not None:
        return stored
    if not settings.plex_url or not settings.plex_token:
        return None
    try:
        item = _plex_client(settings).get_metadata(rating_key)
        return item.user_rating_stars
    except Exception:
        logger.debug("Could not fetch Plex user rating for rating_key=%s", rating_key, exc_info=True)
        return None


def mark_plex_rating_synced(db: Database, review_id: str) -> None:
    now = time.time()
    with db.connect() as conn:
        conn.execute(
            """
            UPDATE user_title_reviews
            SET plex_rating_synced = 1, plex_synced_at = ?
            WHERE id = ?
            """,
            (now, review_id),
        )


def sync_review_rating_to_plex(
    db: Database,
    settings: Settings,
    review: Mapping[str, Any],
    *,
    replace_plex_rating: bool = False,
) -> Dict[str, Any]:
    """Push stars to Plex when enabled. Returns review dict with sync flags updated."""
    payload = dict(review)
    rating_key = str(payload.get("rating_key") or "").strip()
    stars = payload.get("stars")
    review_id = str(payload.get("id") or "")

    if not sync_reviews_to_plex_enabled(settings):
        payload["synced"] = False
        payload["reason"] = "disabled"
        return payload

    if not rating_key or stars is None or not review_id:
        payload["synced"] = False
        payload["reason"] = "missing_rating_key"
        return payload

    if not settings.plex_url or not settings.plex_token:
        payload["synced"] = False
        payload["reason"] = "plex_not_configured"
        return payload

    submitted_stars = float(stars)
    if not replace_plex_rating:
        plex_stars = lookup_plex_user_rating_stars(db, settings, rating_key)
        if plex_stars is not None and plex_stars != submitted_stars:
            payload["synced"] = False
            payload["reason"] = "plex_rating_conflict"
            payload["plex_stars"] = plex_stars
            payload["submitted_stars"] = submitted_stars
            return payload

    try:
        _plex_client(settings).set_user_rating(rating_key, submitted_stars)
    except Exception:
        logger.exception(
            "Failed to sync Plex rating for review %s rating_key=%s",
            review_id,
            rating_key,
        )
        payload["synced"] = False
        payload["reason"] = "plex_error"
        return payload

    mark_plex_rating_synced(db, review_id)
    cache_plex_user_rating_stars(db, rating_key, submitted_stars)
    payload["synced"] = True
    payload["plex_rating_synced"] = True
    payload["plex_synced_at"] = time.time()
    logger.info(
        "Synced Plex rating review_id=%s rating_key=%s stars=%s",
        review_id,
        rating_key,
        stars,
    )
    return payload
