"""Weather Channel–style cable experience — real forecast + optional local muzak.

Forecast egress uses Open-Meteo (no API key). See docs/PRIVACY.md.
Muzak is scanned from the preroll bind (and weather/ sibling folders when present).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from projectionist.theater.preroll import list_preroll_audio, pick_preroll, resolve_preroll_root

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "ProjectionistWeather/1.0 (+https://github.com/romwil/projectionist)"


def _default_coords(environ: Optional[Any] = None) -> Tuple[float, float]:
    env = environ if environ is not None else os.environ
    try:
        lat = float(str(env.get("PROJECTIONIST_WEATHER_LAT") or "41.88").strip())
        lon = float(str(env.get("PROJECTIONIST_WEATHER_LON") or "-87.63").strip())
        return lat, lon
    except ValueError:
        return 41.88, -87.63


def _fetch_json(url: str, *, timeout: float = 8.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed Open-Meteo host
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def fetch_open_meteo_forecast(
    *,
    latitude: float,
    longitude: float,
    fetch_json=None,
) -> Dict[str, Any]:
    """Pull current + daily forecast from Open-Meteo (leaves LAN)."""
    params = urllib.parse.urlencode(
        {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "forecast_days": "3",
        }
    )
    url = f"{OPEN_METEO_URL}?{params}"
    loader = fetch_json or _fetch_json
    return loader(url)


_WMO = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
}


def wmo_label(code: Any) -> str:
    try:
        return _WMO.get(int(code), "Mixed skies")
    except (TypeError, ValueError):
        return "Mixed skies"


def build_voiceover_script(payload: Dict[str, Any], *, place_name: str = "your area") -> str:
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    cond = wmo_label(current.get("weather_code"))
    parts = [
        f"You're watching the Projectionist Weather Channel for {place_name}.",
        f"Right now: {cond}",
    ]
    if temp is not None:
        parts.append(f"at {temp:.0f} degrees.")
    else:
        parts.append(".")
    if humidity is not None:
        parts.append(f"Humidity {humidity:.0f} percent.")
    if wind is not None:
        parts.append(f"Wind around {wind:.0f} miles per hour.")
    times = daily.get("time") if isinstance(daily.get("time"), list) else []
    tmax = daily.get("temperature_2m_max") if isinstance(daily.get("temperature_2m_max"), list) else []
    tmin = daily.get("temperature_2m_min") if isinstance(daily.get("temperature_2m_min"), list) else []
    codes = daily.get("weather_code") if isinstance(daily.get("weather_code"), list) else []
    if times:
        parts.append("Looking ahead:")
        for i, day in enumerate(times[:3]):
            hi = tmax[i] if i < len(tmax) else None
            lo = tmin[i] if i < len(tmin) else None
            label = wmo_label(codes[i] if i < len(codes) else None)
            bit = f"{day}: {label}"
            if hi is not None and lo is not None:
                bit += f", high {hi:.0f}, low {lo:.0f}"
            parts.append(bit + ".")
    parts.append("This has been your local conditions. Stay tuned.")
    return " ".join(parts)


def weather_channel_payload(
    *,
    environ: Optional[Any] = None,
    fetch_json=None,
    place_name: str = "your area",
) -> Dict[str, Any]:
    lat, lon = _default_coords(environ)
    env = environ if environ is not None else os.environ
    place = str(env.get("PROJECTIONIST_WEATHER_PLACE") or place_name).strip() or place_name
    error = ""
    forecast: Dict[str, Any] = {}
    try:
        forecast = fetch_open_meteo_forecast(latitude=lat, longitude=lon, fetch_json=fetch_json)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("weather forecast fetch failed: %s", exc)
        error = "Weather is temporarily unavailable — check LAN egress to api.open-meteo.com."

    root = resolve_preroll_root(environ)
    audio_items = list_preroll_audio(root) if root else []
    # Prefer paths that look like weather/muzak beds.
    preferred = [
        a
        for a in audio_items
        if any(tok in str(a["path"]).lower() for tok in ("weather", "muzak", "elevator", "easy listening", "soft rock"))
    ]
    bed = (preferred or audio_items)
    muzak = None
    if bed:
        chosen = bed[0]
        muzak = {
            "id": chosen["id"],
            "title": chosen["title"],
            "url": f"/api/preroll/asset/{chosen['id']}",
            "content_type": chosen["content_type"],
        }

    script = build_voiceover_script(forecast, place_name=place) if forecast else (
        "Projectionist Weather Channel. Forecast is offline for the moment."
    )
    current = forecast.get("current") if isinstance(forecast.get("current"), dict) else {}
    daily = forecast.get("daily") if isinstance(forecast.get("daily"), dict) else {}
    ticker: List[str] = []
    if current:
        ticker.append(
            f"NOW {wmo_label(current.get('weather_code'))} "
            f"{current.get('temperature_2m', '—')}°"
        )
    times = daily.get("time") if isinstance(daily.get("time"), list) else []
    tmax = daily.get("temperature_2m_max") if isinstance(daily.get("temperature_2m_max"), list) else []
    tmin = daily.get("temperature_2m_min") if isinstance(daily.get("temperature_2m_min"), list) else []
    for i, day in enumerate(times[:3]):
        hi = tmax[i] if i < len(tmax) else "—"
        lo = tmin[i] if i < len(tmin) else "—"
        ticker.append(f"{day}  Hi {hi}° / Lo {lo}°")

    return {
        "enabled": True,
        "place": place,
        "latitude": lat,
        "longitude": lon,
        "egress": {
            "provider": "Open-Meteo",
            "host": "api.open-meteo.com",
            "purpose": "Local forecast for the Weather Channel cable experience",
        },
        "error": error,
        "current": current,
        "daily": daily,
        "ticker": ticker,
        "voiceover": script,
        "muzak": muzak,
        "preroll_root_found": root is not None,
        # Optional bumper before weather graphics (same independent picker).
        "intro_preroll": pick_preroll(context="live", root=root) if root else None,
    }
