"""Preroll bumpers + Weather Channel API (theater delight)."""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from projectionist.config_store import Settings, save_settings
from projectionist.theater.media_browser import browse_media, confine_muzak_folder
from projectionist.theater.preroll import pick_preroll, resolve_asset
from projectionist.theater.weather import get_weather_service, narration_settings, weather_channel_payload
from projectionist.theater.weather_channel.place import short_place
from projectionist.theater.weather_channel.tts import normalize_choice
from projectionist.theater.weather_geo import geocode_query
from projectionist.web.auth import get_current_user_dep, require_role

router = APIRouter(tags=["theater-delight"])

_settings_factory: Optional[Callable[[], Settings]] = None
_db_factory: Optional[Callable[[], Any]] = None


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


def _weather_llm() -> Optional[Callable[[List[Dict[str, str]]], str]]:
    """The household model, or None. It only ever sees weather data, place names, and headlines."""
    from projectionist.config_store import validate_llm_settings

    settings = _settings()
    if validate_llm_settings(settings):
        return None
    from projectionist.agent.providers import get_chat_provider

    provider = get_chat_provider(settings)

    def complete(messages: List[Dict[str, str]]) -> str:
        import asyncio

        response = asyncio.run(provider.chat(messages))
        content = response.get("content") if isinstance(response, dict) else None
        if content:
            return str(content)
        choices = (response or {}).get("choices") or []
        return str(((choices[0] or {}).get("message") or {}).get("content") or "") if choices else ""

    return complete


def _weather_holidays() -> List[Dict[str, Any]]:
    if _db_factory is None:
        return []
    try:
        return list(_db_factory().list_holiday_schedule(horizon_days=60))
    except Exception:  # noqa: BLE001 — holidays are optional garnish
        return []


def _weather_service():
    return get_weather_service(
        _data_dir(),
        settings_factory=_settings,
        llm_factory=_weather_llm,
        holidays_factory=_weather_holidays,
    )


@router.get("/api/live/weather")
def live_weather_channel(user=Depends(get_current_user_dep)):
    """Weather Channel payload from the shared per-location cache.

    Saved profile coordinates skip geocoding. Only coordinates and the place
    label reach the weather service — never who is watching.
    """
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
        service=_weather_service(),
        settings=settings,
        muzak_folder=str(getattr(settings.tunarr, "muzak_folder", "") or ""),
        **kwargs,
    )


@router.get("/api/live/weather/audio/{name}")
def live_weather_audio(name: str, user=Depends(get_current_user_dep)):
    """A rendered voiceover. Shared by every viewer of that script."""
    _ = user
    digest = name[:-5] if name.endswith(".opus") else ""
    path = _weather_service().tts.audio_path(digest)
    if path is None:
        raise HTTPException(status_code=404, detail="That voiceover isn’t rendered.")
    return FileResponse(path, media_type="audio/ogg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/live/weather/image/{image_id}")
def live_weather_image(image_id: str, user=Depends(get_current_user_dep)):
    """A radar, satellite, or webcam image the server fetched (viewers never call map hosts)."""
    _ = user
    stored = _weather_service().images.get(image_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="That map frame has expired.")
    return FileResponse(stored.path, media_type=stored.content_type, headers={"Cache-Control": "private, max-age=600"})


class WeatherNarrationPayload(BaseModel):
    narration_enabled: Optional[bool] = None
    tts_engine: Optional[str] = Field(default=None, max_length=20)
    tts_voice: Optional[str] = Field(default=None, max_length=60)
    tts_rate: Optional[float] = Field(default=None, ge=0.5, le=1.5)
    windy_api_key: Optional[str] = Field(default=None, max_length=200)
    clear_windy_api_key: Optional[bool] = None


def _weather_admin_status(settings: Settings) -> Dict[str, Any]:
    service = _weather_service()
    narration = narration_settings(settings)
    engine, voice, rate = normalize_choice(narration.engine, narration.voice, narration.rate)
    previews = []
    for state in service.active_states():
        with state.lock:
            scripts = {k: [dict(v) for v in rows] for k, rows in state.scripts.items()}
        previews.append({"place": short_place(state.place), "is_us": state.place.is_us, "scripts": scripts})
    return {
        "narration": service.tts.status(engine, voice, rate, narration.enabled),
        "windy_api_key_set": bool(narration.windy_api_key),
        "llm_configured": _weather_llm() is not None,
        "alerts_note": "Weather alerts come from the US National Weather Service, so they appear for US places only.",
        "previews": previews,
    }


@router.get("/api/admin/live/weather")
def live_weather_admin(user=Depends(require_role("owner"))):
    """Narration status, voice choices, Windy key presence, and current scripts. No outbound call."""
    _ = user
    return _weather_admin_status(_settings())


@router.put("/api/admin/live/weather")
def save_live_weather_admin(payload: WeatherNarrationPayload, user=Depends(require_role("owner"))):
    """Save narration and webcam settings. Turning narration on downloads the voice once."""
    _ = user
    settings = _settings()
    weather = asdict(settings.weather)
    for key in ("narration_enabled", "tts_engine", "tts_voice", "tts_rate"):
        value = getattr(payload, key)
        if value is not None:
            weather[key] = value
    engine, voice, rate = normalize_choice(weather["tts_engine"], weather["tts_voice"], weather["tts_rate"])
    weather.update({"tts_engine": engine, "tts_voice": voice, "tts_rate": rate})
    if payload.clear_windy_api_key:
        weather["windy_api_key"] = ""
    elif str(payload.windy_api_key or "").strip():
        weather["windy_api_key"] = str(payload.windy_api_key).strip()
    updated = Settings.from_mapping({**asdict(settings), "weather": weather})
    save_settings(_data_dir(), updated)
    service = _weather_service()
    if weather["narration_enabled"] and not service.tts.installed(engine, voice):
        service.tts.start_download(engine, voice)
    return _weather_admin_status(updated)


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
    db_factory: Optional[Callable[[], Any]] = None,
) -> None:
    global _settings_factory, _db_factory
    _settings_factory = settings_factory
    _db_factory = db_factory
    app.include_router(router)
