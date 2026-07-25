"""Human-friendly library sync progress labels and weighted percents."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

# Cumulative end-of-phase progress (0–100). Within a phase, interpolate using current/total.
# Never report 100% until phase == completed / job is done.
SYNC_PHASE_END_PERCENT: Dict[str, int] = {
    "queued": 0,
    "preparing": 4,
    "movies": 22,
    "tv": 42,
    "enriching": 70,
    "indexing": 80,
    "episodes": 90,
    "finishing": 99,
    # Legacy aliases used by older call sites / episode sync
    "facets": 74,
    "fts": 80,
    "embeddings": 99,
    "completed": 100,
}

SYNC_PHASE_ORDER = (
    "queued",
    "preparing",
    "movies",
    "tv",
    "enriching",
    "indexing",
    "episodes",
    "finishing",
    "completed",
)

# Short phase titles for Config UI
PHASE_LABELS: Dict[str, str] = {
    "queued": "Waiting",
    "preparing": "Preparing",
    "movies": "Scanning movies",
    "tv": "Scanning TV",
    "enriching": "Enriching metadata",
    "indexing": "Building indexes",
    "facets": "Building indexes",
    "fts": "Building indexes",
    "episodes": "Syncing episodes",
    "finishing": "Finishing",
    "embeddings": "Finishing",
    "completed": "Done",
    "done": "Done",
}

FRIENDLY_PROGRESS_MESSAGES: Dict[str, str] = {
    "queued": "Waiting to start…",
    "preparing": "Connecting to Plex…",
    "movies": "Scanning Plex movies…",
    "tv": "Scanning Plex TV shows…",
    "scanning_plex": "Scanning Plex library…",
    "enriching": "Enriching metadata…",
    "indexing": "Building search indexes…",
    "facets": "Building search facets…",
    "fts": "Building search index…",
    "episodes": "Syncing TV episodes…",
    "finishing": "Finishing up…",
    "embeddings": "Building recommendations…",
    "completed": "Done",
    "done": "Done",
}

_SNAKE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

_PHASE_START: Dict[str, int] = {
    "queued": 0,
    "preparing": 0,
    "movies": 4,
    "tv": 22,
    "enriching": 42,
    "indexing": 70,
    "facets": 70,
    "fts": 74,
    "episodes": 80,
    "finishing": 90,
    "embeddings": 90,
    "completed": 99,
}


def phase_label(phase: str = "") -> str:
    key = (phase or "").strip().lower()
    if key in PHASE_LABELS:
        return PHASE_LABELS[key]
    if key and _SNAKE_KEY.match(key):
        return key.replace("_", " ").capitalize()
    return "Working"


def friendly_progress_message(message: str = "", phase: str = "") -> str:
    """Map internal progress keys to short hoster-friendly copy."""
    raw = (message or "").strip()
    phase_key = (phase or "").strip().lower()

    if raw in FRIENDLY_PROGRESS_MESSAGES:
        return FRIENDLY_PROGRESS_MESSAGES[raw]
    if phase_key in FRIENDLY_PROGRESS_MESSAGES and (not raw or _SNAKE_KEY.match(raw)):
        return FRIENDLY_PROGRESS_MESSAGES[phase_key]
    if raw and _SNAKE_KEY.match(raw):
        return raw.replace("_", " ").capitalize() + "…"
    if raw:
        return raw
    if phase_key in FRIENDLY_PROGRESS_MESSAGES:
        return FRIENDLY_PROGRESS_MESSAGES[phase_key]
    if phase_key and _SNAKE_KEY.match(phase_key):
        return phase_key.replace("_", " ").capitalize() + "…"
    return "Working…"


def format_count_message(
    verb: str,
    current: int,
    total: Optional[int] = None,
    *,
    unit: str = "items",
    done: bool = False,
) -> str:
    """Build count-aware progress copy for novices."""
    current = max(int(current or 0), 0)
    total_n = int(total) if total is not None else None
    if done and current > 0:
        return f"Found {current} {unit}"
    if total_n and total_n > 0:
        if current <= 0:
            return f"{verb}…"
        if current < total_n:
            return f"{verb}… {current} of ~{total_n}"
        return f"Found {current} {unit}"
    if current > 0:
        return f"Found {current} {unit} so far"
    return f"{verb}…"


def weighted_sync_percent(phase: str, current: int, total: int) -> int:
    """Overall job percent from phase weights; 100% only at completed."""
    key = (phase or "queued").strip().lower()
    if key in ("completed", "done"):
        return 100
    if key not in SYNC_PHASE_END_PERCENT:
        ratio = min(max(current, 0) / max(total, 1), 1.0) if total else 0.0
        return min(int(ratio * 99), 99)

    start = _PHASE_START.get(key, 0)
    end = SYNC_PHASE_END_PERCENT[key]
    if total <= 0:
        return min(start, 99)
    ratio = min(max(current, 0) / max(total, 1), 1.0)
    percent = int(start + (end - start) * ratio)
    return max(0, min(percent, 99))


def format_job_progress(
    phase: str,
    current: int,
    total: int,
    message: str = "",
) -> Tuple[int, str, str]:
    """Return (percent, friendly_message, phase_label)."""
    friendly = friendly_progress_message(message, phase)
    percent = weighted_sync_percent(phase, current, total)
    return percent, friendly, phase_label(phase)


def friendly_job_error(error: BaseException | str | None) -> str:
    """Short user-facing sync failure text — no stack traces or snake_case keys."""
    if error is None:
        return "Something went wrong during library sync."
    text = str(error).strip()
    if not text:
        return "Something went wrong during library sync."
    if "Traceback" in text:
        before = text.split("Traceback", 1)[0].strip()
        lines = [line.strip() for line in before.splitlines() if line.strip()]
        first_line = lines[-1] if lines else ""
        if not first_line:
            # Exception-only traceback dump — fall back to last non-empty line after Traceback.
            after_lines = [line.strip() for line in text.splitlines() if line.strip() and "Traceback" not in line and not line.startswith("File ")]
            first_line = after_lines[-1] if after_lines else "Something went wrong during library sync."
    else:
        first_line = text.splitlines()[0].strip()
    if ": " in first_line and first_line.lower().startswith("http "):
        first_line = first_line.split(": ", 1)[-1].strip()
    if len(first_line) > 180:
        first_line = first_line[:177].rstrip() + "…"
    if _SNAKE_KEY.match(first_line):
        first_line = first_line.replace("_", " ").capitalize()
    return first_line or "Something went wrong during library sync."
