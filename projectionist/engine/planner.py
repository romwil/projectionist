"""Choose the cheapest plan a device can play, and say why.

Order: direct, remux, audio transcode, full transcode, Plex fallback.
Audio and full transcode are named here so the dry-run is honest. Serving
them waits for ENG-006. ENG-003 serves remux (and direct is a file plan,
not a transcode).
"""

from __future__ import annotations

from typing import Optional

from projectionist.engine.profiles import DeviceProfile, VideoCapability
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import MediaAsset

_CODEC_ALIASES = {
    "avc": "h264",
    "h265": "hevc",
    "hev1": "hevc",
    "ac-3": "ac3",
    "e-ac-3": "eac3",
    "ec-3": "eac3",
    "dts-hd": "dts",
    "truehd": "truehd",
}

_DIRECT_CONTAINERS = frozenset({"mp4", "mov"})


def canonical_codec(name: str) -> str:
    text = str(name or "").strip().lower()
    return _CODEC_ALIASES.get(text, text)


def level_number(codec: str, raw: str) -> Optional[float]:
    """Normalize ffprobe level and profile max_level onto one scale (4.1 → 4.1)."""
    text = str(raw or "").strip()
    if not text or text in {"0", "-99", "unknown"}:
        return None
    try:
        if "." in text:
            return float(text)
        number = int(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    kind = canonical_codec(codec)
    if kind == "hevc" and number >= 30:
        return number / 30.0
    if kind == "h264" and number >= 10:
        return number / 10.0
    return float(number)


def _video_ok(stream: MediaStream, caps: list[VideoCapability]) -> bool:
    codec = canonical_codec(stream.codec)
    for cap in caps:
        if canonical_codec(cap.codec) != codec:
            continue
        limit = level_number(codec, cap.max_level)
        actual = level_number(codec, stream.level)
        if limit is not None and actual is not None and actual > limit + 0.05:
            return False
        return True
    return False


def _audio_ok(stream: MediaStream, profile: DeviceProfile) -> bool:
    return canonical_codec(stream.codec) in {canonical_codec(name) for name in profile.audio}


def _pretty_codec(codec: str) -> str:
    name = canonical_codec(codec)
    labels = {
        "h264": "H.264",
        "hevc": "HEVC",
        "aac": "AAC",
        "ac3": "AC-3",
        "eac3": "E-AC-3",
        "dts": "DTS",
        "truehd": "TrueHD",
        "mp3": "MP3",
        "opus": "Opus",
        "flac": "FLAC",
        "alac": "ALAC",
    }
    return labels.get(name, name.upper() or "unknown")


def _container_label(container: str) -> str:
    name = str(container or "").lower()
    if name == "mkv":
        return "MKV"
    if name == "mp4":
        return "MP4"
    return name.upper() or "unknown container"


def caption_inventory(probe: Optional[ProbeResult]) -> list[dict[str, object]]:
    if probe is None:
        return []
    rows: list[dict[str, object]] = []
    for stream in probe.streams:
        if stream.codec_type != "subtitle":
            continue
        kind = "image-ocr" if stream.subtitle_kind == "image" else "text"
        rows.append(
            {
                "id": f"s{stream.index}",
                "kind": kind,
                "lang": stream.language,
                "ready": kind == "text",
            }
        )
    return rows


def _first(streams: list[MediaStream], codec_type: str) -> Optional[MediaStream]:
    for stream in streams:
        if stream.codec_type == codec_type:
            return stream
    return None


def plan_playback(asset: MediaAsset, profile: DeviceProfile) -> dict[str, object]:
    """Record a plan and a reason. Never includes a file path."""
    captions = caption_inventory(asset.probe)
    base = {"profile": profile.id, "captions": captions, "readable": bool(asset.readable)}
    if not asset.readable or asset.probe is None:
        reason = asset.reason or "Projectionist cannot read this file"
        return {**base, "plan": "plex-fallback", "reason": reason, "readable": False}

    probe = asset.probe
    video = _first(probe.streams, "video")
    audios = [stream for stream in probe.streams if stream.codec_type == "audio"]
    if video is None:
        return {
            **base,
            "plan": "plex-fallback",
            "reason": "No video stream to play",
        }

    video_ok = _video_ok(video, profile.video)
    playable_audio = next((stream for stream in audios if _audio_ok(stream, profile)), None)
    audio = playable_audio or (audios[0] if audios else None)
    video_label = _pretty_codec(video.codec)
    audio_label = _pretty_codec(audio.codec) if audio else "no audio"
    container = _container_label(probe.container)
    direct_ok = probe.container in _DIRECT_CONTAINERS and "mp4" in profile.containers
    remux_ok = "hls-fmp4" in profile.containers

    if video_ok and (playable_audio is not None or audio is None) and direct_ok:
        return {
            **base,
            "plan": "direct",
            "reason": f"{container} container; {video_label} + {audio_label} playable on {profile.id}",
        }
    if video_ok and playable_audio is not None and remux_ok:
        return {
            **base,
            "plan": "remux",
            "reason": (
                f"{container} container; {video_label} + {audio_label} playable on {profile.id}"
            ),
        }
    if video_ok and audio is not None and playable_audio is None and remux_ok:
        return {
            **base,
            "plan": "audio",
            "reason": (
                f"{video_label} video is playable on {profile.id}; "
                f"{audio_label} audio is not, so the audio would be transcoded"
            ),
        }
    if not video_ok:
        return {
            **base,
            "plan": "full",
            "reason": f"{video_label} video is not playable on {profile.id}",
        }
    return {
        **base,
        "plan": "plex-fallback",
        "reason": f"{profile.id} cannot take an fMP4 remux of this {container}",
    }
