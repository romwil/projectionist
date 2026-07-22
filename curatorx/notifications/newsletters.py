"""Weekly member newsletter + owner monthly curation digests."""

from __future__ import annotations

import logging
import time
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from curatorx.config_store import Settings
from curatorx.digest.service import build_weekly_digest
from curatorx.library.db import Database
from curatorx.library.feeds import feed_recently_added
from curatorx.notifications.service import deliver_notification

logger = logging.getLogger(__name__)


def _persona_voice_line(db: Database, *, for_guest: bool = False) -> str:
    """Short voice line from the default (or guest-oriented) persona."""
    try:
        personas = db.list_persona_templates()
    except Exception:  # noqa: BLE001
        personas = []
    default = None
    guest = None
    for persona in personas or []:
        if not isinstance(persona, dict):
            continue
        if persona.get("is_default"):
            default = persona
        name = str(persona.get("name") or "").lower()
        if "guest" in name or "host" in name or "concierge" in name:
            guest = persona
    chosen = guest if for_guest and guest else default or (personas[0] if personas else None)
    if not chosen:
        return "Your curator checked in on the collection this week."
    name = str(chosen.get("name") or "Your curator").strip()
    tagline = str(chosen.get("tagline") or chosen.get("description") or "").strip()
    if tagline:
        return f"{name} here — {tagline}"
    return f"{name} put together a few notes for you."


def _format_title_lines(titles: List[Dict[str, Any]], *, limit: int = 6) -> str:
    lines: List[str] = []
    for item in titles[:limit]:
        title = str(item.get("title") or "Untitled").strip()
        year = item.get("year")
        bit = f"{title} ({year})" if year else title
        lines.append(f"• {bit}")
    return "\n".join(lines)


def build_member_newsletter(
    db: Database,
    settings: Optional[Settings] = None,
    *,
    user: Dict[str, Any],
    now: Optional[float] = None,
) -> Dict[str, str]:
    """Build a personalized weekly newsletter subject + body for one member."""
    del settings
    digest = build_weekly_digest(db, now=now)
    preferred = str(user.get("preferred_name") or user.get("display_name") or "there").strip()
    role = str(user.get("role") or "member")
    for_guest = role == "guest"
    voice = _persona_voice_line(db, for_guest=for_guest)
    new_block = digest.get("new_this_week") or {}
    titles = list(new_block.get("titles") or [])
    count = int(new_block.get("count") or len(titles))
    title_lines = _format_title_lines(titles) or "• Quiet week — nothing new landed yet."
    subject = f"This week for you, {preferred}"
    body = (
        f"Hi {preferred},\n\n"
        f"{voice}\n\n"
        f"New in the library this week: {count} title{'s' if count != 1 else ''}.\n"
        f"{title_lines}\n\n"
        "Open CuratorX anytime to chat about what to watch next.\n"
    )
    return {"subject": subject, "body": body, "title": subject}


def deliver_weekly_newsletters(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
    user_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Fan out opt-in weekly newsletters (inbox + email prefs).

    When ``user_ids`` is provided, only those accounts are considered; otherwise
    every non-disabled user is eligible. Opt-in and channel prefs still apply —
    opted-out users are skipped (counted in ``skipped_opt_out``).
    """
    skipped_disabled = 0
    skipped_opt_out = 0
    skipped_missing = 0
    candidates: List[Dict[str, Any]] = []

    if user_ids is None:
        candidates = list(db.list_users(limit=500))
    else:
        seen: set[str] = set()
        for raw_id in user_ids:
            uid = str(raw_id or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            row = db.get_user(uid)
            if row is None:
                skipped_missing += 1
                continue
            candidates.append(db._row_to_user(row))

    delivered = 0
    emailed = 0
    targeted = 0
    for user in candidates:
        if user.get("disabled"):
            skipped_disabled += 1
            continue
        targeted += 1
        if not user.get("newsletter_opt_in"):
            skipped_opt_out += 1
            continue
        content = build_member_newsletter(db, settings, user=user, now=now)
        result = deliver_notification(
            db,
            settings,
            user_id=str(user["id"]),
            kind="digest",
            title=content["title"],
            body=content["body"],
            payload={"newsletter": "weekly"},
            related_id=f"weekly-{int((now or time.time()) // (7 * 86400))}",
            email_subject=content["subject"],
        )
        if result.get("notification"):
            delivered += 1
        if result.get("emailed"):
            emailed += 1
    return {
        "delivered": delivered,
        "emailed": emailed,
        "targeted": targeted,
        "skipped_opt_out": skipped_opt_out,
        "skipped_disabled": skipped_disabled,
        "skipped_missing": skipped_missing,
    }


def _month_bucket(now: Optional[float] = None) -> str:
    ts = time.time() if now is None else float(now)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def build_owner_monthly_curation(
    db: Database,
    settings: Optional[Settings] = None,
    *,
    now: Optional[float] = None,
) -> Dict[str, str]:
    """Owner monthly collection / curation update body."""
    del settings
    ts = time.time() if now is None else float(now)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    month_label = dt.strftime("%B %Y")
    days = monthrange(dt.year, dt.month)[1]
    try:
        recent = feed_recently_added(db, limit=12, days=min(days, 31))
    except Exception:  # noqa: BLE001
        recent = {"items": [], "total": 0}
    titles = [
        {
            "title": str(item.get("title") or "Untitled"),
            "year": item.get("year"),
        }
        for item in list(recent.get("items") or [])[:10]
    ]
    list_count = 0
    try:
        if hasattr(db, "list_curated_lists"):
            lists = db.list_curated_lists() or []
            list_count = len(lists)
    except Exception:  # noqa: BLE001
        list_count = 0
    title_lines = _format_title_lines(titles, limit=10) or "• No new arrivals logged this month."
    subject = f"Monthly collection update — {month_label}"
    body = (
        f"Here's your monthly curation pulse for {month_label}.\n\n"
        f"Curated lists on hand: {list_count}\n"
        f"Recent arrivals:\n{title_lines}\n\n"
        "Review collections, courses, and gaps in Admin when you're ready.\n"
    )
    return {"subject": subject, "body": body, "title": subject}


def deliver_owner_monthly_curation(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Deliver the monthly curation digest to owners."""
    owners = [u for u in db.list_users(limit=100) if u.get("role") == "owner" and not u.get("disabled")]
    if not owners:
        # Single-user / bootstrap: still try bootstrap owner via list
        owners = [u for u in db.list_users(limit=20) if not u.get("disabled")][:1]
    bucket = _month_bucket(now)
    delivered = 0
    emailed = 0
    content = build_owner_monthly_curation(db, settings, now=now)
    for owner in owners:
        result = deliver_notification(
            db,
            settings,
            user_id=str(owner["id"]),
            kind="digest",
            title=content["title"],
            body=content["body"],
            payload={"newsletter": "monthly-owner", "month": bucket},
            related_id=f"monthly-owner-{bucket}",
            email_subject=content["subject"],
        )
        if result.get("notification"):
            delivered += 1
        if result.get("emailed"):
            emailed += 1
    return {"delivered": delivered, "emailed": emailed, "month": bucket}
