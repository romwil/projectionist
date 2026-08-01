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
    "Watch here or in Plex Live TV — same stations, both first-class."
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


_GUIDE_FLEX_SUFFIX = " · Up next"


def _nested_program(program: Mapping[str, Any]) -> Mapping[str, Any]:
    """Tunarr TvGuideProgram often nests the real title under ``program``."""
    nested = program.get("program")
    return nested if isinstance(nested, Mapping) else {}


def _nested_show(program: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = _nested_program(program)
    show = nested.get("show")
    if isinstance(show, Mapping):
        return show
    show = program.get("show")
    return show if isinstance(show, Mapping) else {}


def _is_guide_flex_placeholder(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    return text.endswith(_GUIDE_FLEX_SUFFIX) or text.lower() in {"flex", "filler", "continuity"}


def _program_title(program: Mapping[str, Any]) -> str:
    """Prefer show/movie title; Tunarr content slots nest titles under ``program``."""
    nested = _nested_program(program)
    show = _nested_show(program)
    nested_type = str(nested.get("type") or program.get("type") or "").strip().lower()

    # Episodes: show title is the guide headline; episode name is the subtitle.
    if nested_type == "episode" or show:
        show_title = str(show.get("title") or nested.get("showTitle") or program.get("showTitle") or "").strip()
        if show_title:
            return show_title

    for source in (program, nested):
        for key in ("title", "showTitle", "name"):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    episode = str(
        program.get("episodeTitle") or nested.get("episodeTitle") or nested.get("title") or ""
    ).strip()
    return episode


def _program_episode(program: Mapping[str, Any]) -> str:
    nested = _nested_program(program)
    primary = _program_title(program)
    for source in (program, nested):
        for key in ("episodeTitle", "episode_title", "subtitle", "secondaryTitle"):
            value = str(source.get(key) or "").strip()
            if value and value != primary:
                return value
    # Nested episode/movie ``title`` becomes the subtitle when the headline is the show.
    show = _nested_show(program)
    nested_type = str(nested.get("type") or "").strip().lower()
    if show or nested_type == "episode":
        ep = str(nested.get("title") or "").strip()
        if ep and ep != primary:
            return ep
    return ""


def _program_rating(program: Mapping[str, Any]) -> str:
    nested = _nested_program(program)
    show = _nested_show(program)
    for source in (program, nested, show):
        for key in ("contentRating", "content_rating", "rating", "ageRating"):
            raw = source.get(key)
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


def _plex_keys_from_mapping(source: Mapping[str, Any]) -> List[str]:
    """Collect bare + ``plex|…|key`` tails from common Tunarr/Plex id fields."""
    keys: List[str] = []
    for key in (
        "externalKey",
        "plexRatingKey",
        "ratingKey",
        "plex_rating_key",
        "grandparentRatingKey",
        "grandparentExternalKey",
    ):
        text = str(source.get(key) or "").strip()
        if not text:
            continue
        keys.append(text)
        if "|" in text:
            tail = text.rsplit("|", 1)[-1].strip()
            if tail:
                keys.append(tail)
    return keys


def _prefer_bare_plex_key(keys: Sequence[str]) -> str:
    for key in keys:
        text = str(key or "").strip()
        if text and "|" not in text:
            return text
    for key in keys:
        text = str(key or "").strip()
        if text:
            return text
    return ""


def _program_plex_rating_key(program: Mapping[str, Any]) -> str:
    """Best-effort Plex rating key from a Tunarr guide / now_playing row."""
    nested = _nested_program(program)
    keys: List[str] = []
    for source in (program, nested):
        if isinstance(source, Mapping):
            keys.extend(_plex_keys_from_mapping(source))
    # Content key — skip show-only grandparent fields already collected above when
    # a leaf externalKey exists (prefer first bare non-grandparent later via order).
    return _prefer_bare_plex_key(keys)


def _program_show_plex_rating_key(program: Mapping[str, Any]) -> str:
    """Show-level Plex key for dig-in (library indexes shows, not episodes)."""
    nested = _nested_program(program)
    show = _nested_show(program)
    keys: List[str] = []
    if isinstance(show, Mapping):
        keys.extend(_plex_keys_from_mapping(show))
    for source in (program, nested):
        if not isinstance(source, Mapping):
            continue
        for key in ("grandparentRatingKey", "grandparentExternalKey", "showRatingKey"):
            text = str(source.get(key) or "").strip()
            if text:
                keys.append(text)
                if "|" in text:
                    tail = text.rsplit("|", 1)[-1].strip()
                    if tail:
                        keys.append(tail)
    return _prefer_bare_plex_key(keys)


def _program_media_type(program: Mapping[str, Any]) -> str:
    """``show`` / ``movie`` for dig-in; empty when unknown."""
    nested = _nested_program(program)
    show = _nested_show(program)
    nested_type = str(nested.get("type") or program.get("type") or "").strip().lower()
    if nested_type in {"episode", "show"} or show:
        return "show"
    if nested_type == "movie":
        return "movie"
    # Soft signal: an episode subtitle implies TV without inventing a title.
    if _program_episode(program):
        return "show"
    if nested_type in {"flex", "filler", "continuity", "commercial"}:
        return ""
    return "movie" if _program_title(program) else ""


def _program_year(program: Mapping[str, Any]) -> Optional[int]:
    nested = _nested_program(program)
    show = _nested_show(program)
    for source in (program, nested, show):
        if not isinstance(source, Mapping):
            continue
        for key in ("year", "releaseYear", "originallyAvailableAt"):
            raw = source.get(key)
            if raw is None:
                continue
            if isinstance(raw, int):
                return raw if raw > 1000 else None
            text = str(raw).strip()
            if len(text) >= 4 and text[:4].isdigit():
                year = int(text[:4])
                return year if year > 1000 else None
    return None


def _program_overview(program: Mapping[str, Any]) -> str:
    nested = _nested_program(program)
    show = _nested_show(program)
    for source in (program, nested, show):
        if not isinstance(source, Mapping):
            continue
        for key in ("summary", "overview", "plot", "description", "tagline"):
            text = str(source.get(key) or "").strip()
            if text:
                return text
    return ""


def _program_season_episode_numbers(
    program: Mapping[str, Any],
) -> tuple[Optional[int], Optional[int]]:
    nested = _nested_program(program)

    def _as_int(value: Any) -> Optional[int]:
        if value is None or value is False:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number >= 0 else None

    season: Optional[int] = None
    episode: Optional[int] = None
    for source in (program, nested):
        if not isinstance(source, Mapping):
            continue
        if season is None:
            season = _as_int(
                source.get("seasonNumber")
                or source.get("season")
                or source.get("parentIndex")
            )
        if episode is None:
            episode = _as_int(
                source.get("episodeNumber")
                or source.get("episode")
                or source.get("index")
            )
    return season, episode


def _program_is_flex(program: Mapping[str, Any]) -> bool:
    for key in ("type", "programType", "kind"):
        value = str(program.get(key) or "").strip().lower()
        if value in {"flex", "filler", "continuity", "commercial"}:
            return True
    # Top-level guideFlexTitle placeholders (even before nested title resolution).
    top_title = str(program.get("title") or "").strip()
    if _is_guide_flex_placeholder(top_title):
        return True
    title = _program_title(program).lower()
    return title in {"flex", "filler", "continuity"}


def _prefer_real_titles_over_flex(
    slots: Mapping[str, Optional[Dict[str, Any]]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Return now/next unchanged — never paint the next episode onto a flex pad.

    Older builds copied the following content title/episode onto ``now`` while
    keeping the flex ``start``/``stop``. The Live OSD then showed mid-episode
    progress for e.g. “The Big Gold Strike” while Tunarr concatenated Continuity
    filler (vintage promos). The real upcoming title already lives in ``next``.
    """
    now = slots.get("now") if isinstance(slots.get("now"), Mapping) else None
    nxt = slots.get("next") if isinstance(slots.get("next"), Mapping) else None
    return {
        "now": dict(now) if now else None,
        "next": dict(nxt) if nxt else None,
    }


def _relabel_flex_program_placeholders(programs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep guideFlexTitle pads labeled as flex (do not steal the next episode).

    Relabeling made EPG cells look like the upcoming Gilligan episode during
    Continuity bumps — tuning that cell played filler while the guide lied.
    """
    return [dict(p) for p in programs]


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
    if duration_ms is None:
        duration_ms = program.get("duration_ms")
    dur_sec = _duration_to_seconds(duration_ms) if duration_ms is not None else None
    if stop is None and start is not None and dur_sec is not None:
        stop = start + dur_sec
    # Progress / remaining follow file EOF when Tunarr padded stop past duration.
    progress_stop = stop
    if start is not None and dur_sec is not None and stop is not None:
        progress_stop = min(float(stop), start + dur_sec)
    elif start is not None and dur_sec is not None:
        progress_stop = start + dur_sec
    rating = _program_rating(program)
    is_paused = bool(program.get("isPaused") or program.get("is_paused"))
    progress = program_airing_progress(
        start,
        progress_stop,
        now=now,
        time_remaining=program.get("timeRemaining") or program.get("time_remaining"),
        is_paused=is_paused,
    )
    episode = _program_episode(program)
    plex_key = _program_plex_rating_key(program)
    show_plex_key = _program_show_plex_rating_key(program)
    media_type = _program_media_type(program)
    year = _program_year(program)
    overview = _program_overview(program)
    season_number, episode_number = _program_season_episode_numbers(program)
    return {
        "title": title,
        "episode_title": episode or None,
        "season": season_number,
        "episode": episode_number,
        "year": year,
        "overview": overview or None,
        "media_type": media_type or None,
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
        "duration_seconds": int(round(dur_sec)) if dur_sec is not None else None,
        "plex_rating_key": plex_key or None,
        "show_plex_rating_key": show_plex_key or None,
    }


def _sorted_programs(programs: Sequence[Any]) -> List[Mapping[str, Any]]:
    items = [p for p in programs if isinstance(p, Mapping)]

    def sort_key(program: Mapping[str, Any]) -> float:
        start = _to_epoch_seconds(program.get("start") or program.get("startTime"))
        return float(start) if start is not None else 0.0

    return sorted(items, key=sort_key)



def now_playing_past_file_eof(
    playing: Optional[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
) -> bool:
    """True when Tunarr now_playing elapsed exceeds content ``duration`` (ms).

    Guide ``stop`` is often padded past the file end, so wall-clock can still
    show minutes remaining while ffmpeg has already left the file (or seeks
    past EOF). Use file duration, not stop, for this check.
    """
    if not isinstance(playing, Mapping):
        return False
    ts_ms = int((time.time() if now is None else float(now)) * 1000)
    try:
        start = int(playing.get("start") or 0)
        duration = int(playing.get("duration") or 0)
    except (TypeError, ValueError):
        return False
    if start <= 0 or duration <= 0:
        return False
    return (ts_ms - start) > duration


def program_airing_bounds(
    program: Mapping[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    """Return ``(start, effective_stop)`` for wall-clock airing membership.

    Tunarr often pads ``stop`` past the file's ``duration``. Once wall-clock is
    past file EOF the stream has moved on — treat the airing as ended even when
    the padded stop is still in the future.
    """
    start = _to_epoch_seconds(program.get("start") or program.get("startTime"))
    stop = _to_epoch_seconds(
        program.get("stop")
        or program.get("end")
        or program.get("endTime")
        or program.get("stopTime")
    )
    duration_ms = program.get("duration")
    if duration_ms is None:
        duration_ms = program.get("duration_ms")
    if duration_ms is None and program.get("duration_seconds") is not None:
        try:
            duration_ms = float(program.get("duration_seconds")) * 1000.0
        except (TypeError, ValueError):
            duration_ms = None
    dur_sec = _duration_to_seconds(duration_ms) if duration_ms is not None else None
    if stop is None and start is not None and dur_sec is not None:
        stop = start + dur_sec
    if start is not None and dur_sec is not None:
        file_end = start + dur_sec
        if stop is None:
            stop = file_end
        else:
            stop = min(float(stop), file_end)
    return start, stop


def pick_now_and_next(
    programs: Sequence[Any],
    *,
    now: Optional[float] = None,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Choose the airing program and the following one from a guide window.

    When Tunarr pads an ended title's ``stop`` past the next item's ``start``
    (file-duration vs guide-slot mismatch), multiple rows can contain ``now``.
    Prefer the latest ``start`` so the OSD/playhead matches the live edge
    instead of a prior title that still claims a few minutes left.

    Past file EOF (``duration``) also ends an airing even when padded ``stop``
    still lies ahead — so a dead Dora cannot stay "now" after the stream rolled
    to MythBusters.
    """
    ts = time.time() if now is None else float(now)
    ordered = _sorted_programs(programs)
    now_prog: Optional[Dict[str, Any]] = None
    next_prog: Optional[Dict[str, Any]] = None
    airing: List[tuple[float, int, Mapping[str, Any]]] = []
    first_future: Optional[Mapping[str, Any]] = None
    for index, program in enumerate(ordered):
        start, stop = program_airing_bounds(program)
        if start is not None and stop is not None and start <= ts < stop:
            airing.append((float(start), index, program))
            continue
        if (
            first_future is None
            and start is not None
            and start > ts
            and not airing
        ):
            first_future = program
    if airing:
        # Latest start wins among overlaps (Tunarr stop-overrun).
        airing.sort(key=lambda row: row[0])
        _start, index, program = airing[-1]
        now_prog = _normalize_program(program, now=ts)
        for j in range(index + 1, len(ordered)):
            next_prog = _normalize_program(ordered[j], now=ts)
            if next_prog:
                break
    elif first_future is not None:
        next_prog = _normalize_program(first_future, now=ts)
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
        row["programs"] = _relabel_flex_program_placeholders(normalized)
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
            if playing and not now_playing_past_file_eof(playing, now=ts):
                slots = {"now": _normalize_program(playing, now=ts), "next": None}
        # Nested Tunarr content + now_playing often beats an empty guide parse;
        # also prefer real titles over guideFlexTitle pads for OSD / on-now.
        if slots["now"] is None or (
            slots["now"].get("is_flex")
            and _is_guide_flex_placeholder(str(slots["now"].get("title") or ""))
        ):
            try:
                playing = tunarr_client.get_now_playing(cid)
            except Exception:  # noqa: BLE001
                playing = None
            playing_norm = _normalize_program(playing, now=ts) if playing else None
            # Past file EOF: now_playing often keeps the ended title with a padded
            # stop while the guide/stream already rolled to the next airing.
            if playing_norm and now_playing_past_file_eof(playing, now=ts):
                playing_norm = None
            if playing_norm and not playing_norm.get("is_flex"):
                next_slot = slots.get("next")
                slots = {"now": playing_norm, "next": next_slot}
                if next_slot is None:
                    guide_next = pick_now_and_next(programs, now=ts).get("next")
                    if guide_next and not guide_next.get("is_flex"):
                        slots["next"] = guide_next
        slots = _prefer_real_titles_over_flex(slots)
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

    from projectionist.live_channels.airing_why import enrich_channels_with_airing_why

    channels = enrich_channels_with_airing_why(settings, channels)

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
