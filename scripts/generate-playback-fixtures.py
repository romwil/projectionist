#!/usr/bin/env python3
"""Generate short playback fixtures with ffmpeg. Do not commit the clips.

Each clip is 48 seconds of real media: long enough to seek, and long enough
for a playhead to pass 30 seconds. A few seconds of lavfi at 320x240 is cheap,
so the files stay out of git.

The TrueHD clip asks for 7.1. ffmpeg's TrueHD encoder only accepts layouts
through 5.1(side), so when 7.1 is rejected the file is TrueHD 5.1(side)
(6 channels) and the catalog records that layout. The planned tier is the
same either way: TrueHD is not a browser codec.

Usage:
  python3 scripts/generate-playback-fixtures.py [output_dir]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

DURATION_S = 48
CUE = "FIXTURE CUE NORTH WINDOW"
REVISION = 1

# kind is what the Playwright test maps to a planned tier.
TITLES = (
    {
        "rating_key": "fx-h264-aac-mp4",
        "file": "h264-aac.mp4",
        "title": "H.264 AAC MP4",
        "kind": "mp4-aac",
        "original_language": "en",
    },
    {
        "rating_key": "fx-h264-aac-mkv",
        "file": "h264-aac.mkv",
        "title": "H.264 AAC MKV",
        "kind": "mkv-aac",
        "original_language": "en",
    },
    {
        "rating_key": "fx-h264-flac-srt",
        "file": "h264-flac.mkv",
        "title": "H.264 FLAC captions",
        "kind": "flac",
        "original_language": "ja",
        "subtitle": "cue.srt",
    },
    {
        "rating_key": "fx-h264-truehd",
        "file": "h264-truehd.mkv",
        "title": "H.264 TrueHD",
        "kind": "truehd",
        "original_language": "en",
    },
    {
        "rating_key": "fx-h264-dts",
        "file": "h264-dts.mkv",
        "title": "H.264 DTS",
        "kind": "dts",
        "original_language": "en",
    },
    {
        "rating_key": "fx-h264-eac3",
        "file": "h264-eac3.mkv",
        "title": "H.264 E-AC-3",
        "kind": "eac3",
        "original_language": "en",
    },
    {
        "rating_key": "fx-mpeg2",
        "file": "mpeg2.ts",
        "title": "MPEG-2",
        "kind": "mpeg2",
        "original_language": "en",
    },
)

_H264 = [
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-pix_fmt",
    "yuv420p",
    "-profile:v",
    "baseline",
    "-level",
    "3.0",
    "-g",
    "24",
    "-b:v",
    "250k",
]


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: generate-playback-fixtures.py [output_dir]", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).expanduser() if len(sys.argv) == 2 else Path("e2e/.playback-fixtures")
    root.mkdir(parents=True, exist_ok=True)
    if _fresh(root):
        print(f"playback fixtures already at {root}")
        return 0
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        print("ffmpeg and ffprobe are required to generate playback fixtures", file=sys.stderr)
        return 1
    cue = _write_cue(root)
    jobs = {
        "h264-aac.mp4": lambda dest: _h264_aac(ffmpeg, dest, "mp4"),
        "h264-aac.mkv": lambda dest: _h264_aac(ffmpeg, dest, "matroska"),
        "h264-flac.mkv": lambda dest: _h264_flac(ffmpeg, dest, cue),
        "h264-truehd.mkv": lambda dest: _h264_truehd(ffmpeg, dest),
        "h264-dts.mkv": lambda dest: _h264_dts(ffmpeg, dest),
        "h264-eac3.mkv": lambda dest: _h264_eac3(ffmpeg, dest),
        "mpeg2.ts": lambda dest: _mpeg2(ffmpeg, dest),
    }
    described: list[dict] = []
    for title in TITLES:
        dest = root / str(title["file"])
        print(f"generating {dest.name}")
        note = jobs[dest.name](dest)
        entry = dict(title)
        entry["streams"] = _streams(ffprobe, dest)
        if note:
            entry["note"] = note
        described.append(entry)
    catalog = {
        "revision": REVISION,
        "duration_s": DURATION_S,
        "cue": CUE,
        "titles": described,
    }
    (root / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {root / 'catalog.json'}")
    return 0


def _fresh(root: Path) -> bool:
    catalog_path = root / "catalog.json"
    if not catalog_path.is_file():
        return False
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if catalog.get("revision") != REVISION or catalog.get("duration_s") != DURATION_S:
        return False
    if catalog.get("cue") != CUE:
        return False
    for title in TITLES:
        if not (root / str(title["file"])).is_file():
            return False
    return (root / "cue.srt").is_file()


def _write_cue(root: Path) -> Path:
    path = root / "cue.srt"
    path.write_text(
        "1\n00:00:00,500 --> 00:00:08,000\n" + CUE + "\n",
        encoding="utf-8",
    )
    return path


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"ffmpeg failed ({result.returncode}): {detail}")


def _lavfi(audio: str, *extra_inputs: str) -> list[str]:
    video = f"testsrc2=size=320x240:rate=12:duration={DURATION_S}"
    cmd = [
        "-f",
        "lavfi",
        "-i",
        video,
        "-f",
        "lavfi",
        "-i",
        audio,
    ]
    for item in extra_inputs:
        cmd.extend(["-i", item])
    return cmd


def _base(ffmpeg: str, audio: str, *extra_inputs: str) -> list[str]:
    return [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *_lavfi(audio, *extra_inputs)]


def _h264_aac(ffmpeg: str, dest: Path, container: str) -> str:
    cmd = _base(ffmpeg, f"sine=frequency=440:sample_rate=48000:duration={DURATION_S}")
    cmd.extend(["-map", "0:v:0", "-map", "1:a:0", *_H264, "-c:a", "aac", "-ac", "2", "-b:a", "128k"])
    if container == "mp4":
        cmd.extend(["-movflags", "+faststart"])
    else:
        cmd.extend(["-f", container])
    cmd.extend(["-t", str(DURATION_S), str(dest)])
    _run(cmd)
    return ""


def _h264_flac(ffmpeg: str, dest: Path, cue: Path) -> str:
    cmd = _base(
        ffmpeg,
        f"sine=frequency=440:sample_rate=48000:duration={DURATION_S}",
        str(cue),
    )
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:s:0",
            *_H264,
            "-c:a",
            "flac",
            "-ac",
            "2",
            "-c:s",
            "srt",
            "-metadata:s:s:0",
            "language=eng",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    _run(cmd)
    return ""


def _h264_truehd(ffmpeg: str, dest: Path) -> str:
    seven = _base(ffmpeg, "anullsrc=channel_layout=7.1:sample_rate=48000")
    seven.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *_H264,
            "-c:a",
            "truehd",
            "-strict",
            "experimental",
            "-ac",
            "8",
            "-channel_layout",
            "7.1",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    result = subprocess.run(seven, capture_output=True, text=True)
    if result.returncode == 0:
        return ""
    # This encoder's widest TrueHD layout is 5.1(side). 7.1 is refused.
    fallback = _base(ffmpeg, "anullsrc=channel_layout=5.1(side):sample_rate=48000")
    fallback.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *_H264,
            "-c:a",
            "truehd",
            "-strict",
            "experimental",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    _run(fallback)
    return (
        "Asked for TrueHD 7.1. This ffmpeg TrueHD encoder stops at 5.1(side), "
        "so the file is 6-channel TrueHD. The planned tier is unchanged."
    )


def _h264_dts(ffmpeg: str, dest: Path) -> str:
    cmd = _base(ffmpeg, "anullsrc=channel_layout=5.1:sample_rate=48000")
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *_H264,
            "-c:a",
            "dca",
            "-strict",
            "experimental",
            "-ac",
            "6",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    _run(cmd)
    return ""


def _h264_eac3(ffmpeg: str, dest: Path) -> str:
    cmd = _base(ffmpeg, "anullsrc=channel_layout=5.1:sample_rate=48000")
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *_H264,
            "-c:a",
            "eac3",
            "-ac",
            "6",
            "-b:a",
            "384k",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    _run(cmd)
    return ""


def _mpeg2(ffmpeg: str, dest: Path) -> str:
    cmd = _base(ffmpeg, f"sine=frequency=440:sample_rate=48000:duration={DURATION_S}")
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "mpeg2video",
            "-b:v",
            "800k",
            "-c:a",
            "mp2",
            "-f",
            "mpegts",
            "-t",
            str(DURATION_S),
            str(dest),
        ]
    )
    _run(cmd)
    return ""


def _streams(ffprobe: str, path: Path) -> list[dict]:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    rows = []
    for stream in payload.get("streams") or []:
        rows.append(
            {
                "codec_type": stream.get("codec_type") or "",
                "codec": stream.get("codec_name") or "",
                "channels": stream.get("channels") or 0,
                "channel_layout": stream.get("channel_layout") or "",
            }
        )
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
