"""Offline password checks for new and changed local passwords (SEC-019)."""

from __future__ import annotations

from pathlib import Path

SHORT_PASSWORD_DETAIL = "Password must be at least 8 characters"
COMMON_PASSWORD_DETAIL = "Choose a password that is not a common one."

_COMMON: frozenset[str] | None = None


class WeakPasswordError(ValueError):
    """A new password is on the bundled common-password list."""


def _common_passwords() -> frozenset[str]:
    global _COMMON
    if _COMMON is None:
        path = Path(__file__).with_name("common_passwords.txt")
        words: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            word = line.strip().casefold()
            if word and not word.startswith("#"):
                words.add(word)
        _COMMON = frozenset(words)
    return _COMMON


def is_common_password(password: str) -> bool:
    """True when the whole password is on the bundled list. Comparison is case-insensitive."""
    cleaned = str(password or "").strip().casefold()
    if not cleaned:
        return False
    return cleaned in _common_passwords()


def password_rejection(password: str) -> str | None:
    """Why a new or changed password is refused, or None when it can be stored."""
    if len(str(password or "")) < 8:
        return SHORT_PASSWORD_DETAIL
    if is_common_password(password):
        return COMMON_PASSWORD_DETAIL
    return None


def reject_common_password(password: str) -> None:
    """Raise when a new or changed password is on the bundled list."""
    reason = password_rejection(password)
    if reason:
        raise WeakPasswordError(reason)
