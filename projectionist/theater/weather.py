"""Weather Channel entry points: household location, music folder, payload.

The data collectors, script writer, TTS renderer, and cache live in
``projectionist.theater.weather_channel``. See docs/PRIVACY.md for every host.
"""

from __future__ import annotations

import os
import random
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from projectionist.theater.media_browser import confine_muzak_folder
from projectionist.theater.preroll import list_preroll_audio, pick_preroll, resolve_preroll_root
from projectionist.theater.weather_channel.payload import build_payload
from projectionist.theater.weather_channel.place import Place, place_from_label
from projectionist.theater.weather_channel.service import NarrationSettings, WeatherService
from projectionist.theater.weather_channel.sources.forecast import wmo_label

__all__ = [
    "household_place",
    "narration_settings",
    "select_muzak",
    "weather_channel_payload",
    "get_weather_service",
    "wmo_label",
]

_DEFAULT_PLACE = "your area"


def _default_coords(environ: Optional[Any] = None) -> Tuple[float, float]:
    env = environ if environ is not None else os.environ
    try:
        lat = float(str(env.get("PROJECTIONIST_WEATHER_LAT") or "41.88").strip())
        lon = float(str(env.get("PROJECTIONIST_WEATHER_LON") or "-87.63").strip())
        return lat, lon
    except ValueError:
        return 41.88, -87.63


def household_place(environ: Optional[Any] = None) -> str:
    """Household label from the server env only.

    A signed-in profile place is an override for the forecast, never this field.
    """
    env = environ if environ is not None else os.environ
    configured = str(env.get("PROJECTIONIST_WEATHER_PLACE") or "").strip()
    return configured or _DEFAULT_PLACE


def select_muzak(
    folder: str,
    *,
    settings: Any = None,
    environ: Optional[Any] = None,
    allowed_roots: Optional[List[Any]] = None,
    rng: Any = None,
    mountinfo_text: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Every audio file in the owner's folder, shuffled — or why there is none.

    The player plays them in turn, reshuffling after the last one, and fades the
    bed around each voiceover.
    """
    text = str(folder or "").strip()
    if not text:
        return [], (
            "No music folder is set — the forecast plays with no soundtrack. "
            "The owner can choose one under Admin → Live Channels → Setup."
        )
    if allowed_roots is not None:
        from projectionist.theater.media_browser import resolve_within_roots

        resolved = resolve_within_roots(text, allowed_roots)
        if resolved is None or not resolved.is_dir():
            return [], "The music folder isn’t available in this container."
    else:
        resolved = confine_muzak_folder(text, settings=settings, environ=environ, mountinfo_text=mountinfo_text)
        if resolved is None:
            return [], "The music folder isn’t available in this container."
    audio_items = list_preroll_audio(resolved)
    if not audio_items:
        return [], "That music folder is empty, so the forecast plays without music."
    picker = rng if rng is not None else random.SystemRandom()
    tracks = [
        {
            "id": item["id"],
            "title": item["title"],
            "url": f"/api/preroll/asset/{item['id']}",
            "content_type": item["content_type"],
        }
        for item in audio_items
    ]
    picker.shuffle(tracks)
    return tracks, ""


def narration_settings(settings: Any) -> NarrationSettings:
    weather = getattr(settings, "weather", None)
    if weather is None:
        return NarrationSettings()
    try:
        rate = float(getattr(weather, "tts_rate", 1.0) or 1.0)
    except (TypeError, ValueError):
        rate = 1.0
    return NarrationSettings(
        enabled=bool(getattr(weather, "narration_enabled", False)),
        engine=str(getattr(weather, "tts_engine", "kokoro") or "kokoro"),
        voice=str(getattr(weather, "tts_voice", "") or ""),
        rate=rate,
        windy_api_key=str(getattr(weather, "windy_api_key", "") or ""),
    )


_SERVICE: Optional[WeatherService] = None
_SERVICE_LOCK = threading.Lock()


def get_weather_service(
    data_dir: Path,
    *,
    settings_factory: Callable[[], Any],
    llm_factory: Callable[[], Any] = lambda: None,
    holidays_factory: Callable[[], Sequence[Dict[str, Any]]] = lambda: (),
) -> WeatherService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or _SERVICE.data_dir != Path(data_dir):
            _SERVICE = WeatherService(
                Path(data_dir),
                settings_factory=lambda: narration_settings(settings_factory()),
                llm_factory=llm_factory,
                holidays_factory=holidays_factory,
            )
        return _SERVICE


def resolve_place(
    *,
    environ: Optional[Any] = None,
    place_name: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_source: str = "household",
) -> Tuple[Place, str]:
    if latitude is not None and longitude is not None:
        label = str(place_name or "").strip() or household_place(environ)
        source = location_source if location_source in {"profile", "household"} else "profile"
        return place_from_label(label, float(latitude), float(longitude)), source
    lat, lon = _default_coords(environ)
    return place_from_label(household_place(environ), lat, lon), "household"


def weather_channel_payload(
    *,
    service: WeatherService,
    environ: Optional[Any] = None,
    place_name: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_source: str = "household",
    muzak_folder: str = "",
    settings: Any = None,
    allowed_roots: Optional[List[Any]] = None,
    rng: Any = None,
    mountinfo_text: Optional[str] = None,
) -> Dict[str, Any]:
    place, source = resolve_place(
        environ=environ,
        place_name=place_name,
        latitude=latitude,
        longitude=longitude,
        location_source=location_source,
    )
    state = service.view(place)
    tracks, note = select_muzak(
        muzak_folder,
        settings=settings,
        environ=environ,
        allowed_roots=allowed_roots,
        rng=rng,
        mountinfo_text=mountinfo_text,
    )
    root = resolve_preroll_root(environ)
    return build_payload(
        service,
        state,
        location_source=source,
        household_place=household_place(environ),
        music=tracks,
        music_note=note,
        intro_preroll=pick_preroll(context="live", root=root, rng=rng) if root else None,
        preroll_root_found=root is not None,
    )
