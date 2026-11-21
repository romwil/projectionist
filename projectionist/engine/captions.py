"""Until ENG-004, a title that needs captions stays on the Plex path.

A title in the household language keeps captions off, so a remux is fine.
Any other title with a subtitle stream or a household caption file falls
back, and the session records why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from projectionist.engine.source import MediaAsset

CAPTION_FALLBACK_REASON = (
    "Captions stay on the Plex path until they are tracks in the playlist."
)


def caption_fallback_reason(
    asset: MediaAsset,
    *,
    title_language: str,
    settings: Any,
    data_dir: Path,
) -> str:
    probe = asset.probe
    has_stream = bool(probe and any(stream.codec_type == "subtitle" for stream in probe.streams))
    cache = Path(data_dir) / "subtitles" / str(asset.rating_key or "")
    has_cache = False
    try:
        has_cache = cache.is_dir() and any(cache.glob("*.srt"))
    except OSError:
        has_cache = False
    if not has_stream and not has_cache:
        return ""
    from projectionist.library.subtitle_cache import title_language_is_household

    if title_language_is_household(title_language, settings) is True:
        return ""
    return CAPTION_FALLBACK_REASON
