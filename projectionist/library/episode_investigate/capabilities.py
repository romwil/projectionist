"""ffmpeg / ffprobe / vision / OpenSubtitles capability probes."""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Mapping, Optional

FFMPEG_NOTE = (
    "ffmpeg is not bundled in the Projectionist image. Install a host binary on "
    "PATH, or set FFMPEG_PATH and FFPROBE_PATH."
)

_VISION_MODEL_HINTS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "gpt-4-turbo",
    "gpt-4-vision",
    "o1",
    "o3",
    "o4",
    "claude",
    "gemini",
    "llava",
    "vision",
    "bakllava",
    "qwen2-vl",
    "qwen-vl",
    "minicpm-v",
    "pixtral",
    "gemma-3",
    "gemma3",
)


def resolve_ffmpeg() -> Optional[str]:
    env = str(os.environ.get("FFMPEG_PATH") or "").strip()
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    return shutil.which("ffmpeg")


def resolve_ffprobe() -> Optional[str]:
    env = str(os.environ.get("FFPROBE_PATH") or "").strip()
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    return shutil.which("ffprobe")


def ffmpeg_note() -> str:
    return FFMPEG_NOTE


def llm_accepts_images(settings: Any) -> bool:
    """True when the configured chat LLM is known to accept image parts."""
    provider = str(getattr(settings, "llm_provider", "") or "").strip().lower()
    model = str(getattr(settings, "llm_model", "") or "").strip().lower()
    if provider in {"anthropic", "openai", "openrouter"}:
        if provider == "openai" and model.startswith("gpt-3"):
            return False
        if "text" in model and "vision" not in model and "gpt-4o" not in model:
            return False
        return True
    blob = f"{provider} {model}"
    return any(hint in blob for hint in _VISION_MODEL_HINTS)


def opensubtitles_api_key(settings: Any = None) -> str:
    env = str(
        os.environ.get("PROJECTIONIST_OPENSUBTITLES_API_KEY")
        or os.environ.get("OPENSUBTITLES_API_KEY")
        or ""
    ).strip()
    if env:
        return env
    if settings is not None:
        return str(getattr(settings, "opensubtitles_api_key", "") or "").strip()
    return ""


def health_payload(settings: Any = None) -> Dict[str, Any]:
    ffmpeg = resolve_ffmpeg()
    ffprobe = resolve_ffprobe()
    vision = llm_accepts_images(settings or _empty_settings())
    tmdb = bool(str(getattr(settings, "tmdb_api_key", "") or "").strip()) if settings else False
    sonarr = bool(
        settings
        and str(getattr(settings, "sonarr_url", "") or "").strip()
        and str(getattr(settings, "sonarr_api_key", "") or "").strip()
    )
    os_key = opensubtitles_api_key(settings)
    return {
        "status": "ok",
        "available": True,
        "ffmpeg": {
            "available": bool(ffmpeg),
            "path": ffmpeg or "",
            "note": "" if ffmpeg else FFMPEG_NOTE,
        },
        "ffprobe": {
            "available": bool(ffprobe),
            "path": ffprobe or "",
        },
        "vision": {
            "available": vision,
            "default_on": vision,
            "leaves_lan": True,
        },
        "opensubtitles": {"available": bool(os_key)},
        "tmdb": {"configured": tmdb},
        "sonarr": {"configured": sonarr},
        "stills_leave_lan": vision,
        "acrcloud": {"available": False, "deferred": "v1.36.1"},
    }


def _empty_settings() -> Mapping[str, Any]:
    return type("S", (), {"llm_provider": "", "llm_model": ""})()
