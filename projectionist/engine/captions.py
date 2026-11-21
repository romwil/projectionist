"""WebVTT caption renditions for an engine session (ENG-004).

The household subtitle cache comes first. An embedded text track is used only
when that language was already extracted to WebVTT ahead of Play. This request
does not run ffmpeg: a large text track that is not ready yet stays on the
Plex path, and the session says the captions are not ready yet. Picture
captions are left for ENG-005 and keep their own fallback sentence.

A title in the household language does not need captions, so a missing track
does not force that fallback. Tracks we can build are still offered, with
none selected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional, Sequence

from projectionist.engine.source import MediaAsset
from projectionist.library.subtitle_cache import (
    MAX_SUBTITLE_BYTES,
    cache_path,
    cached_stream_id,
    cached_track_row,
    household_language,
    household_languages,
    is_usable_subtitle_text,
    iso2,
    title_language_is_household,
)

CAPTION_FALLBACK_REASON = (
    "These captions are not ready as WebVTT, so this title stays on the Plex path."
)
# Text exists, but the ahead-of-time job has not written WebVTT yet. This is
# not a path-mapping failure, and it is not a picture-caption fallback.
CAPTION_PENDING_REASON = (
    "These captions are not ready yet, so this title stays on the Plex path."
)

_LANG_RE = re.compile(r"^[a-z]{2,3}$")


@dataclass(frozen=True)
class CaptionRendition:
    """One playlist caption. Cue text only — never a file path."""

    track_id: str
    language: str
    name: str
    default: bool
    webvtt: str


def prepare_webvtt_renditions(
    asset: MediaAsset,
    *,
    title_language: str,
    settings: Any,
    data_dir: Path,
) -> list[CaptionRendition]:
    """Household cache first, then text tracks already extracted ahead of Play.

    Does not call ffmpeg. A text track with no WebVTT yet is simply absent.
    """
    cached = _cached_renditions(asset, data_dir=data_dir, settings=settings)
    covered = {track.language for track in cached if track.language}
    prepared = _prepared_renditions(asset, data_dir=data_dir, skip=covered)
    return _mark_default(
        cached + prepared,
        captions_on=title_language_is_household(title_language, settings) is not True,
        household=household_language(settings),
    )


def caption_fallback_reason(
    asset: MediaAsset,
    *,
    title_language: str,
    settings: Any,
    data_dir: Path,
    renditions: Optional[Sequence[CaptionRendition]] = None,
) -> str:
    """Empty when this title can play on the engine.

    ``renditions`` is the list already prepared for the session. Pass it so a
    title is not extracted twice. ``None`` prepares that list here.
    """
    if not asset.readable or asset.probe is None:
        return ""
    if title_language_is_household(title_language, settings) is True:
        return ""
    if not _has_caption_source(asset, data_dir):
        return ""
    ready = renditions
    if ready is None:
        ready = prepare_webvtt_renditions(
            asset,
            title_language=title_language,
            settings=settings,
            data_dir=data_dir,
        )
    if ready:
        return ""
    from projectionist.engine.caption_prep import text_streams

    if text_streams(asset):
        return CAPTION_PENDING_REASON
    return CAPTION_FALLBACK_REASON


def _has_caption_source(asset: MediaAsset, data_dir: Path) -> bool:
    probe = asset.probe
    if probe and any(stream.codec_type == "subtitle" for stream in probe.streams):
        return True
    return _any_srt(_cache_dir(asset, data_dir))


def _cache_dir(asset: MediaAsset, data_dir: Path) -> Optional[Path]:
    sample = cache_path(asset.rating_key, "en", data_dir=data_dir)
    if sample is None:
        return None
    return sample.parent


def _any_srt(root: Optional[Path]) -> bool:
    if root is None:
        return False
    try:
        return root.is_dir() and any(root.glob("*.srt"))
    except OSError:
        return False


def _track_name(language: str) -> str:
    if not language:
        return "Captions"
    label = str(cached_track_row("0", language).get("label") or "")
    return label or language.upper()


def _normalize_language(raw: str) -> str:
    code = iso2(raw)
    if _LANG_RE.fullmatch(code):
        return code
    return ""


def _read_limited(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_SUBTITLE_BYTES or path.stat().st_size <= 0:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _as_webvtt(text: str) -> str:
    from projectionist.library.subtitles import srt_to_vtt

    converted = srt_to_vtt(text)
    if "-->" not in converted:
        return ""
    return converted


def _cached_renditions(asset: MediaAsset, *, data_dir: Path, settings: Any) -> list[CaptionRendition]:
    root = _cache_dir(asset, data_dir)
    if root is None:
        return []
    try:
        paths = [item for item in root.glob("*.srt") if item.is_file()]
    except OSError:
        return []
    order = household_languages(settings)
    found: list[tuple[str, str]] = []
    for path in paths:
        language = _normalize_language(path.stem)
        if not language:
            continue
        body = _read_limited(path)
        if not is_usable_subtitle_text(body):
            continue
        webvtt = _as_webvtt(body)
        if not webvtt:
            continue
        found.append((language, webvtt))

    def sort_key(item: tuple[str, str]) -> tuple[int, int, str]:
        language = item[0]
        if language in order:
            return (0, order.index(language), language)
        return (1, 0, language)

    found.sort(key=sort_key)
    renditions: list[CaptionRendition] = []
    seen: set[str] = set()
    for language, webvtt in found:
        if language in seen:
            continue
        seen.add(language)
        renditions.append(
            CaptionRendition(
                track_id=cached_stream_id(language),
                language=language,
                name=_track_name(language),
                default=False,
                webvtt=webvtt,
            )
        )
    return renditions


def _prepared_renditions(
    asset: MediaAsset,
    *,
    data_dir: Path,
    skip: set[str],
) -> list[CaptionRendition]:
    """Text tracks extracted earlier. Missing files are not extracted here."""
    from projectionist.engine.caption_prep import prepared_tracks

    renditions: list[CaptionRendition] = []
    seen = set(skip)
    for track in prepared_tracks(asset, data_dir=data_dir):
        language = track.language
        if language and language in seen:
            continue
        if language:
            seen.add(language)
        renditions.append(
            CaptionRendition(
                track_id=f"s{int(track.index)}",
                language=language,
                name=_track_name(language),
                default=False,
                webvtt=track.webvtt,
            )
        )
    return renditions


def _mark_default(
    tracks: Sequence[CaptionRendition],
    *,
    captions_on: bool,
    household: str,
) -> list[CaptionRendition]:
    chosen = -1
    if captions_on and tracks:
        for index, track in enumerate(tracks):
            if track.language == household:
                chosen = index
                break
        if chosen < 0:
            chosen = 0
    marked: list[CaptionRendition] = []
    for index, track in enumerate(tracks):
        marked.append(replace(track, default=index == chosen))
    return marked
