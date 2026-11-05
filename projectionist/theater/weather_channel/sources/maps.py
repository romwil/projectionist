"""Radar and satellite frames for the location.

US points use Iowa Environmental Mesonet NEXRAD composites (a rendered map with
counties) and a NOAA GOES regional sector still. Elsewhere, radar comes from
RainViewer tiles and there is no satellite board.
"""

from __future__ import annotations

import math
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, fetch_json

IEM_RADMAP_URL = "https://mesonet.agron.iastate.edu/GIS/radmap.php"
RAINVIEWER_MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
GOES_CDN = "https://cdn.star.nesdis.noaa.gov"
RADAR_FRAMES = 6
RADAR_STEP_MINUTES = 10

# (sector, satellite, min_lat, max_lat, min_lon, max_lon)
GOES_SECTORS = (
    ("pnw", "GOES18", 41.0, 50.0, -125.0, -111.0),
    ("psw", "GOES18", 31.0, 42.0, -125.0, -113.0),
    ("nr", "GOES19", 40.0, 50.0, -117.0, -100.0),
    ("sr", "GOES19", 31.0, 42.0, -114.0, -100.0),
    ("umv", "GOES19", 39.0, 50.0, -100.0, -86.0),
    ("cgl", "GOES19", 38.0, 49.0, -92.0, -78.0),
    ("sp", "GOES19", 25.0, 40.0, -107.0, -92.0),
    ("smv", "GOES19", 28.0, 39.0, -95.0, -84.0),
    ("ne", "GOES19", 38.0, 48.0, -80.0, -66.0),
    ("se", "GOES19", 24.0, 37.0, -88.0, -75.0),
    ("ak", "GOES18", 51.0, 72.0, -180.0, -129.0),
    ("hi", "GOES18", 18.0, 23.0, -161.0, -154.0),
    ("pr", "GOES19", 17.0, 19.5, -68.0, -64.0),
)


def _iem_bbox(latitude: float, longitude: float) -> str:
    half_lat, half_lon = 2.2, 3.9
    return f"{longitude - half_lon:.2f},{latitude - half_lat:.2f},{longitude + half_lon:.2f},{latitude + half_lat:.2f}"


def us_radar_frames(latitude: float, longitude: float, *, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Six NEXRAD frames ten minutes apart, newest last."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(minutes=5)
    current = current.replace(minute=current.minute - current.minute % 5, second=0, microsecond=0)
    frames = []
    for step in range(RADAR_FRAMES - 1, -1, -1):
        when = current - timedelta(minutes=RADAR_STEP_MINUTES * step)
        params = [
            ("width", "640"),
            ("height", "360"),
            ("bbox", _iem_bbox(latitude, longitude)),
            ("layers[]", "n0q"),
            ("layers[]", "uscounties"),
            ("layers[]", "interstates"),
            ("ts", when.strftime("%Y%m%d%H%M")),
        ]
        frames.append({"source_url": f"{IEM_RADMAP_URL}?{urllib.parse.urlencode(params)}", "time": when.isoformat()})
    return frames


def _tile_for(latitude: float, longitude: float, zoom: int) -> tuple[int, int, float, float]:
    n = 2**zoom
    x = (longitude + 180.0) / 360.0 * n
    lat_r = math.radians(max(min(latitude, 85.0), -85.0))
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return int(x), int(y), x - int(x), y - int(y)


def global_radar_frames(latitude: float, longitude: float, *, fetch: Optional[Fetcher] = None) -> Dict[str, Any]:
    body = fetch_json(fetch, RAINVIEWER_MAPS_URL)
    host = str(body.get("host") or "") if isinstance(body, dict) else ""
    past = (((body or {}).get("radar") or {}).get("past") or []) if isinstance(body, dict) else []
    zoom = 5
    tx, ty, fx, fy = _tile_for(latitude, longitude, zoom)
    frames = []
    for row in past[-RADAR_FRAMES:]:
        path = str((row or {}).get("path") or "")
        stamp = (row or {}).get("time")
        if not path or not isinstance(stamp, (int, float)):
            continue
        frames.append(
            {
                "source_url": f"{host}{path}/512/{zoom}/{tx}/{ty}/2/1_1.png",
                "time": datetime.fromtimestamp(float(stamp), tz=timezone.utc).isoformat(),
            }
        )
    return {"frames": frames, "marker": {"x": round(fx, 3), "y": round(fy, 3)}}


def goes_sector(latitude: float, longitude: float) -> Optional[tuple[str, str]]:
    best = None
    for sector, sat, lo_lat, hi_lat, lo_lon, hi_lon in GOES_SECTORS:
        if lo_lat <= latitude <= hi_lat and lo_lon <= longitude <= hi_lon:
            center = ((lo_lat + hi_lat) / 2, (lo_lon + hi_lon) / 2)
            distance = (center[0] - latitude) ** 2 + (center[1] - longitude) ** 2
            if best is None or distance < best[0]:
                best = (distance, sector, sat)
    return (best[1], best[2]) if best else None


def satellite_source(latitude: float, longitude: float) -> Optional[Dict[str, str]]:
    found = goes_sector(latitude, longitude)
    if not found:
        return None
    sector, sat = found
    return {
        "source_url": f"{GOES_CDN}/{sat}/ABI/SECTOR/{sector}/GEOCOLOR/600x600.jpg",
        "label": f"NOAA {sat.replace('GOES', 'GOES-')} GeoColor",
    }
