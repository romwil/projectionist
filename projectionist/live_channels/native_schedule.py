"""Projectionist-owned Live lineup.

Tunarr used to be the place the week schedule was stored and the HLS origin
``/live`` proxied. This module keeps that schedule in ``live_lineup.json``
under the data directory. A one-time read of Tunarr's sqlite file plus
``channel-lineups/*.json`` fills the store when it is empty. After that, the
guide and playback do not call Tunarr.

Playback of the programme on now goes through library Play (Plex HLS session
for that rating key, joined at the elapsed offset). A flex pad stays labeled
flex — including the "Up next" lower-third — and plays a filler clip in that
same video element instead of leaving it black.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

SCHEDULE_FILENAME = "live_lineup.json"
BETWEEN_PROGRAMS_TITLE = "Between programs"
_FLEX_TYPES = {"flex", "filler", "offline", "continuity", "commercial"}
_PLEX_TUNER_NOTE = (
    "In-app Live plays through Projectionist's Play tool. "
    "Plex Live TV is not required."
)


def plex_tuner_note() -> str:
    return _PLEX_TUNER_NOTE


def resolve_data_dir(settings: Any = None) -> Path:
    explicit = getattr(settings, "data_dir", None) if settings is not None else None
    if explicit:
        return Path(str(explicit))
    return Path(os.environ.get("DATA_DIR", "/config"))


def schedule_path(settings: Any = None, *, data_dir: Optional[Path] = None) -> Path:
    root = Path(data_dir) if data_dir is not None else resolve_data_dir(settings)
    return root / SCHEDULE_FILENAME


def load_schedule(settings: Any = None, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    path = schedule_path(settings, data_dir=data_dir)
    if not path.is_file():
        return {"version": 1, "channels": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not read %s: %s", path, error)
        return {"version": 1, "channels": {}}
    if not isinstance(doc, Mapping):
        return {"version": 1, "channels": {}}
    channels = doc.get("channels")
    return {
        "version": int(doc.get("version") or 1),
        "imported_from": str(doc.get("imported_from") or ""),
        "channels": dict(channels) if isinstance(channels, Mapping) else {},
    }


def save_schedule(
    doc: Mapping[str, Any],
    settings: Any = None,
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    path = schedule_path(settings, data_dir=data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "imported_from": str(doc.get("imported_from") or ""),
        "channels": dict(doc.get("channels") or {}),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def schedule_has_channels(settings: Any = None, *, data_dir: Optional[Path] = None) -> bool:
    return bool(load_schedule(settings, data_dir=data_dir).get("channels"))


def ensure_schedule(settings: Any = None, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Return the stored lineup, importing from Tunarr's sqlite once if needed.

    A channel whose saved cycle is a single rating key is rebuilt from that
    station's recipe and the local library before the guide is served. The
    rebuilt cycle is written back to ``live_lineup.json``.
    """
    root = Path(data_dir) if data_dir is not None else resolve_data_dir(settings)
    doc = load_schedule(settings, data_dir=root)
    if not doc.get("channels"):
        imported = import_tunarr_lineup(root)
        if imported and imported.get("channels"):
            doc = imported
            save_schedule(doc, data_dir=root)
    from projectionist.live_channels.cycle_rebuild import rebuild_single_title_cycles

    report = rebuild_single_title_cycles(doc, settings, data_dir=root)
    if report.get("changed"):
        save_schedule(doc, data_dir=root)
    return doc


def tunarr_store_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "tunarr" / "tunarr"


def import_tunarr_lineup(data_dir: Path) -> Optional[Dict[str, Any]]:
    """Read channel lineups + program rating keys without starting Tunarr.

    The sqlite file is opened read-only. Nothing is deleted or migrated in place.
    """
    root = tunarr_store_dir(data_dir)
    db_path = root / "db.db"
    lineup_dir = root / "channel-lineups"
    if not db_path.is_file() or not lineup_dir.is_dir():
        return None
    lineups = _read_lineup_files(lineup_dir)
    if not lineups:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?immutable=1", uri=True)
    except sqlite3.Error as error:
        logger.warning("Tunarr lineup import could not open %s: %s", db_path, error)
        return None
    try:
        conn.row_factory = sqlite3.Row
        channels = _load_channels(conn, list(lineups))
        program_ids = [
            str(item.get("id") or "")
            for items in lineups.values()
            for item in items
            if str(item.get("type") or "") == "content" and item.get("id")
        ]
        programs = _load_programs(conn, program_ids)
    except sqlite3.Error as error:
        logger.warning("Tunarr lineup import failed: %s", error)
        return None
    finally:
        conn.close()

    stored: Dict[str, Any] = {}
    for cid, items in lineups.items():
        meta = channels.get(cid) or {}
        name = str(meta.get("name") or "Channel").strip() or "Channel"
        flex_title = str(meta.get("guide_flex_title") or "").strip() or f"{name} · Up next"
        try:
            start_ms = int(meta.get("start_time") or 0)
        except (TypeError, ValueError):
            start_ms = 0
        if start_ms <= 0:
            continue
        stored_items: List[Dict[str, Any]] = []
        for raw in items:
            kind = str(raw.get("type") or "").strip().lower()
            try:
                duration_ms = int(raw.get("durationMs") or raw.get("duration") or 0)
            except (TypeError, ValueError):
                duration_ms = 0
            if duration_ms <= 0:
                continue
            if kind in _FLEX_TYPES or kind != "content":
                stored_items.append({"type": "flex", "duration_ms": duration_ms})
                continue
            prog = programs.get(str(raw.get("id") or "")) or {}
            stored_items.append(
                {
                    "type": "content",
                    "duration_ms": duration_ms,
                    "program_id": str(raw.get("id") or ""),
                    "title": str(prog.get("title") or ""),
                    "show_title": str(prog.get("show_title") or ""),
                    "season": prog.get("season_number"),
                    "episode": prog.get("episode"),
                    "year": prog.get("year"),
                    "overview": str(prog.get("summary") or ""),
                    "content_rating": str(prog.get("rating") or ""),
                    "media_type": str(prog.get("type") or ""),
                    "plex_rating_key": str(prog.get("plex_rating_key") or ""),
                }
            )
        if not stored_items:
            continue
        stored[cid] = {
            "id": cid,
            "name": name,
            "number": meta.get("number"),
            "guide_flex_title": flex_title,
            "icon_url": str(meta.get("icon_url") or ""),
            "start_time_ms": start_ms,
            "items": stored_items,
        }
    if not stored:
        return None
    return {"version": 1, "imported_from": "tunarr_sqlite", "channels": stored}


def _read_lineup_files(lineup_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for path in sorted(lineup_dir.glob("*.json")):
        if path.name.endswith(".bak"):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, Mapping):
            continue
        items = doc.get("items")
        if not isinstance(items, list) or not items:
            continue
        cid = path.stem
        out[cid] = [dict(item) for item in items if isinstance(item, Mapping)]
    return out


def _load_channels(conn: sqlite3.Connection, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    found: Dict[str, Dict[str, Any]] = {}
    for chunk in _chunks(ids, 200):
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT uuid, number, name, start_time, guide_flex_title, icon "
            f"FROM channel WHERE uuid IN ({marks})",
            list(chunk),
        ).fetchall()
        for row in rows:
            icon_url = ""
            raw_icon = row["icon"]
            if isinstance(raw_icon, str) and raw_icon.strip().startswith("{"):
                try:
                    icon = json.loads(raw_icon)
                except json.JSONDecodeError:
                    icon = None
                if isinstance(icon, Mapping):
                    icon_url = str(icon.get("path") or icon.get("url") or "")
            elif isinstance(raw_icon, str) and raw_icon.startswith(("http://", "https://", "/")):
                icon_url = raw_icon
            found[str(row["uuid"])] = {
                "name": row["name"],
                "number": row["number"],
                "start_time": row["start_time"],
                "guide_flex_title": row["guide_flex_title"],
                "icon_url": icon_url,
            }
    return found


def _load_programs(conn: sqlite3.Connection, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    unique = [pid for pid in dict.fromkeys(ids) if pid]
    found: Dict[str, Dict[str, Any]] = {}
    for chunk in _chunks(unique, 200):
        marks = ",".join("?" for _ in chunk)
        rows = conn.execute(
            "SELECT uuid, type, title, show_title, season_number, episode, year, "
            "summary, rating, external_key, plex_rating_key, source_type "
            f"FROM program WHERE uuid IN ({marks})",
            list(chunk),
        ).fetchall()
        for row in rows:
            key = str(row["plex_rating_key"] or "").strip()
            if not key and str(row["source_type"] or "") == "plex":
                key = str(row["external_key"] or "").strip()
            found[str(row["uuid"])] = {
                "type": row["type"],
                "title": row["title"],
                "show_title": row["show_title"],
                "season_number": row["season_number"],
                "episode": row["episode"],
                "year": row["year"],
                "summary": row["summary"],
                "rating": row["rating"],
                "plex_rating_key": key,
            }
    return found


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    step = max(1, int(size))
    for start in range(0, len(items), step):
        yield items[start : start + step]


def iter_slots(
    channel: Mapping[str, Any],
    *,
    start_ms: int,
    end_ms: int,
):
    """Yield ``(item, slot_start_ms, slot_stop_ms)`` for the published cycle."""
    items = channel.get("items") if isinstance(channel.get("items"), list) else []
    usable = [item for item in items if isinstance(item, Mapping)]
    cycle_ms = 0
    for item in usable:
        try:
            cycle_ms += max(0, int(item.get("duration_ms") or 0))
        except (TypeError, ValueError):
            continue
    if cycle_ms <= 0 or not usable:
        return
    try:
        origin = int(channel.get("start_time_ms") or 0)
    except (TypeError, ValueError):
        return
    if origin <= 0:
        return
    if start_ms <= origin:
        cursor = origin
    else:
        cycles = (start_ms - origin) // cycle_ms
        cursor = origin + cycles * cycle_ms
    steps = 0
    while cursor < end_ms and steps < 100_000:
        for item in usable:
            try:
                duration = int(item.get("duration_ms") or 0)
            except (TypeError, ValueError):
                duration = 0
            if duration <= 0:
                continue
            stop = cursor + duration
            if stop > start_ms and cursor < end_ms:
                yield item, cursor, stop
            cursor = stop
            steps += 1
            if cursor >= end_ms:
                break


def guide_programs(
    channel: Mapping[str, Any],
    *,
    now: float,
    window_seconds: int,
) -> List[Dict[str, Any]]:
    """Published slots overlapping ``[now, now + window)``, including the airing on now."""
    now_ms = int(float(now) * 1000)
    end_ms = now_ms + max(1, int(window_seconds)) * 1000
    programs: List[Dict[str, Any]] = []
    for item, start_ms, stop_ms in iter_slots(channel, start_ms=now_ms, end_ms=end_ms):
        start_s = start_ms / 1000.0
        stop_s = stop_ms / 1000.0
        duration_ms = stop_ms - start_ms
        if str(item.get("type") or "") == "flex":
            programs.append(
                {
                    "type": "flex",
                    "title": BETWEEN_PROGRAMS_TITLE,
                    "start": start_s,
                    "stop": stop_s,
                    "duration": duration_ms,
                }
            )
            continue
        media_type = str(item.get("media_type") or "").strip().lower()
        show_title = str(item.get("show_title") or "").strip()
        title = str(item.get("title") or "").strip() or "Untitled"
        nested: Dict[str, Any] = {
            "type": media_type or ("episode" if show_title else "movie"),
            "title": title,
            "plexRatingKey": str(item.get("plex_rating_key") or ""),
            "externalKey": str(item.get("plex_rating_key") or ""),
            "contentRating": str(item.get("content_rating") or ""),
            "summary": str(item.get("overview") or ""),
            "year": item.get("year"),
            "seasonNumber": item.get("season"),
            "episodeNumber": item.get("episode"),
        }
        if show_title:
            nested["show"] = {"title": show_title}
            nested["type"] = "episode"
        programs.append(
            {
                "type": "content",
                "title": show_title or title,
                "start": start_s,
                "stop": stop_s,
                "duration": duration_ms,
                "program": nested,
            }
        )
    return programs


def snapshot_if_scheduled(
    settings: Any,
    *,
    youth_max_rating: Optional[str] = None,
    now: Optional[float] = None,
    window_seconds: int = 6 * 3600,
    max_channels: int = 48,
    include_programs: bool = False,
) -> Optional[Dict[str, Any]]:
    """Guide snapshot from our store, or None when no lineup has been saved."""
    doc = ensure_schedule(settings)
    channels_doc = doc.get("channels") if isinstance(doc.get("channels"), Mapping) else {}
    if not channels_doc:
        return None
    from projectionist.live_channels.airing_why import enrich_channels_with_airing_why
    from projectionist.live_channels.guide import (
        DUAL_WATCH_HINT,
        _channel_row_from_guide,
        _sort_channels,
        apply_youth_filter_to_on_now,
        pick_now_and_next,
    )

    ts = time.time() if now is None else float(now)
    window = max(60, int(window_seconds or 60))
    limit = max(1, min(int(max_channels or 48), 100))
    rows: List[Dict[str, Any]] = []
    ordered = sorted(
        channels_doc.values(),
        key=lambda ch: (
            ch.get("number") is None,
            int(ch.get("number") or 0) if str(ch.get("number") or "").lstrip("-").isdigit() else 0,
            str(ch.get("name") or "").lower(),
        ),
    )
    for channel in ordered[:limit]:
        if not isinstance(channel, Mapping):
            continue
        cid = str(channel.get("id") or "").strip()
        if not cid:
            continue
        programs = guide_programs(channel, now=ts, window_seconds=window)
        slots = pick_now_and_next(programs, now=ts)
        meta = {
            "name": channel.get("name"),
            "number": channel.get("number"),
            "icon_url": channel.get("icon_url") or "",
            "guideFlexTitle": channel.get("guide_flex_title") or "",
        }
        row = _channel_row_from_guide(
            cid,
            meta=meta,
            lineup={"name": channel.get("name"), "number": channel.get("number")},
            programs=programs,
            slots=slots,
            include_programs=include_programs,
        )
        notice = str(channel.get("library_repeat_note") or "").strip()
        if notice:
            row["pool_notice"] = notice
        rows.append(row)
    _sort_channels(rows)
    ceiling = str(youth_max_rating or "").strip()
    if ceiling:
        rows = apply_youth_filter_to_on_now(rows, max_rating=ceiling)
    rows = enrich_channels_with_airing_why(settings, rows)
    ready = bool(rows)
    return {
        "enabled": True,
        "ready": ready,
        "channels": rows,
        "count": len(rows),
        "generated_at": ts,
        "window_seconds": window,
        "reason": "" if ready else "no_channels",
        "error": "",
        "source": "projectionist",
        "plex_hint": DUAL_WATCH_HINT,
        "watch_hint": DUAL_WATCH_HINT,
        "plex_tuner_note": plex_tuner_note(),
    }


def admin_channel_rows(settings: Any, doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Admin station rows from our lineup, merged with station_meta craft fields."""
    from projectionist.live_channels.publish import (
        resolve_media_scope,
        resolve_subtitles_enabled,
        station_craft_snapshot,
    )

    channels = doc.get("channels") if isinstance(doc.get("channels"), Mapping) else {}
    rows: List[Dict[str, Any]] = []
    for cid, channel in channels.items():
        if not isinstance(channel, Mapping):
            continue
        craft = station_craft_snapshot(settings, str(cid))
        rows.append(
            {
                "id": str(cid),
                "name": channel.get("name"),
                "number": channel.get("number"),
                "has_continuity": False,
                "filler_collections_count": 0,
                "guide_flex_title": str(channel.get("guide_flex_title") or ""),
                "media_scope": resolve_media_scope(settings, channel_id=str(cid), default="both"),
                "subtitles_enabled": resolve_subtitles_enabled(settings, channel_id=str(cid)),
                "source": craft.get("source") or "",
                "motif": craft.get("motif") or "",
                "cluster_tag": craft.get("cluster_tag") or "",
                "collection_id": craft.get("collection_id") or "",
                "collection_title": craft.get("collection_title") or "",
                "programming_mode": craft.get("programming_mode") or "",
                "craft_filters": dict(craft.get("craft_filters") or {}),
                "youth_safe": bool(craft.get("youth_safe")),
                "queue_pad": dict(craft.get("queue_pad") or {}),
            }
        )
    rows.sort(
        key=lambda row: (
            int(row["number"]) if str(row.get("number") or "").lstrip("-").isdigit() else 10**9,
            str(row.get("name") or ""),
        )
    )
    return rows


def programme_stats(doc: Mapping[str, Any], *, now: Optional[float] = None, hours: float = 168.0) -> Dict[str, Any]:
    """Count content airings in our schedule. Does not fetch Tunarr XMLTV."""
    ts = time.time() if now is None else float(now)
    window = int(max(1.0, float(hours)) * 3600)
    content = 0
    total = 0
    channels = doc.get("channels") if isinstance(doc.get("channels"), Mapping) else {}
    for channel in channels.values():
        if not isinstance(channel, Mapping):
            continue
        for program in guide_programs(channel, now=ts, window_seconds=window):
            total += 1
            if str(program.get("type") or "") != "flex":
                content += 1
    return {
        "ok": total > 0,
        "programme_count": total,
        "content_programme_count": content,
        "source": "projectionist",
    }


def _channel(doc: Mapping[str, Any], channel_id: str) -> Optional[Mapping[str, Any]]:
    channels = doc.get("channels") if isinstance(doc.get("channels"), Mapping) else {}
    row = channels.get(str(channel_id or "").strip())
    return row if isinstance(row, Mapping) else None


_PROGRESSIVE_EXTS = {".mp4", ".m4v", ".webm", ".mov"}


def _stable_pick(items: Sequence[Any], seed: float) -> Any:
    count = len(items)
    if count <= 0:
        raise IndexError("empty pick")
    try:
        base = int(abs(float(seed)))
    except (TypeError, ValueError):
        base = 0
    return items[base % count]


def filler_rating_keys(channel: Mapping[str, Any]) -> List[str]:
    """Library rating keys this station may play during a flex pad.

    Explicit ``filler_rating_keys`` win. Flex rows that still carry a Plex key
    (a bumper stored in the cycle) are next. Order is preserved.
    """
    keys: List[str] = []

    def add(raw: Any) -> None:
        key = str(raw or "").strip()
        if key and key not in keys:
            keys.append(key)

    listed = channel.get("filler_rating_keys")
    if isinstance(listed, str):
        add(listed)
    elif isinstance(listed, Sequence) and not isinstance(listed, (bytes, bytearray)):
        for item in listed:
            if isinstance(item, Mapping):
                add(item.get("plex_rating_key") or item.get("rating_key"))
            else:
                add(item)
    items = channel.get("items") if isinstance(channel.get("items"), list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("type") or "").strip().lower()
        if kind not in _FLEX_TYPES:
            continue
        add(item.get("plex_rating_key") or item.get("rating_key"))
    return keys


def _filler_keys_from_tunarr(data_dir: Path, channel_id: str) -> List[str]:
    """Plex keys on this station's Tunarr filler show. Read-only; empty if absent."""
    db_path = tunarr_store_dir(data_dir) / "db.db"
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        logger.debug("filler show db unreadable: %s", error)
        return []
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT p.plex_rating_key AS plex_rating_key
            FROM channel_filler_show cfs
            JOIN filler_show_content fsc
              ON fsc.filler_show_uuid = cfs.filler_show_uuid
            JOIN program p ON p.uuid = fsc.program_uuid
            WHERE cfs.channel_uuid = ?
            ORDER BY fsc."index"
            """,
            (str(channel_id or "").strip(),),
        ).fetchall()
    except sqlite3.Error as error:
        logger.debug("filler show query failed: %s", error)
        return []
    finally:
        conn.close()
    keys: List[str] = []
    for row in rows:
        key = str(row["plex_rating_key"] or "").strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _progressive_bumper(seed: float) -> Optional[Dict[str, Any]]:
    """A short browser-playable bumper when the filler show has no Plex key.

    Station commercials on Automat are local mkv files and are not in the
    library. Preroll mp4s are mounted in the app and paint in the video element.
    """
    from projectionist.theater.preroll import list_preroll_videos

    videos = []
    for row in list_preroll_videos():
        if not isinstance(row, Mapping) or not row.get("id"):
            continue
        suffix = Path(str(row.get("path") or "")).suffix.lower()
        if suffix not in _PROGRESSIVE_EXTS:
            continue
        videos.append(row)
    if not videos:
        return None
    chosen = _stable_pick(videos, seed)
    asset_id = str(chosen["id"])
    return {
        "rating_key": asset_id,
        "stream_url": f"/api/preroll/asset/{asset_id}",
        "playback_kind": "progressive",
        "filler_title": str(chosen.get("title") or ""),
    }


def play_source_for_channel(
    db: Any,
    settings: Any,
    user: Any,
    channel_id: str,
    *,
    now: Optional[float] = None,
    start_playback_fn: Any = None,
) -> Optional[Dict[str, Any]]:
    """Library Play session for the file on now.

    A flex pad still reports ``is_flex`` (Up next lower-third) and also starts
    a filler session when the station has a playable filler rating key. With
    no library filler, a progressive preroll bumper is used so the video
    element is not an empty black frame.

    Returns None when this channel is not in our lineup (caller may still use
    the legacy Tunarr tune path).
    """
    doc = ensure_schedule(settings)
    channel = _channel(doc, channel_id)
    if channel is None:
        return None
    from projectionist.live_channels.guide import pick_now_and_next

    ts = time.time() if now is None else float(now)
    programs = guide_programs(channel, now=ts, window_seconds=6 * 3600)
    slots = pick_now_and_next(programs, now=ts)
    current = slots.get("now") if isinstance(slots.get("now"), Mapping) else None
    nxt = slots.get("next") if isinstance(slots.get("next"), Mapping) else None
    if current is None:
        return {
            "ok": False,
            "channel_id": str(channel_id),
            "is_flex": False,
            "stream_url": "",
            "rating_key": "",
            "reason": "nothing_on",
            "source": "projectionist",
        }
    ends_at = current.get("ends_at") or current.get("stop")
    notice = str(channel.get("library_repeat_note") or "").strip()
    next_title = _programme_display_title(nxt)
    base = {
        "ok": True,
        "channel_id": str(channel_id),
        "is_flex": bool(current.get("is_flex")),
        "title": current.get("title") or "",
        "ends_at": ends_at,
        "next_title": next_title,
        "source": "projectionist",
        "plex_tuner_note": plex_tuner_note(),
    }
    if notice:
        base["pool_notice"] = notice
    if current.get("is_flex"):
        keys = filler_rating_keys(channel)
        for key in _filler_keys_from_tunarr(resolve_data_dir(settings), str(channel_id)):
            if key not in keys:
                keys.append(key)
        seed = float(current.get("start") or current.get("started_at") or ts)
        if keys:
            filler_key = str(_stable_pick(keys, seed))
            if start_playback_fn is None:
                from projectionist.library.playback import start_playback as start_playback_fn
            try:
                payload = start_playback_fn(
                    db,
                    settings,
                    rating_key=filler_key,
                    user=user,
                    start_over=True,
                    offset_ms=0,
                )
            except Exception as error:  # noqa: BLE001
                logger.warning("flex filler playback failed for %s: %s", filler_key, error)
                payload = None
            if isinstance(payload, Mapping) and str(payload.get("stream_url") or "").strip():
                base.update(
                    {
                        "stream_url": str(payload.get("stream_url") or ""),
                        "rating_key": filler_key,
                        "session_id": str(payload.get("session_id") or ""),
                        "offset_ms": 0,
                        "duration_ms": payload.get("duration_ms"),
                        "playback_kind": "hls",
                        "filler": True,
                    }
                )
                return base
        bumper = _progressive_bumper(seed)
        if bumper:
            base.update(
                {
                    "stream_url": bumper["stream_url"],
                    "rating_key": bumper["rating_key"],
                    "session_id": "",
                    "offset_ms": 0,
                    "playback_kind": "progressive",
                    "filler": True,
                    "filler_title": bumper.get("filler_title") or "",
                }
            )
            return base
        slate_next = next_title
        base.update(
            {
                "stream_url": "",
                "rating_key": "",
                "session_id": "",
                "offset_ms": 0,
                "playback_kind": "",
                "filler": False,
                "slate": True,
                "slate_title": BETWEEN_PROGRAMS_TITLE,
                "reason": "no_filler",
            }
        )
        if slate_next:
            base["slate_copy"] = f"{BETWEEN_PROGRAMS_TITLE} — up next: {slate_next}"
        else:
            base["slate_copy"] = BETWEEN_PROGRAMS_TITLE
        return base
    rating_key = str(current.get("plex_rating_key") or "").strip()
    if not rating_key:
        base.update(
            {
                "ok": False,
                "stream_url": "",
                "rating_key": "",
                "reason": "no_rating_key",
            }
        )
        return base
    try:
        elapsed_ms = max(0, int(float(current.get("seconds_elapsed") or 0) * 1000))
    except (TypeError, ValueError):
        elapsed_ms = 0
    if start_playback_fn is None:
        from projectionist.library.playback import start_playback as start_playback_fn

    payload = start_playback_fn(
        db,
        settings,
        rating_key=rating_key,
        user=user,
        start_over=True,
        offset_ms=elapsed_ms,
    )
    stream_url = str(payload.get("stream_url") or "")
    base.update(
        {
            "stream_url": stream_url,
            "rating_key": rating_key,
            "session_id": str(payload.get("session_id") or ""),
            "offset_ms": elapsed_ms,
            "duration_ms": payload.get("duration_ms"),
        }
    )
    return base


def _programme_display_title(program: Optional[Mapping[str, Any]]) -> str:
    """Watch 'up next' copy: show + episode, never a flex pad's name."""
    if not isinstance(program, Mapping) or program.get("is_flex"):
        return ""
    title = str(program.get("title") or "").strip()
    episode = str(program.get("episode_title") or "").strip()
    if episode and episode.casefold() != title.casefold():
        return f"{title} — {episode}" if title else episode
    return title


def _mcp_slot(program: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Now/next for MCP: flex vs programme, no Plex keys or host paths."""
    if not isinstance(program, Mapping):
        return None
    is_flex = bool(program.get("is_flex")) or str(program.get("type") or "").strip().lower() == "flex"
    if is_flex:
        title = BETWEEN_PROGRAMS_TITLE
    else:
        title = _programme_display_title(program) or str(program.get("title") or "").strip() or "Untitled"
    return {
        "title": title,
        "kind": "flex" if is_flex else "programme",
        "is_flex": is_flex,
        "starts_at": program.get("start") or program.get("started_at"),
        "ends_at": program.get("ends_at") or program.get("stop"),
    }


def _immediate_now_next(
    programs: Sequence[Mapping[str, Any]],
    *,
    now: float,
) -> tuple[Optional[Mapping[str, Any]], Optional[Mapping[str, Any]]]:
    """Clock now/next including flex — do not skip pads to the next title."""
    ts = float(now)
    ordered = sorted(
        (row for row in programs if isinstance(row, Mapping) and row.get("start") is not None),
        key=lambda row: float(row.get("start") or 0),
    )
    for index, program in enumerate(ordered):
        try:
            start = float(program.get("start"))
            stop = float(program.get("stop") or 0)
        except (TypeError, ValueError):
            continue
        if start <= ts < stop:
            nxt = ordered[index + 1] if index + 1 < len(ordered) else None
            return program, nxt
    return None, ordered[0] if ordered else None


def _mcp_channel_matches(channel: Mapping[str, Any], needle: str) -> bool:
    text = str(needle or "").strip()
    if not text:
        return True
    if str(channel.get("id") or "") == text:
        return True
    if str(channel.get("number") or "") == text:
        return True
    return str(channel.get("name") or "").strip().casefold() == text.casefold()


def _mcp_pool_size(channel: Mapping[str, Any]) -> int:
    seen: List[str] = []
    items = channel.get("items") if isinstance(channel.get("items"), list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("type") or "content").lower() != "content":
            continue
        key = str(item.get("plex_rating_key") or item.get("program_id") or "").strip()
        if key and key not in seen:
            seen.append(key)
    return len(seen)


def live_guide_for_mcp(
    settings: Any,
    *,
    channel: Optional[str] = None,
    now: Optional[float] = None,
    hours: float = 6.0,
) -> Dict[str, Any]:
    """Read-only native guide. Missing ``live_lineup.json`` is ``lineup_missing``.

    Does not import Tunarr leftovers, publish, shuffle, or attach a tuner.
    """
    path = schedule_path(settings)
    if not path.is_file():
        return {"error": "lineup_missing"}
    doc = load_schedule(settings)
    channels_doc = doc.get("channels") if isinstance(doc.get("channels"), Mapping) else {}

    ts = time.time() if now is None else float(now)
    window = max(60, int(float(hours or 6.0) * 3600))
    needle = str(channel or "").strip()
    ordered = sorted(
        (ch for ch in channels_doc.values() if isinstance(ch, Mapping)),
        key=lambda ch: (
            ch.get("number") is None,
            int(ch.get("number") or 0) if str(ch.get("number") or "").lstrip("-").isdigit() else 0,
            str(ch.get("name") or "").lower(),
        ),
    )
    rows: List[Dict[str, Any]] = []
    for stored in ordered:
        if needle and not _mcp_channel_matches(stored, needle):
            continue
        programs = guide_programs(stored, now=ts, window_seconds=window)
        now_row, next_row = _immediate_now_next(programs, now=ts)
        notice = str(stored.get("library_repeat_note") or "").strip()
        pool_size = _mcp_pool_size(stored)
        row: Dict[str, Any] = {
            "id": str(stored.get("id") or ""),
            "name": str(stored.get("name") or "Channel").strip() or "Channel",
            "number": stored.get("number"),
            "now": _mcp_slot(now_row),
            "next": _mcp_slot(next_row),
            "pool_size": pool_size,
            "pool_notice": notice or None,
        }
        rows.append(row)
    return {
        "source": "projectionist",
        "channels": rows,
        "count": len(rows),
    }
