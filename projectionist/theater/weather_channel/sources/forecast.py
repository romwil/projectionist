"""Open-Meteo forecast: current conditions, the next 12 hours, and five days."""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, WeatherFetchError, fetch_json

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

WMO_LABELS = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Freezing fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Dense drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}

WEEKDAY_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def wmo_label(code: Any) -> str:
    try:
        return WMO_LABELS.get(int(code), "Mixed skies")
    except (TypeError, ValueError):
        return "Mixed skies"


def forecast_url(latitude: float, longitude: float) -> str:
    params = urllib.parse.urlencode(
        {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "dew_point_2m",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "wind_gusts_10m",
                    "pressure_msl",
                    "visibility",
                    "is_day",
                ]
            ),
            "hourly": "temperature_2m,weather_code,precipitation_probability,pressure_msl",
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                    "sunrise",
                    "sunset",
                    "daylight_duration",
                    "uv_index_max",
                ]
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "past_days": "1",
            "forecast_days": "6",
        }
    )
    return f"{OPEN_METEO_URL}?{params}"


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _round(value: Any) -> Optional[int]:
    num = _num(value)
    return int(round(num)) if num is not None else None


def _col(block: Dict[str, Any], key: str) -> List[Any]:
    value = block.get(key)
    return value if isinstance(value, list) else []


def _at(values: List[Any], index: int) -> Any:
    return values[index] if 0 <= index < len(values) else None


def hour_label(iso: str) -> str:
    try:
        when = datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    hour = when.hour % 12 or 12
    return f"{hour} {'AM' if when.hour < 12 else 'PM'}"


def compass(degrees: Any) -> str:
    num = _num(degrees)
    if num is None:
        return ""
    return _COMPASS[int(((num % 360) + 22.5) // 45) % 8]


def weekday_for(iso_date: str) -> tuple[str, str]:
    try:
        day = datetime.fromisoformat(str(iso_date)[:10]).weekday()
    except ValueError:
        return "", ""
    return WEEKDAY_SHORT[day], WEEKDAY_NAMES[day]


def _visibility_miles(value: Any, unit: str) -> Optional[float]:
    num = _num(value)
    if num is None:
        return None
    miles = num / 5280.0 if unit.strip().lower() in {"ft", "feet"} else num / 1609.344
    return round(min(miles, 10.0), 1)


def normalize_forecast(raw: Any) -> Dict[str, Any]:
    """Reduce an Open-Meteo body to the fields the boards and scripts use."""
    if not isinstance(raw, dict):
        raise WeatherFetchError("Forecast body was not an object")
    current_raw = raw.get("current") if isinstance(raw.get("current"), dict) else {}
    units = raw.get("current_units") if isinstance(raw.get("current_units"), dict) else {}
    hourly_raw = raw.get("hourly") if isinstance(raw.get("hourly"), dict) else {}
    daily_raw = raw.get("daily") if isinstance(raw.get("daily"), dict) else {}

    now_iso = str(current_raw.get("time") or "")
    hours = [str(t) for t in _col(hourly_raw, "time")]
    pressures = _col(hourly_raw, "pressure_msl")
    current_hour = now_iso[:13]
    now_index = next((i for i, t in enumerate(hours) if t[:13] == current_hour), -1)

    pressure_hpa = _num(current_raw.get("pressure_msl"))
    trend = ""
    if pressure_hpa is not None and now_index >= 3:
        earlier = _num(_at(pressures, now_index - 3))
        if earlier is not None:
            delta = pressure_hpa - earlier
            trend = "rising" if delta >= 1.0 else "falling" if delta <= -1.0 else "steady"

    code = _round(current_raw.get("weather_code"))
    current: Dict[str, Any] = {}
    if current_raw:
        current = {
            "time": now_iso,
            "temp": _round(current_raw.get("temperature_2m")),
            "feels_like": _round(current_raw.get("apparent_temperature")),
            "code": code,
            "sky": wmo_label(code) if code is not None else "",
            "wind": _round(current_raw.get("wind_speed_10m")),
            "wind_dir": compass(current_raw.get("wind_direction_10m")),
            "gusts": _round(current_raw.get("wind_gusts_10m")),
            "humidity": _round(current_raw.get("relative_humidity_2m")),
            "dew_point": _round(current_raw.get("dew_point_2m")),
            "pressure_inhg": round(pressure_hpa * 0.02953, 2) if pressure_hpa is not None else None,
            "pressure_trend": trend,
            "visibility_mi": _visibility_miles(current_raw.get("visibility"), str(units.get("visibility") or "m")),
            "is_day": bool(current_raw.get("is_day", 1)),
        }
        if all(current.get(k) is None for k in ("temp", "code", "wind")):
            current = {}

    hourly: List[Dict[str, Any]] = []
    if now_index >= 0:
        temps = _col(hourly_raw, "temperature_2m")
        codes = _col(hourly_raw, "weather_code")
        precip = _col(hourly_raw, "precipitation_probability")
        for i in range(now_index + 1, min(now_index + 13, len(hours))):
            temp = _round(_at(temps, i))
            if temp is None:
                continue
            hcode = _round(_at(codes, i))
            hourly.append(
                {
                    "time": hours[i],
                    "label": hour_label(hours[i]),
                    "temp": temp,
                    "code": hcode,
                    "sky": wmo_label(hcode) if hcode is not None else "",
                    "precip": _round(_at(precip, i)),
                }
            )

    days = [str(t) for t in _col(daily_raw, "time")]
    today = now_iso[:10]
    start = days.index(today) if today in days else (1 if len(days) > 5 else 0)
    daily: List[Dict[str, Any]] = []
    yesterday: Dict[str, Any] = {}
    for i, iso in enumerate(days):
        dcode = _round(_at(_col(daily_raw, "weather_code"), i))
        short, name = weekday_for(iso)
        row = {
            "date": iso,
            "weekday": short,
            "weekday_name": name,
            "high": _round(_at(_col(daily_raw, "temperature_2m_max"), i)),
            "low": _round(_at(_col(daily_raw, "temperature_2m_min"), i)),
            "code": dcode,
            "sky": wmo_label(dcode) if dcode is not None else "",
            "precip": _round(_at(_col(daily_raw, "precipitation_probability_max"), i)),
            "sunrise": str(_at(_col(daily_raw, "sunrise"), i) or ""),
            "sunset": str(_at(_col(daily_raw, "sunset"), i) or ""),
            "daylight_s": _num(_at(_col(daily_raw, "daylight_duration"), i)),
            "uv_max": _num(_at(_col(daily_raw, "uv_index_max"), i)),
        }
        if i == start - 1:
            yesterday = row
        elif i >= start and len(daily) < 5 and (row["high"] is not None or row["low"] is not None):
            daily.append(row)

    return {
        "timezone": str(raw.get("timezone") or ""),
        "utc_offset_seconds": int(_num(raw.get("utc_offset_seconds")) or 0),
        "now": now_iso,
        "current": current,
        "hourly": hourly,
        "daily": daily,
        "yesterday": yesterday,
    }


def fetch_forecast(latitude: float, longitude: float, *, fetch: Optional[Fetcher] = None) -> Dict[str, Any]:
    return normalize_forecast(fetch_json(fetch, forecast_url(latitude, longitude)))
