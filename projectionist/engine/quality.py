"""Owner quality ceiling.

The ceiling is a household setting, 1080p unless the owner changes it. The
playability report lists titles above it. There is no earlier replaced or
copy-preferred flag: a ready copy is still what the planner plays when the
source would be transcoded. Marking a title replaced records that choice
here. The planner then treats the title as replaced, and the list drops it.

This module does not start an encode and does not copy the library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

DEFAULT_QUALITY_CEILING = "1080p"

# Pixel box for each named ceiling. A title is above the ceiling when its
# picture is wider or taller than this box. Matching the box is within it.
QUALITY_CEILINGS: dict[str, tuple[int, int]] = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2160p": (3840, 2160),
}

_ALIASES = {
    "4k": "2160p",
    "uhd": "2160p",
    "2160": "2160p",
    "1080": "1080p",
    "720": "720p",
}

_REPLACED_NAME = "replaced-titles.json"
LIST_TITLE = "Above your quality target"


def normalize_quality_ceiling(value: Any) -> str:
    """A known ceiling, or the default when the stored value is blank or unknown."""
    text = _alias(value)
    if text in QUALITY_CEILINGS:
        return text
    return DEFAULT_QUALITY_CEILING


def parse_quality_ceiling(value: Any) -> str:
    """The ceiling the owner asked for. Unknown values are refused."""
    text = _alias(value)
    if text not in QUALITY_CEILINGS:
        raise ValueError("Quality ceiling must be 720p, 1080p, or 4K.")
    return text


def exceeds_quality_ceiling(width: int, height: int, ceiling: str) -> bool:
    """True when the picture is wider or taller than the ceiling."""
    name = normalize_quality_ceiling(ceiling)
    max_width, max_height = QUALITY_CEILINGS[name]
    wide = _pixels(width)
    tall = _pixels(height)
    if wide <= 0 and tall <= 0:
        return False
    return tall > max_height or wide > max_width


def resolution_label(width: int, height: int) -> str:
    wide = _pixels(width)
    tall = _pixels(height)
    if wide > 0 and tall > 0:
        return f"{wide}×{tall}"
    if tall > 0:
        return f"{tall}p"
    if wide > 0:
        return f"{wide} wide"
    return ""


def above_quality_target(
    report: Mapping[str, Any],
    *,
    ceiling: str,
    replaced: Sequence[str] = (),
    paths: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Titles above the ceiling, and how many.

    A marked-replaced title is not still above the target. File paths come
    from ``paths``; this function does not read the disk.
    """
    name = normalize_quality_ceiling(ceiling)
    skipped = {str(key or "").strip() for key in replaced if str(key or "").strip()}
    known = paths or {}
    rows = _unique_titles(report)
    titles: list[dict[str, Any]] = []
    for key, row in rows.items():
        if key in skipped:
            continue
        wide = _pixels(row.get("width"))
        tall = _pixels(row.get("height"))
        if wide <= 0 and tall <= 0:
            if not (name == "1080p" and row.get("above_1080p")):
                continue
            resolution = "Above 1080p"
        elif not exceeds_quality_ceiling(wide, tall, name):
            continue
        else:
            resolution = resolution_label(wide, tall)
        titles.append(
            {
                "rating_key": key,
                "title": str(row.get("title") or ""),
                "resolution": resolution,
                "codec": str(row.get("video_codec") or ""),
                "file_size": _pixels(row.get("file_size")),
                "path": str(known.get(key) or ""),
            }
        )
    titles.sort(key=lambda item: (str(item.get("title") or "").casefold(), item["rating_key"]))
    return {
        "title": LIST_TITLE,
        "ceiling": name,
        "count": len(titles),
        "titles": titles,
    }


def load_replaced_titles(data_dir: Path) -> list[str]:
    path = _replaced_path(data_dir)
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = blob.get("rating_keys") if isinstance(blob, dict) else None
    keys: list[str] = []
    for item in raw or []:
        key = str(item or "").strip()
        if key and "/" not in key and key not in {".", ".."} and key not in keys:
            keys.append(key)
    return keys


def mark_title_replaced(data_dir: Path, rating_key: str) -> list[str]:
    """Remember that this title is replaced. Does not transcode or delete the file."""
    key = str(rating_key or "").strip()
    if not key or "/" in key or key in {".", ".."}:
        raise ValueError("rating_key is required")
    folder = Path(data_dir) / "engine"
    folder.mkdir(parents=True, exist_ok=True)
    keys = load_replaced_titles(data_dir)
    if key not in keys:
        keys.append(key)
    _replaced_path(data_dir).write_text(
        json.dumps({"rating_keys": keys}),
        encoding="utf-8",
    )
    return keys


def title_is_replaced(data_dir: Path, rating_key: str) -> bool:
    key = str(rating_key or "").strip()
    return bool(key) and key in load_replaced_titles(data_dir)


def _alias(value: Any) -> str:
    text = str(value or "").strip().lower()
    return _ALIASES.get(text, text)


def _pixels(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _unique_titles(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for block in report.get("profiles") or []:
        if not isinstance(block, Mapping):
            continue
        for row in block.get("titles") or []:
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("rating_key") or "").strip()
            if key and key not in found:
                found[key] = row
    return found


def _replaced_path(data_dir: Path) -> Path:
    return Path(data_dir) / "engine" / _REPLACED_NAME
