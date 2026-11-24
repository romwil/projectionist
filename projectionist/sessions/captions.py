"""Handheld caption feed (SES-006).

The cues are the household subtitle file. Nothing is generated per person,
and the room's captions do not change.
"""

from __future__ import annotations

import re
from typing import Any

_ARROW = re.compile(
    r"(?P<h1>\d{1,2}):(?P<m1>\d{2}):(?P<s1>\d{2})[,.](?P<ms1>\d{1,3})\s*-->\s*"
    r"(?P<h2>\d{1,2}):(?P<m2>\d{2}):(?P<s2>\d{2})[,.](?P<ms2>\d{1,3})"
)
_MAX_CUES = 4000
_MAX_TEXT = 400


def _milliseconds(hours: str, minutes: str, seconds: str, fraction: str) -> int:
    padded = (fraction + "000")[:3]
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(padded)


def parse_cues(text: str) -> list[dict[str, Any]]:
    """Timed lines from an SRT or WebVTT body. Empty when the body has no cues."""
    body = str(text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cues: list[dict[str, Any]] = []
    for block in re.split(r"\n\s*\n", body):
        timing = None
        lines: list[str] = []
        for raw in block.split("\n"):
            line = raw.strip()
            if not line or line.upper().startswith("WEBVTT") or line.upper().startswith("NOTE"):
                continue
            match = _ARROW.search(line)
            if match is not None and timing is None:
                timing = match
                continue
            if timing is not None and not line.isdigit():
                lines.append(line)
        if timing is None or not lines:
            continue
        cues.append(
            {
                "start_ms": _milliseconds(
                    timing.group("h1"), timing.group("m1"), timing.group("s1"), timing.group("ms1")
                ),
                "end_ms": _milliseconds(
                    timing.group("h2"), timing.group("m2"), timing.group("s2"), timing.group("ms2")
                ),
                "text": " ".join(lines)[:_MAX_TEXT],
            }
        )
        if len(cues) >= _MAX_CUES:
            break
    return cues
