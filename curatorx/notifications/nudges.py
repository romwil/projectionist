"""Enthusiast opt-in “you have to see this” nudges over the notification transport."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.service import deliver_notification

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
) -> Optional[Dict[str, Any]]:
    """Pick one unwatched title, preferring neighbors of recent watches when available."""
    recent = recent or recently_watched_context(db, limit=3)
    seed_ids: List[int] = []
    if recent:
        with db.connect() as conn:
            for item in recent[:3]:
                rk = item.get("rating_key")
                tmdb = item.get("tmdb_id")
                row = None
                if rk:
                    row = conn.execute(
                        "SELECT id FROM library_items WHERE rating_key = ? LIMIT 1",
                        (str(rk),),
                    ).fetchone()
                elif tmdb is not None:
                    row = conn.execute(
                        "SELECT id FROM library_items WHERE tmdb_id = ? LIMIT 1",
                        (int(tmdb),),
                    ).fetchone()
                if row is not None:
                    seed_ids.append(int(row["id"]))

    if seed_ids and hasattr(db, "get_neighbors"):
        for seed_id in seed_ids:
            try:
                neighbors = db.get_neighbors(seed_id, limit=8) or []
            except Exception:  # noqa: BLE001
                neighbors = []
            for neighbor in neighbors:
                try:
                    view_count = int(neighbor["view_count"] or 0)
                    title = str(neighbor["title"] or "").strip()
                except (TypeError, KeyError, IndexError):
                    continue
                if view_count > 0 or not title:
                    continue
                return {
                    "title": title,
                    "year": neighbor["year"],
                    "media_type": neighbor["media_type"] or "movie",
                    "tmdb_id": neighbor["tmdb_id"],
                    "tvdb_id": neighbor["tvdb_id"],
                    "rating_key": neighbor["rating_key"],
                    "poster_url": neighbor["poster_url"],
                    "why": f"Because you recently watched {recent[0]['title']}" if recent else None,
                }

    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT title, year, media_type, tmdb_id, tvdb_id, rating_key, poster_url, genres
            FROM library_items
            WHERE COALESCE(view_count, 0) = 0
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {
        "title": str(row["title"] or "Untitled"),
        "year": int(row["year"]) if row["year"] is not None else None,
        "media_type": str(row["media_type"] or "movie"),
        "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
        "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
        "rating_key": str(row["rating_key"]) if row["rating_key"] else None,
        "poster_url": str(row["poster_url"]) if row["poster_url"] else None,
        "why": None,
    }


def build_nudge_copy(
    db: Database,
    *,
    pick: Dict[str, Any],
    recent: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    voice = _persona_nudge_voice(db)
    title = str(pick.get("title") or "this title")
    year = pick.get("year")
    label = f"{title} ({year})" if year else title
    why = str(pick.get("why") or "").strip()
    recent_bit = ""
    if recent:
        names = ", ".join(str(r.get("title") or "") for r in recent[:2] if r.get("title"))
        if names:
            recent_bit = f" (reacting to what you recently watched: {names})"
    subject = f"You have to see this — {label}"
    body = (
        f"{voice} here: you have to see {label}.{recent_bit}\n"
        f"{why or 'An unwatched pick from your shelves that fits the moment.'}\n"
        "Open CuratorX when you’re ready — this is an opt-in nudge, not a live session alert."
    )
    return {"subject": subject, "body": body, "title": subject}


def deliver_enthusiast_nudges(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Fan out opt-in enthusiast nudges (inbox + email prefs)."""
    ts = time.time() if now is None else float(now)
    week_bucket = int(ts // (7 * 86400))
    recent = recently_watched_context(db, limit=3, now=ts)
    pick = pick_nudge_title(db, recent=recent)
    if pick is None:
        return {"delivered": 0, "emailed": 0, "skipped": "no_title"}

    content = build_nudge_copy(db, pick=pick, recent=recent)
    delivered = 0
    emailed = 0
    considered = 0
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
        # Patch title field on notification uses subject; keep media title in payload.
        if result.get("notification"):
            delivered += 1
        if result.get("emailed"):
            emailed += 1
    return {
        "delivered": delivered,
        "emailed": emailed,
        "considered": considered,
        "pick": pick.get("title"),
        "recent_count": len(recent),
    }
