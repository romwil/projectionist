"""Warm-up lines and the playback steps those lines follow (EXP-018).

The lines file is the same copy for every client. The session `step` is the
work actually in progress. A client that does not see `warmup_screen` shows
art and an honest status, and does not show a joke line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STEPS = (
    "waking_disk",
    "probing",
    "remuxing",
    "encoding_audio",
    "preparing_captions",
    "falling_back",
    "waiting_on_plex",
    "buffering",
)

_LINES_PATH = Path(__file__).with_name("warmup_lines.json")


def load_warmup_lines() -> dict[str, Any]:
    """Versioned lines document. Pools are copied so callers cannot edit the file."""
    raw = json.loads(_LINES_PATH.read_text(encoding="utf-8"))
    version = int(raw.get("version") or 0)
    if version < 1:
        raise ValueError("warmup lines are missing a version")
    general = [str(line) for line in raw.get("general") or []]
    steps_in = raw.get("steps") or {}
    steps = {name: [str(line) for line in (steps_in.get(name) or [])] for name in STEPS}
    if not general or any(not pool for pool in steps.values()):
        raise ValueError("warmup lines are missing a pool")
    return {"version": version, "general": general, "steps": steps}


def set_step(session: Any, step: str) -> None:
    """Record the work in progress. An unknown name is a bug, not a joke."""
    if step not in STEPS:
        raise ValueError(f"unknown playback step {step}")
    session.step = step
