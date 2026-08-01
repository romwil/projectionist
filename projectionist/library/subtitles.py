"""Household subtitle helpers — prefer Plex-attached tracks, soft-fail downloads."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.connectors.plex import PlexClient, PlexSubtitleStream

logger = logging.getLogger(__name__)

# Living-room empty copy (Live Watch + dig-in). Never invent third-party providers.
NO_CAPTIONS_AIRING = "No captions available for this airing"
NO_SUBTITLES_STREAM = "No subtitles on this stream"
DOWNLOAD_SOFT_FAIL = (
    "Plex couldn’t find subtitles for this title right now. "
    "Agents may be off, or nothing matched your preferred language."
)


def normalize_subtitle_language(value: Any, *, default: str = "en") -> str:
    """Normalize to a short ISO-ish language code (``en``, ``es``, ``eng`` → ``en``)."""
    text = str(value or "").strip().lower().replace("_", "-")
    if not text:
        return default
    # Accept en, eng, en-US → en / eng
    primary = text.split("-", 1)[0]
    if len(primary) >= 2:
        return primary[:3] if len(primary) == 3 else primary[:2]
    return default


def preferred_subtitle_languages(settings: Any = None) -> List[str]:
    """Household primary + fallback language codes (deduped, non-empty)."""
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    primary = normalize_subtitle_language(
        getattr(tunarr, "subtitle_language_primary", None)
        if tunarr is not None
        else None,
        default="en",
    )
    fallback_raw = (
        getattr(tunarr, "subtitle_language_fallback", None) if tunarr is not None else None
    )
    fallback = normalize_subtitle_language(fallback_raw, default="") if fallback_raw else ""
    out: List[str] = []
    for code in (primary, fallback):
        if code and code not in out:
            out.append(code)
    return out or ["en"]


def language_matches(stream: Mapping[str, Any] | PlexSubtitleStream, code: str) -> bool:
    """True when a stream's language/code matches the preferred code (en↔eng)."""
    wanted = normalize_subtitle_language(code, default="")
    if not wanted:
        return False
    if isinstance(stream, PlexSubtitleStream):
        candidates = (stream.language_code, stream.language)
    else:
        candidates = (
            stream.get("language_code"),
            stream.get("language"),
            stream.get("lang"),
        )
    for raw in candidates:
        have = normalize_subtitle_language(raw, default="")
        if not have:
            continue
        if have == wanted:
            return True
        # eng ↔ en
        if len(have) == 3 and have.startswith(wanted) and len(wanted) == 2:
            return True
        if len(wanted) == 3 and wanted.startswith(have) and len(have) == 2:
            return True
    return False


def has_preferred_subtitle(
    streams: Sequence[Mapping[str, Any] | PlexSubtitleStream],
    languages: Sequence[str],
) -> bool:
    for code in languages:
        for stream in streams:
            if language_matches(stream, code) and not (
                isinstance(stream, PlexSubtitleStream) and stream.forced
            ):
                # Prefer non-forced; still count forced if it's the only match later.
                return True
    # Forced-only match still counts as "has preferred".
    for code in languages:
        for stream in streams:
            if language_matches(stream, code):
                return True
    return False


def pick_search_candidate(
    candidates: Sequence[PlexSubtitleStream],
    *,
    prefer_sdh: bool = False,
) -> Optional[PlexSubtitleStream]:
    """Pick the best on-demand search hit (non-forced preferred; SDH optional)."""
    if not candidates:
        return None
    ranked = list(candidates)

    def score(item: PlexSubtitleStream) -> tuple:
        return (
            0 if item.forced else 1,
            1 if (prefer_sdh and item.hearing_impaired) else 0,
            1 if item.hearing_impaired else 0,
            1 if item.external else 0,
        )

    ranked.sort(key=score, reverse=True)
    return ranked[0]


def plex_client_from_settings(settings: Any, *, timeout: int = 20) -> Optional[PlexClient]:
    url = str(getattr(settings, "plex_url", "") or "").strip()
    token = str(getattr(settings, "plex_token", "") or "").strip()
    if not url or not token:
        return None
    return PlexClient(url, token, timeout=timeout)


def list_item_subtitles(
    settings: Any,
    rating_key: str,
) -> Dict[str, Any]:
    """List Plex-attached subtitle streams for a movie/episode rating key."""
    key = str(rating_key or "").strip()
    languages = preferred_subtitle_languages(settings)
    if not key:
        return {
            "ok": False,
            "rating_key": "",
            "streams": [],
            "preferred_languages": languages,
            "has_preferred": False,
            "message": "A Plex rating key is required.",
            "reason": "missing_rating_key",
        }
    client = plex_client_from_settings(settings)
    if client is None:
        return {
            "ok": False,
            "rating_key": key,
            "streams": [],
            "preferred_languages": languages,
            "has_preferred": False,
            "message": "Plex isn’t connected, so subtitle tracks aren’t available.",
            "reason": "plex_unconfigured",
        }
    try:
        streams = client.list_subtitle_streams(key)
    except Exception as error:  # noqa: BLE001
        logger.info("Plex subtitle list failed for %s: %s", key, error)
        return {
            "ok": False,
            "rating_key": key,
            "streams": [],
            "preferred_languages": languages,
            "has_preferred": False,
            "message": "Couldn’t read subtitle tracks from Plex for this title.",
            "reason": "plex_error",
            "error": str(error)[:200],
        }
    rows = [s.to_dict() for s in streams]
    return {
        "ok": True,
        "rating_key": key,
        "streams": rows,
        "preferred_languages": languages,
        "has_preferred": has_preferred_subtitle(streams, languages),
        "message": "" if rows else "No subtitle tracks are attached in Plex yet.",
        "reason": "" if rows else "none_attached",
    }


def download_preferred_subtitles(
    settings: Any,
    rating_key: str,
    *,
    language: str = "",
    prefer_sdh: bool = False,
) -> Dict[str, Any]:
    """Search + download via Plex when preferred language is missing. Soft-fail honesty."""
    key = str(rating_key or "").strip()
    languages = preferred_subtitle_languages(settings)
    if language:
        languages = [normalize_subtitle_language(language)] + [
            c for c in languages if c != normalize_subtitle_language(language)
        ]
    if not key:
        return {
            "ok": False,
            "downloaded": False,
            "rating_key": "",
            "message": "A Plex rating key is required.",
            "reason": "missing_rating_key",
            "streams": [],
        }
    client = plex_client_from_settings(settings)
    if client is None:
        return {
            "ok": False,
            "downloaded": False,
            "rating_key": key,
            "message": "Plex isn’t connected, so Projectionist can’t ask it for subtitles.",
            "reason": "plex_unconfigured",
            "streams": [],
        }

    try:
        existing = client.list_subtitle_streams(key)
    except Exception as error:  # noqa: BLE001
        logger.info("Plex subtitle list before download failed for %s: %s", key, error)
        return {
            "ok": False,
            "downloaded": False,
            "rating_key": key,
            "message": "Couldn’t read this title’s tracks in Plex.",
            "reason": "plex_error",
            "error": str(error)[:200],
            "streams": [],
        }

    if has_preferred_subtitle(existing, languages):
        return {
            "ok": True,
            "downloaded": False,
            "already_present": True,
            "rating_key": key,
            "message": "Subtitles for your preferred language are already on this title in Plex.",
            "reason": "already_present",
            "streams": [s.to_dict() for s in existing],
            "preferred_languages": languages,
        }

    last_error = ""
    for code in languages:
        try:
            hits = client.search_subtitles(key, language=code)
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:200]
            logger.info("Plex subtitle search failed for %s lang=%s: %s", key, code, error)
            continue
        pick = pick_search_candidate(hits, prefer_sdh=prefer_sdh)
        if pick is None or not pick.key:
            continue
        try:
            client.download_subtitle(key, pick.key)
        except Exception as error:  # noqa: BLE001
            last_error = str(error)[:200]
            logger.info("Plex subtitle download failed for %s: %s", key, error)
            continue
        # Re-list; download is async on PMS — report accepted even if not attached yet.
        try:
            refreshed = client.list_subtitle_streams(key)
        except Exception:  # noqa: BLE001
            refreshed = existing
        return {
            "ok": True,
            "downloaded": True,
            "already_present": False,
            "rating_key": key,
            "language": code,
            "message": (
                f"Asked Plex to download {code} subtitles. "
                "They’ll show up here (and in Plex) once the agent finishes."
            ),
            "reason": "download_started",
            "streams": [s.to_dict() for s in refreshed],
            "preferred_languages": languages,
            "picked": pick.to_dict(),
        }

    return {
        "ok": False,
        "downloaded": False,
        "rating_key": key,
        "message": DOWNLOAD_SOFT_FAIL,
        "reason": "none_found",
        "error": last_error,
        "streams": [s.to_dict() for s in existing],
        "preferred_languages": languages,
    }


def srt_to_vtt(raw: str) -> str:
    """Minimal SRT → WebVTT conversion for Live sidecar tracks."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if text.upper().startswith("WEBVTT"):
        return text if text.endswith("\n") else text + "\n"
    # Strip numeric cue indexes; rewrite comma decimals to dots.
    lines: List[str] = ["WEBVTT", ""]
    for line in text.split("\n"):
        stripped = line.strip()
        if re.fullmatch(r"\d+", stripped):
            continue
        if "-->" in stripped:
            stripped = stripped.replace(",", ".")
        lines.append(stripped)
    body = "\n".join(lines).rstrip() + "\n"
    return body


def live_subtitles_payload(
    settings: Any,
    *,
    channel_id: str,
    now_program: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Richer `/live` CC payload: Plex tracks when a rating key maps; honest empty otherwise."""
    cid = str(channel_id or "").strip()
    languages = preferred_subtitle_languages(settings)
    rating_key = ""
    if isinstance(now_program, Mapping):
        rating_key = str(now_program.get("plex_rating_key") or "").strip()
    base: Dict[str, Any] = {
        "ok": True,
        "channel_id": cid,
        "plex_rating_key": rating_key or None,
        "preferred_languages": languages,
        "stream_hint": (
            "Captions appear here when the Live encode carries them, "
            "or when this airing maps to a Plex library title with tracks."
        ),
        "plex_streams": [],
        "has_preferred": False,
        "can_download": False,
        "empty_message": NO_CAPTIONS_AIRING,
        "message": "",
        "reason": "",
    }
    if not rating_key:
        base["reason"] = "no_plex_mapping"
        base["message"] = NO_CAPTIONS_AIRING
        return base

    listed = list_item_subtitles(settings, rating_key)
    base["plex_streams"] = list(listed.get("streams") or [])
    base["has_preferred"] = bool(listed.get("has_preferred"))
    base["can_download"] = bool(listed.get("ok")) and not bool(listed.get("has_preferred"))
    if listed.get("ok") and base["plex_streams"]:
        base["message"] = ""
        base["reason"] = ""
        base["empty_message"] = ""
    else:
        base["message"] = NO_CAPTIONS_AIRING
        base["reason"] = str(listed.get("reason") or "none_attached")
        if listed.get("reason") == "plex_unconfigured":
            base["message"] = str(listed.get("message") or base["message"])
    return base
