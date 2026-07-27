"""Idle task: recompute taste profile weights.

Reads ``preference_facts``, ``message_feedback``, ``user_title_reviews``, and
``library_episodes`` (season-decay + episode sentiment) to build genre/keyword
cluster weights, then upserts them into ``lens_taste_profile``.

Free-text preference / feedback prose is tokenized with
``projectionist.taste.clusters`` so stop-words, contractions, and punctuation
never become Taste settings clusters. Each run also purges unlocked junk rows
left by older naive splits.

Lightweight — should complete in under a second for typical libraries.
Default interval: 6 hours.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Mapping

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.preferences.tv_taste import show_taste_multiplier
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.taste.clusters import (
    cluster_tokens_from_text,
    filter_cluster_tags,
    is_valid_cluster_tag,
)

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours


def _parse_tags(raw: Any) -> List[str]:
    if not raw:
        return []
    try:
        tags = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(tags, list):
        return []
    return filter_cluster_tags(str(tag).strip().lower() for tag in tags if str(tag).strip())


def _load_show_episode_multipliers(conn: Any) -> Dict[int, float]:
    """Map show ``library_items.id`` → episode/season-decay taste multiplier."""
    rows = conn.execute(
        """
        SELECT show_item_id, season_number, episode_number, view_count,
               plex_user_rating_stars
        FROM library_episodes
        ORDER BY show_item_id, season_number, episode_number
        """
    ).fetchall()
    by_show: Dict[int, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_show[int(row["show_item_id"])].append(
            {
                "season_number": row["season_number"],
                "episode_number": row["episode_number"],
                "view_count": row["view_count"],
                "plex_user_rating_stars": row["plex_user_rating_stars"],
            }
        )
    return {
        show_id: show_taste_multiplier(episodes) for show_id, episodes in by_show.items()
    }


def _apply_tags(cluster_weights: Counter[str], tags: List[str], weight: float) -> None:
    if not weight:
        return
    for tag in tags:
        if is_valid_cluster_tag(tag):
            cluster_weights[tag] += weight


def _purge_junk_clusters(conn: Any) -> int:
    """Delete unlocked junk tags left over from older naive tokenization."""
    deleted = 0
    for table, key_col in (
        ("lens_taste_profile", "lens_id"),
        ("user_taste_profile", "user_id"),
    ):
        rows = conn.execute(
            f"SELECT {key_col} AS scope_key, cluster_tag, explicit_lock FROM {table}"
        ).fetchall()
        for row in rows:
            tag = str(row["cluster_tag"] or "")
            if is_valid_cluster_tag(tag):
                continue
            # Leave locked overrides alone; owners can Reset them in Taste settings.
            if int(row["explicit_lock"] or 0):
                continue
            conn.execute(
                f"DELETE FROM {table} WHERE {key_col} = ? AND cluster_tag = ?",
                (row["scope_key"], tag),
            )
            deleted += 1
    return deleted

async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    cluster_weights: Counter[str] = Counter()
    tv_shows_adjusted = 0

    with db.connect() as conn:
        show_multipliers = _load_show_episode_multipliers(conn)

        # Preference facts — each signal contributes to genre/keyword clusters.
        pref_rows = conn.execute(
            "SELECT signal_type, text, weight, media_type, tvdb_id, tmdb_id FROM preference_facts"
        ).fetchall()
        for row in pref_rows:
            multiplier = float(row["weight"] or 1.0)
            if str(row["signal_type"]) == "negative":
                multiplier *= -0.5
            # Soften TV facts when episode curves show mid-series abandonment.
            if str(row["media_type"] or "").lower() in {"show", "tv", "series"}:
                show_id = None
                if row["tvdb_id"] is not None:
                    match = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'show' AND tvdb_id = ?",
                        (int(row["tvdb_id"]),),
                    ).fetchone()
                    if match:
                        show_id = int(match["id"])
                if show_id is None and row["tmdb_id"] is not None:
                    match = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'show' AND tmdb_id = ?",
                        (int(row["tmdb_id"]),),
                    ).fetchone()
                    if match:
                        show_id = int(match["id"])
                if show_id is not None and show_id in show_multipliers:
                    multiplier *= float(show_multipliers[show_id])
                    tv_shows_adjusted += 1
            text = str(row["text"] or "").strip().lower()
            if text:
                for token in cluster_tokens_from_text(text):
                    cluster_weights[token] += multiplier

        if should_stop():
            return {"status": "interrupted"}

        # Message feedback — positive/negative signals from chat responses.
        fb_rows = conn.execute(
            "SELECT feedback_type, excerpt FROM message_feedback"
        ).fetchall()
        for row in fb_rows:
            w = 1.0 if str(row["feedback_type"]) == "helpful" else -0.5
            excerpt = str(row["excerpt"] or "").strip().lower()
            for token in cluster_tokens_from_text(excerpt)[:20]:
                cluster_weights[token] += w
        if should_stop():
            return {"status": "interrupted"}

        # User reviews — star ratings boost genre affinity for highly-rated titles.
        # Shows apply episode season-decay so abandoned series don't keep forcing
        # later-season neighbors.
        review_rows = conn.execute(
            """
            SELECT r.stars, li.id AS item_id, li.media_type, li.genres, li.keywords
            FROM user_title_reviews r
            LEFT JOIN library_items li
              ON li.rating_key = r.rating_key
            WHERE r.stars IS NOT NULL AND li.id IS NOT NULL
            """
        ).fetchall()
        for row in review_rows:
            stars = int(row["stars"] or 3)
            w = (stars - 3) * 0.5  # 1★ → -1.0, 3★ → 0, 5★ → +1.0
            item_id = int(row["item_id"])
            if str(row["media_type"] or "") == "show" and item_id in show_multipliers:
                w *= float(show_multipliers[item_id])
                tv_shows_adjusted += 1
            for col in ("genres", "keywords"):
                _apply_tags(cluster_weights, _parse_tags(row[col]), w)

        # Episode-only shows (no review yet): fold decayed sentiment into genres.
        show_rows = conn.execute(
            """
            SELECT id, genres, keywords FROM library_items
            WHERE media_type = 'show'
            """
        ).fetchall()
        for row in show_rows:
            item_id = int(row["id"])
            if item_id not in show_multipliers:
                continue
            # Skip if already contributed via a review (avoid double-count).
            # Mild contribution from episode curve alone (0.25 scale).
            # Reviews path already counted when present; detect via multiplier use
            # only when there was no review for this id.
            reviewed = any(int(r["item_id"]) == item_id for r in review_rows)
            if reviewed:
                continue
            mult = float(show_multipliers[item_id])
            if mult <= 0:
                continue
            w = (mult - 0.5) * 0.5  # center neutral at 0.5 → 0 contribution
            if abs(w) < 0.01:
                continue
            for col in ("genres", "keywords"):
                _apply_tags(cluster_weights, _parse_tags(row[col]), w)
            tv_shows_adjusted += 1

    if not cluster_weights:
        with db.connect() as conn:
            purged = _purge_junk_clusters(conn)
        return {
            "status": "completed",
            "clusters_updated": 0,
            "tv_shows_adjusted": tv_shows_adjusted,
            "junk_purged": purged,
        }

    # Normalize to 0..1 range.
    max_abs = max(abs(v) for v in cluster_weights.values()) or 1.0
    normalized = {
        tag: max(0.0, min(1.0, (w / max_abs + 1) / 2)) for tag, w in cluster_weights.items()
    }

    # Keep top 200 clusters (already filtered at ingest).
    top = [
        (tag, weight)
        for tag, weight in sorted(
            normalized.items(), key=lambda x: abs(x[1] - 0.5), reverse=True
        )
        if is_valid_cluster_tag(tag)
    ][:200]

    with db.connect() as conn:
        for tag, weight in top:
            conn.execute(
                """
                INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, last_updated)
                VALUES ('general', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(lens_id, cluster_tag) DO UPDATE SET
                    weight = excluded.weight,
                    last_updated = CURRENT_TIMESTAMP
                WHERE explicit_lock = 0
                """,
                (tag, round(weight, 4)),
            )
        purged = _purge_junk_clusters(conn)

    logger.info(
        "Taste profile refreshed: %d cluster weights updated "
        "(tv_shows_adjusted=%d, junk_purged=%d)",
        len(top),
        tv_shows_adjusted,
        purged,
    )
    return {
        "status": "completed",
        "clusters_updated": len(top),
        "tv_shows_adjusted": tv_shows_adjusted,
        "junk_purged": purged,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="taste_refresh",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Recomputes taste-profile weights from reviews, preference facts, "
                "feedback, and TV episode/season-decay curves so recommendations "
                "stay aligned with what you actually like — including shows you "
                "abandoned mid-series."
            ),
        )
    )
