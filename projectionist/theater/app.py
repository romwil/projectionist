"""Minimal FastAPI app for lobby theater (dedicated port)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from projectionist.config_store import Settings, load_merged_settings
from projectionist.library.db import Database
from projectionist.theater import POSTER_CACHE_CONTROL, POSTER_RATE_LIMIT_PER_MINUTE
from projectionist.theater.hub import TheaterHub, get_theater_hub, init_theater_hub
from projectionist.theater.normalize import normalize_theater_feed, normalize_theater_settings, theater_host_port_hint
from projectionist.theater.poster import fetch_poster_bytes, poster_response
from projectionist.theater.poster_cache import get_poster_cache
from projectionist.web.ingress import (
    direct_peer,
    is_docker_nat_peer,
    is_tailscale_or_cgnat,
    parse_ip,
    peer_class_name,
)
from projectionist.web.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def theater_peer_allowed(request: Request) -> bool:
    """LAN / loopback / CGNAT / Docker-bridge only — never a visible public peer."""
    peer_host, _port = direct_peer(request)
    peer = parse_ip(peer_host)
    if peer is None:
        # TestClient / missing peer → treat as loopback LAN.
        if not peer_host or str(peer_host).strip().lower() in {"testclient", "localhost"}:
            return True
        return False
    if peer.is_loopback or peer.is_link_local:
        return True
    if is_tailscale_or_cgnat(peer):
        return True
    if is_docker_nat_peer(peer):
        return True
    if peer.is_private:
        return True
    return False


class TheaterLanGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not theater_peer_allowed(request):
            peer_host, _ = direct_peer(request)
            logger.info(
                "theater WAN reject peer_class=%s path=%s",
                peer_class_name(parse_ip(peer_host)),
                request.url.path,
            )
            return Response(
                content="Lobby theater is LAN-only.",
                status_code=403,
                media_type="text/plain",
            )
        return await call_next(request)


def create_theater_app(
    *,
    data_dir: Optional[Path] = None,
    db_factory: Optional[Callable[[], Database]] = None,
    settings_factory: Optional[Callable[[], Settings]] = None,
    hub: Optional[TheaterHub] = None,
) -> FastAPI:
    resolved_data_dir = Path(
        data_dir or os.environ.get("DATA_DIR") or "/config"
    ).expanduser()

    def _db() -> Database:
        if db_factory is not None:
            return db_factory()
        from projectionist.library.db import Database as Db
        from projectionist.web.jobs import _resolve_db_path

        return Db(_resolve_db_path(resolved_data_dir))

    def _settings() -> Settings:
        if settings_factory is not None:
            return settings_factory()
        return load_merged_settings(resolved_data_dir)

    try:
        theater_hub = hub or get_theater_hub()
    except RuntimeError:
        theater_hub = init_theater_hub(
            data_dir=resolved_data_dir,
            db_factory=_db,
            settings_factory=_settings,
        )
    theater_hub.start()

    app = FastAPI(title="Projectionist Lobby Theater", docs_url=None, redoc_url=None)
    app.add_middleware(TheaterLanGateMiddleware)
    app.state.theater_hub = theater_hub
    app.state.data_dir = resolved_data_dir

    @app.get("/api/health")
    def theater_health() -> dict:
        settings = _settings()
        theater = normalize_theater_settings(getattr(settings, "theater", None))
        cache = get_poster_cache(resolved_data_dir)
        return {
            "status": "ok",
            "service": "theater",
            "enabled": bool(theater.enabled),
            "subscribers": theater_hub.subscriber_count,
            "port_hint": theater_host_port_hint(),
            "watcher_interval_s": theater_hub.next_poll_seconds,
            "watcher_degraded": theater_hub.degraded,
            "poster_cache_hits": cache.hits,
            "poster_cache_misses": cache.misses,
            "poster_cache_negative_hits": cache.negative_hits,
        }

    @app.get("/api/theater/events")
    async def theater_events(
        request: Request,
        feed: Optional[str] = Query(None),
    ) -> StreamingResponse:
        del request
        idle_feed = normalize_theater_feed(feed)
        settings = _settings()
        theater = normalize_theater_settings(getattr(settings, "theater", None))
        if not theater.enabled:
            async def disabled_stream():
                import json

                payload = json.dumps(
                    {
                        "enabled": False,
                        "mode": "empty",
                        "watching": False,
                        "sessions": [],
                        "available": [],
                        "header_label": "DISABLED",
                        "header_mode": "static",
                        "orientation": theater.orientation,
                        "multi_mode": theater.multi_mode,
                        "idle_mode": theater.idle_mode,
                        "rotate_seconds": theater.rotate_seconds,
                        "feed": idle_feed,
                    },
                    separators=(",", ":"),
                )
                yield f"event: hydrate\ndata: {payload}\n\n"
                while True:
                    import asyncio

                    await asyncio.sleep(15)
                    yield ": ping\n\n"
                    yield "event: ping\ndata: {}\n\n"

            return StreamingResponse(
                disabled_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        return StreamingResponse(
            theater_hub.subscribe(feed=idle_feed),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/theater/poster")
    async def theater_poster(
        request: Request,
        rk: str = Query(..., min_length=1, max_length=64),
    ) -> Response:
        enforce_rate_limit(
            request,
            bucket="theater_poster",
            limit=POSTER_RATE_LIMIT_PER_MINUTE,
            window_seconds=60.0,
        )
        body, content_type, etag = await fetch_poster_bytes(
            _db(),
            _settings(),
            rating_key=rk,
            data_dir=resolved_data_dir,
        )
        if_none_match = (request.headers.get("if-none-match") or "").strip()
        if etag and if_none_match and if_none_match == etag:
            return Response(
                status_code=304,
                headers={
                    "Cache-Control": POSTER_CACHE_CONTROL,
                    "ETag": etag,
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return poster_response(body, content_type, etag=etag)

    @app.get("/", response_class=HTMLResponse)
    def theater_index() -> HTMLResponse:
        settings = _settings()
        theater = normalize_theater_settings(getattr(settings, "theater", None))
        index = STATIC_DIR / "index.html"
        if not index.exists():
            raise HTTPException(status_code=500, detail="Theater UI missing")
        html = index.read_text(encoding="utf-8")
        if not theater.enabled:
            # Quiet disabled page — still serve shell so owners see a clear state.
            pass
        return HTMLResponse(html)

    @app.get("/theater.css")
    def theater_css() -> Response:
        path = STATIC_DIR / "theater.css"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return Response(
            content=path.read_text(encoding="utf-8"),
            media_type="text/css",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/theater.js")
    def theater_js() -> Response:
        path = STATIC_DIR / "theater.js"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        return Response(
            content=path.read_text(encoding="utf-8"),
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    return app


# Built by create_theater_app() in the dual-server entrypoint.
app = None
