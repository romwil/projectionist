"""Almanac: sun, moon (computed here), and archive records for today's date."""

from __future__ import annotations

import math
import statistics
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, fetch_json

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ARCHIVE_START = "1960-01-01"
_SYNODIC_DAYS = 29.530588853
_KNOWN_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def moon_phase(when: Optional[datetime] = None) -> Dict[str, Any]:
    now = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = ((now - _KNOWN_NEW_MOON).total_seconds() / 86400.0) % _SYNODIC_DAYS
    fraction = age / _SYNODIC_DAYS
    illumination = round((1 - math.cos(2 * math.pi * fraction)) / 2 * 100)
    names = [
        (0.0339, "New moon"), (0.2161, "Waxing crescent"), (0.2839, "First quarter"),
        (0.4661, "Waxing gibbous"), (0.5339, "Full moon"), (0.7161, "Waning gibbous"),
        (0.7839, "Last quarter"), (0.9661, "Waning crescent"), (1.01, "New moon"),
    ]
    name = next(label for cutoff, label in names if fraction < cutoff)
    return {"name": name, "illumination": int(illumination), "age_days": round(age, 1)}


def clock_label(iso: str) -> str:
    try:
        when = datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    hour = when.hour % 12 or 12
    return f"{hour}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"


def month_day(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} {d.day}"


def long_month_day(d: date) -> str:
    return f"{_MONTH_NAMES[d.month - 1]} {d.day}"


def sun_facts(forecast: Dict[str, Any]) -> Dict[str, Any]:
    days = forecast.get("daily") or []
    today = days[0] if days else {}
    yesterday = forecast.get("yesterday") or {}
    if not today.get("sunrise") or not today.get("sunset"):
        return {}
    length = today.get("daylight_s")
    change = None
    if isinstance(length, (int, float)) and isinstance(yesterday.get("daylight_s"), (int, float)):
        change = int(round(length - yesterday["daylight_s"]))
    return {
        "sunrise": clock_label(today["sunrise"]),
        "sunset": clock_label(today["sunset"]),
        "day_length_min": int(round(length / 60)) if isinstance(length, (int, float)) else None,
        "day_length_change_s": change,
    }


def archive_url(latitude: float, longitude: float, *, today: date) -> str:
    params = urllib.parse.urlencode(
        {
            "latitude": f"{latitude:.2f}",
            "longitude": f"{longitude:.2f}",
            "start_date": ARCHIVE_START,
            "end_date": (today - timedelta(days=7)).isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,snowfall_sum",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
        }
    )
    return f"{OPEN_METEO_ARCHIVE_URL}?{params}"


def _avg_day(days_of_year: List[int], year: int) -> Optional[date]:
    if not days_of_year:
        return None
    return date(year, 1, 1) + timedelta(days=int(round(statistics.mean(days_of_year))) - 1)


def _median_day(days_of_year: List[int], year: int) -> Optional[date]:
    if not days_of_year:
        return None
    return date(year, 1, 1) + timedelta(days=int(statistics.median(days_of_year)) - 1)


def archive_facts(body: Any, *, today: date) -> Dict[str, Any]:
    daily = body.get("daily") if isinstance(body, dict) else None
    if not isinstance(daily, dict):
        return {}
    times = daily.get("time") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    snow = daily.get("snowfall_sum") or []
    record_high = record_low = None
    last_spring: Dict[int, int] = {}
    first_fall: Dict[int, int] = {}
    first_snow: Dict[int, int] = {}
    years = set()
    for i, iso in enumerate(times):
        try:
            d = date.fromisoformat(str(iso))
        except ValueError:
            continue
        hi = highs[i] if i < len(highs) else None
        lo = lows[i] if i < len(lows) else None
        sn = snow[i] if i < len(snow) else None
        years.add(d.year)
        if (d.month, d.day) == (today.month, today.day):
            if isinstance(hi, (int, float)) and (record_high is None or hi > record_high[0]):
                record_high = (hi, d.year)
            if isinstance(lo, (int, float)) and (record_low is None or lo < record_low[0]):
                record_low = (lo, d.year)
        doy = d.timetuple().tm_yday
        if isinstance(lo, (int, float)) and lo <= 32.0:
            if d.month <= 6:
                last_spring[d.year] = max(last_spring.get(d.year, 0), doy)
            elif d.year not in first_fall:
                first_fall[d.year] = doy
        if d.month >= 7 and isinstance(sn, (int, float)) and sn >= 0.1 and d.year not in first_snow:
            first_snow[d.year] = doy
    out: Dict[str, Any] = {"years": len(years), "first_year": min(years) if years else None, "today": long_month_day(today)}
    if record_high:
        out["record_high"] = {"value": int(round(record_high[0])), "year": record_high[1]}
    if record_low:
        out["record_low"] = {"value": int(round(record_low[0])), "year": record_low[1]}
    spring = _avg_day(list(last_spring.values()), today.year)
    fall = _avg_day(list(first_fall.values()), today.year)
    snow_day = _median_day(list(first_snow.values()), today.year) if len(first_snow) >= max(3, len(years) // 2) else None
    if spring and fall and len(last_spring) >= 3:
        out["frost"] = {"last_spring": long_month_day(spring), "first_fall": long_month_day(fall)}
    if snow_day:
        out["first_snow_by"] = long_month_day(snow_day)
        out["first_snow_date"] = snow_day.isoformat()
    return out


def fetch_archive_facts(latitude: float, longitude: float, *, today: date, fetch: Optional[Fetcher] = None) -> Dict[str, Any]:
    return archive_facts(fetch_json(fetch, archive_url(latitude, longitude, today=today)), today=today)


def next_season(today: date, *, southern: bool = False) -> Dict[str, Any]:
    """Approximate next solstice or equinox (dates drift by a day across years)."""
    marks = [(3, 20, "spring equinox", "fall equinox"), (6, 21, "summer solstice", "winter solstice"),
             (9, 22, "fall equinox", "spring equinox"), (12, 21, "winter solstice", "summer solstice")]
    for year in (today.year, today.year + 1):
        for month, day, north, south in marks:
            when = date(year, month, day)
            if when > today:
                return {"name": south if southern else north, "date": long_month_day(when), "days": (when - today).days}
    return {}
