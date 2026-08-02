"""Soft inbox nudges when Live Channels becomes ready.

Uses existing ``nudge`` kind + ``nudge_opt_in``. Deduped via ``related_id`` so
each household only sees one “ready” nudge per enable cycle.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.service import deliver_notification

logger = logging.getLogger(__name__)

RELATED_ID = "live-channels-ready"
MAX_RECIPIENTS = 40


def maybe_deliver_live_channels_ready_nudge(
    db: Database,
    settings: Settings,
    *,
    ready: bool,
    channel_count: int = 0,
) -> Dict[str, Any]:
    """Fan out a one-shot ready nudge when Live Channels is on and Tunarr has channels.

    Safe to call frequently — no-ops when not ready, flag off, or already delivered.
    """
    features = getattr(settings, "features", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))
    if not enabled or not ready:
        return {"delivered": 0, "skipped": "not_ready"}

    count_label = f"{int(channel_count)} channel{'s' if int(channel_count) != 1 else ''}"
    title = "Live Channels ready"
    body = (
        f"Your household stations are ready ({count_label}). "
        "Open Live in Projectionist to browse what’s on now."
    )
    payload = {
        "live_channels": True,
        "channel_count": int(channel_count),
        "cta": "/live",
    }

    delivered = 0
    considered = 0
    try:
        users = db.list_users(limit=500)
    except Exception:  # noqa: BLE001
        logger.debug("Could not list users for Live Channels ready nudge", exc_info=True)
        return {"delivered": 0, "skipped": "list_users_failed"}

    for user in users:
        if considered >= MAX_RECIPIENTS:
            break
        if user.get("disabled"):
            continue
        if not user.get("nudge_opt_in"):
            continue
        role = str(user.get("role") or "member").lower()
        if role == "guest":
            continue
        considered += 1
        user_id = str(user["id"])
        try:
            existing = db.find_notification_by_related(
                user_id, kind="nudge", related_id=RELATED_ID
            )
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            continue
        try:
            result = deliver_notification(
                db,
                settings,
                user_id=user_id,
                kind="nudge",
                title=title,
                body=body,
                payload=payload,
                related_id=RELATED_ID,
                email_subject=title,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Live Channels ready nudge failed for %s", user_id, exc_info=True)
            continue
        if result.get("notification"):
            delivered += 1
    return {"delivered": delivered, "considered": considered, "skipped": ""}


def reset_live_channels_ready_nudge(db: Database) -> Dict[str, Any]:
    """Clear ready-nudge dedupe rows so a disable→re-enable cycle can nudge again."""
    try:
        deleted = db.delete_notifications_by_related(kind="nudge", related_id=RELATED_ID)
    except Exception:  # noqa: BLE001
        logger.debug("Could not reset Live Channels ready nudge", exc_info=True)
        return {"deleted": 0, "ok": False}
    return {"deleted": int(deleted or 0), "ok": True}
