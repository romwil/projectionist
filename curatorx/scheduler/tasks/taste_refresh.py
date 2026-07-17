"""Idle task: recompute taste profile weights.

Reads ``preference_facts``, ``message_feedback``, and ``user_title_reviews``
to build genre/keyword cluster weights, then upserts them into
``lens_taste_profile``.

Lightweight — should complete in under a second for typical libraries.
Default interval: 6 hours.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    cluster_weights: Counter[str] = Counter()

    with db.connect() as conn:
        # Preference facts — each signal contributes to genre/keyword clusters.
        pref_rows = conn.execute(
            "SELECT signal_type, text, weight FROM preference_facts"
        ).fetchall()
        for row in pref_rows:
            multiplier = float(row["weight"] or 1.0)
            if str(row["signal_type"]) == "negative":
                multiplier *= -0.5
            text = str(row["text"] or "").strip().lower()
            if text:
                for token in text.split():
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
            for token in excerpt.split()[:20]:
                cluster_weights[token] += w

        if should_stop():
            return {"status": "interrupted"}

        # User reviews — star ratings boost genre affinity for highly-rated titles.
        review_rows = conn.execute(
            """
            SELECT r.stars, li.genres, li.keywords
            FROM user_title_reviews r
            LEFT JOIN library_items li
              ON li.rating_key = r.rating_key
            WHERE r.stars IS NOT NULL AND li.id IS NOT NULL
            """
        ).fetchall()
        for row in review_rows:
            stars = int(row["stars"] or 3)
            w = (stars - 3) * 0.5  # 1★ → -1.0, 3★ → 0, 5★ → +1.0
            for col in ("genres", "keywords"):
                raw = row[col]
                if not raw:
                    continue
                try:
                    tags = json.loads(raw) if isinstance(raw, str) else raw
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(tags, list):
                    for tag in tags:
                        cluster_weights[str(tag).strip().lower()] += w

    if not cluster_weights:
        return {"status": "completed", "clusters_updated": 0}

    # Normalize to 0..1 range.
    max_abs = max(abs(v) for v in cluster_weights.values()) or 1.0
    normalized = {tag: max(0.0, min(1.0, (w / max_abs + 1) / 2)) for tag, w in cluster_weights.items()}

    # Keep top 200 clusters.
    top = sorted(normalized.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)[:200]

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

    logger.info("Taste profile refreshed: %d cluster weights updated", len(top))
    return {"status": "completed", "clusters_updated": len(top)}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="taste_refresh",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Recomputes taste-profile weights from reviews, preference facts, and "
                "feedback so recommendations stay aligned with what you actually like."
            ),
        )
    )
