"""Assemble the Weather Channel payload from the cache. No network here."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import WEATHER_HOSTS
from projectionist.theater.weather_channel.scripts import trivia_line
from projectionist.theater.weather_channel.service import LocationState, WeatherService, segment_facts
from projectionist.theater.weather_channel.sources import almanac

SEGMENT_LABELS = {
    "current": "Current conditions",
    "overview": "The overview",
    "hourly": "Next 12 hours",
    "five_day": "5-day forecast",
    "alerts": "Weather bulletin",
    "regional": "Regional observations",
    "radar": "Radar",
    "satellite": "Satellite",
    "webcams": "Around the area",
    "almanac": "Almanac",
    "seasonal": "Seasonal",
    "headlines": "Headlines",
}
LOCAL_ON_THE_8S = ("current", "overview", "hourly")


def chyron_items(state: LocationState) -> List[Dict[str, str]]:
    """Weather only: NOW, then HOURLY, then 5-DAY. Never headlines."""
    fc = state.data.get("forecast") or {}
    items: List[Dict[str, str]] = []
    current = fc.get("current") or {}
    if current.get("temp") is not None:
        items.append({"group": "NOW", "text": f"{current['temp']}° {current.get('sky') or ''}".strip()})
    for hour in (fc.get("hourly") or [])[:12:2]:
        items.append({"group": "HOURLY", "text": f"{hour['label']} {hour['temp']}°"})
    for day in (fc.get("daily") or [])[:5]:
        if day.get("high") is None or day.get("low") is None:
            continue
        items.append({"group": "5-DAY", "text": f"{day['weekday']} {day['high']}°/{day['low']}°"})
    return items


def chyron_summary(items: List[Dict[str, str]], place: str) -> str:
    groups: Dict[str, List[str]] = {}
    for item in items:
        groups.setdefault(item["group"], []).append(item["text"])
    parts = [f"{group}: {', '.join(texts)}" for group, texts in groups.items()]
    return f"{place}. " + ". ".join(parts) + "." if parts else ""


def _image_url(image_id: str) -> str:
    return f"/api/live/weather/image/{image_id}"


def _boards(state: LocationState, scripts: Dict[str, List[Dict[str, Any]]], holidays: Any = ()) -> Dict[str, Any]:
    fc = state.data.get("forecast") or {}
    map_data = state.data.get("maps") or {}
    radar = map_data.get("radar") or {}
    satellite = map_data.get("satellite") or {}
    archive = state.data.get("archive") or {}
    sun = almanac.sun_facts(fc) if fc else {}
    overview = (scripts.get("overview") or [{}])[0].get("text") if scripts.get("overview") else ""
    facts_seasonal = segment_facts(state, today=_today(state), holidays=holidays).get("seasonal") or {}
    almanac_board: Dict[str, Any] = {}
    if sun or archive.get("record_high"):
        almanac_board = {
            **sun,
            "moon": almanac.moon_phase(),
            "record_high": archive.get("record_high"),
            "record_low": archive.get("record_low"),
            "archive_years": archive.get("years"),
            "today_label": archive.get("today"),
            "trivia": trivia_line(archive, state.place.city or "here"),
        }
    return {
        "current": fc.get("current") or None,
        "overview": {"text": overview, "days": (fc.get("daily") or [])[:2]} if overview else None,
        "hourly": fc.get("hourly") or [],
        "five_day": fc.get("daily") or [],
        "alerts": {"supported": state.place.is_us, "items": state.data.get("alerts") or []},
        "regional": state.data.get("regional") or [],
        "radar": (
            {
                "source": radar.get("source"),
                "marker": radar.get("marker"),
                "frames": [{"url": _image_url(f["image_id"]), "time": f["time"]} for f in radar.get("frames") or []],
            }
            if radar.get("frames")
            else None
        ),
        "satellite": (
            {"url": _image_url(satellite["image_id"]), "time": satellite.get("time"), "source": satellite.get("source")}
            if satellite.get("image_id")
            else None
        ),
        "webcams": [
            {"title": w.get("title"), "city": w.get("city"), "time": w.get("time"), "url": _image_url(w["image_id"])}
            for w in state.data.get("webcams") or []
        ],
        "almanac": almanac_board or None,
        "seasonal": facts_seasonal or None,
    }


def _today(state: LocationState):
    from datetime import date

    now = str((state.data.get("forecast") or {}).get("now") or "")[:10]
    try:
        return date.fromisoformat(now)
    except ValueError:
        return date.today()


def available_segments(boards: Dict[str, Any], headlines_ready: bool) -> List[str]:
    out = []
    if boards.get("current"):
        out.append("current")
    if boards.get("overview"):
        out.append("overview")
    if len(boards.get("hourly") or []) >= 2:
        out.append("hourly")
    if len(boards.get("five_day") or []) >= 2:
        out.append("five_day")
    alerts_board = boards.get("alerts") or {}
    if alerts_board.get("supported") and alerts_board.get("items"):
        out.append("alerts")
    if len(boards.get("regional") or []) >= 3:
        out.append("regional")
    if boards.get("radar"):
        out.append("radar")
    if boards.get("satellite"):
        out.append("satellite")
    if boards.get("webcams"):
        out.append("webcams")
    if boards.get("almanac"):
        out.append("almanac")
    if boards.get("seasonal"):
        out.append("seasonal")
    if headlines_ready:
        out.append("headlines")
    return out


def headlines_block(state: LocationState) -> Dict[str, Any]:
    news = state.data.get("headlines")
    if news is None:
        status = "failed" if "headlines" in state.errors else "pending"
        return {"status": status, "scopes": [], "failed": []}
    scopes = news.get("scopes") or []
    status = "ready" if scopes else ("failed" if news.get("failed") else "empty")
    return {"status": status, "scopes": scopes, "failed": news.get("failed") or []}


def egress_hosts(*, is_us: bool, webcams: bool) -> List[Dict[str, str]]:
    skip = set()
    if not is_us:
        skip |= {"api.weather.gov", "mesonet.agron.iastate.edu", "cdn.star.nesdis.noaa.gov"}
    else:
        skip |= {"api.rainviewer.com", "tilecache.rainviewer.com"}
    if not webcams:
        skip |= {"api.windy.com", "imgproxy.windy.com"}
    return [{"host": host, "purpose": purpose} for host, purpose in WEATHER_HOSTS.items() if host not in skip]


def build_payload(
    service: WeatherService,
    state: LocationState,
    *,
    location_source: str,
    household_place: str,
    music: List[Dict[str, Any]],
    music_note: str,
    intro_preroll: Optional[Dict[str, Any]] = None,
    preroll_root_found: bool = False,
) -> Dict[str, Any]:
    with state.lock:
        scripts = {k: list(v) for k, v in state.scripts.items()}
        version = state.scripts_version
        errors = dict(state.errors)
    boards = _boards(state, scripts, service.holidays())
    news = headlines_block(state)
    segments = available_segments(boards, news["status"] == "ready")
    settings = service.settings_factory()
    choice = service.voice_choice()
    spoken: Dict[str, List[Dict[str, Any]]] = {}
    for segment in segments:
        rows = scripts.get(segment) or []
        spoken[segment] = [
            {
                "text": row["text"],
                "source": row.get("source", "template"),
                "audio_url": (f"/api/live/weather/audio/{digest}.opus" if (digest := service.audio_for(row["text"])) else None),
            }
            for row in rows
        ]
    items = chyron_items(state)
    place_label = state.place.label
    narration: Dict[str, Any] = {"enabled": bool(settings.enabled), "ready": False}
    if choice is not None:
        engine, voice, _rate = choice
        narration["ready"] = service.tts.installed(engine, voice) or service.tts.engine_factory is not None
    error = ""
    if not (state.data.get("forecast") or {}).get("current") and "forecast" in errors:
        error = "Weather is temporarily unavailable — check LAN egress to api.open-meteo.com."
    first = (spoken.get("current") or [{}])[0].get("text") if spoken.get("current") else ""
    return {
        "enabled": True,
        "place": place_label,
        "latitude": state.place.latitude,
        "longitude": state.place.longitude,
        "location_source": location_source,
        "household_place": household_place,
        "country": state.place.country,
        "is_us": state.place.is_us,
        "error": error,
        "boards": boards,
        "segments": [{"id": seg, "label": SEGMENT_LABELS[seg]} for seg in segments],
        "local_on_the_8s": [seg for seg in LOCAL_ON_THE_8S if seg in segments],
        "scripts": spoken,
        "scripts_version": version,
        "chyron": items,
        "chyron_summary": chyron_summary(items, place_label),
        "headlines": news,
        "music": {"tracks": music, "note": music_note},
        "muzak": music[0] if music else None,
        "muzak_note": music_note,
        "narration": narration,
        "voiceover": first or "",
        "egress": egress_hosts(is_us=state.place.is_us, webcams=bool(settings.windy_api_key)),
        "intro_preroll": intro_preroll,
        "preroll_root_found": preroll_root_found,
    }
