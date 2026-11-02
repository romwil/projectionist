"""Youth curator-memory policy: off unless the owner opts in."""

from __future__ import annotations

from typing import Any

YOUTH_MEMORY_OFF_ERROR = (
    "Curator memory is off for Youth accounts in this household, so nothing was saved."
)


def youth_memory_enabled(settings: Any) -> bool:
    return bool(getattr(getattr(settings, "youth", None), "memory_enabled", False))


def curator_memory_paused(settings: Any, *, is_youth: bool) -> bool:
    """True when the curator must neither read nor write this account's memory."""
    return bool(is_youth) and not youth_memory_enabled(settings)
