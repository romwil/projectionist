"""Choose the cheapest plan a device can play, and say why.

Order: direct, remux, audio transcode, source transcode, then a fallback
when the file itself cannot be planned. ENG-003 serves remux. ENG-012
serves audio by copying the video and encoding the audio. ENG-013 asks the
media source to transcode the picture and records why. This server does
not start that transcode. A file the engine cannot read stays a fallback.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from projectionist.engine.profiles import DeviceProfile, VideoCapability
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import (
    MediaAsset,
    PlexMediaSource,
    SourceTranscode,
    normalize_source_transcode,
    source_transcode_reason,
)

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


def _reports_hdr10(cap: VideoCapability) -> bool:
    return any(str(name).strip().lower() == "hdr10" for name in cap.hdr)


def _video_decision(stream: MediaStream, caps: list[VideoCapability]) -> tuple[str, str]:
    """``play``, ``try``, or ``block``, and the profile answer that chose it.

    HEVC above the advertised level is a try: the remux might play, and a
    transcode is the wrong first answer. HDR10 is a try only when a video row
    for that codec lists ``hdr10``. A device that does not report HDR is not
    given an HDR try. H.264 above its level, a missing codec, and a bit depth
    the profile refuses stay blocked.
    """
    codec = canonical_codec(stream.codec)
    depth = stream_bit_depth(stream)
    same = [cap for cap in caps if canonical_codec(cap.codec) == codec]
    if not same:
        return "block", f"{codec} not in profile"
    depth_limit = 0
    level_limit = ""
    level_score = -1.0
    saw_hevc_level = False
    hdr = str(stream.hdr or "").strip().lower()
    device_hdr = any(_reports_hdr10(cap) for cap in same)
    for cap in same:
        limit = level_number(codec, cap.max_level)
        actual = level_number(codec, stream.level)
        if limit is not None and actual is not None and actual > limit + 0.05:
            if codec == "hevc" and limit > level_score:
                saw_hevc_level = True
                level_score = limit
                level_limit = cap.max_level
            continue
        if cap.bit_depth and depth > cap.bit_depth:
            depth_limit = max(depth_limit, cap.bit_depth)
            continue
        bits = f", {cap.bit_depth}-bit" if cap.bit_depth else ""
        level = cap.max_level or "any level"
        answer = f"{codec} up to {level}{bits}"
        if hdr == "hdr10" and device_hdr:
            return "try", f"{answer}; hdr10"
        return "play", answer
    if depth_limit:
        return "block", f"{codec} {depth}-bit is above profile {codec} {depth_limit}-bit"
    if saw_hevc_level:
        shown = level_limit or same[0].max_level
        return "try", f"{codec} level is above profile {codec} {shown}"
    return "block", f"{codec} level is above profile {codec} {same[0].max_level}"


def _audio_decision(
    audios: list[MediaStream], profile: DeviceProfile
) -> tuple[bool, str, Optional[MediaStream]]:
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


def _ask_source(
    source: Optional[SourceTranscode],
    *,
    reason: str,
    video_answer: str,
) -> dict[str, Any]:
    """The media source owns the transcode. Plex is the source when none is passed."""
    kind = source_transcode_reason(video_answer) or "codec"
    method = getattr(source, "source_transcode", None) if source is not None else None
    asker = source if callable(method) else None
    if asker is None:
        asker = PlexMediaSource(mappings=[], path_lookup=lambda _key: [])
    offer = asker.source_transcode(reason=reason, source_reason=kind)
    if not isinstance(offer, Mapping):
        offer = {}
    return normalize_source_transcode(offer, reason=reason, source_reason=kind)


def plan_playback(
    asset: MediaAsset,
    profile: DeviceProfile,
    *,
    source: Optional[SourceTranscode] = None,
    failed_tries: Optional[set[tuple[str, str]]] = None,
    ready_copy: Optional[MediaAsset] = None,
    replaced: bool = False,
) -> dict[str, object]:
    """Record a plan, the profile answer that chose it, and a reason. Never a file path.

    When the picture is outside the profile, ``source`` is asked to transcode.
    The default source is Plex. The returned plan is ``source-transcode`` and
    is not playable here.

    A ready copy that direct-plays or remuxes is used instead of that live
    transcode. A partial file is not a ready copy.

    HEVC above the advertised level, and HDR10 on a device that reports HDR,
    are plan ``try``: a remux, not a claim that it will play. ``failed_tries``
    holds ``(rating_key, profile id)`` pairs whose first frame did not arrive.
    Those titles are not tried again.

    A title marked replaced is not still above the quality target. When that
    title has a ready copy that direct-plays or remuxes, the plan uses the copy.
    """
    if replaced:
        chosen = plan_playback(
            asset,
            profile,
            source=source,
            failed_tries=failed_tries,
            ready_copy=ready_copy,
        )
        if ready_copy is not None:
            copy_plan = plan_playback(
                ready_copy,
                profile,
                source=source,
                failed_tries=failed_tries,
            )
            if str(copy_plan.get("plan") or "") in {"direct", "remux"}:
                chosen = dict(copy_plan)
                chosen["from_copy"] = True
        marked = dict(chosen)
        marked["replaced"] = True
        marked["above_target"] = False
        return marked
    if ready_copy is not None:
        copy_plan = plan_playback(ready_copy, profile, source=source, failed_tries=failed_tries)
        if str(copy_plan.get("plan") or "") in {"direct", "remux"}:
            source_plan = plan_playback(asset, profile, source=source, failed_tries=failed_tries)
            if str(source_plan.get("plan") or "") == "source-transcode":
                chosen = dict(copy_plan)
                chosen["from_copy"] = True
                return chosen
            return source_plan
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

    video_mode, video_text = _video_decision(video, profile.video)
    remembered_miss = video_mode == "try" and (
        (str(asset.rating_key or ""), str(profile.id or "")) in set(failed_tries or ())
    )
    if remembered_miss:
        video_mode = "block"
    video_ok = video_mode == "play"
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
                f"{audio_label} audio is not, so the audio is transcoded ({audio_text})"
            ),
        }
    if video_mode == "try" and remux_ok:
        transcode_audio = audio is not None and not audio_ok
        if transcode_audio:
            reason = (
                f"{video_label} video is a try on {profile.id} ({video_text}); "
                f"{audio_label} audio is not, so the audio is transcoded ({audio_text})"
            )
        else:
            reason = (
                f"{container} container; {video_label} + {audio_label} is a try on {profile.id} "
                f"({video_text}; {audio_text})"
            )
        return {**base, "plan": "try", "reason": reason, "audio_transcode": transcode_audio}
    if not video_ok:
        if remembered_miss:
            sentence = (
                f"A try on {profile.id} did not show a picture, so this stays on the media source "
                f"({video_text})"
            )
        else:
            sentence = f"{video_label} video is not playable on {profile.id} ({video_text})"
        return {**base, **_ask_source(source, reason=sentence, video_answer=video_text)}
    return {
        **base,
        "plan": "plex-fallback",
        "reason": f"{profile.id} cannot take an fMP4 remux of this {container}",
    }
