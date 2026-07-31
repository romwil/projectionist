"""Read-only Tunarr guide snapshots for household “On now” and `/live` EPG.

Empty-safe when the feature is off or Tunarr is unreachable. Playback itself
goes through the auth’d stream proxy — this module only shapes guide data.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.connectors.tunarr import TunarrClient
from projectionist.youth.rating_gate import content_rating_allowed, normalize_content_rating

logger = logging.getLogger(__name__)

# On-now: short window (now + next). EPG grid uses a wider default.
GUIDE_WINDOW_SECONDS = 3 * 3600
GUIDE_GRID_WINDOW_SECONDS = 6 * 3600
MAX_CHANNELS = 24
MAX_GUIDE_CHANNELS = 48

DUAL_WATCH_HINT = (
    "Watch in Projectionist (/live) or open Plex → Live TV — both are first-class."
)


def _empty_snapshot(
    *,
    enabled: bool = False,
    ready: bool = False,
    reason: str = "",
    error: str = "",
) -> Dict[str, Any]:
    return {
        "enabled": enabled,
        "ready": ready,
        "channels": [],
        "count": 0,
        "generated_at": time.time(),
        "reason": reason,
        "error": error,
        "plex_hint": DUAL_WATCH_HINT,
        "watch_hint": DUAL_WATCH_HINT,
    }


def _program_title(program: Mapping[str, Any]) -> str:
    # Prefer show/movie title; episode title is a separate subtitle field.
    for key in ("title", "showTitle", "name"):
        value = str(program.get(key) or "").strip()
        if value:
            return value
    episode = str(program.get("episodeTitle") or "").strip()
    return episode


def _program_episode(program: Mapping[str, Any]) -> str:
    for key in ("episodeTitle", "episode_title", "subtitle", "secondaryTitle"):
        value = str(program.get(key) or "").strip()
        if value:
            # Avoid duplicating the primary title when Tunarr only has one field.
            primary = _program_title(program)
            if value == primary:
                continue
            return value
    return ""


def _program_rating(program: Mapping[str, Any]) -> str:
    for key in ("contentRating", "content_rating", "rating", "ageRating"):
        raw = program.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _channel_icon_url(meta: Mapping[str, Any]) -> str:
    icon = meta.get("icon")
    if isinstance(icon, Mapping):
        path = str(icon.get("path") or icon.get("url") or "").strip()
        if path:
            return path
    for key in ("icon_url", "iconUrl", "logo"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return ""


def _program_is_flex(program: Mapping[str, Any]) -> bool:
    for key in ("type", "programType", "kind"):
        value = str(program.get(key) or "").strip().lower()
        if value in {"flex", "filler", "continuity", "commercial"}:
            return True
    title = _program_title(program).lower()
    return title in {"flex", "filler", "continuity"}


def _to_epoch_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            return ts / 1000.0
        return ts
    text = str(value).strip()
    if not text:
        return None
    try:
        # ISO-8601
        if "T" in text or text.endswith("Z"):
            from datetime import datetime

            normalized = text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        pass
    try:
        ts = float(text)
    except ValueError:
        return None
    if ts > 1e12:
        return ts / 1000.0
    return ts


def _duration_to_seconds(value: Any) -> Optional[float]:
    """Normalize Tunarr duration / timeRemaining (milliseconds) to seconds."""
    if value is None:
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if raw < 0:
        return None
    # Tunarr guide ``duration`` / ``timeRemaining`` are ms. Values under 1000 are
    # treated as seconds so small test fixtures stay convenient.
    if raw >= 1000:
        return raw / 1000.0
    return raw


def program_airing_progress(
    start: Optional[float],
    stop: Optional[float],
    *,
    now: Optional[float] = None,
    time_remaining: Any = None,
    is_paused: bool = False,
) -> Dict[str, Any]:
    """Derive airing progress from Tunarr ``TvGuideProgram`` start/stop.

    Tunarr does not expose a dedicated percent field — ``GET …/now_playing`` and
    guide lineups return ``start`` / ``stop`` / ``duration`` (ms). Optional
    ``isPaused`` + ``timeRemaining`` apply to on-demand paused slots.
    """
    ts = time.time() if now is None else float(now)
    result: Dict[str, Any] = {
        "started_at": start,
        "ends_at": stop,
        "seconds_elapsed": None,
        "seconds_remaining": None,
        "percent": None,
        "is_paused": bool(is_paused),
    }
    remaining_hint = _duration_to_seconds(time_remaining)
    if start is None or stop is None:
        if remaining_hint is not None:
            result["seconds_remaining"] = max(0, int(round(remaining_hint)))
        return result
    duration = stop - start
    if duration <= 0:
        return result
    elapsed = max(0.0, min(duration, ts - start))
    remaining = max(0.0, stop - ts)
    if is_paused and remaining_hint is not None:
        remaining = max(0.0, min(duration, remaining_hint))
        elapsed = max(0.0, duration - remaining)
    percent = round((elapsed / duration) * 100.0, 1)
    result["seconds_elapsed"] = int(round(elapsed))
    result["seconds_remaining"] = int(round(remaining))
    result["percent"] = max(0.0, min(100.0, percent))
    return result


def _normalize_program(
    program: Optional[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(program, Mapping):
        return None
    title = _program_title(program)
    if not title:
        return None
    start = _to_epoch_seconds(program.get("start") or program.get("startTime"))
    stop = _to_epoch_seconds(
        program.get("stop")
        or program.get("end")
        or program.get("endTime")
        or program.get("stopTime")
    )
    duration_ms = program.get("duration")
    if stop is None and start is not None and duration_ms is not None:
        dur_sec = _duration_to_seconds(duration_ms)
        if dur_sec is not None:
            stop = start + dur_sec
    rating = _program_rating(program)
    is_paused = bool(program.get("isPaused") or program.get("is_paused"))
    progress = program_airing_progress(
        start,
        stop,
        now=now,
        time_remaining=program.get("timeRemaining") or program.get("time_remaining"),
        is_paused=is_paused,
    )
    episode = _program_episode(program)
    return {
        "title": title,
        "episode_title": episode or None,
        "start": start,
        "stop": stop,
        "started_at": progress["started_at"],
        "ends_at": progress["ends_at"],
        "seconds_elapsed": progress["seconds_elapsed"],
        "seconds_remaining": progress["seconds_remaining"],
        "percent": progress["percent"],
        "is_paused": progress["is_paused"],
        "content_rating": rating or None,
        "is_flex": _program_is_flex(program),
    }


def _sorted_programs(programs: Sequence[Any]) -> List[Mapping[str, Any]]:
    items = [p for p in programs if isinstance(p, Mapping)]

    def sort_key(program: Mapping[str, Any]) -> float:
        start = _to_epoch_seconds(program.get("start") or program.get("startTime"))
        return float(start) if start is not None else 0.0

    return sorted(items, key=sort_key)


def pick_now_and_next(
    programs: Sequence[Any],
    *,
    now: Optional[float] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Choose the airing program and the following one from a guide window."""
    ts = time.time() if now is None else float(now)
    ordered = _sorted_programs(programs)
    now_prog: Optional[Dict[str, Any]] = None
    next_prog: Optional[Dict[str, Any]] = None
    for index, program in enumerate(ordered):
        start = _to_epoch_seconds(program.get("start") or program.get("startTime"))
        stop = _to_epoch_seconds(
            program.get("stop")
            or program.get("end")
            or program.get("endTime")
            or program.get("stopTime")
        )
        duration_ms = program.get("duration")
        if stop is None and start is not None and duration_ms is not None:
            dur_sec = _duration_to_seconds(duration_ms)
            stop = start + dur_sec if dur_sec is not None else None
        if start is not None and stop is not None and start <= ts < stop:
            now_prog = _normalize_program(program, now=ts)
            if index + 1 < len(ordered):
                next_prog = _normalize_program(ordered[index + 1], now=ts)
            break
        if start is not None and start > ts:
            # Nothing currently airing in the window; surface the upcoming slot.
            if now_prog is None:
                next_prog = _normalize_program(program, now=ts)
            break
    if now_prog is None and next_prog is None and ordered:
        # Fallback: first program as "now" when timestamps are missing.
        now_prog = _normalize_program(ordered[0], now=ts)
        if len(ordered) > 1:
            next_prog = _normalize_program(ordered[1], now=ts)
    return {"now": now_prog, "next": next_prog}


def _youth_allows_program(
    program: Optional[Mapping[str, Any]],
    *,
    max_rating: str,
) -> bool:
    """Filter only when a rating is present; unrated guide titles stay visible."""
    if not program:
        return True
    raw = program.get("content_rating")
    if not normalize_content_rating(raw):
        return True
    return content_rating_allowed(raw, max_rating=max_rating)


def apply_youth_filter_to_on_now(
    channels: Sequence[Mapping[str, Any]],
    *,
    max_rating: str,
) -> List[Dict[str, Any]]:
    """Drop / scrub guide rows that exceed the youth ceiling when rated."""
    ceiling = str(max_rating or "").strip()
    if not ceiling:
        return [dict(c) for c in channels if isinstance(c, Mapping)]
    out: List[Dict[str, Any]] = []
    for channel in channels:
        if not isinstance(channel, Mapping):
            continue
        row = dict(channel)
        now = row.get("now") if isinstance(row.get("now"), Mapping) else None
        nxt = row.get("next") if isinstance(row.get("next"), Mapping) else None
        if now and not _youth_allows_program(now, max_rating=ceiling):
            continue
        if not now and nxt and not _youth_allows_program(nxt, max_rating=ceiling):
            continue
        if nxt and not _youth_allows_program(nxt, max_rating=ceiling):
            row["next"] = None
        programs = row.get("programs")
        if isinstance(programs, list):
            row["programs"] = [
                p
                for p in programs
                if isinstance(p, Mapping) and _youth_allows_program(p, max_rating=ceiling)
            ]
        out.append(row)
    return out


def youth_allows_channel_now(
    channel: Mapping[str, Any],
    *,
    max_rating: str,
) -> bool:
    """True when the channel's current (or next) rated program is within the ceiling."""
    ceiling = str(max_rating or "").strip()
    if not ceiling:
        return True
    now = channel.get("now") if isinstance(channel.get("now"), Mapping) else None
    nxt = channel.get("next") if isinstance(channel.get("next"), Mapping) else None
    if now:
        return _youth_allows_program(now, max_rating=ceiling)
    if nxt:
        return _youth_allows_program(nxt, max_rating=ceiling)
    return True


def _lineup_programs(lineup: Mapping[str, Any]) -> List[Any]:
    for key in ("programs", "lineup", "items"):
        value = lineup.get(key)
        if isinstance(value, list):
            return value
    return []


def _channel_row_from_guide(
    cid: str,
    *,
    meta: Mapping[str, Any],
    lineup: Any,
    programs: Sequence[Any],
    slots: Mapping[str, Optional[Dict[str, Any]]],
    include_programs: bool = False,
) -> Dict[str, Any]:
    name = str(
        meta.get("name")
        or meta.get("channelName")
        or (lineup.get("name") if isinstance(lineup, Mapping) else "")
        or f"Channel {meta.get('number') or ''}".strip()
        or "Channel"
    ).strip()
    number_raw = meta.get("number")
    if number_raw is None and isinstance(lineup, Mapping):
        number_raw = lineup.get("number")
    try:
        number = int(number_raw) if number_raw is not None else None
    except (TypeError, ValueError):
        number = None
    row: Dict[str, Any] = {
        "id": cid,
        "name": name or "Channel",
        "number": number,
        "icon_url": _channel_icon_url(meta) or None,
        "now": slots.get("now"),
        "next": slots.get("next"),
    }
    if include_programs:
        normalized: List[Dict[str, Any]] = []
        for program in _sorted_programs(programs):
            item = _normalize_program(program)
            if item:
                normalized.append(item)
        row["programs"] = normalized
    return row


def _sort_channels(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    channels.sort(
        key=lambda c: (
            c["number"] is None,
            c["number"] if c["number"] is not None else 0,
            str(c.get("name") or "").lower(),
        )
    )
    return channels


def build_on_now_snapshot(
    settings: Any,
    *,
    youth_max_rating: Optional[str] = None,
    now: Optional[float] = None,
    client: Optional[TunarrClient] = None,
    window_seconds: int = GUIDE_WINDOW_SECONDS,
    max_channels: int = MAX_CHANNELS,
    include_programs: bool = False,
) -> Dict[str, Any]:
    """Build a household-readable guide snapshot (never raises)."""
    features = getattr(settings, "features", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))
    if not enabled:
        return _empty_snapshot(enabled=False, reason="live_channels_disabled")

    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        return _empty_snapshot(enabled=True, reason="tunarr_url_missing")

    ts = time.time() if now is None else float(now)
    window = max(GUIDE_WINDOW_SECONDS, int(window_seconds or GUIDE_WINDOW_SECONDS))
    limit = max(1, min(int(max_channels or MAX_CHANNELS), 100))
    try:
        tunarr_client = client or TunarrClient(url, timeout=8)
        channels_meta = tunarr_client.list_channels()
        guide_by_id = tunarr_client.get_all_channel_guides(ts, ts + window)
    except Exception as error:  # noqa: BLE001
        logger.debug("Live Channels on-now unavailable: %s", error)
        return _empty_snapshot(
            enabled=True,
            reason="tunarr_unreachable",
            error=str(error)[:240],
        )

    meta_by_id: Dict[str, Mapping[str, Any]] = {}
    for item in channels_meta or []:
        if not isinstance(item, Mapping):
            continue
        cid = str(item.get("id") or item.get("uuid") or "").strip()
        if cid:
            meta_by_id[cid] = item

    # Prefer guide keys; fall back to channel list alone.
    channel_ids: List[str] = []
    if isinstance(guide_by_id, dict) and guide_by_id:
        channel_ids = [str(k) for k in guide_by_id.keys()]
    else:
        channel_ids = list(meta_by_id.keys())

    channels: List[Dict[str, Any]] = []
    for cid in channel_ids[:limit]:
        meta = meta_by_id.get(cid) or {}
        lineup = guide_by_id.get(cid) if isinstance(guide_by_id, dict) else None
        programs: List[Any] = []
        if isinstance(lineup, Mapping):
            programs = _lineup_programs(lineup)
            if not meta:
                meta = lineup
        slots = pick_now_and_next(programs, now=ts)
        if slots["now"] is None and slots["next"] is None and not programs:
            # Best-effort now_playing fallback when the guide window is empty.
            try:
                playing = tunarr_client.get_now_playing(cid)
            except Exception:  # noqa: BLE001
                playing = None
            if playing:
                slots = {"now": _normalize_program(playing, now=ts), "next": None}
        channels.append(
            _channel_row_from_guide(
                cid,
                meta=meta,
                lineup=lineup,
                programs=programs,
                slots=slots,
                include_programs=include_programs,
            )
        )

    _sort_channels(channels)

    ceiling = str(youth_max_rating or "").strip()
    if ceiling:
        channels = apply_youth_filter_to_on_now(channels, max_rating=ceiling)

    ready = bool(channels)
    return {
        "enabled": True,
        "ready": ready,
        "channels": channels,
        "count": len(channels),
        "generated_at": ts,
        "window_seconds": window,
        "reason": "" if ready else "no_channels",
        "error": "",
        "plex_hint": DUAL_WATCH_HINT,
        "watch_hint": DUAL_WATCH_HINT,
    }


def build_guide_snapshot(
    settings: Any,
    *,
    youth_max_rating: Optional[str] = None,
    now: Optional[float] = None,
    client: Optional[TunarrClient] = None,
    hours: float = 6.0,
) -> Dict[str, Any]:
    """Wider channel × time guide for the `/live` newspaper EPG."""
    hours_clamped = max(1.0, min(float(hours or 6.0), 12.0))
    window = int(hours_clamped * 3600)
    snap = build_on_now_snapshot(
        settings,
        youth_max_rating=youth_max_rating,
        now=now,
        client=client,
        window_seconds=max(window, GUIDE_GRID_WINDOW_SECONDS),
        max_channels=MAX_GUIDE_CHANNELS,
        include_programs=True,
    )
    snap["hours"] = hours_clamped
    return snap
