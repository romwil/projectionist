"""Named-member whisper inbox — a 12-word why, not Good News, not a grab ping."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.good_news import persona_from_db
from projectionist.notifications.recommendation_reasons import pick_linked_unwatched
from projectionist.notifications.service import deliver_notification

logger = logging.getLogger(__name__)

WHISPER_KIND = "nudge"
WHY_WORD_LIMIT = 12
WEEK_SECONDS = 7 * 86400
_FORBIDDEN = ("download complete", "grabbed", "nzb", "torrent complete")

_FALLBACK_WHYS = {
    "warm": "{name}, an unwatched title that still belongs on your night.",
    "direct": "{name}, one unwatched title worth opening when you are ready.",
    "analytical": "{name}, an unwatched title that still fits your shelf.",
    "balanced": "{name}, a quiet pick waiting on your shelf tonight.",
}


def _band_for_preset(preset_id: Optional[str]) -> str:
    key = str(preset_id or "").strip().lower()
    if key in {"classic-curator", "midnight-host"}:
        return "warm"
    if key in {"archivist", "critic-scholar"}:
        return "analytical"
    if key in {"scout"}:
        return "direct"
    return "balanced"


def member_display_name(user: Mapping[str, Any]) -> str:
    for key in ("preferred_name", "display_name"):
        value = str(user.get(key) or "").strip()
        if value:
            return value
    return "You"


def whisper_week_bucket(now: Optional[float] = None) -> int:
    ts = time.time() if now is None else float(now)
    return int(ts) - (int(ts) % WEEK_SECONDS)


def whisper_related_id(user_id: str, *, now: Optional[float] = None) -> str:
    return f"whisper-{whisper_week_bucket(now)}-{user_id}"


def clip_why(text: str, *, limit: int = WHY_WORD_LIMIT) -> str:
    words = [part for part in str(text or "").split() if part]
    if not words:
        return ""
    return " ".join(words[: max(1, int(limit))])


def word_count(text: str) -> int:
    return len([part for part in str(text or "").split() if part])


def _scrub_forbidden(why: str, *, member_name: str) -> str:
    lowered = why.lower()
    if any(banned in lowered for banned in _FORBIDDEN):
        return clip_why(f"{member_name}, a quiet pick waiting on your shelf tonight.")
    return why


def format_whisper_why(
    *,
    member_name: str,
    title: str = "",
    seed_title: Optional[str] = None,
    cluster: Optional[str] = None,
    preset_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> str:
    """Named-member why. A specific link is stored whole; a watch alone is not.

    The 12-word clip stays on the whisper page reader. The stored sentence is
    complete so the household inbox does not cut it mid-phrase.
    """
    del title, seed_title, cluster
    name = str(member_name or "").strip() or "You"
    specific = " ".join(str(reason or "").split())
    if specific:
        if specific[-1] not in ".!?":
            specific += "."
        return _scrub_forbidden(f"{name}, {specific}", member_name=name)
    # Citing a recent title or a shelf tag without a named link is the old bug.
    band = _band_for_preset(preset_id)
    raw = _FALLBACK_WHYS[band].format(name=name)
    return _scrub_forbidden(clip_why(raw), member_name=name)


def is_whisper_row(row: Mapping[str, Any]) -> bool:
    payload = row.get("payload") if isinstance(row, Mapping) else None
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("whisper"))


def _eligible_member(user: Mapping[str, Any]) -> bool:
    if user.get("disabled"):
        return False
    if user.get("is_youth"):
        return False
    role = str(user.get("role") or "member").strip().lower()
    return role in {"owner", "member"}


def pick_whisper_title(
    db: Database,
    *,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Pick one unwatched title with a named link to something already watched.

    A taste tag, a shared genre, or the highest-rated shelf title is not a pick.
    ``user_id`` stays in the signature for callers; the link is household graph.
    """
    del user_id
    return pick_linked_unwatched(db)


def serialize_whisper(row: Mapping[str, Any]) -> Dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    why = str(payload.get("why") or row.get("body") or "").strip()
    return {
        "id": row.get("id"),
        "kind": "whisper",
        "title": row.get("title"),
        "why": clip_why(why),
        "member_name": payload.get("member_name"),
        "year": row.get("year"),
        "media_type": row.get("media_type"),
        "tmdb_id": row.get("tmdb_id"),
        "tvdb_id": row.get("tvdb_id"),
        "rating_key": row.get("rating_key"),
        "poster_url": row.get("poster_url"),
        "created_at": row.get("created_at"),
        "seen_at": row.get("seen_at"),
        "related_id": row.get("related_id"),
    }


def list_whispers_for_user(
    db: Database,
    user_id: str,
    *,
    unread_only: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    rows = db.list_notifications_for_user(
        user_id,
        unread_only=unread_only,
        kinds=[WHISPER_KIND],
        limit=min(max(1, int(limit)), 50),
    )
    return [serialize_whisper(row) for row in rows if is_whisper_row(row)]


def mark_whispers_seen(
    db: Database,
    user_id: str,
    *,
    notification_ids: Optional[Sequence[str]] = None,
    all_unread: bool = False,
) -> int:
    """Mark only whisper rows seen — never the rest of the household inbox."""
    if all_unread:
        ids = [str(row["id"]) for row in list_whispers_for_user(db, user_id, unread_only=True, limit=50)]
    else:
        wanted = {str(item).strip() for item in (notification_ids or []) if str(item).strip()}
        if not wanted:
            return 0
        known = {
            str(row["id"])
            for row in list_whispers_for_user(db, user_id, unread_only=False, limit=50)
        }
        ids = [item for item in wanted if item in known]
    if not ids:
        return 0
    return db.mark_notifications_seen(user_id, notification_ids=ids)


def _deliver_one(
    db: Database,
    settings: Settings,
    *,
    user: Mapping[str, Any],
    pick: Dict[str, Any],
    now: Optional[float] = None,
) -> Dict[str, Any]:
    user_id = str(user["id"])
    member_name = member_display_name(user)
    curator_name, preset_id = persona_from_db(db)
    del curator_name
    why = format_whisper_why(
        member_name=member_name,
        title=str(pick.get("title") or ""),
        seed_title=pick.get("seed_title"),
        cluster=pick.get("cluster"),
        preset_id=preset_id,
        reason=pick.get("why"),
    )
    related = whisper_related_id(user_id, now=now)
    existing = db.find_notification_by_related(user_id, kind=WHISPER_KIND, related_id=related)
    if existing and is_whisper_row(existing):
        return {"notification": existing, "created": False}
    result = deliver_notification(
        db,
        settings,
        user_id=user_id,
        kind=WHISPER_KIND,
        title=str(pick.get("title") or "A title").strip() or "A title",
        body=why,
        payload={
            "whisper": True,
            "why": why,
            "member_name": member_name,
            "cluster": pick.get("cluster"),
            "seed_title": pick.get("seed_title"),
        },
        media_type=pick.get("media_type"),
        tmdb_id=pick.get("tmdb_id"),
        tvdb_id=pick.get("tvdb_id"),
        rating_key=pick.get("rating_key"),
        year=pick.get("year"),
        poster_url=pick.get("poster_url"),
        related_id=related,
        email_subject=f"{member_name} — a whisper about {pick.get('title') or 'a title'}",
        force_inbox=True,
    )
    return {"notification": result.get("notification"), "created": bool(result.get("notification"))}


def ensure_member_whisper(
    db: Database,
    settings: Settings,
    user: Mapping[str, Any],
    *,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Create this week's whisper for a named member if it is not already there."""
    if not _eligible_member(user):
        return None
    user_id = str(user["id"])
    related = whisper_related_id(user_id, now=now)
    existing = db.find_notification_by_related(user_id, kind=WHISPER_KIND, related_id=related)
    if existing and is_whisper_row(existing):
        return serialize_whisper(existing)
    pick = pick_whisper_title(db, user_id=user_id)
    if pick is None:
        return None
    delivered = _deliver_one(db, settings, user=user, pick=pick, now=now)
    row = delivered.get("notification")
    return serialize_whisper(row) if row else None


def deliver_member_whispers(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Fan out one weekly whisper per named household member (not owner-only)."""
    created = 0
    skipped = 0
    considered = 0
    for user in db.list_users(limit=500):
        if not _eligible_member(user):
            skipped += 1
            continue
        considered += 1
        user_id = str(user["id"])
        related = whisper_related_id(user_id, now=now)
        existing = db.find_notification_by_related(user_id, kind=WHISPER_KIND, related_id=related)
        if existing and is_whisper_row(existing):
            continue
        pick = pick_whisper_title(db, user_id=user_id)
        if pick is None:
            continue
        delivered = _deliver_one(db, settings, user=user, pick=pick, now=now)
        if delivered.get("created"):
            created += 1
    return {"created": created, "considered": considered, "skipped": skipped}


def inbox_payload_for_user(
    db: Database,
    settings: Settings,
    user: Mapping[str, Any],
    *,
    unread_only: bool = False,
    limit: int = 20,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Member-scoped whisper inbox. Lazy-creates this week's row when the shelf has a pick."""
    ensure_member_whisper(db, settings, user, now=now)
    items = list_whispers_for_user(
        db, str(user["id"]), unread_only=unread_only, limit=limit
    )
    unread = [
        row
        for row in list_whispers_for_user(db, str(user["id"]), unread_only=True, limit=50)
    ]
    return {
        "items": items,
        "count": len(items),
        "unread_count": len(unread),
        "member_name": member_display_name(user),
    }
