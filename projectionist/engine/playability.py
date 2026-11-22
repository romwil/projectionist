"""Library playability report (ENG-011).

A dry run of the planner that already exists. For each movie and episode, and
for each device profile, record the cheapest tier that would play the title.
Nothing here transcodes, remuxes, or extracts captions. A browser profile is
an optional input with the same fields a session already accepts. File paths
never leave this module.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from projectionist.engine.captions import (
    CAPTION_FALLBACK_REASON,
    CAPTION_PENDING_REASON,
    caption_fallback_reason,
)
from projectionist.engine.planner import canonical_codec, level_number, plan_playback
from projectionist.engine.probe import MediaStream, ProbeResult, subtitle_kind
from projectionist.engine.profiles import (
    DeviceProfile,
    known_profile_ids,
    named_profile,
    profile_from_mapping,
)
from projectionist.engine.source import MediaAsset, source_transcode_reason

logger = logging.getLogger(__name__)

REPORT_NAME = "playability.json"
TASK_NAME = "playability_report"

# Cheapest outcome first. These are labels for the planner's answer. The
# report itself does not transcode. Audio-only is served by ENG-012 when a
# client opts in. Source-transcode is the media source's own path, with a
# reason. This report does not start it.
TIER_DIRECT = "direct"
TIER_REMUX = "remux"
TIER_AUDIO = "audio"
TIER_CAPTIONS_PENDING = "captions-pending"
TIER_NEEDS_OCR = "needs-ocr"
TIER_SOURCE = "source-transcode"
TIER_NOT_PLAYABLE = "not-playable"

TIER_LABELS: dict[str, str] = {
    TIER_DIRECT: "Serve the file",
    TIER_REMUX: "Remux",
    TIER_AUDIO: "Audio-only",
    TIER_CAPTIONS_PENDING: "These captions are not ready yet",
    TIER_NEEDS_OCR: "Picture captions that are not text yet",
    TIER_SOURCE: "Ask the media source to transcode",
    TIER_NOT_PLAYABLE: "Not playable through the engine",
}

TIER_ORDER: tuple[str, ...] = tuple(TIER_LABELS)

_ENGINE_PLANS = frozenset({"direct", "remux", "audio"})
_TOP_REASONS = 5

LocateFn = Callable[[str], MediaAsset]
StopFn = Callable[[], bool]


class PlayabilityProfileError(ValueError):
    """The owner asked for a device profile this server does not know."""


@dataclass(frozen=True)
class LibraryTitle:
    rating_key: str
    title: str
    title_language: str
    watch_count: int = 0
    file_size: int = 0


def _nonneg(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def report_path(data_dir: Path) -> Path:
    return Path(data_dir) / "engine" / REPORT_NAME


def empty_playability_report(*, message: str = "") -> dict[str, Any]:
    return {
        "generated_at": None,
        "complete": False,
        "running": False,
        "phase": "idle",
        "planned_from_plex": 0,
        "confirmed_by_ffprobe": 0,
        "message": message or "No playability report yet. Refresh to walk the library.",
        "title_count": 0,
        "profiles": [],
    }


def hardware_sentence(video_transcodes: int) -> str:
    """What a GPU would change for this profile. N is titles that need video work."""
    count = max(0, int(video_transcodes))
    noun = "title" if count == 1 else "titles"
    return f"A GPU with Quick Sync would let {count} {noun} play without Plex."


def named_profiles() -> list[DeviceProfile]:
    found: list[DeviceProfile] = []
    for name in known_profile_ids():
        profile = named_profile(name)
        if profile is not None:
            found.append(profile)
    return found


def profiles_for_report(raw: Any) -> list[DeviceProfile]:
    """Named dry-run profiles, or one named profile, or those plus a browser profile.

    A browser profile uses the same object a session already accepts. It does
    not replace the named profiles unless the caller passed a single name.
    """
    named = named_profiles()
    if raw is None or raw == "":
        return named
    if isinstance(raw, str):
        chosen = named_profile(raw)
        if chosen is None:
            names = ", ".join(known_profile_ids())
            raise PlayabilityProfileError(f"Unknown device profile. Use one of: {names}.")
        return [chosen]
    if isinstance(raw, dict):
        extra = profile_from_mapping(raw)
        replaced = False
        merged: list[DeviceProfile] = []
        for profile in named:
            if profile.id == extra.id:
                merged.append(extra)
                replaced = True
            else:
                merged.append(profile)
        if not replaced:
            merged.append(extra)
        return merged
    raise PlayabilityProfileError("Device profile must be a name or an object.")


def library_titles(db: Any) -> list[LibraryTitle]:
    """Movies and episodes the report can name. No file paths."""
    if db is None:
        return []
    try:
        with db.connect() as conn:
            movies = conn.execute(
                """
                SELECT rating_key, title, original_language
                FROM library_items
                WHERE media_type = 'movie'
                  AND rating_key IS NOT NULL
                  AND rating_key != ''
                ORDER BY title, rating_key
                """
            ).fetchall()
            episodes = conn.execute(
                """
                SELECT e.rating_key AS rating_key,
                       CASE
                         WHEN e.title IS NOT NULL AND e.title != '' THEN e.title
                         ELSE s.title
                       END AS title,
                       s.original_language AS original_language
                FROM library_episodes e
                JOIN library_items s ON s.id = e.show_item_id
                WHERE e.rating_key IS NOT NULL AND e.rating_key != ''
                ORDER BY s.title, e.season_number, e.episode_number, e.rating_key
                """
            ).fetchall()
    except Exception:  # noqa: BLE001 — a report of nothing is safer than a traceback
        logger.exception("playability report could not list the library")
        return []
    rows: list[LibraryTitle] = []
    seen: set[str] = set()
    for row in list(movies) + list(episodes):
        key = str(row["rating_key"] or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(
            LibraryTitle(
                rating_key=key,
                title=str(row["title"] or ""),
                title_language=str(row["original_language"] or ""),
            )
        )
    return rows


def _safe_reason(reason: str, asset: MediaAsset) -> str:
    text = str(reason or "")
    for secret in (asset.local_path, asset.source_path):
        if secret and secret in text:
            text = text.replace(str(secret), "this file")
    return text


_SOURCE_REASONS = ("codec", "level", "bit_depth", "resolution", "hdr")


def empty_source_breakdown() -> dict[str, Any]:
    """Why a title is in the source-transcode bucket, plus size and HDR inside it.

    Codec, level, and bit depth are the planner's reason and add up to
    ``video_transcode`` when every title has one of those. ``codecs`` names
    the video codec of each title in that bucket. Resolution and HDR count
    titles in that same bucket that are above 1080p or carry HDR, so a 4K
    HEVC title can be both ``codec`` and ``resolution``.

    ``level``, ``bit_depth``, and ``hdr`` are null when that fact was not in
    the metadata and ffprobe has not confirmed it. Null is not a zero.
    """
    counts: dict[str, Any] = {name: 0 for name in ("video_transcode", *_SOURCE_REASONS)}
    counts["codecs"] = {}
    return counts


def _codec_from_answer(text: str) -> str:
    """The video codec named in a planner answer, when the row has no codec field."""
    folded = str(text or "").strip().lower()
    if not folded:
        return ""
    if " not in profile" in folded:
        return folded.split(" not in profile")[0].split()[-1]
    if " level is above" in folded:
        return folded.split(" level is above")[0].split()[-1]
    if "-bit is above" in folded:
        return folded.split("-bit is above")[0].split()[0]
    return ""


def _video_codec_name(row: Mapping[str, Any]) -> str:
    named = str(row.get("video_codec") or "").strip().lower()
    if named:
        return canonical_codec(named)
    answer = ""
    profile_answer = row.get("profile_answer")
    if isinstance(profile_answer, dict):
        answer = str(profile_answer.get("video") or "")
    return canonical_codec(_codec_from_answer(answer))


def _bit_depth_is_known(stream) -> bool:
    if bool(getattr(stream, "bit_depth_known", False)):
        return True
    if int(getattr(stream, "bit_depth", 0) or 0) >= 8:
        return True
    text = str(getattr(stream, "profile", "") or "").lower()
    return "12" in text or "10" in text


def source_block_reason(answer: str) -> str:
    """The planner's video answer, as one of codec, level, or bit depth."""
    return source_transcode_reason(answer)


def _video_stream(asset: MediaAsset):
    if asset.probe is None:
        return None
    for stream in asset.probe.streams:
        if stream.codec_type == "video":
            return stream
    return None


def _above_1080p(stream) -> bool:
    if stream is None:
        return False
    return (
        int(getattr(stream, "height", 0) or 0) > 1080
        or int(getattr(stream, "width", 0) or 0) > 1920
    )


def source_transcode_breakdown(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = empty_source_breakdown()
    codecs: dict[str, int] = {}
    level_unchecked = False
    saw_bucket = False
    bucket_hdr_known = True
    bit_depth_gap = False
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        video_codec = _video_codec_name(row)
        if video_codec and row.get("codec_in_profile") and not row.get("level_known"):
            # The codec is one this device plays, and the level was missing, so
            # the planner skipped the level check. A level count of 0 would
            # hide that.
            level_unchecked = True
        if str(row.get("tier") or "") != TIER_SOURCE:
            continue
        saw_bucket = True
        counts["video_transcode"] += 1
        reason = str(row.get("source_reason") or "")
        if reason not in {"codec", "level", "bit_depth"}:
            reason = "codec"
        counts[reason] += 1
        name = video_codec or "unknown"
        codecs[name] = codecs.get(name, 0) + 1
        if row.get("above_1080p"):
            counts["resolution"] += 1
        if row.get("video_hdr"):
            counts["hdr"] += 1
        if not row.get("hdr_known"):
            bucket_hdr_known = False
        if row.get("profile_limits_bit_depth") and not row.get("bit_depth_known"):
            bit_depth_gap = True
    counts["codecs"] = {
        name: count
        for name, count in sorted(codecs.items(), key=lambda item: (-item[1], item[0]))
    }
    if level_unchecked:
        counts["level"] = None
    if saw_bucket and counts["hdr"] == 0 and not bucket_hdr_known:
        counts["hdr"] = None
    # A profile that states no bit-depth limit never rejects for bit depth.
    # Zero there is the reason, not a claim that every file is 8-bit.
    # A profile that does limit bit depth, with a file whose depth was never
    # read, must not report that zero as a measurement.
    if saw_bucket and bit_depth_gap and counts["bit_depth"] == 0:
        counts["bit_depth"] = None
    return counts


def _copy_ahead_block(report: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Safari and Apple TV share this video-transcode set. Safari is the row we rank."""
    found: dict[str, Mapping[str, Any]] = {}
    for block in report.get("profiles") or []:
        if isinstance(block, Mapping) and block.get("profile"):
            found[str(block["profile"])] = block
    for profile_id in ("safari", "apple-tv-4k-3"):
        block = found.get(profile_id)
        if block is not None:
            return block
    return None


def copy_ahead_ranking(report: Mapping[str, Any]) -> dict[str, Any]:
    """Order a copy made ahead of time. This does not make the copy or transcode.

    Titles above 1080p in the Safari or Apple TV video-transcode set come first.
    The rest of that set follows, most-watched first. ``disk_bytes`` is the sum
    of the file sizes Plex already stored for the whole set.
    """
    block = _copy_ahead_block(report)
    empty: dict[str, Any] = {
        "profile": "",
        "title_count": 0,
        "above_1080p": 0,
        "disk_bytes": 0,
        "above_1080p_codecs": {},
        "titles": [],
    }
    if block is None:
        return empty
    waiting: list[Mapping[str, Any]] = []
    for row in block.get("titles") or []:
        if isinstance(row, Mapping) and str(row.get("tier") or "") == TIER_SOURCE:
            waiting.append(row)

    def sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            0 if row.get("above_1080p") else 1,
            -_nonneg(row.get("watch_count")),
            -_nonneg(row.get("file_size")),
            str(row.get("title") or ""),
            str(row.get("rating_key") or ""),
        )

    disk = 0
    above = 0
    codecs: dict[str, int] = {}
    titles: list[dict[str, Any]] = []
    for row in sorted(waiting, key=sort_key):
        size = _nonneg(row.get("file_size"))
        watches = _nonneg(row.get("watch_count"))
        is_above = bool(row.get("above_1080p"))
        disk += size
        name = str(row.get("video_codec") or "") or "unknown"
        if is_above:
            above += 1
            codecs[name] = codecs.get(name, 0) + 1
        titles.append(
            {
                "rating_key": str(row.get("rating_key") or ""),
                "title": str(row.get("title") or ""),
                "video_codec": name if row.get("video_codec") else "",
                "above_1080p": is_above,
                "watch_count": watches,
                "file_size": size,
                "hdr": str(row.get("hdr") or ""),
            }
        )
    return {
        "profile": str(block.get("profile") or ""),
        "title_count": len(titles),
        "above_1080p": above,
        "disk_bytes": disk,
        "above_1080p_codecs": {
            name: count
            for name, count in sorted(codecs.items(), key=lambda item: (-item[1], item[0]))
        },
        "titles": titles,
    }


def gpu_decision(profiles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """How many titles need a video transcode on Safari and on Apple TV.

    A missing profile stays null so a browser-only refresh does not claim
    that device needs zero titles.
    """
    found: dict[str, Optional[int]] = {"safari": None, "apple_tv": None}
    for block in profiles:
        if not isinstance(block, dict):
            continue
        profile_id = str(block.get("profile") or "")
        count = int((block.get("source_breakdown") or {}).get("video_transcode") or 0)
        if profile_id == "safari":
            found["safari"] = count
        elif profile_id == "apple-tv-4k-3":
            found["apple_tv"] = count
    return found


def _tier_for_plan(plan: str) -> str:
    if plan == "direct":
        return TIER_DIRECT
    if plan == "remux":
        return TIER_REMUX
    if plan == "audio":
        return TIER_AUDIO
    if plan in {"full", "source-transcode"}:
        return TIER_SOURCE
    return TIER_NOT_PLAYABLE


def classify_title(
    asset: MediaAsset,
    profile: DeviceProfile,
    *,
    title: str = "",
    title_language: str = "",
    settings: Any,
    data_dir: Path,
    watch_count: int = 0,
    file_size: int = 0,
) -> dict[str, Any]:
    """One title on one profile. The planner chooses. Captions can keep it off the engine.

    A text track that is not WebVTT yet, and a picture track, are counted apart.
    A video codec the profile cannot play asks the media source to transcode.
    That is a label, not a transcode.
    """
    planned = plan_playback(asset, profile)
    plan = str(planned.get("plan") or "")
    reason = _safe_reason(str(planned.get("reason") or ""), asset)
    tier = _tier_for_plan(plan)
    if plan in _ENGINE_PLANS:
        caption = caption_fallback_reason(
            asset,
            title_language=title_language,
            settings=settings,
            data_dir=data_dir,
        )
        if caption == CAPTION_PENDING_REASON:
            tier = TIER_CAPTIONS_PENDING
            reason = caption
        elif caption == CAPTION_FALLBACK_REASON:
            tier = TIER_NEEDS_OCR
            reason = caption
        elif caption:
            tier = TIER_NOT_PLAYABLE
            reason = _safe_reason(caption, asset)
    answer_raw = planned.get("profile_answer")
    answer: dict[str, object] = {}
    if isinstance(answer_raw, dict):
        answer = answer_raw
    video = _video_stream(asset)
    video_answer = str(answer.get("video") or "")
    source_reason = ""
    provider = ""
    if tier == TIER_SOURCE:
        source_reason = (
            str(planned.get("source_reason") or "") or source_block_reason(video_answer) or "codec"
        )
        provider = str(planned.get("provider") or "") or "plex"
    video_codec = canonical_codec(video.codec) if video is not None else ""
    hdr_value = str(getattr(video, "hdr", "") or "").strip() if video is not None else ""
    level_known = (
        level_number(video_codec, str(getattr(video, "level", "") or "")) is not None
        if video is not None and video_codec
        else False
    )
    codec_in_profile = bool(
        video_codec
        and any(canonical_codec(cap.codec) == video_codec for cap in profile.video)
    )
    profile_limits_bit_depth = bool(
        video_codec
        and any(
            canonical_codec(cap.codec) == video_codec and int(cap.bit_depth or 0) > 0
            for cap in profile.video
        )
    )
    return {
        "rating_key": str(asset.rating_key or ""),
        "title": str(title or ""),
        "tier": tier,
        "label": TIER_LABELS.get(tier, TIER_LABELS[TIER_NOT_PLAYABLE]),
        "plan": plan,
        "reason": reason,
        "profile_answer": {
            "video": video_answer,
            "audio": str(answer.get("audio") or ""),
        },
        "source_reason": source_reason,
        "provider": provider,
        "video_codec": video_codec,
        "level_known": level_known,
        "bit_depth_known": _bit_depth_is_known(video) if video is not None else False,
        "hdr_known": (
            bool(getattr(video, "hdr_known", False) or hdr_value) if video is not None else False
        ),
        "codec_in_profile": codec_in_profile,
        "profile_limits_bit_depth": profile_limits_bit_depth,
        "above_1080p": _above_1080p(video),
        "video_hdr": bool(hdr_value),
        "hdr": hdr_value,
        "watch_count": _nonneg(watch_count),
        "file_size": _nonneg(file_size) or _nonneg(getattr(asset.probe, "size", 0)),
    }


def _shares(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    total = len(rows)
    counts = {tier: 0 for tier in TIER_ORDER}
    for row in rows:
        tier = str(row.get("tier") or "")
        if tier in counts:
            counts[tier] += 1
    shares: dict[str, dict[str, Any]] = {}
    for tier in TIER_ORDER:
        count = counts[tier]
        shares[tier] = {
            "count": count,
            "share": round(count / total, 4) if total else 0,
            "label": TIER_LABELS[tier],
        }
    return shares


def _top_reasons(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason") or "").strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"reason": reason, "count": count} for reason, count in ordered[:_TOP_REASONS]]


def summarize_profile(
    profile: DeviceProfile,
    rows: Sequence[Mapping[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    shares = _shares(rows)
    return {
        "profile": profile.id,
        "generated_at": generated_at,
        "title_count": len(rows),
        "shares": shares,
        "top_reasons": _top_reasons(rows),
        "titles": [dict(row) for row in rows],
        "hardware": hardware_sentence(int(shares[TIER_SOURCE]["count"])),
        "source_breakdown": source_transcode_breakdown(rows),
    }


def build_playability_report(
    titles: Sequence[LibraryTitle],
    assets: Mapping[str, MediaAsset],
    profiles: Sequence[DeviceProfile],
    *,
    settings: Any,
    data_dir: Path,
    generated_at: Optional[str] = None,
    complete: bool = True,
    message: str = "",
) -> dict[str, Any]:
    """Classify the titles already in hand. ``assets`` is keyed by rating key."""
    stamp = generated_at or _stamp()
    if not message:
        if not complete:
            message = "The walk stopped early. Refresh to finish the library."
        elif not titles:
            message = "The library has no titles to check yet."
    profiles_out: list[dict[str, Any]] = []
    for profile in profiles:
        rows: list[dict[str, Any]] = []
        for item in titles:
            asset = assets.get(item.rating_key)
            if asset is None:
                asset = MediaAsset(
                    rating_key=item.rating_key,
                    readable=False,
                    reason="Projectionist cannot read this file",
                )
            rows.append(
                classify_title(
                    asset,
                    profile,
                    title=item.title,
                    title_language=item.title_language,
                    settings=settings,
                    data_dir=data_dir,
                    watch_count=item.watch_count,
                    file_size=item.file_size,
                )
            )
        profiles_out.append(summarize_profile(profile, rows, generated_at=stamp))
    report = {
        "generated_at": stamp,
        "complete": bool(complete),
        "message": message,
        "title_count": len(titles),
        "profiles": profiles_out,
        "gpu": gpu_decision(profiles_out),
    }
    report["copy_ahead"] = copy_ahead_ranking(report)
    return report


_TITLE_PAGE = 40


def playability_progress(report: Mapping[str, Any]) -> dict[str, Any]:
    """Shares and walk progress. Title rows stay in the saved report."""
    copied = dict(report)
    profiles: list[dict[str, Any]] = []
    for block in report.get("profiles") or []:
        if not isinstance(block, dict):
            continue
        profiles.append({key: value for key, value in block.items() if key != "titles"})
    copied["profiles"] = profiles
    ahead = copied.get("copy_ahead")
    if isinstance(ahead, dict):
        copied["copy_ahead"] = {key: value for key, value in ahead.items() if key != "titles"}
    return copied


def playability_title_page(
    report: Mapping[str, Any],
    *,
    profile: str,
    tier: str,
    limit: int = _TITLE_PAGE,
    offset: int = 0,
) -> dict[str, Any]:
    """One page of title rows for a profile and tier. The page is capped."""
    try:
        page_limit = int(limit)
    except (TypeError, ValueError):
        page_limit = _TITLE_PAGE
    page_limit = min(max(page_limit, 1), _TITLE_PAGE)
    try:
        page_offset = int(offset)
    except (TypeError, ValueError):
        page_offset = 0
    page_offset = max(page_offset, 0)
    wanted_profile = str(profile or "")
    wanted_tier = str(tier or "")
    matched: list[dict[str, Any]] = []
    for block in report.get("profiles") or []:
        if not isinstance(block, dict) or str(block.get("profile") or "") != wanted_profile:
            continue
        for row in block.get("titles") or []:
            if isinstance(row, dict) and str(row.get("tier") or "") == wanted_tier:
                matched.append(dict(row))
        break
    return {
        "profile": wanted_profile,
        "tier": wanted_tier,
        "total": len(matched),
        "offset": page_offset,
        "limit": page_limit,
        "titles": matched[page_offset : page_offset + page_limit],
    }


def load_playability_report(data_dir: Path) -> dict[str, Any]:
    path = report_path(data_dir)
    if not path.is_file():
        return empty_playability_report()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("playability report could not be read")
        return empty_playability_report(
            message="The saved playability report could not be read. Refresh to walk the library."
        )
    if not isinstance(loaded, dict):
        return empty_playability_report(
            message="The saved playability report could not be read. Refresh to walk the library."
        )
    if _WALKING:
        loaded = dict(loaded)
        loaded["running"] = True
    elif loaded.get("running"):
        loaded = dict(loaded)
        loaded["running"] = False
    return loaded


def save_playability_report(data_dir: Path, report: Mapping[str, Any]) -> None:
    """Write the report atomically. Each caller gets its own temp file.

    ``request_owner_report`` already refuses a second walker, and the scheduled
    task does not save. This helper can still be called from more than one
    thread, so the temp name is not a single ``playability.json.tmp``.
    """
    path = report_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(report), indent=2))
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def merge_playability_reports(
    previous: Mapping[str, Any], fresh: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep profiles this run did not refresh, such as a browser profile from Settings.

    A walk that stopped early is not a refresh. Its prefix must not replace
    named profiles while a browser row this run left alone keeps another title count.
    """
    if not fresh.get("complete"):
        copied = dict(previous)
        copied["profiles"] = [
            dict(row) if isinstance(row, dict) else row for row in (previous.get("profiles") or [])
        ]
        return copied
    by_id: dict[str, dict[str, Any]] = {}
    for row in previous.get("profiles") or []:
        if isinstance(row, dict) and row.get("profile"):
            by_id[str(row["profile"])] = dict(row)
    order: list[str] = []
    for row in fresh.get("profiles") or []:
        if not isinstance(row, dict) or not row.get("profile"):
            continue
        key = str(row["profile"])
        by_id[key] = dict(row)
        if key not in order:
            order.append(key)
    for key in by_id:
        if key not in order:
            order.append(key)
    merged = dict(fresh)
    merged["profiles"] = [by_id[key] for key in order]
    return merged


def _unread(rating_key: str) -> MediaAsset:
    return MediaAsset(
        rating_key=rating_key,
        readable=False,
        reason="Projectionist cannot read this file",
    )


def _stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_library_report(
    db: Any,
    settings: Any,
    data_dir: Path,
    *,
    locate: LocateFn,
    profiles: Optional[Sequence[DeviceProfile]] = None,
    should_stop: Optional[StopFn] = None,
    merge: bool = True,
) -> dict[str, Any]:
    """Walk the library once, plan every requested profile, and store the report.

    A stop leaves the saved report unchanged. Titles visited so far are not
    a new snapshot.
    """
    chosen = list(profiles) if profiles is not None else named_profiles()
    titles = library_titles(db)
    kept: list[LibraryTitle] = []
    assets: dict[str, MediaAsset] = {}
    stopped = False
    for item in titles:
        if should_stop is not None and should_stop():
            stopped = True
            break
        try:
            asset = locate(item.rating_key)
        except Exception:  # noqa: BLE001 — one title must not sink the report
            logger.exception("playability locate failed for %s", item.rating_key)
            asset = _unread(item.rating_key)
        if asset is None:
            asset = _unread(item.rating_key)
        assets[item.rating_key] = asset
        kept.append(item)
    if stopped:
        logger.info(
            "playability walk stopped after %s of %s titles; the saved report stays",
            len(kept),
            len(titles),
        )
        return load_playability_report(Path(data_dir))
    report = build_playability_report(
        kept,
        assets,
        chosen,
        settings=settings,
        data_dir=Path(data_dir),
        complete=True,
    )
    if merge:
        report = merge_playability_reports(load_playability_report(data_dir), report)
    save_playability_report(data_dir, report)
    return report


_WALK_LOCK = threading.Lock()
_WALKING = False


def _default_spawn(target: Callable[[], None]) -> None:
    threading.Thread(target=target, name="playability-report", daemon=True).start()


spawn_walk = _default_spawn


def _timeout_text(text: str) -> bool:
    folded = str(text or "").lower()
    return "timeout" in folded or "timed out" in folded or "circuit open" in folded


def asset_from_plex_row(row: Mapping[str, Any]) -> MediaAsset:
    """A planner asset from Plex stream metadata. No file path and no ffprobe."""
    streams: list[MediaStream] = []
    for index, raw in enumerate(row.get("streams") or []):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("codec_type") or "")
        codec = str(raw.get("codec") or "")
        raw_index = raw.get("index")
        try:
            stream_index = int(raw_index) if raw_index is not None else index
        except (TypeError, ValueError):
            stream_index = index
        profile = str(raw.get("profile") or "")
        bit_depth = int(raw.get("bit_depth") or 0)
        hdr = str(raw.get("hdr") or "") if kind == "video" else ""
        profile_bits = "12" in profile.lower() or "10" in profile.lower()
        streams.append(
            MediaStream(
                index=stream_index,
                codec_type=kind,
                codec=codec,
                language=str(raw.get("language") or ""),
                width=int(raw.get("width") or 0),
                height=int(raw.get("height") or 0),
                channels=int(raw.get("channels") or 0),
                profile=profile,
                level=str(raw.get("level") or ""),
                hdr=hdr,
                bit_depth=bit_depth,
                subtitle_kind=subtitle_kind(codec) if kind == "subtitle" else "",
                hdr_known=bool(raw.get("hdr_known") or hdr) if kind == "video" else False,
                bit_depth_known=bool(raw.get("bit_depth_known") or bit_depth >= 8 or profile_bits)
                if kind == "video"
                else False,
            )
        )
    container = str(row.get("container") or "")
    return MediaAsset(
        rating_key=str(row.get("rating_key") or ""),
        readable=True,
        probe=ProbeResult(
            container=container,
            format_name=container,
            duration_s=0,
            bitrate=0,
            size=0,
            streams=streams,
        ),
    )


def plex_stream_catalog(settings: Any) -> list[dict[str, Any]]:
    """The library's stream list from Plex. Tests replace this."""
    url = str(getattr(settings, "plex_url", "") or "").strip()
    token = str(getattr(settings, "plex_token", "") or "").strip()
    if not url or not token:
        return []
    from projectionist.connectors.plex import PlexClient

    client = PlexClient(
        url,
        token,
        timeout=30,
        movie_section=str(getattr(settings, "plex_movie_section", "") or "") or None,
        tv_section=str(getattr(settings, "plex_tv_section", "") or "") or None,
    )
    rows = list(client.playback_stream_catalog())
    database = str(getattr(settings, "plex_library_database", "") or "").strip()
    if not database:
        database = str(os.environ.get("PLEX_LIBRARY_DATABASE") or "").strip()
    if not database:
        return rows
    from projectionist.connectors.plex import apply_plex_media_analysis, read_plex_media_analysis

    analysis = read_plex_media_analysis(Path(database))
    if not analysis:
        return rows
    return apply_plex_media_analysis(rows, analysis)


def _mark_unconfirmed(report: dict[str, Any]) -> None:
    for block in report.get("profiles") or []:
        if not isinstance(block, dict):
            continue
        for row in block.get("titles") or []:
            if isinstance(row, dict):
                row["confirmed"] = False


def _confirmed_keys(report: Mapping[str, Any]) -> set[str]:
    profiles = report.get("profiles") or []
    if not profiles or not isinstance(profiles[0], dict):
        return set()
    found: set[str] = set()
    for row in profiles[0].get("titles") or []:
        if isinstance(row, dict) and row.get("confirmed"):
            found.add(str(row.get("rating_key") or ""))
    found.discard("")
    return found


def _apply_confirmed_title(
    report: dict[str, Any],
    rating_key: str,
    classified: Mapping[str, dict[str, Any]],
) -> None:
    for block in report.get("profiles") or []:
        if not isinstance(block, dict):
            continue
        profile_id = str(block.get("profile") or "")
        incoming = classified.get(profile_id)
        if incoming is None:
            continue
        rows: list[dict[str, Any]] = []
        replaced = False
        for row in block.get("titles") or []:
            if isinstance(row, dict) and str(row.get("rating_key") or "") == rating_key:
                kept = dict(incoming)
                if not _nonneg(kept.get("watch_count")):
                    kept["watch_count"] = _nonneg(row.get("watch_count"))
                if not _nonneg(kept.get("file_size")):
                    kept["file_size"] = _nonneg(row.get("file_size"))
                rows.append(kept)
                replaced = True
            elif isinstance(row, dict):
                rows.append(row)
        if not replaced:
            rows.append(dict(incoming))
        shares = _shares(rows)
        block["titles"] = rows
        block["shares"] = shares
        block["top_reasons"] = _top_reasons(rows)
        block["title_count"] = len(rows)
        block["hardware"] = hardware_sentence(int(shares[TIER_SOURCE]["count"]))
        block["source_breakdown"] = source_transcode_breakdown(rows)
    report["gpu"] = gpu_decision(
        [block for block in report.get("profiles") or [] if isinstance(block, dict)]
    )
    report["copy_ahead"] = copy_ahead_ranking(report)
    report["confirmed_by_ffprobe"] = len(_confirmed_keys(report))
    report["title_count"] = max(
        (
            int(block.get("title_count") or 0)
            for block in report.get("profiles") or []
            if isinstance(block, dict)
        ),
        default=0,
    )


def _run_owner_report(
    db: Any,
    settings: Any,
    data_dir: Path,
    *,
    profiles: Sequence[DeviceProfile],
    locate: LocateFn,
    catalog: Callable[[Any], Sequence[Mapping[str, Any]]],
    should_stop: Optional[StopFn] = None,
) -> dict[str, Any]:
    """Plan from Plex metadata, save that, then confirm with one ffprobe at a time."""
    root = Path(data_dir)
    current = load_playability_report(root)
    resume = bool(current.get("planned_from_plex")) and not current.get("complete")
    chosen = list(profiles)
    if resume and current.get("profile_specs"):
        chosen = [
            profile_from_mapping(spec)
            for spec in current["profile_specs"]
            if isinstance(spec, dict)
        ]
    report = dict(current) if resume else empty_playability_report()
    report["running"] = True
    report["phase"] = "plex-metadata" if not resume else "ffprobe"
    save_playability_report(root, report)
    if not resume:
        try:
            rows = list(catalog(settings))
        except Exception as error:  # noqa: BLE001 — the owner can refresh
            logger.exception("playability catalog failed")
            message = (
                "Plex timed out before the stream list was ready. Refresh to try again."
                if _timeout_text(str(error))
                else "The playability report could not read Plex's stream list. Refresh to try again."
            )
            failed = empty_playability_report(message=message)
            failed["running"] = False
            save_playability_report(root, failed)
            return failed
        names = {item.rating_key: item for item in library_titles(db)}
        titles: list[LibraryTitle] = []
        assets: dict[str, MediaAsset] = {}
        for row in rows:
            key = str(row.get("rating_key") or "")
            if not key:
                continue
            known = names.get(key)
            titles.append(
                LibraryTitle(
                    rating_key=key,
                    title=known.title if known is not None else str(row.get("title") or ""),
                    title_language=known.title_language if known is not None else "",
                    watch_count=_nonneg(row.get("view_count")),
                    file_size=_nonneg(row.get("file_size")),
                )
            )
            assets[key] = asset_from_plex_row(row)
        if not titles:
            empty = empty_playability_report(
                message="Plex did not return stream metadata. Refresh to try again."
            )
            empty["running"] = False
            save_playability_report(root, empty)
            return empty
        report = build_playability_report(
            titles,
            assets,
            chosen,
            settings=settings,
            data_dir=root,
            complete=False,
            message="Planned from Plex metadata. Confirming files in the background.",
        )
        _mark_unconfirmed(report)
        report["running"] = True
        report["phase"] = "ffprobe"
        report["planned_from_plex"] = len(titles)
        report["confirmed_by_ffprobe"] = 0
        report["profile_specs"] = [profile.as_public() for profile in chosen]
        save_playability_report(root, report)
    else:
        report["running"] = True
        report["phase"] = "ffprobe"
        report["message"] = "Confirming files in the background."
        save_playability_report(root, report)

    done = _confirmed_keys(report)
    order = library_titles(db)
    known_keys = {item.rating_key for item in order}
    for block in report.get("profiles") or []:
        if not isinstance(block, dict):
            continue
        for row in block.get("titles") or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("rating_key") or "")
            if key and key not in known_keys:
                order.append(
                    LibraryTitle(
                        rating_key=key, title=str(row.get("title") or ""), title_language=""
                    )
                )
                known_keys.add(key)
        break
    stopped = False
    paused = False
    since_save = 0
    for item in order:
        if should_stop is not None and should_stop():
            stopped = True
            break
        if item.rating_key in done:
            continue
        try:
            asset = locate(item.rating_key)
        except Exception:  # noqa: BLE001 — one title must not sink the report
            logger.exception("playability confirm failed for %s", item.rating_key)
            asset = _unread(item.rating_key)
        if asset is None:
            asset = _unread(item.rating_key)
        if _timeout_text(asset.reason):
            paused = True
            report["message"] = "Confirmation paused because Plex timed out. Refresh to continue."
            break
        classified: dict[str, dict[str, Any]] = {}
        for profile in chosen:
            row = classify_title(
                asset,
                profile,
                title=item.title,
                title_language=item.title_language,
                settings=settings,
                data_dir=root,
            )
            row["confirmed"] = True
            classified[profile.id] = row
        _apply_confirmed_title(report, item.rating_key, classified)
        done.add(item.rating_key)
        since_save += 1
        if since_save >= 20:
            save_playability_report(root, report)
            since_save = 0
    report["running"] = False
    report["confirmed_by_ffprobe"] = len(_confirmed_keys(report))
    if paused or stopped:
        report["complete"] = False
        report["phase"] = "ffprobe"
        if stopped and not paused:
            report["message"] = "The walk stopped early. Refresh to continue."
    else:
        report["complete"] = True
        report["phase"] = "idle"
        planned = int(report.get("planned_from_plex") or 0)
        confirmed = int(report.get("confirmed_by_ffprobe") or 0)
        report["message"] = (
            f"Planned {planned} titles from Plex metadata. Confirmed {confirmed} with ffprobe."
        )
    save_playability_report(root, report)
    return report


def request_owner_report(
    db: Any,
    settings: Any,
    data_dir: Path,
    *,
    profiles: Sequence[DeviceProfile],
    locate: LocateFn,
    catalog: Optional[Callable[[Any], Sequence[Mapping[str, Any]]]] = None,
    should_stop: Optional[StopFn] = None,
) -> dict[str, Any]:
    """Start the owner walk if one is not already running, and return what we have.

    The response does not wait for ffprobe. A second request does not start
    another walker.
    """
    global _WALKING
    root = Path(data_dir)
    source = catalog or plex_stream_catalog
    with _WALK_LOCK:
        if _WALKING:
            current = load_playability_report(root)
            current["running"] = True
            return current
        _WALKING = True

    def _target() -> None:
        global _WALKING
        try:
            _run_owner_report(
                db,
                settings,
                root,
                profiles=profiles,
                locate=locate,
                catalog=source,
                should_stop=should_stop,
            )
        finally:
            with _WALK_LOCK:
                _WALKING = False

    spawn_walk(_target)
    current = load_playability_report(root)
    if _WALKING:
        current["running"] = True
        if not current.get("message"):
            current["message"] = "The playability report is starting."
    return current
