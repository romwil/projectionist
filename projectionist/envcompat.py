"""Branded environment helpers (PROJECTIONIST_* only)."""

from __future__ import annotations

import os
from typing import Optional

CANONICAL_PREFIX = "PROJECTIONIST_"


def resolve_env(env_name: str) -> Optional[str]:
    """Return a non-empty env value, or None when unset/blank."""
    raw = os.environ.get(env_name)
    if raw is None or str(raw).strip() == "":
        return None
    return raw


def branded_env(suffix: str) -> Optional[str]:
    """Resolve ``PROJECTIONIST_{suffix}``."""
    return resolve_env(f"{CANONICAL_PREFIX}{suffix}")


def env_bool(name: str) -> Optional[bool]:
    """Return True/False when a branded (or plain) env is set, else None."""
    raw = resolve_env(name) if name.startswith(CANONICAL_PREFIX) else os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def skip_dotenv() -> bool:
    """True when PROJECTIONIST_SKIP_DOTENV is ``1``."""
    return (branded_env("SKIP_DOTENV") or "").strip() == "1"
