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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from projectionist.engine.captions import (
    CAPTION_FALLBACK_REASON,
    CAPTION_PENDING_REASON,
    caption_fallback_reason,
)
from projectionist.engine.planner import plan_playback
from projectionist.engine.profiles import (
    DeviceProfile,
    known_profile_ids,
    named_profile,
    profile_from_mapping,
)
from projectionist.engine.source import MediaAsset

logger = logging.getLogger(__name__)

REPORT_NAME = "playability.json"
TASK_NAME = "playability_report"

# Cheapest outcome first. These are labels for the planner's answer, not new
# pipelines. Audio-only and a video transcode are named so the report is honest
# about what would have to happen. Serving them is later work.
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


def report_path(data_dir: Path) -> Path:
    return Path(data_dir) / "engine" / REPORT_NAME


def empty_playability_report(*, message: str = "") -> dict[str, Any]:
    return {
        "generated_at": None,
        "complete": False,
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


def _tier_for_plan(plan: str) -> str:
    if plan == "direct":
        return TIER_DIRECT
    if plan == "remux":
        return TIER_REMUX
    if plan == "audio":
        return TIER_AUDIO
    if plan == "full":
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
    return {
        "rating_key": str(asset.rating_key or ""),
        "title": str(title or ""),
        "tier": tier,
        "label": TIER_LABELS.get(tier, TIER_LABELS[TIER_NOT_PLAYABLE]),
        "plan": plan,
        "reason": reason,
        "profile_answer": {
            "video": str(answer.get("video") or ""),
            "audio": str(answer.get("audio") or ""),
        },
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
                )
            )
        profiles_out.append(summarize_profile(profile, rows, generated_at=stamp))
    return {
        "generated_at": stamp,
        "complete": bool(complete),
        "message": message,
        "title_count": len(titles),
        "profiles": profiles_out,
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
    return loaded


def save_playability_report(data_dir: Path, report: Mapping[str, Any]) -> None:
    path = report_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(dict(report), indent=2), encoding="utf-8")
    temporary.replace(path)


def merge_playability_reports(previous: Mapping[str, Any], fresh: Mapping[str, Any]) -> dict[str, Any]:
    """Keep profiles this run did not refresh, such as a browser profile from Settings."""
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
    """Walk the library once, plan every requested profile, and store the report."""
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
    report = build_playability_report(
        kept,
        assets,
        chosen,
        settings=settings,
        data_dir=Path(data_dir),
        complete=not stopped,
    )
    if merge:
        report = merge_playability_reports(load_playability_report(data_dir), report)
    save_playability_report(data_dir, report)
    return report
