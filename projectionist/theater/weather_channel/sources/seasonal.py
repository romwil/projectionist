"""Seasonal board: UV, air quality, pollen (where the model covers it), holiday ties."""

from __future__ import annotations

import urllib.parse
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from projectionist.theater.weather_channel.http import Fetcher, fetch_json

OPEN_METEO_AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
POLLEN_FIELDS = ("alder_pollen", "birch_pollen", "grass_pollen", "mugwort_pollen", "olive_pollen", "ragweed_pollen")


def air_url(latitude: float, longitude: float) -> str:
    params = urllib.parse.urlencode(
        {
            "latitude": f"{latitude:.2f}",
            "longitude": f"{longitude:.2f}",
            "current": ",".join(("us_aqi", "uv_index") + POLLEN_FIELDS),
            "timezone": "auto",
        }
    )
    return f"{OPEN_METEO_AIR_URL}?{params}"


def aqi_label(aqi: Optional[int]) -> str:
    if aqi is None:
        return ""
    for cutoff, label in ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"), (200, "Unhealthy"), (300, "Very unhealthy")):
        if aqi <= cutoff:
            return label
    return "Hazardous"


def uv_label(uv: Optional[float]) -> str:
    if uv is None:
        return ""
    for cutoff, label in ((2, "Low"), (5, "Moderate"), (7, "High"), (10, "Very high")):
        if uv <= cutoff:
            return label
    return "Extreme"


def pollen_label(grains: float) -> str:
    return "Low" if grains < 20 else "Moderate" if grains < 100 else "High"


def parse_air(body: Any) -> Dict[str, Any]:
    current = body.get("current") if isinstance(body, dict) else None
    if not isinstance(current, dict):
        return {}
    out: Dict[str, Any] = {}
    aqi = current.get("us_aqi")
    if isinstance(aqi, (int, float)) and not isinstance(aqi, bool):
        out["aqi"] = int(round(aqi))
        out["aqi_label"] = aqi_label(out["aqi"])
    uv = current.get("uv_index")
    if isinstance(uv, (int, float)) and not isinstance(uv, bool):
        out["uv_index"] = int(round(uv))
        out["uv_label"] = uv_label(float(uv))
    pollen = []
    for name in POLLEN_FIELDS:
        value = current.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            pollen.append({"kind": name.replace("_pollen", "").title(), "level": pollen_label(float(value))})
    if pollen:
        out["pollen"] = pollen
    return out


def fetch_air(latitude: float, longitude: float, *, fetch: Optional[Fetcher] = None) -> Dict[str, Any]:
    return parse_air(fetch_json(fetch, air_url(latitude, longitude)))


def holiday_ties(
    holidays: Sequence[Dict[str, Any]],
    forecast: Dict[str, Any],
    archive: Dict[str, Any],
    *,
    today: date,
) -> List[Dict[str, Any]]:
    """Household holidays that land in the forecast window or near first snow."""
    days = {row.get("date"): row for row in (forecast.get("daily") or [])}
    ties: List[Dict[str, Any]] = []
    for holiday in holidays:
        name = str(holiday.get("name") or "").strip()
        when = str(holiday.get("grounding_date") or holiday.get("date") or "")[:10]
        if not name or not when:
            continue
        row = days.get(when)
        if row:
            ties.append(
                {
                    "name": name,
                    "date": when,
                    "kind": "forecast",
                    "weekday_name": row.get("weekday_name"),
                    "low": row.get("low"),
                    "high": row.get("high"),
                    "sky": row.get("sky"),
                    "precip": row.get("precip"),
                }
            )
            continue
        snow_date = str(archive.get("first_snow_date") or "")
        if snow_date and when >= today.isoformat() and snow_date <= when and snow_date >= today.isoformat():
            ties.append({"name": name, "date": when, "kind": "first_snow", "first_snow_by": archive.get("first_snow_by")})
    return ties[:2]
