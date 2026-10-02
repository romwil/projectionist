"""Open-Meteo place search for Weather Channel locations.

Forecast already leaves the LAN for ``api.open-meteo.com``. Place search is a
separate call to ``geocoding-api.open-meteo.com`` and only runs when someone
searches — a saved lat/lon is reused on later forecasts. See docs/PRIVACY.md.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def parse_geocode_results(payload: Any) -> List[Dict[str, Any]]:
    """Turn an Open-Meteo geocoding body into labeled candidates."""
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        name = str(row.get("name") or "").strip()
        admin1 = str(row.get("admin1") or "").strip()
        country = str(row.get("country") or "").strip()
        parts = [part for part in (name, admin1, country) if part]
        label = ", ".join(parts) if parts else "Saved place"
        out.append(
            {
                "label": label,
                "name": name,
                "admin1": admin1,
                "country": country,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return out


def normalize_saved_location(place: Any, latitude: Any, longitude: Any) -> tuple[str, float, float]:
    """Validate a chosen candidate before it is stored on the user profile."""
    label = " ".join(str(place or "").split())
    if not label or len(label) > 160:
        raise ValueError("Pick a place from the search results.")
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("That place is missing map coordinates.") from exc
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Those coordinates are out of range.")
    return label, lat, lon


def geocode_query(
    query: str,
    *,
    fetch_json: Optional[Callable[[str], Any]] = None,
    count: int = 8,
) -> List[Dict[str, Any]]:
    """Search Open-Meteo geocoding. ``query`` may be a ZIP, city/state, or city/country."""
    text = " ".join(str(query or "").split())
    if len(text) < 2 or len(text) > 120:
        return []
    if fetch_json is None:
        from projectionist.theater.weather import _fetch_json

        fetch_json = _fetch_json
    from urllib.parse import urlencode

    params = urlencode(
        {
            "name": text,
            "count": max(1, min(int(count), 10)),
            "language": "en",
            "format": "json",
        }
    )
    payload = fetch_json(f"{GEOCODE_URL}?{params}")
    return parse_geocode_results(payload)
