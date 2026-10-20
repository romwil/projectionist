"""Enthusiast opt-in “you have to see this” nudges over the notification transport."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.recommendation_reasons import pick_linked_unwatched
from projectionist.notifications.service import deliver_notification

logger = logging.getLogger(__name__)

# Cap fan-out so a weekly run stays cheap even on large households.
MAX_NUDGES_PER_RUN = 40
RECENT_WATCH_LOOKBACK_SECONDS = 14 * 86400


def _persona_nudge_voice(db: Database) -> str:
    try:
        personas = db.list_persona_templates()
    except Exception:  # noqa: BLE001
        personas = []
    chosen = None
    for persona in personas or []:
        if not isinstance(persona, dict):
            continue
        if persona.get("is_default"):
            chosen = persona
            break
        name = str(persona.get("name") or "").lower()
        if "enthusiast" in name or "energy" in name:
            chosen = persona
            break
    if not chosen and personas:
        chosen = personas[0] if isinstance(personas[0], dict) else None
    if not chosen:
        return "Your curator"
    return str(chosen.get("name") or "Your curator").strip() or "Your curator"


def recently_watched_context(
    db: Database,
    *,
    limit: int = 3,
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Compact recently-watched / continue-watching context (not live sessions)."""
    ts = time.time() if now is None else float(now)
    cutoff = ts - RECENT_WATCH_LOOKBACK_SECONDS
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT title, year, media_type, tmdb_id, tvdb_id, rating_key, poster_url,
                   last_viewed_at, view_offset_ms, duration_ms, view_count
            FROM library_items
            WHERE last_viewed_at IS NOT NULL AND last_viewed_at >= ?
            ORDER BY last_viewed_at DESC
            LIMIT ?
            """,
            (cutoff, max(1, min(int(limit), 12))),
        ).fetchall()
    context: List[Dict[str, Any]] = []
    for row in rows:
        context.append(
            {
                "title": str(row["title"] or "Untitled"),
                "year": int(row["year"]) if row["year"] is not None else None,
                "media_type": str(row["media_type"] or "movie"),
                "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
                "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
                "rating_key": str(row["rating_key"]) if row["rating_key"] else None,
                "poster_url": str(row["poster_url"]) if row["poster_url"] else None,
                "last_viewed_at": float(row["last_viewed_at"]) if row["last_viewed_at"] else None,
                "in_progress": bool(
                    row["view_offset_ms"]
                    and int(row["view_offset_ms"] or 0) > 0
                    and int(row["view_count"] or 0) == 0
                ),
            }
        )
    return context


def pick_nudge_title(
    db: Database,
    *,
    recent: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    multi_user_enabled: bool = False,
) -> Optional[Dict[str, Any]]:
    """Pick one unwatched title that shares a named link with a real watch.

    Embedding neighbors and a random unwatched shelf title are not picks.
    ``recent`` is accepted for callers; the link itself is read from the graph.
    When multi-user is on, prefer the acting member's watch evidence, then
    fall back to the household.
    """
    del recent
    return pick_linked_unwatched(
        db, user_id=user_id, multi_user_enabled=multi_user_enabled
    )


def build_nudge_copy(
    db: Database,
    *,
    pick: Dict[str, Any],
    recent: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """Build nudge subject/body. Inbox lead uses media title; no comma-dump of watches.

    ``recent`` is accepted for callers/tests but kept out of the visible body — the
    structured ``recently_watched`` payload carries context for future chips.
    """
    del recent  # payload keeps recently_watched; inbox must not dump a title list
    voice = _persona_nudge_voice(db)
    title = str(pick.get("title") or "this title")
    year = pick.get("year")
    label = f"{title} ({year})" if year else title
    why = str(pick.get("why") or "").strip()
    subject = f"You have to see this — {label}"
    # Inbox card lead prefers the media title; the why line is the recognizable link.
    lines = [f"{voice} here: you have to see {label}."]
    if why:
        lines.append(why)
    lines.append("This is an opt-in nudge, not a live session alert.")
    body = "\n".join(lines)
    return {"subject": subject, "body": body, "title": title}


def deliver_enthusiast_nudges(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Fan out opt-in enthusiast nudges (inbox + email prefs)."""
    ts = time.time() if now is None else float(now)
    week_bucket = int(ts // (7 * 86400))
    multi_user = bool(getattr(getattr(settings, "features", None), "multi_user_enabled", False))
    recent = recently_watched_context(db, limit=3, now=ts)
    delivered = 0
    emailed = 0
    considered = 0
    last_pick_title: Optional[str] = None
    for user in db.list_users(limit=500):
        if considered >= MAX_NUDGES_PER_RUN:
            break
        if user.get("disabled"):
            continue
        if not user.get("nudge_opt_in"):
            continue
        considered += 1
        related = f"enthusiast-nudge-{week_bucket}-{user['id']}"
        existing = db.find_notification_by_related(
            str(user["id"]), kind="nudge", related_id=related
        )
        if existing:
            continue
        pick = pick_nudge_title(
            db,
            recent=recent,
            user_id=str(user["id"]),
            multi_user_enabled=multi_user,
        )
        if pick is None:
            continue
        last_pick_title = str(pick.get("title") or "") or last_pick_title
        content = build_nudge_copy(db, pick=pick, recent=recent)
        result = deliver_notification(
            db,
            settings,
            user_id=str(user["id"]),
            kind="nudge",
            title=content["title"],
            body=content["body"],
            payload={
                "enthusiast": True,
                "recently_watched": recent,
                "pick_why": pick.get("why"),
                "explanation": pick.get("explanation"),
                "seed_title": pick.get("seed_title"),
            },
            media_type=pick.get("media_type"),
            tmdb_id=pick.get("tmdb_id"),
            tvdb_id=pick.get("tvdb_id"),
            rating_key=pick.get("rating_key"),
            year=pick.get("year"),
            poster_url=pick.get("poster_url"),
            related_id=related,
            email_subject=content["subject"],
        )
        if result.get("notification"):
            delivered += 1
        if result.get("emailed"):
            emailed += 1
    if considered and delivered == 0 and last_pick_title is None:
        return {"delivered": 0, "emailed": 0, "skipped": "no_title", "considered": considered}
    return {
        "delivered": delivered,
        "emailed": emailed,
        "considered": considered,
        "pick": last_pick_title,
        "recent_count": len(recent),
    }
