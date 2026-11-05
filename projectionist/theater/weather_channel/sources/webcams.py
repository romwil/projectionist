"""Windy Webcams near the location. Only runs when the owner saved a Windy key."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, fetch_json

WINDY_WEBCAMS_URL = "https://api.windy.com/webcams/api/v3/webcams"
MAX_WEBCAMS = 4


def webcams_url(latitude: float, longitude: float) -> str:
    params = urllib.parse.urlencode(
        {
            "nearby": f"{latitude:.3f},{longitude:.3f},60",
            "limit": str(MAX_WEBCAMS),
            "include": "images,location",
        }
    )
    return f"{WINDY_WEBCAMS_URL}?{params}"


def parse_webcams(body: Any) -> List[Dict[str, Any]]:
    rows = body.get("webcams") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in rows[:MAX_WEBCAMS]:
        if not isinstance(row, dict):
            continue
        images = (row.get("images") or {}).get("current") or {}
        url = str(images.get("preview") or images.get("thumbnail") or "")
        if not url:
            continue
        stamp = str(row.get("lastUpdatedOn") or "")
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            when = ""
        out.append(
            {
                "title": " ".join(str(row.get("title") or "Webcam").split())[:120],
                "city": str((row.get("location") or {}).get("city") or ""),
                "source_url": url,
                "time": when,
            }
        )
    return out


def fetch_webcams(latitude: float, longitude: float, *, api_key: str, fetch: Optional[Fetcher] = None) -> List[Dict[str, Any]]:
    key = str(api_key or "").strip()
    if not key:
        return []
    return parse_webcams(fetch_json(fetch, webcams_url(latitude, longitude), headers={"x-windy-api-key": key}))
