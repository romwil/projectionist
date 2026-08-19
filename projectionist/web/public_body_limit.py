"""ASGI clamp for unauthenticated JSON bodies — before Starlette parses JSON."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable

PUBLIC_BODY_CLAMP_PATHS = frozenset(
    {
        "/api/auth/local/login",
        "/api/auth/plex",
        "/api/auth/plex/pin",
        "/api/access-requests",
        "/api/invites/redeem/local",
    }
)
PUBLIC_BODY_MAX_BYTES = 64 * 1024
_PAYLOAD_TOO_LARGE = b'{"detail":"Payload too large"}'


class BodyTooLarge(Exception):
    """Request body exceeded the public handshake cap."""


def _header_map(headers: Iterable[tuple[bytes, bytes]]) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in headers}


async def _send_413(send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_PAYLOAD_TOO_LARGE)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _PAYLOAD_TOO_LARGE})


class PublicBodyLimitMiddleware:
    """Reject oversized POST bodies on the public handshake before JSON parse."""

    def __init__(self, app: Callable, *, max_bytes: int = PUBLIC_BODY_MAX_BYTES) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "")
        if method not in {"POST", "PUT", "PATCH"} or path not in PUBLIC_BODY_CLAMP_PATHS:
            await self.app(scope, receive, send)
            return

        headers = _header_map(scope.get("headers") or [])
        raw_len = headers.get(b"content-length")
        if raw_len:
            try:
                if int(raw_len) > self.max_bytes:
                    await _send_413(send)
                    return
            except ValueError:
                await _send_413(send)
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body") or b""
                received += len(chunk)
                if received > self.max_bytes:
                    raise BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await _send_413(send)
