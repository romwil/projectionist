"""Copy a readable file into VOD fMP4 HLS. No re-encode.

The master playlist is ours, so BANDWIDTH follows the file instead of a
guessed ladder. ffmpeg writes the media playlist and segments beside it.
WebVTT captions, when the session has them, are a SUBTITLES group: one
file and a one-segment VOD playlist per rendition.
"""

from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence

from projectionist.engine.captions import CaptionRendition
from projectionist.engine.probe import ProbeResult
from projectionist.library.playback import variant_bandwidth_bps

_TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

Runner = Callable[..., object]

_CODECS = {
    "h264": "avc1.640028",
    "hevc": "hvc1.1.6.L120.90",
    "aac": "mp4a.40.2",
    "ac3": "ac-3",
    "eac3": "ec-3",
    "mp3": "mp4a.40.34",
    "alac": "alac",
    "flac": "fLaC",
}


def bandwidth_bps(probe: Optional[ProbeResult], *, file_size: int = 0, duration_ms: int = 0) -> int:
    if probe is not None and int(probe.bitrate or 0) > 0:
        return max(1, int(round(probe.bitrate * 1.25)))
    guessed = variant_bandwidth_bps(file_size or (probe.size if probe else 0), duration_ms)
    if guessed:
        return guessed
    return 5_000_000


def _codec_token(name: str) -> str:
    text = str(name or "").strip().lower()
    aliases = {
        "ac-3": "ac3",
        "e-ac-3": "eac3",
        "ec-3": "eac3",
        "avc": "h264",
        "h265": "hevc",
    }
    return _CODECS.get(aliases.get(text, text), "")


def _codecs(probe: Optional[ProbeResult], *, audio_codec: str = "") -> str:
    """Playlist codec string. ``audio_codec`` is the stream the player will decode.

    A remux advertises the file's audio. An audio-only transcode advertises the
    encoded audio, so the player does not try to decode E-AC-3 or DTS.
    """
    names: list[str] = []
    video = next(
        (item for item in (probe.streams if probe else []) if item.codec_type == "video"), None
    )
    if video is not None:
        token = _codec_token(video.codec)
        if token:
            names.append(token)
    if audio_codec:
        token = _codec_token(audio_codec)
        if token:
            names.append(token)
    else:
        audio = next(
            (item for item in (probe.streams if probe else []) if item.codec_type == "audio"), None
        )
        if audio is not None:
            token = _codec_token(audio.codec)
            if token:
                names.append(token)
    return ",".join(names)


def _attr(value: str) -> str:
    return str(value or "").replace("\\", "").replace('"', "").replace("\n", " ").replace(",", " ")


def _unique_name(name: str, used: set[str]) -> str:
    base = _attr(name) or "Captions"
    candidate = base
    number = 2
    while candidate in used:
        candidate = f"{base} {number}"
        number += 1
    used.add(candidate)
    return candidate


def _with_timestamp_map(body: str) -> str:
    """Cue times are media times. hls.js drops an fMP4 WebVTT that has no map.

    LOCAL 0 equals MPEG-TS 0, which is the start of this remux. A file that
    already names a map is left alone.
    """
    text = str(body or "")
    if "X-TIMESTAMP-MAP" in text or "-->" not in text:
        return text
    stamp = "X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0"
    lines = text.splitlines()
    if lines and lines[0].lstrip("\ufeff").strip().upper().startswith("WEBVTT"):
        lines.insert(1, stamp)
        mapped = "\n".join(lines)
    else:
        mapped = f"WEBVTT\n{stamp}\n\n{text}"
    return mapped if mapped.endswith("\n") else mapped + "\n"


def _media_line(track: CaptionRendition, *, name: str) -> str:
    default = "YES" if track.default else "NO"
    attrs = [
        "TYPE=SUBTITLES",
        'GROUP-ID="subs"',
        f'NAME="{name}"',
        f"DEFAULT={default}",
        f"AUTOSELECT={default}",
        "FORCED=NO",
    ]
    if track.language:
        attrs.append(f'LANGUAGE="{_attr(track.language)}"')
    attrs.append(f'URI="subs/{track.track_id}.m3u8"')
    return "#EXT-X-MEDIA:" + ",".join(attrs)


def write_caption_renditions(
    directory: Path,
    captions: Sequence[CaptionRendition],
    *,
    duration_ms: int,
) -> list[str]:
    """Write one WebVTT and a one-segment VOD playlist per rendition.

    Returns the master ``EXT-X-MEDIA`` lines. A track id that is not a plain
    token is skipped, so a rendition cannot escape ``subs/``.
    """
    lines: list[str] = []
    seconds = max(float(duration_ms or 0) / 1000.0, 1.0)
    target = max(1, math.ceil(seconds - 1e-9))
    subs = directory / "subs"
    used_names: set[str] = set()
    for track in captions:
        if not _TRACK_ID.fullmatch(track.track_id):
            continue
        body = _with_timestamp_map(str(track.webvtt or ""))
        if "-->" not in body:
            continue
        subs.mkdir(parents=True, exist_ok=True)
        (subs / f"{track.track_id}.vtt").write_text(
            body if body.endswith("\n") else body + "\n", encoding="utf-8"
        )
        playlist = "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:3",
                f"#EXT-X-TARGETDURATION:{target}",
                "#EXT-X-MEDIA-SEQUENCE:0",
                "#EXT-X-PLAYLIST-TYPE:VOD",
                f"#EXTINF:{seconds:.3f},",
                f"{track.track_id}.vtt",
                "#EXT-X-ENDLIST",
                "",
            ]
        )
        (subs / f"{track.track_id}.m3u8").write_text(playlist, encoding="utf-8")
        lines.append(_media_line(track, name=_unique_name(track.name, used_names)))
    return lines


def write_master(
    directory: Path,
    probe: Optional[ProbeResult],
    *,
    file_size: int,
    duration_ms: int,
    captions: Optional[Sequence[CaptionRendition]] = None,
    audio_codec: str = "",
    audio_channels: int = 0,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    media_lines = write_caption_renditions(directory, list(captions or []), duration_ms=duration_ms)
    bandwidth = bandwidth_bps(probe, file_size=file_size, duration_ms=duration_ms)
    extras = [f"BANDWIDTH={bandwidth}", f"AVERAGE-BANDWIDTH={bandwidth}"]
    codecs = _codecs(probe, audio_codec=audio_codec)
    if codecs:
        extras.append(f'CODECS="{codecs}"')
    if int(audio_channels or 0) > 0:
        extras.append(f'CHANNELS="{int(audio_channels)}"')
    video = next(
        (item for item in (probe.streams if probe else []) if item.codec_type == "video"), None
    )
    if video and video.width and video.height:
        extras.append(f"RESOLUTION={video.width}x{video.height}")
    if media_lines:
        extras.append('SUBTITLES="subs"')
    line = "#EXT-X-STREAM-INF:" + ",".join(extras)
    path = directory / "master.m3u8"
    path.write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:7",
                *media_lines,
                line,
                "av/stream.m3u8",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def remux_command(ffmpeg: str, source: Path) -> list[str]:
    """Copy the picture and sound into fMP4 HLS.

    ``event`` writes ``stream.m3u8`` as each segment lands. ``vod`` waits
    until ffmpeg exits, so a feature-length copy has no media playlist and
    the player gets 404 for ``av/stream.m3u8``.
    """
    return [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c",
        "copy",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "event",
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        "seg_%04d.m4s",
        "stream.m3u8",
    ]


def start_remux(
    source: Path,
    directory: Path,
    *,
    probe: Optional[ProbeResult],
    file_size: int,
    duration_ms: int,
    runner: Optional[Runner] = None,
    ffmpeg: Optional[str] = None,
    captions: Optional[Sequence[CaptionRendition]] = None,
) -> Optional[subprocess.Popen]:
    """Write the master playlist and start a copy remux. ``runner`` replaces ffmpeg in tests."""
    av = directory / "av"
    av.mkdir(parents=True, exist_ok=True)
    write_master(
        directory,
        probe,
        file_size=file_size,
        duration_ms=duration_ms,
        captions=captions,
    )
    binary = ffmpeg
    if not binary and runner is None:
        from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg

        binary = resolve_ffmpeg()
    if runner is not None:
        runner(remux_command(binary or "ffmpeg", source), cwd=av)
        return None
    if not binary:
        raise FileNotFoundError("ffmpeg is not available")
    return subprocess.Popen(
        remux_command(binary, source),
        cwd=av,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
