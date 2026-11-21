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
    """Normalize ffprobe level_idc and a profile's major.minor onto one scale.

    ffprobe reports HEVC ``level`` as level_idc (153 is 5.1, 186 is 6.2). The
    browser profile says ``5.1``. A dotted value below the idc threshold is
    already major.minor. A value at or above that threshold is the integer
    code, including when it was stringified as ``153.0``.
    """
    text = str(raw or "").strip()
    if not text or text in {"0", "-99", "unknown"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number <= 0:
        return None
    kind = canonical_codec(codec)
    # HEVC level_idc = major * 30 + minor. 5.1 → 153. H.264 is major * 10.
    # "5.1" is already on the major.minor scale and stays below the threshold.
    if kind == "hevc" and number >= 30:
        return number / 30.0
    if kind == "h264" and number >= 10:
        return number / 10.0
    return number


def stream_bit_depth(stream: MediaStream) -> int:
    reported = int(getattr(stream, "bit_depth", 0) or 0)
    if reported >= 8:
        return reported
    text = str(stream.profile or "").lower()
    if "12" in text:
        return 12
    if "10" in text:
        return 10
    return 8


def _video_decision(stream: MediaStream, caps: list[VideoCapability]) -> tuple[bool, str]:
    """Which profile video row allowed this stream, or why none did."""
    codec = canonical_codec(stream.codec)
    depth = stream_bit_depth(stream)
    same = [cap for cap in caps if canonical_codec(cap.codec) == codec]
    if not same:
        return False, f"{codec} not in profile"
    depth_limit = 0
    for cap in same:
        limit = level_number(codec, cap.max_level)
        actual = level_number(codec, stream.level)
        if limit is not None and actual is not None and actual > limit + 0.05:
            continue
        if cap.bit_depth and depth > cap.bit_depth:
            depth_limit = max(depth_limit, cap.bit_depth)
            continue
        bits = f", {cap.bit_depth}-bit" if cap.bit_depth else ""
        level = cap.max_level or "any level"
        return True, f"{codec} up to {level}{bits}"
    if depth_limit:
        return False, f"{codec} {depth}-bit is above profile {codec} {depth_limit}-bit"
    return False, f"{codec} level is above profile {codec} {same[0].max_level}"


def _audio_decision(audios: list[MediaStream], profile: DeviceProfile) -> tuple[bool, str, Optional[MediaStream]]:
    if not audios:
        return True, "no audio", None
    names = {canonical_codec(name) for name in profile.audio}
    for stream in audios:
        codec = canonical_codec(stream.codec)
        if codec in names:
            return True, codec, stream
    return False, f"{canonical_codec(audios[0].codec)} not in profile", audios[0]


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
    """Record a plan, the profile answer that chose it, and a reason. Never a file path."""
    captions = caption_inventory(asset.probe)
    empty_answer = {"video": "", "audio": ""}
    base = {
        "profile": profile.id,
        "captions": captions,
        "readable": bool(asset.readable),
        "profile_answer": empty_answer,
    }
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
            "profile_answer": {"video": "no video", "audio": ""},
        }

    video_ok, video_text = _video_decision(video, profile.video)
    audio_ok, audio_text, playable_audio = _audio_decision(audios, profile)
    audio = playable_audio or (audios[0] if audios else None)
    video_label = _pretty_codec(video.codec)
    audio_label = _pretty_codec(audio.codec) if audio else "no audio"
    container = _container_label(probe.container)
    direct_ok = probe.container in _DIRECT_CONTAINERS and "mp4" in profile.containers
    remux_ok = "hls-fmp4" in profile.containers
    answer = {"video": video_text, "audio": audio_text}
    base = {**base, "profile_answer": answer}

    if video_ok and audio_ok and direct_ok:
        return {
            **base,
            "plan": "direct",
            "reason": (
                f"{container} container; {video_label} + {audio_label} playable on {profile.id} "
                f"({video_text}; {audio_text})"
            ),
        }
    if video_ok and audio_ok and playable_audio is not None and remux_ok:
        return {
            **base,
            "plan": "remux",
            "reason": (
                f"{container} container; {video_label} + {audio_label} playable on {profile.id} "
                f"({video_text}; {audio_text})"
            ),
        }
    if video_ok and audio is not None and not audio_ok and remux_ok:
        return {
            **base,
            "plan": "audio",
            "reason": (
                f"{video_label} video is playable on {profile.id}; "
                f"{audio_label} audio is not, so the audio would be transcoded ({audio_text})"
            ),
        }
    if not video_ok:
        return {
            **base,
            "plan": "full",
            "reason": f"{video_label} video is not playable on {profile.id} ({video_text})",
        }
    return {
        **base,
        "plan": "plex-fallback",
        "reason": f"{profile.id} cannot take an fMP4 remux of this {container}",
    }
