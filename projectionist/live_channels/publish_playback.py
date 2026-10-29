"""Playhead align, stream warm, and playback prepare for Live publish."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.live_channels.publish_icons import (
    _channel_put_body,
    apply_station_icons,
    ensure_channel_labels,
    resolve_channel_icon_url,
)

# Historical annotations used this name for the broadcast HTTP client.
TunarrClient = Any

# Cold HDHR tunes that seek deep into a program (or past EOF) lose the race with
# Plex before ffmpeg writes playlist.m3u8 → "Stream not ready yet" / 0-byte .ts
# → Plex "This live TV session has ended." Snap playhead forward when deep/cold.
_ALIGN_MIN_ELAPSED_MS = 5 * 60 * 1000
_WARM_DEFAULT_TIMEOUT_S = 45
_WARM_MIN_TS_BYTES = 200_000
_WARM_POLL_SLEEP_S = 1.5


def _sessions_by_channel(client: TunarrClient) -> Dict[str, Any]:
    try:
        raw = client.list_sessions()
    except Exception:  # noqa: BLE001
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def should_align_playhead(
    *,
    elapsed_ms: int,
    program_duration_ms: int = 0,
    has_session: bool = False,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
) -> bool:
    """True when a mid-program seek is likely to cold-fail Plex HDHR tunes."""
    elapsed = max(0, int(elapsed_ms or 0))
    duration = max(0, int(program_duration_ms or 0))
    if duration and elapsed > duration:
        return True  # past EOF — ffmpeg seek hangs / empty playlist
    if has_session:
        return False
    return elapsed >= max(0, int(min_elapsed_ms or 0))


def _now_playing_is_flex(playing: Mapping[str, Any]) -> bool:
    """True when Tunarr now_playing is a flex / continuity / offline pad."""
    kind = str(playing.get("type") or playing.get("programType") or "").strip().lower()
    if kind in {"flex", "filler", "continuity", "offline", "commercial"}:
        return True
    title = str(playing.get("title") or "").strip().lower()
    if title.endswith("· up next") or title.endswith("up next"):
        return True
    if title in {"flex", "filler", "continuity"}:
        return True
    return False


def snap_future_channel_start_time(
    client: TunarrClient,
    channel: Mapping[str, Any],
    *,
    now_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Pull a future ``startTime`` back by whole cycle lengths (preserve playhead).

    When ``startTime`` is ahead of wall-clock, Tunarr synthesizes long flex /
    offline pads until the cycle begins — Continuity filler airs while the
    guide looks empty or misleading. Subtracting ``duration`` keeps the same
    offset into the lineup without wiping the schedule.
    """
    cid = str(channel.get("id") or channel.get("uuid") or "").strip()
    if not cid:
        return {"ok": False, "snapped": False, "error": "channel_id required"}
    ts = int(now_ms if now_ms is not None else time.time() * 1000)
    try:
        start = int(channel.get("startTime") or 0)
    except (TypeError, ValueError):
        start = 0
    try:
        duration = int(channel.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if start <= ts:
        return {
            "ok": True,
            "snapped": False,
            "channel_id": cid,
            "reason": "already_live",
            "start_time_ms": start,
        }
    if duration <= 0:
        new_start = ts - 60_000
    else:
        new_start = start
        # Bound iterations — pathological durations must not spin.
        for _ in range(10_000):
            if new_start <= ts:
                break
            new_start -= duration
        if new_start > ts:
            new_start = ts - (start - ts) % duration
    body = _channel_put_body(channel, start_time_ms=int(new_start))
    if not body["transcodeConfigId"]:
        return {
            "ok": False,
            "snapped": False,
            "channel_id": cid,
            "error": "missing transcodeConfigId",
        }
    try:
        client.update_channel(cid, body)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "snapped": False,
            "channel_id": cid,
            "error": str(error)[:200],
        }
    return {
        "ok": True,
        "snapped": True,
        "channel_id": cid,
        "start_time_ms": int(new_start),
        "previous_start_time_ms": start,
        "message": "Snapped future startTime back into the live window.",
    }


def align_channel_playhead_to_program_start(
    client: TunarrClient,
    channel: Mapping[str, Any],
    *,
    has_session: bool = False,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
    force: bool = False,
) -> Dict[str, Any]:
    """Shift channel ``startTime`` so 'now' is the start of the current program.

    Deep ``-ss`` seeks (or seeks past file EOF) delay HLS readiness past Plex's
    patience. Start-over keeps cold tunes near ``-ss 0``.

    Never start-over on flex/continuity pads — adding flex elapsed to
    ``startTime`` pushes the cycle into the future (Gilligan / Kung Fu drift).
    """
    cid = str(channel.get("id") or channel.get("uuid") or "").strip()
    if not cid:
        return {"ok": False, "aligned": False, "error": "channel_id required"}
    now_ms = int(time.time() * 1000)
    # Repair drifted schedules before consulting now_playing (which is often a
    # synthetic flex window while startTime is still in the future).
    snap = snap_future_channel_start_time(client, channel, now_ms=now_ms)
    if snap.get("snapped"):
        channel = {**dict(channel), "startTime": snap.get("start_time_ms")}
    try:
        playing = client.get_now_playing(cid) or {}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": str(error)[:200],
            "snap": snap,
        }
    if not isinstance(playing, Mapping):
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "reason": "no_now_playing",
            "snap": snap,
        }
    if _now_playing_is_flex(playing) and not force:
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "reason": "flex_skip",
            "title": str(playing.get("title") or "").strip(),
            "snap": snap,
            "message": snap.get("message") or "Skipped start-over during flex/continuity.",
        }
    prog_start = int(playing.get("start") or 0)
    prog_duration = int(playing.get("duration") or 0)
    title = ""
    program = playing.get("program")
    if isinstance(program, Mapping):
        title = str(program.get("title") or "").strip()
    if not title:
        title = str(playing.get("title") or "").strip()
    elapsed = max(0, now_ms - prog_start) if prog_start else 0
    if not force and not should_align_playhead(
        elapsed_ms=elapsed,
        program_duration_ms=prog_duration,
        has_session=has_session,
        min_elapsed_ms=min_elapsed_ms,
    ):
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "elapsed_ms": elapsed,
            "title": title,
            "reason": "near_start_or_active",
            "snap": snap,
        }
    channel_start = int(channel.get("startTime") or now_ms)
    new_start = channel_start + elapsed
    # Never push the cycle into the future — that recreates pre-start flex.
    if new_start > now_ms:
        new_start = now_ms
    body = _channel_put_body(channel, start_time_ms=new_start)
    if not body["transcodeConfigId"]:
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": "missing transcodeConfigId",
        }
    try:
        client.update_channel(cid, body)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": str(error)[:200],
        }
    return {
        "ok": True,
        "aligned": True,
        "channel_id": cid,
        "elapsed_ms": elapsed,
        "title": title,
        "start_time_ms": new_start,
        "snap": snap,
        "message": f"Start-over: was {elapsed // 60000}m into {title or 'program'}.",
    }


def warm_channel_stream(
    client: TunarrClient,
    channel_id: str,
    *,
    timeout: int = _WARM_DEFAULT_TIMEOUT_S,
    min_ts_bytes: int = _WARM_MIN_TS_BYTES,
    pull_ts: bool = True,
) -> Dict[str, Any]:
    """Warm HLS until the media playlist has segments, optionally pull MPEG-TS.

    A single GET of the master ``.m3u8`` is not enough — Tunarr often returns the
    master before ``playlist.m3u8`` / segments exist. Plex HDHR uses ``.ts``.

    Background keepalive should pass ``pull_ts=False``: opening ``.ts`` on every
    channel every few minutes keeps six ffmpeg pipelines hot (2000%+ CPU) and
    SIGKILLs mid-watch sessions when they contend for resources.
    """
    from projectionist.circuit_breaker import CircuitOpenError, is_host_circuit_open
    from projectionist.connectors.http import request_bytes

    cid = str(channel_id or "").strip()
    if not cid:
        return {"ok": False, "error": "channel_id required"}
    base = client.base_url.rstrip("/")
    master_url = f"{base}/stream/channels/{cid}.m3u8?mode=hls"
    media_url = f"{base}/stream/channels/{cid}/hls/stream.m3u8"
    ts_url = f"{base}/stream/channels/{cid}.ts"
    deadline = time.time() + max(8, int(timeout or _WARM_DEFAULT_TIMEOUT_S))
    playlist_ready = False
    last_error = ""
    poll_count = 0
    hard_fail = False
    while time.time() < deadline and not hard_fail:
        poll_count += 1
        for url in (media_url, master_url):
            try:
                body = request_bytes(url, timeout=8, max_bytes=8192).decode("utf-8", "replace")
                if "#EXTINF" in body:
                    playlist_ready = True
                    break
                if body.strip():
                    last_error = "playlist returned without segments yet"
            except CircuitOpenError as error:
                last_error = str(error)[:160]
                hard_fail = True
                break
            except Exception as error:  # noqa: BLE001
                last_error = str(error)[:160]
                # Connection refused / DNS / invalid URL — do not burn the full timeout.
                err_l = last_error.lower()
                if any(
                    token in err_l
                    for token in (
                        "connection refused",
                        "nodename nor servname",
                        "name or service not known",
                        "timed out",
                        "unreachable",
                        "invalid url",
                        "unknown url type",
                        "circuit open",
                    )
                ) or is_host_circuit_open(url):
                    hard_fail = True
                    break
        if playlist_ready or hard_fail:
            break
        time.sleep(_WARM_POLL_SLEEP_S)

    ts_bytes = 0
    ts_error = ""
    if pull_ts:
        try:
            ts_bytes = len(
                request_bytes(
                    ts_url,
                    timeout=max(10, int(timeout or _WARM_DEFAULT_TIMEOUT_S)),
                    max_bytes=max(int(min_ts_bytes or 0), _WARM_MIN_TS_BYTES),
                )
            )
        except Exception as error:  # noqa: BLE001
            ts_error = str(error)[:200]

    if pull_ts:
        ok = playlist_ready or ts_bytes >= max(
            1, int(min_ts_bytes or _WARM_MIN_TS_BYTES) // 4
        )
        message = (
            "Stream warmed (playlist + MPEG-TS)."
            if ok
            else "Warm-up incomplete — first Plex tune may still race cold start."
        )
    else:
        ok = playlist_ready
        message = (
            "Playlist keepalive ok."
            if ok
            else "Playlist keepalive incomplete — stream may still be cold."
        )
    return {
        "ok": ok,
        "channel_id": cid,
        "playlist_ready": playlist_ready,
        "ts_bytes": ts_bytes,
        "pull_ts": bool(pull_ts),
        "polls": poll_count,
        "error": "" if ok else (ts_error or last_error or "stream not ready"),
        "message": message,
    }


def prepare_channels_for_playback(
    client: TunarrClient,
    *,
    settings: Any = None,
    channel_ids: Optional[Sequence[str]] = None,
    icon_url: str = "",
    align_playhead: bool = True,
    warm_streams: bool = True,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
    skip_active_sessions: bool = False,
    max_warm_channels: Optional[int] = None,
    pull_ts: bool = True,
) -> Dict[str, Any]:
    """Labels + start-over (when deep/cold) + HLS warm for playback.

    ``skip_active_sessions`` / ``max_warm_channels`` / ``pull_ts=False`` are for
    the background keepalive scheduler — never thrash channels that already have
    viewers, and never keep every station's ffmpeg pipeline hot at once.
    """
    wanted = {str(cid).strip() for cid in (channel_ids or ()) if str(cid).strip()}
    resolved_icon = str(icon_url or "").strip() or resolve_channel_icon_url(settings)
    labels = ensure_channel_labels(
        client, icon_url=resolved_icon, channel_ids=list(wanted) if wanted else None
    )
    try:
        station_icons = apply_station_icons(
            client,
            settings,
            channel_ids=list(wanted) if wanted else None,
            fallback_icon=resolved_icon,
        )
        if station_icons.get("count_updated"):
            labels = {
                **labels,
                "count_updated": int(labels.get("count_updated") or 0)
                + int(station_icons.get("count_updated") or 0),
                "station_icons": station_icons,
            }
    except Exception:  # noqa: BLE001
        pass
    sessions = _sessions_by_channel(client)
    channels = [ch for ch in client.list_channels() if isinstance(ch, Mapping)]
    if wanted:
        channels = [
            ch
            for ch in channels
            if str(ch.get("id") or ch.get("uuid") or "").strip() in wanted
        ]

    aligned: List[Dict[str, Any]] = []
    snapped: List[Dict[str, Any]] = []
    skipped_active = 0
    # Always pull future startTimes back (preserves lineup offset). Safe on
    # channel-surf / background warm — unlike content start-over, which was
    # drifting schedules into flex/Continuity after leave→rejoin.
    repaired_channels: List[Mapping[str, Any]] = []
    for ch in channels:
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid:
            repaired_channels.append(ch)
            continue
        snap = snap_future_channel_start_time(client, ch)
        snapped.append(snap)
        if snap.get("snapped"):
            repaired_channels.append(
                {**dict(ch), "startTime": snap.get("start_time_ms")}
            )
            # Drop stale HLS so warm rebuilds against the repaired schedule
            # instead of keeping a Continuity/flex session under the guide.
            try:
                client.stop_channel_sessions(cid)
            except Exception:  # noqa: BLE001
                pass
            sessions.pop(cid, None)
        else:
            repaired_channels.append(ch)
    channels = repaired_channels

    if align_playhead:
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            has_session = bool(sessions.get(cid))
            if skip_active_sessions and has_session:
                skipped_active += 1
                aligned.append(
                    {
                        "ok": True,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "active_session",
                    }
                )
                continue
            result = align_channel_playhead_to_program_start(
                client,
                ch,
                has_session=has_session,
                min_elapsed_ms=min_elapsed_ms,
            )
            aligned.append(result)
    else:
        # Live-edge tune/warm: still unstick past-EOF playheads (ffmpeg -ss past
        # file end → offline/Continuity while guide keeps the episode title).
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            if not cid:
                continue
            try:
                playing = client.get_now_playing(cid) or {}
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(playing, Mapping) or _now_playing_is_flex(playing):
                continue
            try:
                prog_start = int(playing.get("start") or 0)
                prog_duration = int(playing.get("duration") or 0)
                prog_stop = int(playing.get("stop") or 0)
            except (TypeError, ValueError):
                continue
            if not prog_start or not prog_duration:
                continue
            now_ms = int(time.time() * 1000)
            elapsed = max(0, now_ms - prog_start)
            if elapsed <= prog_duration:
                continue
            file_end = prog_start + prog_duration
            overflow = elapsed - prog_duration
            # Tunarr often pads ``stop`` past file EOF while the engine has already
            # rolled into the next lineup item. Shifting startTime by overflow then
            # pulls the playhead BACK into the dead zone and SIGKILLs a healthy
            # next-title transcode (Kung Fu: Samurai → Five Fingers).
            if prog_stop and prog_stop > file_end + 2_000:
                aligned.append(
                    {
                        "ok": True,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "past_eof_padded_stop_skip",
                        "overflow_ms": overflow,
                        "message": (
                            "now_playing past file EOF with padded stop; "
                            "skip startTime shift to preserve live edge."
                        ),
                    }
                )
                continue
            try:
                channel_start = int(ch.get("startTime") or now_ms)
            except (TypeError, ValueError):
                channel_start = now_ms
            # Advance the cycle just past the ended program into the next item
            # (do not restart the finished episode via classic start-over).
            # Decreasing effective playhead offset by (overflow - 1s) lands ~1s
            # after file end: new_start = channel_start + overflow - 1_000.
            new_start = channel_start + overflow - 1_000
            if new_start > now_ms:
                new_start = now_ms
            body = _channel_put_body(ch, start_time_ms=int(new_start))
            if not body.get("transcodeConfigId"):
                continue
            try:
                client.update_channel(cid, body)
                client.stop_channel_sessions(cid)
            except Exception as error:  # noqa: BLE001
                aligned.append(
                    {
                        "ok": False,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "past_eof_advance_failed",
                        "error": str(error)[:200],
                    }
                )
                continue
            sessions.pop(cid, None)
            aligned.append(
                {
                    "ok": True,
                    "aligned": True,
                    "channel_id": cid,
                    "reason": "past_eof_advance",
                    "overflow_ms": overflow,
                    "start_time_ms": int(new_start),
                    "message": "Advanced past ended program into the next lineup item.",
                }
            )

    warmed: List[Dict[str, Any]] = []
    if warm_streams:
        warm_budget = max_warm_channels
        if warm_budget is not None:
            try:
                warm_budget = max(0, int(warm_budget))
            except (TypeError, ValueError):
                warm_budget = None
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            if not cid:
                continue
            if skip_active_sessions and sessions.get(cid):
                warmed.append(
                    {
                        "ok": True,
                        "channel_id": cid,
                        "skipped": True,
                        "reason": "active_session",
                        "message": "Skipped warm — session already active.",
                    }
                )
                continue
            if warm_budget is not None and warm_budget <= 0:
                warmed.append(
                    {
                        "ok": True,
                        "channel_id": cid,
                        "skipped": True,
                        "reason": "warm_budget",
                        "message": "Skipped warm — background budget exhausted.",
                    }
                )
                continue
            result = warm_channel_stream(client, cid, pull_ts=pull_ts)
            warmed.append(result)
            if warm_budget is not None and not result.get("skipped"):
                warm_budget -= 1

    aligned_count = sum(1 for row in aligned if row.get("aligned"))
    snapped_count = sum(1 for row in snapped if row.get("snapped"))
    warmed_attempted = [row for row in warmed if not row.get("skipped")]
    warmed_ok = sum(1 for row in warmed_attempted if row.get("ok"))
    return {
        "ok": (not labels.get("errors"))
        and (warmed_ok == len(warmed_attempted) if warmed_attempted else True),
        "labels": labels,
        "aligned": aligned,
        "snapped": snapped,
        "count_aligned": aligned_count,
        "count_snapped": snapped_count,
        "warmed": warmed,
        "count_warmed_ok": warmed_ok,
        "count_warmed_skipped": sum(1 for row in warmed if row.get("skipped")),
        "count_skipped_active": skipped_active,
        "count_channels": len(channels),
        "icon_url": resolved_icon,
        "message": (
            f"Prepared {len(channels)} station(s): "
            f"{snapped_count} snapped, {aligned_count} start-over, "
            f"{warmed_ok}/{len(warmed_attempted) or 0} warmed"
            + (
                f", {sum(1 for row in warmed if row.get('skipped'))} skipped."
                if any(row.get("skipped") for row in warmed)
                else "."
            )
        ),
    }
