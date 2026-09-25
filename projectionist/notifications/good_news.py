"""Persona-voiced Good News copy for watchlist / gap arrivals.

Arrival mail is never a download-client ping. Named-member whispers live in
``projectionist.notifications.whisper``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

_FORBIDDEN = ("download complete", "grabbed", "nzb", "torrent complete")

_GAP_HEADLINES = {
    "warm": "Good news from {curator_name} — {title}{year_bit} just filled a gap.",
    "direct": "{curator_name}: the gap for {title}{year_bit} is closed.",
    "analytical": "{curator_name} closed a collection gap: {title}{year_bit} is on the shelf.",
    "balanced": "{curator_name} has good news: {title}{year_bit} is on the shelf.",
}

_WATCH_HEADLINES = {
    "warm": "Good news from {curator_name} — {title}{year_bit}, the one you were watching for, is here.",
    "direct": "{curator_name}: {title}{year_bit} from the watchlist just arrived.",
    "analytical": "{curator_name} can report {title}{year_bit} is now in the library — off the watchlist.",
    "balanced": "{curator_name} has good news: {title}{year_bit} you were watching for is here.",
}

_GAP_BODY = {
    "warm": "A hole in the collection just filled. Come find it when you are ready.",
    "direct": "That missing title is on the shelf now.",
    "analytical": "A tracked collection gap resolved when this title landed in the library.",
    "balanced": "A collection gap just closed — this is not a download ping.",
}

_WATCH_BODY = {
    "warm": "Off the watchlist and onto the shelf. Whenever tonight is.",
    "direct": "The title you pinned is in the library.",
    "analytical": "A watchlist pin matched a newly added library title.",
    "balanced": "Something from a watchlist arrived — not a grab notification.",
}


def _band_for_preset(preset_id: Optional[str]) -> str:
    key = str(preset_id or "").strip().lower()
    if key in {"classic-curator", "midnight-host"}:
        return "warm"
    if key in {"archivist", "critic-scholar"}:
        return "analytical"
    if key in {"scout"}:
        return "direct"
    return "balanced"


def _year_bit(year: Any) -> str:
    if year in (None, ""):
        return ""
    try:
        return f" ({int(year)})"
    except (TypeError, ValueError):
        return f" ({year})"


def format_good_news(
    *,
    title: str,
    year: Any = None,
    source: str = "watchlist",
    curator_name: str = "Curator",
    preset_id: Optional[str] = None,
) -> Tuple[str, str]:
    """Return (headline, body) in persona voice. Never 'download complete'."""
    name = str(curator_name or "Curator").strip() or "Curator"
    label = str(title or "A title").strip() or "A title"
    year_bit = _year_bit(year)
    band = _band_for_preset(preset_id)
    is_gap = str(source or "").strip().lower() == "gap"
    headlines = _GAP_HEADLINES if is_gap else _WATCH_HEADLINES
    bodies = _GAP_BODY if is_gap else _WATCH_BODY
    headline = headlines[band].format(curator_name=name, title=label, year_bit=year_bit)
    body = bodies[band]
    lowered = f"{headline} {body}".lower()
    for banned in _FORBIDDEN:
        if banned in lowered:
            headline = f"{name} has good news: {label}{year_bit} is on the shelf."
            body = "A title you were waiting on is in the library."
            break
    return headline, body


def persona_from_db(db: Any) -> Tuple[str, Optional[str]]:
    """Resolve curator name + preset from the persona row, with safe defaults."""
    name = "Curator"
    preset: Optional[str] = None
    getter = getattr(db, "get_persona", None)
    if getter is None:
        return name, preset
    try:
        row = getter()
    except Exception:  # noqa: BLE001
        return name, preset
    if row is None:
        return name, preset
    keys = row.keys() if hasattr(row, "keys") else []
    if isinstance(row, Mapping):
        raw_name = row.get("curator_name")
        raw_preset = row.get("persona_preset_id")
    else:
        raw_name = row["curator_name"] if "curator_name" in keys else None
        raw_preset = row["persona_preset_id"] if "persona_preset_id" in keys else None
    if raw_name:
        name = str(raw_name).strip() or "Curator"
    if raw_preset:
        preset = str(raw_preset).strip() or None
    return name, preset
