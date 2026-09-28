"""House gift copy + delivery over the existing inbox / mail transport."""

from __future__ import annotations

import logging
from typing import Any, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.service import deliver_notification

logger = logging.getLogger(__name__)


def _persona_voice(db: Database) -> str:
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
    if not chosen and personas and isinstance(personas[0], dict):
        chosen = personas[0]
    if not chosen:
        return "Your curator"
    return str(chosen.get("name") or "Your curator").strip() or "Your curator"


def build_gift_copy(db: Database, gift: Dict[str, Any]) -> Dict[str, str]:
    voice = _persona_voice(db)
    title = str(gift.get("title") or "this title")
    year = gift.get("year")
    label = f"{title} ({year})" if year else title
    why = str(gift.get("why") or "A title from the house, chosen for you.").strip()
    member = str(gift.get("member_name") or "you").strip() or "you"
    subject = f"A gift from the house — {label}"
    body = (
        f"{voice} here: this is a gift for {member}, not a download ping.\n"
        f"{label}. {why}\n"
        "Open it when the night is right. Nobody else was blasted."
    )
    return {"subject": subject, "body": body, "title": title}


def deliver_house_gift(
    db: Database,
    settings: Settings,
    *,
    gift: Dict[str, Any],
) -> Dict[str, Any]:
    """Deliver one owner-queued gift as a recommendation (inbox + optional mail)."""
    content = build_gift_copy(db, gift)
    related = f"house-gift-{gift.get('id')}"
    return deliver_notification(
        db,
        settings,
        user_id=str(gift["user_id"]),
        kind="recommendation",
        title=content["title"],
        body=content["body"],
        payload={
            "gift": True,
            "why": gift.get("why"),
            "source": "house_gift_queue",
        },
        media_type=gift.get("media_type"),
        tmdb_id=gift.get("tmdb_id"),
        tvdb_id=gift.get("tvdb_id"),
        rating_key=gift.get("rating_key"),
        year=gift.get("year"),
        poster_url=gift.get("poster_url"),
        related_id=related,
        email_subject=content["subject"],
        force_inbox=True,
    )
