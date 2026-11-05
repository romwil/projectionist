"""Regional observations: current temperature and sky for nearby cities.

Nearby cities come from a bundled list, so no extra lookup leaves the LAN. One
Open-Meteo call carries every city's coordinates.
"""

from __future__ import annotations

import json
import math
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, fetch_json
from projectionist.theater.weather_channel.sources.forecast import OPEN_METEO_URL, wmo_label

_DATA = Path(__file__).resolve().parent.parent / "data" / "regional_cities.json"
MAX_CITIES = 8
MIN_CITIES = 3
MAX_DISTANCE_KM = 900.0
SAME_PLACE_KM = 20.0


@lru_cache(maxsize=1)
def _cities() -> List[tuple]:
    rows = json.loads(_DATA.read_text(encoding="utf-8"))
    return [tuple(row) for row in rows if isinstance(row, list) and len(row) == 4]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby_cities(latitude: float, longitude: float, *, limit: int = MAX_CITIES) -> List[Dict[str, Any]]:
    scored = []
    for name, region, lat, lon in _cities():
        distance = haversine_km(latitude, longitude, float(lat), float(lon))
        if distance < SAME_PLACE_KM or distance > MAX_DISTANCE_KM:
            continue
        scored.append((distance, {"name": name, "region": region, "latitude": float(lat), "longitude": float(lon)}))
    scored.sort(key=lambda pair: pair[0])
    picked: List[Dict[str, Any]] = []
    seen = set()
    for _distance, city in scored:
        if city["name"] in seen:
            continue
        seen.add(city["name"])
        picked.append(city)
        if len(picked) >= limit:
            break
    return picked


def regional_url(cities: List[Dict[str, Any]]) -> str:
    params = urllib.parse.urlencode(
        {
            "latitude": ",".join(f"{c['latitude']:.2f}" for c in cities),
            "longitude": ",".join(f"{c['longitude']:.2f}" for c in cities),
            "current": "temperature_2m,weather_code",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
        }
    )
    return f"{OPEN_METEO_URL}?{params}"


def parse_regional(cities: List[Dict[str, Any]], body: Any) -> List[Dict[str, Any]]:
    rows = body if isinstance(body, list) else [body]
    out: List[Dict[str, Any]] = []
    for city, row in zip(cities, rows):
        current = row.get("current") if isinstance(row, dict) else None
        if not isinstance(current, dict):
            continue
        temp = current.get("temperature_2m")
        if not isinstance(temp, (int, float)) or isinstance(temp, bool):
            continue
        code = current.get("weather_code")
        out.append(
            {
                "name": city["name"],
                "region": city["region"],
                "temp": int(round(float(temp))),
                "code": code,
                "sky": wmo_label(code),
            }
        )
    return out


def fetch_regional(latitude: float, longitude: float, *, fetch: Optional[Fetcher] = None) -> List[Dict[str, Any]]:
    cities = nearby_cities(latitude, longitude)
    if len(cities) < MIN_CITIES:
        return []
    rows = parse_regional(cities, fetch_json(fetch, regional_url(cities)))
    return rows if len(rows) >= MIN_CITIES else []
