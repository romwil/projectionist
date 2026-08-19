"""MCP trust-mode resolution (privacy vs full)."""

from __future__ import annotations

import hmac
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Literal, Optional, Tuple

from projectionist.privacy.schema import Audience

McpMode = Literal["privacy", "full"]

logger = logging.getLogger(__name__)


def _secret_eq(a: str, b: str) -> bool:
    """Constant-time equality for API-key comparison (review finding M11)."""
    if not a or not b:
        return False
    left = a.encode("utf-8")
    right = b.encode("utf-8")
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


_mcp_mode: ContextVar[McpMode] = ContextVar("curatorx_mcp_mode", default="privacy")


def get_mcp_mode() -> McpMode:
    return _mcp_mode.get()


def set_mcp_mode(mode: McpMode) -> None:
    _mcp_mode.set("full" if mode == "full" else "privacy")


def audience_for_mode(mode: Optional[McpMode] = None) -> Audience:
    resolved = mode or get_mcp_mode()
    return "mcp_full" if resolved == "full" else "privacy"


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def privacy_api_key() -> str:
    """Privacy-mode key from settings.json (preferred) or PROJECTIONIST_MCP_API_KEY."""
    from projectionist.config_store import load_merged_settings

    return str(load_merged_settings(_data_dir()).mcp_api_key or "").strip()


def full_api_key() -> str:
    """Full-mode key from settings.json (preferred) or PROJECTIONIST_MCP_FULL_API_KEY."""
    from projectionist.config_store import load_merged_settings

    return str(load_merged_settings(_data_dir()).mcp_full_api_key or "").strip()


def full_mode_allowed() -> bool:
    """Full mode requires a distinct, non-empty full key (never equal to privacy key)."""
    full = full_api_key()
    privacy = privacy_api_key()
    if not full:
        return False
    if privacy and _secret_eq(full, privacy):
        return False
    return True


def full_confirm_scope_enabled() -> bool:
    """True when the full key is scoped for active curation (self-confirm).

    Resolved from the ``mcp_full_confirm_enabled`` setting (chosen at key
    creation) or ``PROJECTIONIST_MCP_FULL_CONFIRM`` /
    ``CURATORX_MCP_FULL_CONFIRM`` for stdio / Unraid CA.
    """
    from projectionist.config_store import load_merged_settings
    from projectionist.envcompat import env_bool

    if bool(getattr(load_merged_settings(_data_dir()), "mcp_full_confirm_enabled", False)):
        return True
    flag = env_bool("PROJECTIONIST_MCP_FULL_CONFIRM")
    return bool(flag)


def full_confirm_allowed() -> bool:
    """True only when full mode is available *and* granted the confirm scope."""
    return full_mode_allowed() and full_confirm_scope_enabled()


_HTTP_UNAUTHORIZED: Tuple[Optional[McpMode], Optional[str], int] = (
    None,
    "Unauthorized",
    401,
)


def resolve_http_mcp_auth(provided: str) -> Tuple[Optional[McpMode], Optional[str], int]:
    """Map a presented key to a mode.

    Returns (mode, error_detail, http_status). mode is None on failure.
    Unauthenticated and disabled HTTP MCP always fail closed as generic 401 —
    never 503, and never name environment variables.
    """
    privacy = privacy_api_key()
    full = full_api_key()
    if not privacy and not full:
        return _HTTP_UNAUTHORIZED
    if not provided:
        return _HTTP_UNAUTHORIZED

    # Prefer exact full-key match first when both configured and distinct.
    if full and _secret_eq(provided, full):
        if full_mode_allowed():
            return "full", None, 200
        # Keys collide / misconfigured — fall through to privacy if it matches.
        if privacy and _secret_eq(provided, privacy):
            return "privacy", None, 200
        return _HTTP_UNAUTHORIZED

    if privacy and _secret_eq(provided, privacy):
        return "privacy", None, 200

    # Only full key configured.
    if full and not privacy and _secret_eq(provided, full):
        if not full_mode_allowed():
            return _HTTP_UNAUTHORIZED
        return "full", None, 200

    return _HTTP_UNAUTHORIZED


def resolve_stdio_mcp_mode() -> McpMode:
    """Stdio: PROJECTIONIST_MCP_MODE=privacy|full (CURATORX_MCP_MODE still accepted)."""
    from projectionist.envcompat import branded_env

    raw = (branded_env("MCP_MODE") or "privacy").strip().lower()
    if raw == "full":
        if not full_mode_allowed():
            logger.warning(
                "PROJECTIONIST_MCP_MODE=full refused: set a distinct "
                "PROJECTIONIST_MCP_FULL_API_KEY; falling back to privacy"
            )
            return "privacy"
        return "full"
    return "privacy"
