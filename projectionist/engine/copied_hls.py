"""Cut copied-video HLS on IDR pictures.

ffmpeg's HLS muxer starts a new fMP4 segment on every packet it calls a
keyframe. An open-GOP recovery point is that kind of packet, and its first
slice is not an IDR. VideoToolbox then fails the segment
(``kVTVideoDecoderBadDataErr``, -12909) even though a continuous decode of
the whole playlist still works. Chrome appends each segment on its own.

This packs ffmpeg's fragmented MP4 and publishes a segment only when the
picture starts on an IDR. Recovery-point fragments stay in the segment that
began at the previous IDR, so the decoder still has the frames they use.
"""

from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Optional

logger = logging.getLogger(__name__)

_IDR = {
    "h264": frozenset({5}),
    "hevc": frozenset({19, 20}),
}
_VCL = {
    "h264": frozenset({1, 2, 3, 4, 5}),
    "hevc": frozenset(range(0, 32)),
}


def copied_hls_command(
    ffmpeg: str,
    source: Path,
    audio_codec: str,
    *,
    channels: int = 0,
    max_channels: int = 0,
    video_codec: str = "h264",
) -> list[str]:
    """Argv spawn_heavy runs. ffmpeg itself is the child of this module."""
    return [
        sys.executable,
        "-m",
        "projectionist.engine.copied_hls",
        "--ffmpeg",
        ffmpeg,
        "--source",
        str(source),
        "--audio-codec",
        audio_codec,
        "--channels",
        str(int(channels or 0)),
        "--max-channels",
        str(int(max_channels or 0)),
        "--video-codec",
        str(video_codec or "h264"),
    ]


def fragment_starts_on_idr(payload: bytes, codec: str = "h264") -> bool:
    """True when the first video slice in ``payload`` is an IDR."""
    kind = "hevc" if str(codec or "").strip().lower() in {"hevc", "h265"} else "h264"
    idx = payload.find(b"mdat")
    if idx < 0:
        return False
    i = idx + 4
    end = min(len(payload), i + 256_000)
    idr = _IDR[kind]
    vcl = _VCL[kind]
    while i + 5 < end:
        length = int.from_bytes(payload[i : i + 4], "big")
        if length <= 0 or length > 2_000_000 or i + 4 + length > len(payload):
            i += 1
            continue
        nal = payload[i + 4]
        if kind == "hevc":
            nal_type = (nal >> 1) & 0x3F
        else:
            nal_type = nal & 0x1F
        if nal_type in idr:
            return True
        if nal_type in vcl:
            return False
        i += 4 + length
    return False


def _iter_boxes(stream: BinaryIO | Any) -> Iterator[bytes]:
    buf = bytearray()
    while True:
        while len(buf) < 8:
            chunk = stream.read(65536)
            if not chunk:
                return
            buf.extend(chunk)
        size = int.from_bytes(buf[0:4], "big")
        header = 8
        if size == 1:
            while len(buf) < 16:
                chunk = stream.read(65536)
                if not chunk:
                    return
                buf.extend(chunk)
            size = int.from_bytes(buf[8:16], "big")
            header = 16
        if size < header:
            return
        while len(buf) < size:
            chunk = stream.read(max(65536, size - len(buf)))
            if not chunk:
                return
            buf.extend(chunk)
        box = bytes(buf[:size])
        del buf[:size]
        yield box


def _duration_seconds(ffprobe: str, init: Path, segment: Path) -> float:
    combo = segment.with_suffix(".probe.mp4")
    try:
        combo.write_bytes(init.read_bytes() + segment.read_bytes())
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(combo),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return max(0.001, float((result.stdout or "").strip() or "0"))
    except (OSError, ValueError):
        return 6.0
    finally:
        try:
            combo.unlink()
        except OSError:
            pass


def _write_playlist(directory: Path, rows: list[tuple[str, float]], *, finished: bool) -> None:
    target = max([1] + [int(duration) + (0 if duration.is_integer() else 1) for _, duration in rows])
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:EVENT",
        '#EXT-X-MAP:URI="init.mp4"',
    ]
    for name, duration in rows:
        lines.append(f"#EXTINF:{duration:.6f},")
        lines.append(name)
    if finished:
        lines.append("#EXT-X-ENDLIST")
    lines.append("")
    (directory / "stream.m3u8").write_text("\n".join(lines), encoding="utf-8")


def pack_copied_hls(
    directory: Path,
    ffmpeg_argv: list[str],
    *,
    video_codec: str = "h264",
    ffprobe: Optional[str] = None,
) -> None:
    """Run ``ffmpeg_argv`` and write IDR-aligned fMP4 HLS into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    probe = ffprobe
    if not probe:
        from projectionist.library.episode_investigate.capabilities import resolve_ffprobe

        probe = resolve_ffprobe() or "ffprobe"
    process = subprocess.Popen(
        ffmpeg_argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def _stop(*_args: object) -> None:
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, _stop)
    errors: list[str] = []

    def _drain() -> None:
        if process.stderr is None:
            return
        errors.append(process.stderr.read().decode("utf-8", errors="replace")[-4000:])

    threading.Thread(target=_drain, name="projectionist-copied-hls-log", daemon=True).start()
    init = bytearray()
    init_path = directory / "init.mp4"
    pending = b""
    open_parts: list[bytes] = []
    rows: list[tuple[str, float]] = []

    def flush() -> None:
        if not open_parts or not init_path.is_file():
            open_parts.clear()
            return
        name = f"seg_{len(rows):04d}.m4s"
        segment = directory / name
        segment.write_bytes(b"".join(open_parts))
        open_parts.clear()
        rows.append((name, _duration_seconds(probe or "ffprobe", init_path, segment)))
        _write_playlist(directory, rows, finished=False)

    code = 1
    try:
        assert process.stdout is not None
        for box in _iter_boxes(process.stdout):
            marker = box[4:8]
            if marker in {b"ftyp", b"moov"}:
                init.extend(box)
                if marker == b"moov":
                    init_path.write_bytes(init)
            elif marker == b"moof":
                pending = box
            elif marker == b"mdat" and pending:
                fragment = pending + box
                pending = b""
                if fragment_starts_on_idr(fragment, video_codec) and open_parts:
                    flush()
                open_parts.append(fragment)
        flush()
        code = int(process.wait() or 0)
    finally:
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    if rows:
        _write_playlist(directory, rows, finished=True)
    if code != 0:
        logger.warning("copied video ffmpeg exited %s %s", code, "".join(errors)[-500:])


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="IDR-aligned copied-video HLS")
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--audio-codec", required=True)
    parser.add_argument("--channels", type=int, default=0)
    parser.add_argument("--max-channels", type=int, default=0)
    parser.add_argument("--video-codec", default="h264")
    args = parser.parse_args(argv)
    from projectionist.engine.audio import audio_transcode_command

    command = audio_transcode_command(
        args.ffmpeg,
        Path(args.source),
        args.audio_codec,
        channels=args.channels,
        max_channels=args.max_channels,
        output="frag",
    )
    pack_copied_hls(Path.cwd(), command, video_codec=args.video_codec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
