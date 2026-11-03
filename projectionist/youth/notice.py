"""Member notice when an owner turns Youth mode on for an existing account.

The notice describes the change only. It never includes memory contents.
"""

from __future__ import annotations

import logging
from typing import Any

from projectionist.youth.chat_route import CHAT_ROUTE_LOCAL, resolve_youth_chat_route
from projectionist.youth.memory_policy import youth_memory_enabled
from projectionist.youth.rating_gate import resolve_youth_max_rating

logger = logging.getLogger(__name__)

YOUTH_ON_TITLE = "Youth mode is on for your account"


def youth_on_notice_body(settings: Any, *, owner_name: str) -> str:
    rating = resolve_youth_max_rating(settings)
    who = owner_name.strip() or "The household owner"
    parts = [
        f"{who} turned on Youth mode for your account.",
        f"You'll now see titles rated {rating} or lower, and titles without a rating are hidden.",
        "What the curator remembered about you before this change stays private. "
        "Youth mode doesn't show it to anyone.",
    ]
    if youth_memory_enabled(settings):
        parts.append(
            "From now on the curator may remember things from your chats, and the "
            "household owner can read those new notes."
        )
    else:
        parts.append("Curator memory is off for Youth accounts here, so nothing new is remembered.")
    route = resolve_youth_chat_route(settings)
    if route.settings is not None and route.route == CHAT_ROUTE_LOCAL:
        parts.append("Chat uses a model that runs at home, not a cloud service.")
    else:
        parts.append("Chat with the curator is off for Youth accounts, so nothing is sent to an AI model.")
    parts.append("If this looks wrong, talk to the person who runs this server.")
    return " ".join(parts)


def notify_youth_mode_on(db: Any, settings: Any, *, target_id: str, actor_id: str) -> bool:
    """Deliver the inbox notice (and email/Apprise if the member opted in). Never raises."""
    from projectionist.notifications.service import deliver_notification

    try:
        owner = db.get_user(actor_id)
        owner_name = ""
        if owner is not None:
            keys = set(owner.keys()) if hasattr(owner, "keys") else set()
            if "preferred_name" in keys and owner["preferred_name"]:
                owner_name = str(owner["preferred_name"])
            else:
                owner_name = str(owner["display_name"] or "")
        result = deliver_notification(
            db,
            settings,
            user_id=target_id,
            kind="account",
            title=YOUTH_ON_TITLE,
            body=youth_on_notice_body(settings, owner_name=owner_name),
            payload={"event": "youth_mode_on", "path": "/settings/profile"},
            from_user_id=actor_id,
            force_inbox=True,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Youth mode notice could not be delivered", exc_info=True)
        return False
    return bool(result.get("notification"))
