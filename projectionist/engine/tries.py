"""Whether a try showed a picture, per title and device profile.

A miss is remembered. The next plan for that title and profile is the media
source, not another try. A recorded arrival does not block a later try. The
file stays under the data directory and never holds a path.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_LOCK = threading.Lock()
FILE_NAME = "playback_tries.json"


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "engine" / FILE_NAME


def _load(data_dir: Path) -> dict:
    path = _path(data_dir)
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _save(data_dir: Path, blob: dict) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(blob, indent=2, sort_keys=True))
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def record_first_frame(
    data_dir: Path,
    *,
    rating_key: str,
    profile_id: str,
    arrived: bool,
) -> None:
    """Remember whether this title's try showed a picture on this profile."""
    key = str(rating_key or "").strip()
    profile = str(profile_id or "").strip()
    if not key or not profile:
        return
    with _LOCK:
        blob = _load(data_dir)
        row = blob.get(key)
        if not isinstance(row, dict):
            row = {}
        row[str(profile)] = {"arrived": bool(arrived)}
        blob[key] = row
        _save(data_dir, blob)


def failed_try_keys(data_dir: Path) -> set[tuple[str, str]]:
    """Title and profile pairs whose last try did not show a picture."""
    found: set[tuple[str, str]] = set()
    with _LOCK:
        blob = _load(data_dir)
    for rating_key, profiles in blob.items():
        if not isinstance(profiles, dict):
            continue
        for profile_id, row in profiles.items():
            if isinstance(row, dict) and row.get("arrived") is False:
                found.add((str(rating_key), str(profile_id)))
    return found
