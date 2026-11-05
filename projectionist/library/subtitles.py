"""Household subtitle helpers — prefer Plex-attached tracks, soft-fail downloads."""

from __future__ import annotations

import logging
import re
import urllib.parse
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

# Text-based formats Projectionist can overlay. Image formats (PGS/VobSub/…)
# cannot be painted by SubtitleOverlay — never treat them as a preferred hit.
IMAGE_SUBTITLE_FORMATS = frozenset(
    {
        "pgs",
        "pgssub",
        "pgs_subtitle",
        "hdmv_pgs",
        "hdmv_pgs_subtitle",
        "hdmv_text_subtitle",
        "vobsub",
        "dvd_subtitle",
        "dvdsub",
        "dvb_subtitle",
        "dvbsub",
        "xsub",
        "overlay",
    }
)
IMAGE_SUBTITLE_NOTE = (
    "This track is picture-based, so Projectionist can’t draw it as text. "
    "Pick another track or watch in Plex."
)
_NATIVE_TEXT_FORMATS = frozenset({"srt", "subrip", "vtt", "webvtt"})
_IMAGE_TITLE_RE = re.compile(r"\b(pgs|vobsub|dvd\s*sub|hdmv|overlay)\b", re.I)
_OUR_SUBTITLE_PROXY_RE = re.compile(
    r"^/api/library/items/[^/]+/subtitles/[^/]+/file$"
)


def _subtitle_row(stream: Mapping[str, Any] | PlexSubtitleStream) -> Mapping[str, Any]:
    if isinstance(stream, PlexSubtitleStream):
        return stream.to_dict()
    return stream


def subtitle_is_renderable(stream: Mapping[str, Any] | PlexSubtitleStream) -> bool:
    """True when the track is text we can fetch and render (not PGS/VobSub bitmap)."""
    row = _subtitle_row(stream)
    fmt = str(row.get("format") or row.get("codec") or "").strip().lower()
    if fmt in IMAGE_SUBTITLE_FORMATS:
        return False
    blob = " ".join(str(row.get(key) or "") for key in ("display_title", "title", "label"))
    if _IMAGE_TITLE_RE.search(blob):
        return False
    return True


def is_our_subtitle_proxy_url(url: Any) -> bool:
    """True for Projectionist's cookie-authed VTT proxy — never a plex:// or PMS path."""
    return bool(_OUR_SUBTITLE_PROXY_RE.match(str(url or "").strip()))


def sanitize_live_plex_streams(streams: Sequence[Any] | None) -> List[Dict[str, Any]]:
    """Keep only our proxy URLs. Overlay/PGS keys are not loadable text."""
    out: List[Dict[str, Any]] = []
    for row in streams or []:
        if not isinstance(row, Mapping):
            continue
        item = dict(row)
        url = str(item.get("proxy_url") or "").strip()
        renderable = bool(item.get("renderable")) and is_our_subtitle_proxy_url(url)
        if not renderable:
            item["proxy_url"] = ""
            item["renderable"] = False
        else:
            item["proxy_url"] = url
            item["renderable"] = True
        out.append(item)
    return out


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
    """True when a *drawable* (text) track matches the preferred language.

    Bitmap/PGS/VobSub rows do not count — the player cannot overlay them.
    """
    usable = [stream for stream in streams if subtitle_is_renderable(stream)]
    for code in languages:
        for stream in usable:
            if language_matches(stream, code) and not (
                isinstance(stream, PlexSubtitleStream) and stream.forced
            ):
                return True
    for code in languages:
        for stream in usable:
            if language_matches(stream, code):
                return True
    return False


def pick_search_candidate(
    candidates: Sequence[PlexSubtitleStream],
    *,
    prefer_sdh: bool = False,
) -> Optional[PlexSubtitleStream]:
    """Pick the best on-demand search hit (text only; non-forced preferred; SDH optional)."""
    ranked = [item for item in candidates if subtitle_is_renderable(item)]
    if not ranked:
        return None

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


def subtitle_fetch_paths(stream: Mapping[str, Any]) -> List[str]:
    """Plex-relative paths to try, best first. Embedded tracks have no ``key``.

    Sidecar files expose ``key`` (``/library/streams/<id>``). Embedded text tracks are
    extracted by PMS from the same ``/library/streams/<id>`` route when asked for SRT.
    """
    key = str(stream.get("key") or "").strip()
    stream_id = str(stream.get("id") or "").strip()
    fmt = str(stream.get("format") or "").strip().lower()
    base = key or (f"/library/streams/{stream_id}" if stream_id.isdigit() else "")
    if not base:
        return []
    if not base.startswith("/"):
        base = f"/{base}"
    if "?" in base:
        return [base]
    paths: List[str] = []
    if fmt not in _NATIVE_TEXT_FORMATS or not key:
        paths.append(f"{base}?encoding=utf-8&format=srt")
    paths.append(f"{base}?encoding=utf-8")
    paths.append(base)
    out: List[str] = []
    for path in paths:
        if path not in out:
            out.append(path)
    return out


def decorate_subtitle_row(rating_key: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Add the authenticated proxy URL + renderability. Never exposes Plex tokens."""
    out = dict(row)
    renderable = subtitle_is_renderable(out)
    out["renderable"] = renderable
    out["image"] = not renderable
    paths = subtitle_fetch_paths(out)
    stream_id = str(out.get("id") or "").strip()
    if renderable and paths and stream_id:
        out["proxy_url"] = (
            f"/api/library/items/{urllib.parse.quote(str(rating_key), safe='')}"
            f"/subtitles/{urllib.parse.quote(stream_id, safe='')}/file"
        )
    else:
        out["proxy_url"] = ""
    out["unavailable_reason"] = (
        "" if out["proxy_url"] else (IMAGE_SUBTITLE_NOTE if not renderable else "No file path for this track.")
    )
    return out


def fetch_subtitle_vtt(client: PlexClient, stream: Mapping[str, Any]) -> str:
    """Fetch one track from Plex (trying fallback paths) and return WebVTT text."""
    paths = subtitle_fetch_paths(stream)
    if not paths:
        raise ValueError("Subtitle track has no fetchable path")
    last: Optional[Exception] = None
    for path in paths:
        try:
            raw = client.fetch_subtitle_bytes(path)
        except Exception as error:  # noqa: BLE001
            last = error
            continue
        text = raw.decode("utf-8-sig", errors="replace")
        if not text.strip():
            last = ValueError("Plex returned an empty subtitle file")
            continue
        return srt_to_vtt(text)
    raise last or ValueError("Could not fetch subtitle track")


def _title_fields(settings: Any, db: Any, key: str) -> Dict[str, Any]:
    from projectionist.library.episode_investigate.capabilities import opensubtitles_api_key
    from projectionist.library.subtitle_cache import household_language, title_subtitle_context

    ctx = title_subtitle_context(db, key)
    return {
        "media_type": ctx.get("media_type") or "",
        "title_language": ctx.get("original_language") or "",
        "household_language": household_language(settings),
        "opensubtitles_configured": bool(opensubtitles_api_key(settings)),
    }


def list_item_subtitles(
    settings: Any,
    rating_key: str,
    *,
    db: Any = None,
    data_dir: Any = None,
) -> Dict[str, Any]:
    """List the cached household file plus Plex-attached streams for a movie/episode."""
    from projectionist.library.subtitle_cache import cached_track_rows

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
    cached = cached_track_rows(key, settings, data_dir=data_dir)
    title = _title_fields(settings, db, key)
    client = plex_client_from_settings(settings)
    if client is None:
        return {
            "ok": bool(cached),
            "rating_key": key,
            "streams": cached,
            "preferred_languages": languages,
            "has_preferred": bool(cached),
            "message": "" if cached else "Plex isn’t connected, so subtitle tracks aren’t available.",
            "reason": "" if cached else "plex_unconfigured",
            **title,
        }
    try:
        streams = client.list_subtitle_streams(key)
    except Exception as error:  # noqa: BLE001
        logger.info("Plex subtitle list failed for %s: %s", key, error)
        return {
            "ok": bool(cached),
            "rating_key": key,
            "streams": cached,
            "preferred_languages": languages,
            "has_preferred": bool(cached),
            "message": "" if cached else "Couldn’t read subtitle tracks from Plex for this title.",
            "reason": "" if cached else "plex_error",
            "error": str(error)[:200],
            **title,
        }
    rows = cached + [decorate_subtitle_row(key, s.to_dict()) for s in streams]
    return {
        "ok": True,
        "rating_key": key,
        "streams": rows,
        "preferred_languages": languages,
        "has_preferred": bool(cached) or has_preferred_subtitle(streams, languages),
        "message": "" if rows else "No subtitle tracks are attached in Plex yet.",
        "reason": "" if rows else "none_attached",
        **title,
    }


def fetch_household_subtitles(
    settings: Any,
    rating_key: str,
    *,
    db: Any = None,
    data_dir: Any = None,
    language: str = "",
    prefer_sdh: bool = False,
    ask_plex: bool = True,
) -> Dict[str, Any]:
    """Play and Live on-the-spot fetch: cache the household file, else ask Plex.

    Same helper the subtitle task uses, so a file fetched here is the one the
    next viewer gets from the cache.
    """
    from projectionist.library.subtitle_cache import ensure_household_subtitle

    key = str(rating_key or "").strip()
    ensured = ensure_household_subtitle(
        settings,
        key,
        db=db,
        data_dir=data_dir,
        language=language,
        prefer_sdh=prefer_sdh,
    )
    if ensured.get("track") is not None:
        listed = list_item_subtitles(settings, key, db=db, data_dir=data_dir)
        return {
            "ok": True,
            "downloaded": ensured.get("reason") != "already_cached",
            "already_present": ensured.get("reason") == "already_cached",
            "rating_key": key,
            "language": ensured.get("language") or "",
            "source": ensured.get("source") or "",
            "message": "",
            "reason": str(ensured.get("reason") or ""),
            "streams": listed.get("streams") or [ensured["track"]],
            "preferred_languages": listed.get("preferred_languages") or [],
            "opensubtitles_configured": bool(ensured.get("opensubtitles_configured")),
        }
    if ask_plex:
        asked = download_preferred_subtitles(
            settings, key, language=language, prefer_sdh=prefer_sdh
        )
        if asked.get("downloaded") or asked.get("already_present"):
            return {**asked, "opensubtitles_configured": bool(ensured.get("opensubtitles_configured"))}
        note = str(ensured.get("message") or "")
        if not note or ensured.get("reason") == "none_found":
            note = str(asked.get("message") or note)
        return {
            **asked,
            "message": note,
            "cache_reason": str(ensured.get("reason") or ""),
            "opensubtitles_configured": bool(ensured.get("opensubtitles_configured")),
        }
    listed = list_item_subtitles(settings, key, db=db, data_dir=data_dir)
    return {
        "ok": False,
        "downloaded": False,
        "rating_key": key,
        "message": str(ensured.get("message") or DOWNLOAD_SOFT_FAIL),
        "reason": str(ensured.get("reason") or "none_found"),
        "streams": listed.get("streams") or [],
        "opensubtitles_configured": bool(ensured.get("opensubtitles_configured")),
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
            "streams": [decorate_subtitle_row(key, s.to_dict()) for s in existing],
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
            "streams": [decorate_subtitle_row(key, s.to_dict()) for s in refreshed],
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
        "streams": [decorate_subtitle_row(key, s.to_dict()) for s in existing],
        "preferred_languages": languages,
    }


def srt_to_vtt(raw: str) -> str:
    """Minimal SRT → WebVTT conversion for sidecar tracks (cue text left intact)."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").strip()
    if text.upper().startswith("WEBVTT"):
        return text if text.endswith("\n") else text + "\n"
    src = text.split("\n")
    lines: List[str] = ["WEBVTT", ""]
    for i, line in enumerate(src):
        stripped = line.strip()
        # Drop the numeric cue index only (the line right before a timing line),
        # so cue text that is just a number (e.g. "42") survives.
        if re.fullmatch(r"\d+", stripped) and i + 1 < len(src) and "-->" in src[i + 1]:
            continue
        if "-->" in stripped:
            stripped = re.sub(r"(\d),(\d{1,3})", r"\1.\2", stripped)
        lines.append(stripped)
    return "\n".join(lines).rstrip() + "\n"


def live_subtitles_payload(
    settings: Any,
    *,
    channel_id: str,
    now_program: Optional[Mapping[str, Any]] = None,
    db: Any = None,
    data_dir: Any = None,
) -> Dict[str, Any]:
    """Richer `/live` CC payload: cached file + Plex tracks when a rating key maps.

    Carries the airing's media type and ``original_language`` so the player can
    decide whether captions start on. Flex and filler never list or fetch.
    """
    from projectionist.library.subtitle_cache import household_language

    cid = str(channel_id or "").strip()
    languages = preferred_subtitle_languages(settings)
    rating_key = ""
    program_media_type = ""
    is_flex = False
    if isinstance(now_program, Mapping):
        rating_key = str(now_program.get("plex_rating_key") or "").strip()
        program_media_type = str(now_program.get("media_type") or "").strip().lower()
        is_flex = bool(now_program.get("is_flex"))
    if is_flex:
        rating_key = ""
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
        "is_flex": is_flex,
        "media_type": program_media_type,
        "original_language": "",
        "household_language": household_language(settings),
        "cached_track": None,
        "opensubtitles_configured": False,
    }
    if not rating_key:
        base["reason"] = "flex" if is_flex else "no_plex_mapping"
        base["message"] = NO_CAPTIONS_AIRING
        return base

    listed = list_item_subtitles(settings, rating_key, db=db, data_dir=data_dir)
    base["plex_streams"] = sanitize_live_plex_streams(listed.get("streams") or [])
    base["has_preferred"] = bool(listed.get("has_preferred"))
    base["media_type"] = str(listed.get("media_type") or program_media_type)
    base["original_language"] = str(listed.get("title_language") or "")
    base["opensubtitles_configured"] = bool(listed.get("opensubtitles_configured"))
    base["cached_track"] = next(
        (row for row in base["plex_streams"] if str(row.get("id") or "").startswith("cached-")),
        None,
    )
    can_fetch = bool(listed.get("ok")) or base["opensubtitles_configured"]
    base["can_download"] = can_fetch and not bool(listed.get("has_preferred"))
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
