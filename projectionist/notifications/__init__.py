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
from projectionist.notifications.gifts import deliver_house_gift
from projectionist.notifications.whisper import (
    deliver_member_whispers,
    format_whisper_why,
)

__all__ = [
    "deliver_notification",
    "fan_out_notifications",
    "notification_channel_offerings",
    "resolve_notification_email",
    "user_wants_channel",
    "deliver_enthusiast_nudges",
    "recently_watched_context",
    "deliver_house_gift",
    "deliver_member_whispers",
    "format_whisper_why",
]
