"""Keep Plex's Live guide a week ahead, then roll the next week.

Tunarr's XMLTV ``programmingHours`` is the slice Plex ingests. The default is
12 hours. Plex does not re-read that file every hour, so a morning fetch runs
out in the evening: the grid becomes Unknown Airing and playback ends with
"This live TV session has ended". Station lineups can already be a week long;
only the published window was short.

This module asks the engine for seven days of programme titles and, before
that window is gone, rebuilds the next week from each station's saved lineup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)

GUIDE_HORIZON_DAYS = 7
GUIDE_HORIZON_HOURS = 24 * GUIDE_HORIZON_DAYS
# Roll the next week while the household still has two days of the current one.
REFILL_LEAD_HOURS = 48
# Guide ends snap to the hour; a week that is a few hours short is still a week.
HORIZON_SLACK_HOURS = 6
# Re-read into Plex often enough that a seven-day ingest cannot expire first.
PLEX_RELOAD_INTERVAL_HOURS = 20
PLEX_RELOAD_STATE_KEY = "live_guide_plex_reload_at"
_MS_PER_HOUR = 3_600_000


def programming_hours_to_set(current: Any, *, horizon_hours: int = GUIDE_HORIZON_HOURS) -> Optional[int]:
    """Hours to write, or None when the published window is already a week."""
    try:
        hours = int(current or 0)
    except (TypeError, ValueError):
        hours = 0
    target = max(1, int(horizon_hours))
    if hours >= target:
        return None
    return target


def hours_until(end: datetime, now: datetime) -> float:
    """Hours from ``now`` until ``end`` (negative when the guide already ended)."""
    return (end - now).total_seconds() / 3600.0


def parse_guide_instant(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def soonest_guide_hours(
    guide_times: Optional[Mapping[str, Any]],
    now: datetime,
) -> Optional[float]:
    """Hours until the earliest channel guide end, or None when no end is known."""
    if not isinstance(guide_times, Mapping) or not guide_times:
        return None
    ahead: List[float] = []
    for window in guide_times.values():
        if not isinstance(window, Mapping):
            continue
        end = parse_guide_instant(window.get("end"))
        if end is None:
            continue
        ahead.append(hours_until(end, now))
    if not ahead:
        return None
    return min(ahead)


def window_is_short(
    hours_ahead: Optional[float],
    *,
    horizon_hours: int = GUIDE_HORIZON_HOURS,
    slack_hours: int = HORIZON_SLACK_HOURS,
) -> bool:
    """True when the published guide does not cover about a week from now."""
    if hours_ahead is None:
        return True
    return float(hours_ahead) + float(slack_hours) < float(horizon_hours)


def window_needs_roll(
    hours_ahead: Optional[float],
    *,
    lead_hours: int = REFILL_LEAD_HOURS,
) -> bool:
    """True when the published guide is missing or inside the refill lead."""
    if hours_ahead is None:
        return True
    return float(hours_ahead) < float(lead_hours)


def lineup_cycle_hours(duration_ms: Any) -> float:
    try:
        ms = int(duration_ms or 0)
    except (TypeError, ValueError):
        return 0.0
    if ms <= 0:
        return 0.0
    return ms / _MS_PER_HOUR


def lineup_needs_week(
    duration_ms: Any,
    *,
    horizon_hours: int = GUIDE_HORIZON_HOURS,
    slack_hours: int = HORIZON_SLACK_HOURS,
) -> bool:
    """True when the station cycle is shorter than a week of real titles."""
    return lineup_cycle_hours(duration_ms) + float(slack_hours) < float(horizon_hours)


def plex_reload_due(
    last_epoch: Optional[float],
    now_epoch: float,
    *,
    interval_hours: int = PLEX_RELOAD_INTERVAL_HOURS,
) -> bool:
    if last_epoch is None:
        return True
    try:
        age = float(now_epoch) - float(last_epoch)
    except (TypeError, ValueError):
        return True
    return age >= float(interval_hours) * 3600.0


def _live_enabled(settings: Any) -> bool:
    flags = getattr(settings, "features", None)
    return bool(getattr(flags, "live_channels_enabled", False))


def _tunarr_url(settings: Any) -> str:
    tunarr = getattr(settings, "tunarr", None)
    return str(getattr(tunarr, "url", "") or "").strip()


def _read_reload_stamp(db: Any) -> Optional[float]:
    if db is None or not hasattr(db, "get_sync_state"):
        return None
    raw = db.get_sync_state(PLEX_RELOAD_STATE_KEY)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def maintain_guide_week(
    settings: Any,
    db: Any = None,
    *,
    client: Any = None,
    now: Optional[datetime] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    reload_plex: Optional[Callable[[], Mapping[str, Any]]] = None,
    refill_lineup: Optional[Callable[[str], Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Publish a week of guide titles and roll the next week before it expires.

    Lineup refill runs only when the published window is inside the lead and
    that station's cycle is shorter than a week. A week-long cycle is left
    alone so a maintenance pass does not reshuffle what is on the air.
    """
    if not _live_enabled(settings):
        return {"skipped": "live_off", "extended": False, "rolled": False}
    if client is None:
        base = _tunarr_url(settings)
        if not base:
            return {"skipped": "no_engine", "extended": False, "rolled": False}
        from projectionist.connectors.tunarr import TunarrClient

        client = TunarrClient(base, timeout=120)

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    if should_stop and should_stop():
        return {"skipped": "interrupted", "extended": False, "rolled": False}

    # Read the window first. Extending programming hours rebuilds XMLTV, so a
    # status read afterwards can already show the new week and hide the roll.
    try:
        status = client.get_guide_status() or {}
    except Exception as error:  # noqa: BLE001 — still try to lengthen the file
        logger.warning("live guide status failed: %s", error)
        status = {}
    hours_ahead = soonest_guide_hours(
        status.get("guideTimes") if isinstance(status, Mapping) else None,
        moment,
    )
    needs_roll = window_needs_roll(hours_ahead)
    short = window_is_short(hours_ahead)
    ensured = client.ensure_xmltv_programming_hours(GUIDE_HORIZON_HOURS)
    extended = bool(ensured.get("changed"))
    if (needs_roll or short) and not extended:
        try:
            client.put_xmltv_settings({"programmingHours": GUIDE_HORIZON_HOURS})
        except Exception as error:  # noqa: BLE001
            logger.warning("live guide rebuild failed: %s", error)
    rolled = needs_roll

    refilled: List[str] = []
    if rolled:
        from projectionist.live_channels.publish import (
            recipe_from_station_meta,
            refill_channel_lineup,
        )

        do_refill = refill_lineup
        for channel in client.list_channels() or []:
            if should_stop and should_stop():
                break
            if not isinstance(channel, Mapping):
                continue
            if not lineup_needs_week(channel.get("duration")):
                continue
            cid = str(channel.get("id") or channel.get("uuid") or "").strip()
            if not cid:
                continue
            if recipe_from_station_meta(settings, cid) is None:
                continue
            try:
                if do_refill is not None:
                    do_refill(cid)
                else:
                    refill_channel_lineup(client, cid, settings=settings)
            except Exception as error:  # noqa: BLE001 — one station must not stop the week
                logger.warning("live guide refill %s failed: %s", cid, error)
                continue
            refilled.append(cid)

    reload_result: Dict[str, Any] = {"reloaded": False}
    now_epoch = moment.timestamp()
    last_reload = _read_reload_stamp(db)
    due = plex_reload_due(last_reload, now_epoch)
    if extended or short or rolled or due:
        reloader = reload_plex
        if reloader is None:
            from projectionist.live_channels.plex_attach import reload_published_plex_guide

            def reloader() -> Mapping[str, Any]:
                return reload_published_plex_guide(settings)

        try:
            payload = reloader() or {}
            reload_result = dict(payload) if isinstance(payload, Mapping) else {"reloaded": False}
        except Exception as error:  # noqa: BLE001
            logger.warning("live guide plex reload failed: %s", error)
            reload_result = {"ok": False, "reloaded": False, "error": str(error)[:200]}
        if reload_result.get("reloaded") and db is not None and hasattr(db, "set_sync_state"):
            db.set_sync_state(PLEX_RELOAD_STATE_KEY, str(now_epoch))

    return {
        "skipped": None,
        "extended": extended,
        "rolled": rolled,
        "programming_hours": int(ensured.get("programmingHours") or GUIDE_HORIZON_HOURS),
        "hours_ahead": None if hours_ahead is None else round(float(hours_ahead), 2),
        "refilled": refilled,
        "plex": reload_result,
    }
