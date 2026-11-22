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


def audio_transcode_command(ffmpeg: str, source: Path, audio_codec: str) -> list[str]:
    """Copy video, encode audio, package fMP4 HLS. Never a video encoder."""
    encoder = _ENCODERS[audio_codec]
    return [
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
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        "seg_%04d.m4s",
        "stream.m3u8",
    ]


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
    write_master(
        directory,
        probe,
        file_size=file_size,
        duration_ms=duration_ms,
        captions=captions,
        audio_codec=audio_codec,
    )
    binary = ffmpeg
    if not binary and runner is None:
        from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg

        binary = resolve_ffmpeg()
    argv = audio_transcode_command(binary or "ffmpeg", source, audio_codec)
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
