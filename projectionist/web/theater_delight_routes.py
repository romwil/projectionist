"""Preroll bumpers + Weather Channel API (theater delight)."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from projectionist.config_store import Settings, save_settings
from projectionist.theater.media_browser import browse_media, confine_muzak_folder
from projectionist.theater.preroll import pick_preroll, resolve_asset
from projectionist.theater.weather import weather_channel_payload
from projectionist.theater.weather_geo import geocode_query
from projectionist.web.auth import get_current_user_dep, require_role

router = APIRouter(tags=["theater-delight"])

_settings_factory: Optional[Callable[[], Settings]] = None


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("theater delight routes not registered")
    return _settings_factory()


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


class MuzakFolderPayload(BaseModel):
    path: str = Field(default="", max_length=500)


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
    """Stream a preroll / muzak file from an allowed media folder (progressive)."""
    _ = user
    extra = _muzak_scan_root()
    item = resolve_asset(asset_id, extra_roots=[extra] if extra is not None else None)
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


def _muzak_scan_root() -> Optional[Path]:
    settings = _settings()
    folder = str(getattr(settings.tunarr, "muzak_folder", "") or "").strip()
    if not folder:
        return None
    return confine_muzak_folder(folder, settings=settings)


@router.get("/api/live/weather")
def live_weather_channel(user=Depends(get_current_user_dep)):
    """Weather Channel payload. Saved profile coordinates skip geocoding."""
    settings = _settings()
    place = getattr(user, "weather_place", None)
    lat = getattr(user, "weather_lat", None)
    lon = getattr(user, "weather_lon", None)
    kwargs = {}
    if place and lat is not None and lon is not None:
        kwargs = {
            "place_name": place,
            "latitude": lat,
            "longitude": lon,
            "location_source": "profile",
        }
    return weather_channel_payload(
        settings=settings,
        muzak_folder=str(getattr(settings.tunarr, "muzak_folder", "") or ""),
        **kwargs,
    )


@router.get("/api/weather/places")
def weather_places(
    q: str = Query(min_length=2, max_length=120),
    user=Depends(get_current_user_dep),
):
    """Search Open-Meteo geocoding (ZIP, city/state, or city/country)."""
    _ = user
    try:
        results = geocode_query(q)
    except (OSError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Place search is unavailable right now.",
        ) from exc
    return {
        "query": " ".join(q.split()),
        "results": results,
        "egress": {
            "provider": "Open-Meteo",
            "host": "geocoding-api.open-meteo.com",
            "purpose": "Find a weather place to save on your profile",
        },
    }


@router.get("/api/admin/live/media-browser")
def live_media_browser(
    path: str = Query(default="", max_length=500),
    user=Depends(require_role("owner")),
):
    """One level of container-visible media folders. Bind mounts are flagged."""
    _ = user
    try:
        return browse_media(path, settings=_settings())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/admin/live/muzak-folder")
def set_live_muzak_folder(
    payload: MuzakFolderPayload,
    user=Depends(require_role("owner")),
):
    """Save the Weather Channel music folder, confined to allowed media roots."""
    _ = user
    settings = _settings()
    raw = str(payload.path or "").strip()
    if raw:
        resolved = confine_muzak_folder(raw, settings=settings)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail="Choose a folder this container can see. Shared-in mounts are marked in the browser.",
            )
        stored = str(resolved)
    else:
        stored = ""
    tunarr = asdict(settings.tunarr)
    tunarr["muzak_folder"] = stored
    save_settings(_data_dir(), Settings.from_mapping({**asdict(settings), "tunarr": tunarr}))
    return {"muzak_folder": stored}


def register_theater_delight_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
) -> None:
    global _settings_factory
    _settings_factory = settings_factory
    app.include_router(router)
