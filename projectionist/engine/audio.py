"""Audio-only transcode (ENG-012).

The video stream is copied. The audio is encoded to the first codec on the
device profile that ffmpeg can write. A plan whose video is not playable
never reaches this module. One heavy ffmpeg holds the shared media slot
until it exits. A Play probe does not take that slot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from projectionist.engine.captions import CaptionRendition
from projectionist.engine.planner import canonical_codec
from projectionist.engine.probe import ProbeResult
from projectionist.engine.profiles import DeviceProfile
from projectionist.engine.remux import write_master

# Encoder name, then the bitrate flags that encoder accepts. No video encoder.
_ENCODERS: dict[str, tuple[str, ...]] = {
    "aac": ("aac", "-b:a", "256k"),
    "mp3": ("libmp3lame", "-b:a", "192k"),
    "opus": ("libopus", "-b:a", "160k"),
    "ac3": ("ac3", "-b:a", "384k"),
    "flac": ("flac",),
    "alac": ("alac",),
}


def audio_encode_codec(profile: DeviceProfile) -> str:
    """First profile audio codec this server can encode. Empty when none match."""
    for name in profile.audio:
        codec = canonical_codec(name)
        if codec in _ENCODERS:
            return codec
    return ""


# AAC-LC can name these. 5.1(side), 7.1, and Atmos cannot, and the init
# segment then says the layout is unknown. Players reject that segment.
_AAC_LAYOUT = {1: "mono", 2: "stereo", 6: "5.1"}


def aac_channel_count(source_channels: int, *, max_channels: int = 0) -> int:
    """Channel count AAC can name, capped by the profile.

    A missing cap stays at 5.1. Seven or eight channels, including Atmos,
    fold down to that cap. One and two stay as they are.
    """
    count = int(source_channels or 0)
    if count <= 0:
        count = 2
    cap = int(max_channels or 0)
    if cap <= 0:
        cap = 6
    capped = min(count, max(1, cap))
    if capped >= 6 and cap >= 6:
        return 6
    if capped >= 2:
        return 2
    return 1


def _aac_layout_flags(source_channels: int, *, max_channels: int = 0) -> list[str]:
    output = aac_channel_count(source_channels, max_channels=max_channels)
    if output == 2 and int(source_channels or 0) in {0, 2}:
        return []
    return ["-ac", str(output), "-channel_layout", _AAC_LAYOUT[output]]


def audio_transcode_command(
    ffmpeg: str,
    source: Path,
    audio_codec: str,
    *,
    channels: int = 0,
    max_channels: int = 0,
) -> list[str]:
    """Copy video, encode audio, package fMP4 HLS. Never a video encoder.

    ``event`` publishes the media playlist as each segment is written.
    ``vod`` waits until ffmpeg exits, so a feature-length encode has
    segments and no playlist.
    """
    encoder = _ENCODERS[audio_codec]
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-c:v",
        "copy",
        "-c:a",
        *encoder,
    ]
    if audio_codec == "aac":
        command.extend(_aac_layout_flags(channels, max_channels=max_channels))
    command.extend(
        [
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
    )
    return command


def _source_channels(probe: Optional[ProbeResult]) -> int:
    if probe is None:
        return 0
    for stream in probe.streams:
        if stream.codec_type == "audio":
            return int(stream.channels or 0)
    return 0


def start_audio_transcode(
    source: Path,
    directory: Path,
    *,
    probe: Optional[ProbeResult],
    file_size: int,
    duration_ms: int,
    audio_codec: str,
    runner: Optional[Callable[..., object]] = None,
    ffmpeg: Optional[str] = None,
    captions: Optional[Sequence[CaptionRendition]] = None,
    still_wanted: Optional[Callable[[], bool]] = None,
    attach: Optional[Callable[..., bool]] = None,
    max_channels: int = 0,
) -> None:
    """Write the master playlist and start the audio transcode.

    ``runner`` replaces ffmpeg in tests and holds the media slot until it
    returns, so the playlist files exist before the caller continues. Without
    a runner, ffmpeg starts on a background thread once the slot is free.
    """
    if audio_codec not in _ENCODERS:
        raise ValueError(f"cannot encode {audio_codec}")
    av = directory / "av"
    av.mkdir(parents=True, exist_ok=True)
    source_channels = _source_channels(probe)
    output_channels = (
        aac_channel_count(source_channels, max_channels=max_channels) if audio_codec == "aac" else 0
    )
    write_master(
        directory,
        probe,
        file_size=file_size,
        duration_ms=duration_ms,
        captions=captions,
        audio_codec=audio_codec,
        audio_channels=output_channels,
    )
    binary = ffmpeg
    if not binary and runner is None:
        from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg

        binary = resolve_ffmpeg()
    argv = audio_transcode_command(
        binary or "ffmpeg",
        source,
        audio_codec,
        channels=source_channels,
        max_channels=max_channels,
    )
    if runner is not None:
        from projectionist.engine.media_slot import run_media_tool

        run_media_tool(argv, runner, cwd=av)
        return
    if not binary:
        raise FileNotFoundError("ffmpeg is not available")
    from projectionist.engine.media_slot import spawn_heavy

    spawn_heavy(
        argv,
        cwd=str(av),
        still_wanted=still_wanted or (lambda: True),
        attach=attach or (lambda _process: True),
    )
