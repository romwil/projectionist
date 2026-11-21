"""Cached ffprobe for one media file.

The cache key is the path. A hit requires the same size and mtime, so a
replaced file is probed again. The cache lives under ``DATA_DIR`` and is not
part of any API response.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

logger = logging.getLogger(__name__)

RunFn = Callable[..., Any]

IMAGE_SUBTITLE_CODECS = frozenset(
    {
        "hdmv_pgs_subtitle",
        "pgssub",
        "dvd_subtitle",
        "dvdsub",
        "vobsub",
        "dvb_subtitle",
        "dvbsub",
        "xsub",
    }
)
TEXT_SUBTITLE_CODECS = frozenset(
    {
        "subrip",
        "srt",
        "ass",
        "ssa",
        "mov_text",
        "webvtt",
        "text",
        "subviewer",
        "subviewer1",
    }
)


class ProbeError(RuntimeError):
    """ffprobe could not describe this file."""


@dataclass
class MediaStream:
    index: int
    codec_type: str
    codec: str
    language: str = ""
    width: int = 0
    height: int = 0
    channels: int = 0
    bitrate: int = 0
    profile: str = ""
    level: str = ""
    hdr: str = ""
    subtitle_kind: str = ""
    bit_depth: int = 0


@dataclass
class ProbeResult:
    container: str
    format_name: str
    duration_s: float
    bitrate: int
    size: int
    streams: list[MediaStream] = field(default_factory=list)

    def as_public(self) -> dict[str, Any]:
        return {
            "container": self.container,
            "duration_s": self.duration_s,
            "bitrate": self.bitrate,
            "size": self.size,
            "streams": [asdict(stream) for stream in self.streams],
        }


def subtitle_kind(codec: str) -> str:
    name = str(codec or "").strip().lower()
    if not name:
        return ""
    if name in IMAGE_SUBTITLE_CODECS or "pgs" in name:
        return "image"
    if name in TEXT_SUBTITLE_CODECS:
        return "text"
    return ""


def container_of(format_name: str) -> str:
    tokens = [part.strip().lower() for part in str(format_name or "").split(",") if part.strip()]
    if "matroska" in tokens:
        return "mkv"
    if "mp4" in tokens or "mov" in tokens:
        return "mp4"
    if "mpegts" in tokens:
        return "mpegts"
    return tokens[0] if tokens else ""


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _hdr(stream: Mapping[str, Any]) -> str:
    side = stream.get("side_data_list")
    items = side if isinstance(side, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("side_data_type") or "")
        if "DOVI" in label.upper() or "Dolby Vision" in label:
            return "dolby-vision"
    transfer = str(stream.get("color_transfer") or "").lower()
    if transfer == "smpte2084":
        return "hdr10"
    if transfer == "arib-std-b67":
        return "hlg"
    return ""


def _bit_depth(stream: Mapping[str, Any]) -> int:
    sample = _int(stream.get("bits_per_raw_sample"))
    if sample >= 8:
        return sample
    pix = str(stream.get("pix_fmt") or "").lower()
    if "p12" in pix or "12le" in pix or "12be" in pix:
        return 12
    if "p10" in pix or "10le" in pix or "10be" in pix:
        return 10
    profile = str(stream.get("profile") or "").lower()
    if "12" in profile:
        return 12
    if "10" in profile:
        return 10
    return 0


def _language(stream: dict[str, Any]) -> str:
    raw_tags = stream.get("tags")
    tags: dict[str, Any] = raw_tags if isinstance(raw_tags, dict) else {}
    raw = str(tags.get("language") or stream.get("language") or "").strip().lower()
    if raw in {"und", "unknown", "unk"}:
        return ""
    return raw


def parse_ffprobe(payload: dict[str, Any]) -> ProbeResult:
    raw_fmt = payload.get("format")
    fmt: dict[str, Any] = raw_fmt if isinstance(raw_fmt, dict) else {}
    format_name = str(fmt.get("format_name") or "")
    streams: list[MediaStream] = []
    for raw in payload.get("streams") or []:
        if not isinstance(raw, dict):
            continue
        codec_type = str(raw.get("codec_type") or "").strip().lower()
        if codec_type not in {"video", "audio", "subtitle"}:
            continue
        codec = str(raw.get("codec_name") or "").strip().lower()
        streams.append(
            MediaStream(
                index=_int(raw.get("index")),
                codec_type=codec_type,
                codec=codec,
                language=_language(raw),
                width=_int(raw.get("width")),
                height=_int(raw.get("height")),
                channels=_int(raw.get("channels")),
                bitrate=_int(raw.get("bit_rate")),
                profile=str(raw.get("profile") or ""),
                level=str(raw.get("level") or ""),
                hdr=_hdr(raw) if codec_type == "video" else "",
                subtitle_kind=subtitle_kind(codec) if codec_type == "subtitle" else "",
                bit_depth=_bit_depth(raw) if codec_type == "video" else 0,
            )
        )
    return ProbeResult(
        container=container_of(format_name),
        format_name=format_name,
        duration_s=_float(fmt.get("duration")),
        bitrate=_int(fmt.get("bit_rate")),
        size=_int(fmt.get("size")),
        streams=streams,
    )


def _cache_path(cache_dir: Path, media_path: str) -> Path:
    digest = hashlib.sha256(media_path.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def probe_file(
    path: str,
    *,
    cache_dir: Path,
    runner: RunFn,
    ffprobe: Optional[str] = None,
) -> ProbeResult:
    """Probe ``path``, reusing a cache entry when size and mtime still match."""
    media = Path(path)
    try:
        stat = media.stat()
    except OSError as error:
        raise ProbeError("Media file is not readable") from error
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = _cache_path(cache_dir, str(media))
    if cached.is_file():
        try:
            blob = json.loads(cached.read_text(encoding="utf-8"))
            if (
                int(blob.get("mtime_ns") or -1) == int(stat.st_mtime_ns)
                and int(blob.get("size") or -1) == int(stat.st_size)
                and isinstance(blob.get("probe"), dict)
            ):
                return parse_ffprobe(blob["probe"])
        except (OSError, ValueError, TypeError):
            logger.debug("engine probe cache miss path=%s", media, exc_info=True)

    binary = ffprobe
    if not binary:
        from projectionist.library.episode_investigate.capabilities import resolve_ffprobe

        binary = resolve_ffprobe()
    if not binary:
        raise ProbeError("ffprobe is not available")
    from projectionist.engine.media_slot import run_media_tool

    try:
        result = run_media_tool(
            [
                binary,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(media),
            ],
            runner,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, TimeoutError) as error:
        raise ProbeError("ffprobe failed") from error
    stdout = str(getattr(result, "stdout", "") or "")
    if int(getattr(result, "returncode", 1) or 0) != 0 or not stdout.strip():
        raise ProbeError("ffprobe failed")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ProbeError("ffprobe returned no stream list") from error
    if not isinstance(payload, dict):
        raise ProbeError("ffprobe returned no stream list")
    parsed = parse_ffprobe(payload)
    cached.write_text(
        json.dumps(
            {"mtime_ns": int(stat.st_mtime_ns), "size": int(stat.st_size), "probe": payload}
        ),
        encoding="utf-8",
    )
    return parsed
