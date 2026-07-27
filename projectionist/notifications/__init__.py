"""Notification platform package."""

from __future__ import annotations

from projectionist.notifications.service import (
    deliver_notification,
    fan_out_notifications,
    notification_channel_offerings,
    resolve_notification_email,
    user_wants_channel,
)
from projectionist.notifications.nudges import (
    deliver_enthusiast_nudges,
    recently_watched_context,
)

__all__ = [
    "deliver_notification",
    "fan_out_notifications",
    "notification_channel_offerings",
    "resolve_notification_email",
    "user_wants_channel",
    "deliver_enthusiast_nudges",
    "recently_watched_context",
]
