"""Owner gift queue — persist + deliver through the nudge/newsletter transport."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database

GIFT_QUEUE_CONFIG_KEY = "house_gift_queue"
MAX_WHY_WORDS = 24
MAX_QUEUE = 80


def _load_queue(db: Database) -> List[Dict[str, Any]]:
    raw = db.get_config(GIFT_QUEUE_CONFIG_KEY) if hasattr(db, "get_config") else None
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for row in items:
        if isinstance(row, dict) and row.get("id"):
            cleaned.append(row)
    return cleaned


def _save_queue(db: Database, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    db.set_config(GIFT_QUEUE_CONFIG_KEY, json.dumps({"items": items}, separators=(",", ":")))
    return items


def _clean_why(why: Optional[str]) -> str:
    words = [part for part in str(why or "").strip().split() if part]
    if not words:
        return "A title from the house, chosen for you."
    return " ".join(words[:MAX_WHY_WORDS])


def list_gifts(db: Database) -> Dict[str, Any]:
    items = _load_queue(db)
    pending = [row for row in items if not row.get("delivered_at")]
    delivered = [row for row in items if row.get("delivered_at")]
    return {
        "items": items,
        "pending": pending,
        "delivered": delivered,
        "total": len(items),
        "pending_count": len(pending),
    }


def enqueue_gift(
    db: Database,
    *,
    user_id: str,
    library_item_id: int,
    why: Optional[str] = None,
    scheduled_for: Optional[float] = None,
    created_by: Optional[str] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Queue one gift. Does not send — confirm-before-fleet."""
    ts = time.time() if now is None else float(now)
    member_id = str(user_id or "").strip()
    if not member_id:
        raise ValueError("A household member is required")
    user = db.get_user(member_id) if hasattr(db, "get_user") else None
    if user is None:
        raise ValueError("Household member not found")
    try:
        member_name = str(user["display_name"] or "Member")
    except (KeyError, TypeError, IndexError):
        member_name = "Member"
    item_id = int(library_item_id)
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT id, title, year, media_type, tmdb_id, tvdb_id, rating_key, poster_url
            FROM library_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    if row is None:
        raise ValueError("Library title not found")

    items = _load_queue(db)
    if len([row for row in items if not row.get("delivered_at")]) >= MAX_QUEUE:
        raise ValueError("Gift queue is full — deliver or remove a gift first")

    gift = {
        "id": f"gift_{uuid.uuid4().hex[:12]}",
        "user_id": member_id,
        "member_name": member_name,
        "library_item_id": item_id,
        "title": str(row["title"] or "Untitled"),
        "year": int(row["year"]) if row["year"] is not None else None,
        "media_type": str(row["media_type"] or "movie"),
        "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
        "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
        "rating_key": str(row["rating_key"]) if row["rating_key"] else None,
        "poster_url": str(row["poster_url"]) if row["poster_url"] else None,
        "why": _clean_why(why),
        "scheduled_for": float(scheduled_for) if scheduled_for is not None else None,
        "delivered_at": None,
        "created_at": ts,
        "created_by": str(created_by or "owner"),
    }
    items.append(gift)
    _save_queue(db, items)
    return gift


def remove_gift(db: Database, gift_id: str) -> bool:
    cleaned = str(gift_id or "").strip()
    items = _load_queue(db)
    kept = [row for row in items if str(row.get("id")) != cleaned]
    if len(kept) == len(items):
        return False
    _save_queue(db, kept)
    return True


def deliver_gift(
    db: Database,
    settings: Settings,
    gift_id: str,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Send one queued gift over the existing notification transport."""
    from projectionist.notifications.gifts import deliver_house_gift

    ts = time.time() if now is None else float(now)
    cleaned = str(gift_id or "").strip()
    items = _load_queue(db)
    target = None
    for row in items:
        if str(row.get("id")) == cleaned:
            target = row
            break
    if target is None:
        raise ValueError("Gift not found")
    if target.get("delivered_at"):
        return {"ok": True, "already_delivered": True, "gift": target}

    result = deliver_house_gift(db, settings, gift=target)
    target["delivered_at"] = ts
    target["delivery"] = {
        "inbox": bool(result.get("notification")),
        "emailed": bool(result.get("emailed")),
    }
    _save_queue(db, items)
    return {"ok": True, "already_delivered": False, "gift": target, **result}


def deliver_due_gifts(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Scheduler entry: deliver queued gifts whose time has come. Never a fleet blast."""
    ts = time.time() if now is None else float(now)
    delivered = 0
    emailed = 0
    skipped = 0
    errors: List[str] = []
    for row in list(_load_queue(db)):
        if row.get("delivered_at"):
            continue
        scheduled = row.get("scheduled_for")
        if scheduled is not None and float(scheduled) > ts:
            skipped += 1
            continue
        try:
            result = deliver_gift(db, settings, str(row["id"]), now=ts)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if result.get("notification") or result.get("gift", {}).get("delivery", {}).get("inbox"):
            delivered += 1
        if result.get("emailed") or result.get("gift", {}).get("delivery", {}).get("emailed"):
            emailed += 1
    return {
        "status": "completed",
        "delivered": delivered,
        "emailed": emailed,
        "skipped_future": skipped,
        "errors": errors,
    }
