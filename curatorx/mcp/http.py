"""HTTP /mcp mount helpers (API-key gated Streamable HTTP)."""

from __future__ import annotations

import os
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class McpApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        expected = (os.environ.get("CURATORX_MCP_API_KEY") or "").strip()
        if not expected:
            return JSONResponse(
                {
                    "detail": (
                        "MCP HTTP transport disabled. Set CURATORX_MCP_API_KEY "
                        "to enable /mcp."
                    )
                },
                status_code=503,
            )
        provided = (
            request.headers.get("x-curatorx-mcp-key")
            or request.headers.get("authorization")
            or ""
        ).strip()
        if provided.lower().startswith("bearer "):
            provided = provided[7:].strip()
        if not provided or provided != expected:
            return JSONResponse({"detail": "Invalid MCP API key"}, status_code=401)
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
