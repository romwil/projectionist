"""Named device profiles. The planner never guesses from a user-agent string.

ENG-003 accepts the same shape in a session body. A name here is the dry-run
shortcut for ``GET /api/playback/plan``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass
class VideoCapability:
    codec: str
    max_level: str = ""
    hdr: list[str] = field(default_factory=list)
    # 0 means the profile does not state a bit depth. 8 or 10 is the browser's answer.
    bit_depth: int = 0


@dataclass
class DeviceProfile:
    id: str
    containers: list[str]
    video: list[VideoCapability]
    audio: list[str]
    captions: list[str] = field(default_factory=lambda: ["webvtt"])
    max_bitrate_kbps: Optional[int] = None
    # 0 means the client did not say. AAC then stays within a named 5.1 layout.
    max_channels: int = 0

    def as_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "containers": list(self.containers),
            "video": [
                {
                    "codec": item.codec,
                    "max_level": item.max_level,
                    "hdr": list(item.hdr),
                    **({"bit_depth": item.bit_depth} if item.bit_depth else {}),
                }
                for item in self.video
            ],
            "audio": list(self.audio),
            "captions": list(self.captions),
            "max_bitrate_kbps": self.max_bitrate_kbps,
            "max_channels": self.max_channels,
        }


def _video(*rows: tuple[str, str]) -> list[VideoCapability]:
    return [VideoCapability(codec=codec, max_level=level) for codec, level in rows]


APPLE_TV_4K = DeviceProfile(
    id="apple-tv-4k-3",
    containers=["mp4", "hls-fmp4", "hls-ts"],
    video=[
        VideoCapability("hevc", "5.1", ["hdr10", "dolby-vision"]),
        VideoCapability("h264", "5.2"),
    ],
    audio=["aac", "ac3", "eac3", "alac", "flac"],
)

SAFARI = DeviceProfile(
    id="safari",
    containers=["mp4", "hls-fmp4"],
    video=_video(("hevc", "5.1"), ("h264", "5.2")),
    audio=["aac", "ac3", "eac3", "alac", "flac", "mp3"],
)

# Chrome 157.0.8103.79 on this Mac, headless with its own profile, answered
# probably / Media Source / decodingInfo for Main and Main 10 through level 6.2
# (hvc1 and hev1). The named profile uses that level. It does not list HDR.
CHROME = DeviceProfile(
    id="chrome",
    containers=["mp4", "hls-fmp4"],
    video=[
        VideoCapability("hevc", "6.2", bit_depth=10),
        VideoCapability("hevc", "6.2", bit_depth=8),
        VideoCapability("h264", "5.2"),
    ],
    audio=["aac", "mp3", "opus", "flac"],
)

_NAMED = {
    APPLE_TV_4K.id: APPLE_TV_4K,
    SAFARI.id: SAFARI,
    CHROME.id: CHROME,
}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def profile_from_mapping(raw: Mapping[str, Any]) -> DeviceProfile:
    """The object a client sends. Same fields as a named profile, including bit depth."""
    video: list[VideoCapability] = []
    for item in raw.get("video") or []:
        if not isinstance(item, dict):
            continue
        video.append(
            VideoCapability(
                codec=str(item.get("codec") or ""),
                max_level=str(item.get("max_level") or ""),
                hdr=[str(name) for name in (item.get("hdr") or [])],
                bit_depth=_int(item.get("bit_depth")),
            )
        )
    captions = raw.get("captions")
    bitrate = raw.get("max_bitrate_kbps")
    return DeviceProfile(
        id=str(raw.get("id") or "custom"),
        containers=[str(name) for name in (raw.get("containers") or [])],
        video=video,
        audio=[str(name) for name in (raw.get("audio") or [])],
        captions=[str(name) for name in (captions if isinstance(captions, list) else ["webvtt"])],
        max_bitrate_kbps=_int(bitrate) if bitrate not in (None, "") else None,
        max_channels=_int(raw.get("max_channels")),
    )


def named_profile(name: str) -> Optional[DeviceProfile]:
    return _NAMED.get(str(name or "").strip().lower())


def known_profile_ids() -> list[str]:
    return list(_NAMED)
