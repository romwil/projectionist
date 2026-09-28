"""ffmpeg / ffprobe / vision / OpenSubtitles capability probes."""

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Mapping, Optional

FFMPEG_NOTE = (
    "This running container cannot find ffmpeg on PATH. Image includes ffmpeg; "
    "a missing binary is a bad image or PATH, not a host install. "
    "Set FFMPEG_PATH and FFPROBE_PATH only to override."
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


def acrcloud_config(settings: Any = None) -> Dict[str, Any]:
    """Region host + keys. Environment wins over encrypted settings."""
    host = str(
        os.environ.get("PROJECTIONIST_ACRCLOUD_HOST")
        or os.environ.get("ACRCLOUD_HOST")
        or ""
    ).strip()
    key = str(
        os.environ.get("PROJECTIONIST_ACRCLOUD_ACCESS_KEY")
        or os.environ.get("ACRCLOUD_ACCESS_KEY")
        or ""
    ).strip()
    secret = str(
        os.environ.get("PROJECTIONIST_ACRCLOUD_ACCESS_SECRET")
        or os.environ.get("ACRCLOUD_ACCESS_SECRET")
        or ""
    ).strip()
    nested = getattr(settings, "acrcloud", None) if settings is not None else None
    if not host and nested is not None:
        host = str(getattr(nested, "host", "") or "").strip()
    if not key and nested is not None:
        key = str(getattr(nested, "access_key", "") or "").strip()
    if not secret and nested is not None:
        secret = str(getattr(nested, "access_secret", "") or "").strip()
    return {
        "host": host,
        "access_key": key,
        "access_secret": secret,
        "available": bool(key and secret),
        "host_source": _acrcloud_source("HOST", host, nested, "host"),
        "access_key_source": _acrcloud_source("ACCESS_KEY", key, nested, "access_key"),
        "access_secret_source": _acrcloud_source("ACCESS_SECRET", secret, nested, "access_secret"),
    }


def _acrcloud_source(suffix: str, resolved: str, nested: Any, field: str) -> str:
    if not resolved:
        return ""
    env = str(
        os.environ.get(f"PROJECTIONIST_ACRCLOUD_{suffix}")
        or os.environ.get(f"ACRCLOUD_{suffix}")
        or ""
    ).strip()
    if env:
        return "env"
    if nested is not None and str(getattr(nested, field, "") or "").strip():
        return "file"
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
    acr = acrcloud_config(settings)
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
        "acrcloud": {
            "available": bool(acr.get("available")),
            "configured": bool(acr.get("available")),
            "host": str(acr.get("host") or ""),
            "deferred": False,
        },
    }


def _empty_settings() -> Mapping[str, Any]:
    return type("S", (), {"llm_provider": "", "llm_model": ""})()
