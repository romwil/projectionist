"""Library API audience sanitization (members → public schema)."""

from __future__ import annotations

from typing import Any

from curatorx.config_store import Settings
from curatorx.privacy import sanitize


def library_audience(settings: Settings, user: Any) -> str:
    """Members get public schema when multi-user is on; owners/single-user keep internal."""
    if settings.features.multi_user_enabled and getattr(user, "role", "owner") != "owner":
        return "member"
    return "owner"


def sanitize_library_payload(payload: Any, *, settings: Settings, user: Any) -> Any:
    return sanitize(
        payload,
        audience=library_audience(settings, user),  # type: ignore[arg-type]
        settings=settings,
    )
