"""Outbound HTTP for the Weather Channel. Fixed hosts only; nothing else is fetched."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional

USER_AGENT = "ProjectionistWeather/2.0 (+https://github.com/romwil/projectionist)"
MAX_BODY_BYTES = 8 * 1024 * 1024

# Every host the channel may call. Map and webcam image URLs that arrive inside an
# API response are checked against this set before they are fetched.
WEATHER_HOSTS: Dict[str, str] = {
    "api.open-meteo.com": "Forecast, hourly, and regional cities (coordinates)",
    "archive-api.open-meteo.com": "Record highs and lows, frost and first-snow averages (coordinates)",
    "air-quality-api.open-meteo.com": "UV, air quality, and pollen (coordinates)",
    "api.weather.gov": "NWS alerts, US only (coordinates)",
    "mesonet.agron.iastate.edu": "NEXRAD radar frames, US only (map box around the coordinates)",
    "api.rainviewer.com": "Radar frame list outside the US",
    "tilecache.rainviewer.com": "Radar tiles outside the US (map tile around the coordinates)",
    "cdn.star.nesdis.noaa.gov": "GOES satellite still for the region, US only",
    "api.windy.com": "Webcams near the coordinates, only when the owner adds a Windy key",
    "imgproxy.windy.com": "Webcam stills, only when the owner adds a Windy key",
    "news.google.com": "Local and national headlines (the city or the country)",
    "feeds.bbci.co.uk": "World headlines (nothing about the place)",
}


class WeatherFetchError(RuntimeError):
    """A source failed; the board that depends on it is skipped."""


def host_allowed(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(str(url or ""))
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in WEATHER_HOSTS


@dataclass
class FetchResult:
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


Fetcher = Callable[..., FetchResult]


def default_fetch(url: str, *, headers: Optional[Mapping[str, str]] = None, timeout: float = 10.0) -> FetchResult:
    if not host_allowed(url):
        raise WeatherFetchError(f"Refusing a host the Weather Channel does not list: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **dict(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — allowlisted hosts
            final = resp.geturl()
            if not host_allowed(final):
                raise WeatherFetchError(f"Redirected off the listed hosts: {final}")
            body = resp.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise WeatherFetchError(f"Response too large from {url}")
            return FetchResult(body=body, headers={k.lower(): v for k, v in resp.headers.items()})
    except WeatherFetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — network failures skip one board
        raise WeatherFetchError(f"{type(exc).__name__}: {exc}") from exc


def fetch_json(fetch: Optional[Fetcher], url: str, *, headers: Optional[Mapping[str, str]] = None) -> Any:
    result = (fetch or default_fetch)(url, headers={"Accept": "application/json", **dict(headers or {})})
    try:
        return json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherFetchError(f"Bad JSON from {url}") from exc
