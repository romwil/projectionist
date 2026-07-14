"""HTTP /mcp mount helpers (API-key gated Streamable HTTP, dual-mode)."""

from __future__ import annotations

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from curatorx.mcp.mode import resolve_http_mcp_auth, set_mcp_mode

logger = logging.getLogger(__name__)


class McpApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        provided = (
            request.headers.get("x-curatorx-mcp-key")
            or request.headers.get("authorization")
            or ""
        ).strip()
        if provided.lower().startswith("bearer "):
            provided = provided[7:].strip()

        mode, detail, status = resolve_http_mcp_auth(provided)
        if mode is None:
            return JSONResponse({"detail": detail}, status_code=status)

        set_mcp_mode(mode)
        # Log trust plane only — never the key material.
        logger.info("MCP HTTP auth ok mode=%s path=%s", mode, request.url.path)
        request.state.mcp_mode = mode
        return await call_next(request)


def mount_mcp_http(app, mcp_server) -> Optional[str]:
    """Mount Streamable HTTP MCP under /mcp when the optional mcp package is available."""
    try:
        asgi_app = mcp_server.streamable_http_app()
    except Exception:
        return None
    asgi_app.add_middleware(McpApiKeyMiddleware)
    app.mount("/mcp", asgi_app)
    return "/mcp"
