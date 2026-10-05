"""Stale-while-revalidate guide snapshots for ``/live``, On Now, and youth picks.

``build_on_now_snapshot`` / ``build_guide_snapshot`` call Tunarr synchronously
(channel list + guide window + up to two ``now_playing`` probes per channel, 8s
timeouts). That is fine for a background worker and fatal for first paint.

Request handlers should use :func:`get_guide_snapshot` / :func:`get_on_now_snapshot`:
the last good guide is served immediately (with "now / next" re-derived from the
cached programs so stale never lies), and Tunarr is only asked in the background.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional

from projectionist.live_channels import guide as _guide
from projectionist.live_channels.guide import (
    DUAL_WATCH_HINT,
    _empty_snapshot,
    clamp_flex_progress_to_next,
    program_airing_bounds,
    program_airing_progress,
)
from projectionist.swr_cache import SwrCache, SwrResult

logger = logging.getLogger(__name__)

# Guide rows are cheap to re-derive; Tunarr guide generation is not.
GUIDE_SOFT_TTL_SECONDS = 30.0
# Window is 6h+; a two-hour-old guide still has hours of valid programming.
GUIDE_HARD_TTL_SECONDS = 2 * 3600.0
# Briefly show an honest upstream error when there is nothing better cached.
GUIDE_DEGRADED_SOFT_TTL_SECONDS = 5.0
# Never wait on Tunarr/Docker/Plex on the request path. A cold start returns
# the warming skeleton immediately; the last guide (memory or disk) paints
# while a refresh runs behind it.
GUIDE_COLD_WAIT_SECONDS = 0.0

GUIDE_CACHE = SwrCache(
    "live_guide",
    soft_ttl=GUIDE_SOFT_TTL_SECONDS,
    hard_ttl=GUIDE_HARD_TTL_SECONDS,
    durable=True,
)
ON_NOW_CACHE = SwrCache(
    "live_on_now",
    soft_ttl=GUIDE_SOFT_TTL_SECONDS,
    hard_ttl=GUIDE_HARD_TTL_SECONDS,
    durable=True,
)


def invalidate_live_guide_cache() -> None:
    """Mark guide/on-now stale (settings change, publish, refill)."""
    GUIDE_CACHE.invalidate()
    ON_NOW_CACHE.invalidate()


def _accept_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """Do not let an unreachable-Tunarr error replace a good cached guide."""
    return str(snapshot.get("reason") or "") != "tunarr_unreachable"


def _cache_key(settings: Any, *, youth_max_rating: Optional[str], extra: str) -> str:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    ceiling = str(youth_max_rating or "").strip()
    return f"url={url}|youth={ceiling}|{extra}"


def _warming_snapshot(*, hours: Optional[float] = None) -> Dict[str, Any]:
    snap = _empty_snapshot(enabled=True, ready=False, reason="warming")
    snap["warming"] = True
    if hours is not None:
        snap["hours"] = hours
    return snap


def rebase_snapshot_to_now(
    snapshot: Mapping[str, Any],
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Re-derive each channel's now/next (and progress) from its cached programs.

    Only rows that carry normalized ``programs`` are touched; on-now snapshots
    without programs are returned unchanged. Never raises.
    """
    ts = time.time() if now is None else float(now)
    channels_in = snapshot.get("channels")
    if not isinstance(channels_in, list):
        return dict(snapshot)
    channels: List[Any] = []
    for channel in channels_in:
        programs = channel.get("programs") if isinstance(channel, Mapping) else None
        if not isinstance(programs, list) or not programs:
            channels.append(channel)
            continue
        slots = _slots_from_normalized(programs, ts)
        if slots["now"] is None and slots["next"] is None:
            channels.append(channel)
            continue
        row = dict(channel)
        row["now"] = slots["now"]
        row["next"] = slots["next"]
        channels.append(row)
    out = dict(snapshot)
    out["channels"] = channels
    return out


def _with_progress(program: Mapping[str, Any], ts: float) -> Dict[str, Any]:
    row = dict(program)
    start, stop = program_airing_bounds(program)
    progress = program_airing_progress(
        start,
        stop,
        now=ts,
        is_paused=bool(row.get("is_paused")),
    )
    row["started_at"] = progress["started_at"]
    row["ends_at"] = progress["ends_at"]
    row["seconds_elapsed"] = progress["seconds_elapsed"]
    row["seconds_remaining"] = progress["seconds_remaining"]
    row["percent"] = progress["percent"]
    return row


def _slots_from_normalized(
    programs: List[Any],
    ts: float,
) -> Dict[str, Optional[Dict[str, Any]]]:
    ordered = sorted(
        (p for p in programs if isinstance(p, Mapping)),
        key=lambda p: float(p.get("start") or 0.0),
    )
    airing_index: Optional[int] = None
    airing_start = -1.0
    first_future: Optional[int] = None
    for index, program in enumerate(ordered):
        start, stop = program_airing_bounds(program)
        if start is not None and stop is not None and start <= ts < stop:
            if float(start) >= airing_start:
                airing_start = float(start)
                airing_index = index
        elif first_future is None and start is not None and start > ts and airing_index is None:
            first_future = index

    now_prog: Optional[Dict[str, Any]] = None
    next_prog: Optional[Dict[str, Any]] = None
    if airing_index is not None:
        now_prog = _with_progress(ordered[airing_index], ts)
        flex_fallback: Optional[Dict[str, Any]] = None
        for candidate in ordered[airing_index + 1 :]:
            if candidate.get("is_flex"):
                if flex_fallback is None:
                    flex_fallback = _with_progress(candidate, ts)
                continue
            next_prog = _with_progress(candidate, ts)
            break
        if next_prog is None:
            next_prog = flex_fallback
    elif first_future is not None:
        next_prog = _with_progress(ordered[first_future], ts)
    return clamp_flex_progress_to_next({"now": now_prog, "next": next_prog}, now=ts)


def _is_trivial(settings: Any) -> Optional[Dict[str, Any]]:
    """Disabled / unconfigured guides are instant — no cache needed."""
    features = getattr(settings, "features", None)
    if not bool(getattr(features, "live_channels_enabled", False)):
        return _empty_snapshot(enabled=False, reason="live_channels_disabled")
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        return _empty_snapshot(enabled=True, reason="tunarr_url_missing")
    return None


def _finish(result: SwrResult) -> Dict[str, Any]:
    out = result.annotated()
    out.setdefault("plex_hint", DUAL_WATCH_HINT)
    out.setdefault("watch_hint", DUAL_WATCH_HINT)
    if result.built_at is not None:
        out["cache_age_seconds"] = max(0, int(time.time() - result.built_at))
    return out


def get_guide_snapshot(
    settings: Any,
    *,
    youth_max_rating: Optional[str] = None,
    hours: float = 6.0,
    cold_wait: float = GUIDE_COLD_WAIT_SECONDS,
    db: Any = None,
) -> Dict[str, Any]:
    """``/live`` EPG guide — cached, never blocks on Tunarr."""
    trivial = _is_trivial(settings)
    if trivial is not None:
        trivial.update({"cached": False, "stale": False, "warming": False})
        return trivial
    hours_clamped = max(1.0, min(float(hours or 6.0), 12.0))
    key = _cache_key(settings, youth_max_rating=youth_max_rating, extra=f"guide|h={hours_clamped}")

    def _build() -> Dict[str, Any]:
        return _guide.build_guide_snapshot(
            settings,
            youth_max_rating=youth_max_rating,
            hours=hours_clamped,
        )

    result = GUIDE_CACHE.get(
        key,
        _build,
        db=db,
        warming=lambda: _warming_snapshot(hours=hours_clamped),
        accept=_accept_snapshot,
        cold_wait=cold_wait,
        cold_soft_ttl=GUIDE_DEGRADED_SOFT_TTL_SECONDS,
        rebase=rebase_snapshot_to_now,
    )
    return _finish(result)


def get_on_now_snapshot(
    settings: Any,
    *,
    youth_max_rating: Optional[str] = None,
    cold_wait: float = GUIDE_COLD_WAIT_SECONDS,
    db: Any = None,
) -> Dict[str, Any]:
    """Household On Now rows — cached, never blocks on Tunarr.

    Served from the (richer) guide cache when it already holds this audience so
    one Tunarr round-trip feeds ``/live`` and every On Now widget.
    """
    trivial = _is_trivial(settings)
    if trivial is not None:
        trivial.update({"cached": False, "stale": False, "warming": False})
        return trivial
    key = _cache_key(settings, youth_max_rating=youth_max_rating, extra="on-now")

    def _build() -> Dict[str, Any]:
        return _guide.build_on_now_snapshot(settings, youth_max_rating=youth_max_rating)

    result = ON_NOW_CACHE.get(
        key,
        _build,
        db=db,
        warming=lambda: _warming_snapshot(),
        accept=_accept_snapshot,
        cold_wait=cold_wait,
        cold_soft_ttl=GUIDE_DEGRADED_SOFT_TTL_SECONDS,
        rebase=rebase_snapshot_to_now,
    )
    return _finish(result)


def prewarm_live_guide(settings: Any, db: Any = None) -> None:
    """Build the household (non-youth) guide + On Now once, off the request path."""
    if _is_trivial(settings) is not None:
        return
    try:
        guide_key = _cache_key(settings, youth_max_rating=None, extra="guide|h=6.0")
        guide = _guide.build_guide_snapshot(settings, youth_max_rating=None, hours=6.0)
        if _accept_snapshot(guide):
            GUIDE_CACHE.put(guide_key, guide, db=db)
        on_now_key = _cache_key(settings, youth_max_rating=None, extra="on-now")
        on_now = _guide.build_on_now_snapshot(settings, youth_max_rating=None)
        if _accept_snapshot(on_now):
            ON_NOW_CACHE.put(on_now_key, on_now, db=db)
    except Exception:  # noqa: BLE001
        logger.debug("live guide prewarm skipped", exc_info=True)


__all__ = [
    "GUIDE_CACHE",
    "ON_NOW_CACHE",
    "get_guide_snapshot",
    "get_on_now_snapshot",
    "invalidate_live_guide_cache",
    "prewarm_live_guide",
    "rebase_snapshot_to_now",
]
