"""Preroll bumpers + Weather Channel API (theater delight)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse

from projectionist.config_store import Settings
from projectionist.theater.preroll import pick_preroll, resolve_asset
from projectionist.theater.weather import weather_channel_payload
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["theater-delight"])

_settings_factory: Optional[Callable[[], Settings]] = None


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("theater delight routes not registered")
    return _settings_factory()


@router.get("/api/preroll/next")
def preroll_next(
    context: str = Query(default="movie"),
    user=Depends(get_current_user_dep),
):
    """Pick a host preroll for this client only (no shared playhead)."""
    _ = user
    ctx = str(context or "movie").strip().lower()
    if ctx not in {"movie", "live", "weather"}:
        ctx = "movie"
    item = pick_preroll(context=ctx)
    if item is None:
        return Response(status_code=204)
    return item


@router.get("/api/preroll/asset/{asset_id}")
def preroll_asset(
    asset_id: str,
    user=Depends(get_current_user_dep),
):
    """Stream a preroll / muzak file from the host bind (progressive)."""
    _ = user
    item = resolve_asset(asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="That preroll isn’t available.")
    path = item["path"]
    return FileResponse(
        path,
        media_type=str(item.get("content_type") or "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'inline; filename="{path.name}"',
        },
    )


@router.get("/api/live/weather")
def live_weather_channel(user=Depends(get_current_user_dep)):
    """Weather Channel–style payload (forecast egress + optional local muzak)."""
    _ = user
    _ = _settings()  # keep settings factory wired for future owner prefs
    return weather_channel_payload()


def register_theater_delight_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
) -> None:
    global _settings_factory
    _settings_factory = settings_factory
    app.include_router(router)
