"""HTTP /mcp mount helpers (API-key gated Streamable HTTP, dual-mode)."""

from __future__ import annotations

import logging
from typing import Mapping, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from projectionist.mcp.mode import resolve_http_mcp_auth, set_mcp_mode

logger = logging.getLogger(__name__)

_UNAUTHORIZED = {"detail": "Unauthorized"}


def extract_mcp_key(headers: Mapping[str, str]) -> str:
    """Read the MCP key from Projectionist, legacy CuratorX, or Bearer headers."""
    provided = (
        headers.get("x-projectionist-mcp-key")
        or headers.get("x-curatorx-mcp-key")
        or headers.get("authorization")
        or ""
    ).strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()
    return provided


def _unauthorized() -> JSONResponse:
    return JSONResponse(_UNAUTHORIZED, status_code=401)


class McpApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        mode, _detail, _status = resolve_http_mcp_auth(extract_mcp_key(request.headers))
        if mode is None:
            return _unauthorized()

        set_mcp_mode(mode)
        # Log trust plane only — never the key material.
        logger.info("MCP HTTP auth ok mode=%s path=%s", mode, request.url.path)
        request.state.mcp_mode = mode
        return await call_next(request)


class McpParentAuthMiddleware(BaseHTTPMiddleware):
    """Gate ``/mcp`` on the parent app so slash-redirect cannot run before auth."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path != "/mcp" and not path.startswith("/mcp/"):
            return await call_next(request)
        mode, _detail, _status = resolve_http_mcp_auth(extract_mcp_key(request.headers))
        if mode is None:
            return _unauthorized()
        set_mcp_mode(mode)
        request.state.mcp_mode = mode
        return await call_next(request)


def install_mcp_parent_auth(app) -> None:
    """Install parent-app MCP auth even when the Streamable HTTP extra is absent."""
    app.add_middleware(McpParentAuthMiddleware)


def mount_mcp_http(app, mcp_server) -> Optional[str]:
    """Mount Streamable HTTP MCP under /mcp when the optional mcp package is available."""
    try:
        asgi_app = mcp_server.streamable_http_app()
    except Exception:
        return None
    asgi_app.add_middleware(McpApiKeyMiddleware)
    app.mount("/mcp", asgi_app)
    return "/mcp"
