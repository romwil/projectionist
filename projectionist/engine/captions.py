"""WebVTT caption renditions for an engine session (ENG-004).

The household subtitle cache comes first. An embedded text track is extracted
only when that language is not already cached. Picture captions are left for
ENG-005: a title that needs captions and has none the engine can turn into
WebVTT stays on the Plex path, and the session records why.

A title in the household language does not need captions, so a missing track
does not force that fallback. Tracks we can build are still offered, with
none selected.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from projectionist.engine.probe import TEXT_SUBTITLE_CODECS, subtitle_kind
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

logger = logging.getLogger(__name__)

CAPTION_FALLBACK_REASON = (
    "These captions are not ready as WebVTT, so this title stays on the Plex path."
)

_LANG_RE = re.compile(r"^[a-z]{2,3}$")
_MAX_EMBEDDED = 8
_EXTRACT_TIMEOUT_S = 20

Extractor = Callable[[Path, int, Path], None]


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
    extractor: Optional[Extractor] = None,
) -> list[CaptionRendition]:
    """Household cache first, then embedded text tracks the cache does not cover."""
    cached = _cached_renditions(asset, data_dir=data_dir, settings=settings)
    covered = {track.language for track in cached if track.language}
    embedded = _embedded_renditions(asset, skip=covered, extractor=extractor)
    return _mark_default(
        cached + embedded,
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


def _embedded_renditions(
    asset: MediaAsset,
    *,
    skip: set[str],
    extractor: Optional[Extractor],
) -> list[CaptionRendition]:
    probe = asset.probe
    if probe is None or not asset.local_path:
        return []
    source = Path(asset.local_path)
    try:
        if not source.is_file():
            return []
    except OSError:
        return []
    streams = []
    for stream in probe.streams:
        if stream.codec_type != "subtitle":
            continue
        kind = stream.subtitle_kind or subtitle_kind(stream.codec)
        if kind != "text" and stream.codec not in TEXT_SUBTITLE_CODECS:
            continue
        if kind == "image":
            continue
        language = _normalize_language(stream.language)
        if language and language in skip:
            continue
        streams.append(stream)
        if len(streams) >= _MAX_EMBEDDED:
            break
    if not streams:
        return []
    extract = extractor or _ffmpeg_extract
    renditions: list[CaptionRendition] = []
    seen = set(skip)
    for stream in streams:
        language = _normalize_language(stream.language)
        if language and language in seen:
            continue
        webvtt = _extract_text(source, stream.index, extract)
        if not webvtt:
            continue
        if language:
            seen.add(language)
        renditions.append(
            CaptionRendition(
                track_id=f"s{int(stream.index)}",
                language=language,
                name=_track_name(language),
                default=False,
                webvtt=webvtt,
            )
        )
    return renditions


def _extract_text(source: Path, index: int, extract: Extractor) -> str:
    if index < 0:
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="eng-caption-") as tmp:
            dest = Path(tmp) / "track.vtt"
            extract(source, int(index), dest)
            return _as_webvtt(_read_limited(dest))
    except Exception:  # noqa: BLE001 — one bad track must not fail the session
        logger.debug("embedded caption extract failed index=%s", index, exc_info=True)
        return ""


def _ffmpeg_extract(source: Path, index: int, dest: Path) -> None:
    from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg

    binary = resolve_ffmpeg()
    if not binary:
        return
    try:
        subprocess.run(
            [
                binary,
                "-y",
                "-i",
                str(source),
                "-map",
                f"0:{int(index)}",
                "-f",
                "webvtt",
                str(dest),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_EXTRACT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("embedded caption extract failed index=%s", index, exc_info=True)


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
