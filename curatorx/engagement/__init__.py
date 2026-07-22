"""Engagement substrate: badges, streaks, challenges, courses, explainers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from curatorx.library.db import Database

logger = logging.getLogger(__name__)


def sync_review_challenges(db: Database, user_id: str) -> Dict[str, Any]:
    """Align rate-N challenge progress + review badges with current review count."""
    count = db.count_user_reviews(user_id)
    updated = []
    for challenge in db.list_engagement_challenges(active_only=True):
        if challenge.get("kind") != "rate_n":
            continue
        item = db.set_challenge_progress(user_id, challenge["id"], count)
        updated.append(item)
    awarded = []
    for badge in db.list_engagement_badges():
        criteria = badge.get("criteria") or {}
        if criteria.get("event") != "review":
            continue
        min_count = int(criteria.get("min_count") or 1)
        if count >= min_count and db.award_badge(user_id, badge["id"]):
            awarded.append(badge["slug"])
    if count >= 1:
        # Course / streak badges are handled elsewhere; first-review covered above.
        pass
    return {"review_count": count, "challenges": updated, "awarded": awarded}


def sync_chat_streak(db: Database, user_id: str) -> Dict[str, Any]:
    streak = db.touch_user_streak(user_id, "chat")
    awarded = []
    for badge in db.list_engagement_badges():
        criteria = badge.get("criteria") or {}
        if criteria.get("event") != "chat_streak":
            continue
        min_count = int(criteria.get("min_count") or 3)
        if int(streak.get("current_count") or 0) >= min_count:
            if db.award_badge(user_id, badge["id"]):
                awarded.append(badge["slug"])
    return {"streak": streak, "awarded": awarded}


def engagement_summary(
    db: Database,
    *,
    user_id: str,
    youth_safe_only: bool = False,
) -> Dict[str, Any]:
    """Aggregate engagement payload for the member UI."""
    sync_review_challenges(db, user_id)
    session_count = 0
    try:
        session_count = db.count_chat_sessions_last_days(30)
    except Exception:  # noqa: BLE001
        session_count = 0
    streak = db.get_user_streak(user_id, "chat")
    badges = db.list_user_badges(user_id)
    if youth_safe_only:
        badges = [b for b in badges if b.get("youth_safe")]
    challenges = db.get_user_challenge_progress(user_id)
    if youth_safe_only:
        challenges = [c for c in challenges if c.get("youth_safe")]
    explainers = db.list_engagement_explainers(youth_safe_only=youth_safe_only)
    courses: List[Dict[str, Any]] = []
    try:
        published = []
        if hasattr(db, "list_published_lists"):
            published = db.list_published_lists() or []
        progress_rows = {p["list_id"]: p for p in db.list_user_course_progress(user_id)}
        for coll in published:
            if str(coll.get("list_kind") or "") != "course":
                continue
            prog = progress_rows.get(coll["id"]) or {
                "position": 0,
                "completed_at": None,
                "updated_at": None,
            }
            courses.append(
                {
                    "id": coll["id"],
                    "name": coll.get("name"),
                    "description": coll.get("description") or "",
                    "item_count": coll.get("item_count") or 0,
                    "position": prog.get("position") or 0,
                    "completed_at": prog.get("completed_at"),
                    "updated_at": prog.get("updated_at"),
                }
            )
    except Exception:  # noqa: BLE001
        logger.debug("engagement courses listing failed", exc_info=True)
    return {
        "session_count_30d": session_count,
        "streak_visible": session_count >= 3 or int(streak.get("current_count") or 0) >= 3,
        "streak": streak,
        "badges": badges,
        "challenges": challenges,
        "courses": courses,
        "explainers": explainers,
        "review_count": db.count_user_reviews(user_id),
    }
