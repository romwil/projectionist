"""Notification platform package."""

from __future__ import annotations

from curatorx.notifications.service import (
    deliver_notification,
    fan_out_notifications,
    resolve_notification_email,
    user_wants_channel,
)
from curatorx.notifications.nudges import (
    deliver_enthusiast_nudges,
    recently_watched_context,
)

__all__ = [
    "deliver_notification",
    "fan_out_notifications",
    "resolve_notification_email",
    "user_wants_channel",
    "deliver_enthusiast_nudges",
    "recently_watched_context",
]
