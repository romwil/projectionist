"""Copy a readable file into VOD fMP4 HLS. No re-encode.

The master playlist is ours, so BANDWIDTH follows the file instead of a
guessed ladder. ffmpeg writes the media playlist and segments beside it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

from projectionist.engine.probe import ProbeResult
from projectionist.library.playback import variant_bandwidth_bps

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


def _codecs(probe: Optional[ProbeResult]) -> str:
    if probe is None:
        return ""
    names: list[str] = []
    for kind in ("video", "audio"):
        stream = next((item for item in probe.streams if item.codec_type == kind), None)
        if stream is None:
            continue
        token = _CODECS.get(stream.codec)
        if token:
            names.append(token)
    return ",".join(names)


def write_master(directory: Path, probe: Optional[ProbeResult], *, file_size: int, duration_ms: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    bandwidth = bandwidth_bps(probe, file_size=file_size, duration_ms=duration_ms)
    extras = [f"BANDWIDTH={bandwidth}", f"AVERAGE-BANDWIDTH={bandwidth}"]
    codecs = _codecs(probe)
    if codecs:
        extras.append(f'CODECS="{codecs}"')
    video = next((item for item in (probe.streams if probe else []) if item.codec_type == "video"), None)
    if video and video.width and video.height:
        extras.append(f"RESOLUTION={video.width}x{video.height}")
    line = "#EXT-X-STREAM-INF:" + ",".join(extras)
    path = directory / "master.m3u8"
    path.write_text(
        "\n".join(
            [
                "#EXTM3U",
                "#EXT-X-VERSION:7",
                line,
                "av/stream.m3u8",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def remux_command(ffmpeg: str, source: Path) -> list[str]:
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
        "vod",
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
) -> Optional[subprocess.Popen]:
    """Write the master playlist and start a copy remux. ``runner`` replaces ffmpeg in tests."""
    av = directory / "av"
    av.mkdir(parents=True, exist_ok=True)
    write_master(directory, probe, file_size=file_size, duration_ms=duration_ms)
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
