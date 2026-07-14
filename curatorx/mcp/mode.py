"""MCP trust-mode resolution (privacy vs full)."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Literal, Optional, Tuple

from curatorx.privacy.schema import Audience

McpMode = Literal["privacy", "full"]

logger = logging.getLogger(__name__)

_mcp_mode: ContextVar[McpMode] = ContextVar("curatorx_mcp_mode", default="privacy")


def get_mcp_mode() -> McpMode:
    return _mcp_mode.get()


def set_mcp_mode(mode: McpMode) -> None:
    _mcp_mode.set("full" if mode == "full" else "privacy")


def audience_for_mode(mode: Optional[McpMode] = None) -> Audience:
    resolved = mode or get_mcp_mode()
    return "mcp_full" if resolved == "full" else "privacy"


def privacy_api_key() -> str:
    return (os.environ.get("CURATORX_MCP_API_KEY") or "").strip()


def full_api_key() -> str:
    return (os.environ.get("CURATORX_MCP_FULL_API_KEY") or "").strip()


def full_mode_allowed() -> bool:
    """Full mode requires a distinct, non-empty full key (never equal to privacy key)."""
    full = full_api_key()
    privacy = privacy_api_key()
    if not full:
        return False
    if privacy and full == privacy:
        return False
    return True


def resolve_http_mcp_auth(provided: str) -> Tuple[Optional[McpMode], Optional[str], int]:
    """Map a presented key to a mode.

    Returns (mode, error_detail, http_status). mode is None on failure.
    """
    privacy = privacy_api_key()
    full = full_api_key()
    if not privacy and not full:
        return None, (
            "MCP HTTP transport disabled. Set CURATORX_MCP_API_KEY "
            "and/or CURATORX_MCP_FULL_API_KEY to enable /mcp."
        ), 503
    if not provided:
        return None, "Invalid MCP API key", 401

    # Prefer exact full-key match first when both configured and distinct.
    if full and provided == full:
        if full_mode_allowed():
            return "full", None, 200
        # Keys collide / misconfigured — fall through to privacy if it matches.
        if privacy and provided == privacy:
            return "privacy", None, 200
        return None, (
            "Full MCP mode refused: CURATORX_MCP_FULL_API_KEY must differ "
            "from CURATORX_MCP_API_KEY."
        ), 503

    if privacy and provided == privacy:
        return "privacy", None, 200

    # Only full key configured.
    if full and not privacy and provided == full:
        if not full_mode_allowed():
            return None, "Full MCP mode misconfigured", 503
        return "full", None, 200

    return None, "Invalid MCP API key", 401


def resolve_stdio_mcp_mode() -> McpMode:
    """Stdio: CURATORX_MCP_MODE=privacy|full; full requires FULL key present and distinct."""
    raw = (os.environ.get("CURATORX_MCP_MODE") or "privacy").strip().lower()
    if raw == "full":
        if not full_mode_allowed():
            logger.warning(
                "CURATORX_MCP_MODE=full refused: set a distinct CURATORX_MCP_FULL_API_KEY; "
                "falling back to privacy"
            )
            return "privacy"
        return "full"
    return "privacy"
