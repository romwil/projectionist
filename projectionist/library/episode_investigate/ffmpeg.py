"""Extract three stills and probe runtime via ffmpeg/ffprobe on PATH."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg, resolve_ffprobe

logger = logging.getLogger(__name__)

STILL_FRACTIONS = (0.18, 0.50, 0.78)
RunFn = Callable[..., subprocess.CompletedProcess]


def probe_runtime_seconds(
    path: str,
    *,
    ffprobe: Optional[str] = None,
    runner: RunFn = subprocess.run,
) -> Optional[float]:
    binary = ffprobe or resolve_ffprobe()
    if not binary or not path:
        return None
    try:
        result = runner(
            [
                binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.info("ffprobe failed path=%s error=%s", path, error)
        return None
    text = str(result.stdout or "").strip()
    if not text:
        return None
    try:
        value = float(text.splitlines()[0])
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def extract_stills(
    path: str,
    dest_dir: Path,
    *,
    count: int = 3,
    fractions: Sequence[float] = STILL_FRACTIONS,
    ffmpeg: Optional[str] = None,
    runtime_seconds: Optional[float] = None,
    runner: RunFn = subprocess.run,
) -> List[Path]:
    """Grab ``count`` JPEGs at mid-episode fractions. Empty list if ffmpeg missing."""
    binary = ffmpeg or resolve_ffmpeg()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if not binary or not path or not Path(path).is_file():
        return []
    duration = runtime_seconds
    if duration is None:
        duration = probe_runtime_seconds(path, runner=runner)
    if not duration or duration <= 1:
        duration = 120.0
    written: List[Path] = []
    picks = list(fractions)[: max(1, int(count))]
    while len(picks) < count:
        picks.append(picks[-1] if picks else 0.5)
    for index, fraction in enumerate(picks[:count]):
        stamp = max(0.5, min(float(duration) * float(fraction), float(duration) - 0.5))
        out = dest / f"{index}.jpg"
        try:
            result = runner(
                [
                    binary,
                    "-y",
                    "-ss",
                    f"{stamp:.2f}",
                    "-i",
                    path,
                    "-frames:v",
                    "1",
                    "-q:v",
                    "5",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.info("ffmpeg still failed path=%s error=%s", path, error)
            continue
        if result.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            written.append(out)
    return written


IDENTIFY_CLIP_SECONDS = 12.0
IDENTIFY_CLIP_FRACTION = 0.40
IDENTIFY_MAX_BYTES = 2 * 1024 * 1024


def extract_identify_clip(
    path: str,
    dest: Path,
    *,
    runtime_seconds: Optional[float] = None,
    seconds: float = IDENTIFY_CLIP_SECONDS,
    fraction: float = IDENTIFY_CLIP_FRACTION,
    max_bytes: int = IDENTIFY_MAX_BYTES,
    ffmpeg: Optional[str] = None,
    runner: RunFn = subprocess.run,
) -> Optional[Path]:
    """~12s mono WAV from 40% in. Empty if ffmpeg is missing or the clip is over the cap."""
    binary = ffmpeg or resolve_ffmpeg()
    if not binary or not path or not Path(path).is_file():
        return None
    duration = runtime_seconds
    if duration is None:
        duration = probe_runtime_seconds(path, runner=runner)
    if not duration or duration <= 1:
        duration = 120.0
    stamp = max(0.0, min(float(duration) * float(fraction), max(0.0, float(duration) - seconds)))
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = runner(
            [
                binary,
                "-y",
                "-ss",
                f"{stamp:.2f}",
                "-t",
                f"{float(seconds):.2f}",
                "-i",
                path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(out),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.info("ffmpeg identify clip failed path=%s error=%s", path, error)
        return None
    if result.returncode != 0 or not out.is_file() or out.stat().st_size <= 0:
        return None
    if out.stat().st_size > int(max_bytes):
        logger.info("identify clip over size cap path=%s size=%s", out, out.stat().st_size)
        try:
            out.unlink()
        except OSError:
            pass
        return None
    return out
