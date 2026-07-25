"""Branded environment dual-read (PROJECTIONIST_* with CURATORX_* fallback).

During the ~2-release compatibility window, every ``PROJECTIONIST_*`` variable
also accepts the matching ``CURATORX_*`` name. Prefer the new prefix; when only
the legacy key supplies a value, log a deprecation warning once per key.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

CANONICAL_PREFIX = "PROJECTIONIST_"
LEGACY_PREFIX = "CURATORX_"

_warned_legacy: set[str] = set()


def legacy_twin(env_name: str) -> Optional[str]:
    """Return the CURATORX_* twin for a PROJECTIONIST_* name (or vice versa)."""
    if env_name.startswith(CANONICAL_PREFIX):
        return LEGACY_PREFIX + env_name[len(CANONICAL_PREFIX) :]
    if env_name.startswith(LEGACY_PREFIX):
        return CANONICAL_PREFIX + env_name[len(LEGACY_PREFIX) :]
    return None


def _warn_legacy(legacy: str, canonical: str) -> None:
    if legacy in _warned_legacy:
        return
    _warned_legacy.add(legacy)
    logger.warning(
        "Deprecated environment variable %s is set; prefer %s (compat window).",
        legacy,
        canonical,
    )


def resolve_env(env_name: str) -> Optional[str]:
    """Return a non-empty env value, preferring PROJECTIONIST_* over CURATORX_*.

    For unbranded names (no prefix), behaves like a non-empty ``os.environ.get``.
    """
    twin = legacy_twin(env_name)
    if twin is None:
        raw = os.environ.get(env_name)
        if raw is None or str(raw).strip() == "":
            return None
        return raw

    if env_name.startswith(CANONICAL_PREFIX):
        canonical, legacy = env_name, twin
    else:
        canonical, legacy = twin, env_name

    canonical_raw = os.environ.get(canonical)
    if canonical_raw is not None and str(canonical_raw).strip() != "":
        return canonical_raw

    legacy_raw = os.environ.get(legacy)
    if legacy_raw is not None and str(legacy_raw).strip() != "":
        _warn_legacy(legacy, canonical)
        return legacy_raw
    return None


def branded_env(suffix: str) -> Optional[str]:
    """Resolve ``PROJECTIONIST_{suffix}`` with ``CURATORX_{suffix}`` fallback."""
    return resolve_env(f"{CANONICAL_PREFIX}{suffix}")


def env_bool(name: str) -> Optional[bool]:
    """Return True/False when a branded (or plain) env is set, else None."""
    raw = resolve_env(name) if legacy_twin(name) else os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def skip_dotenv() -> bool:
    """True when PROJECTIONIST_SKIP_DOTENV / CURATORX_SKIP_DOTENV is ``1``."""
    return (branded_env("SKIP_DOTENV") or "").strip() == "1"


def reset_deprecation_warnings() -> None:
    """Test helper: allow legacy-key warnings to fire again."""
    _warned_legacy.clear()
