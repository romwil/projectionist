"""Owner-only still cache under DATA_DIR/investigate."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

SAFE_NAME = re.compile(r"^[\w.-]+$")
SAFE_ID = re.compile(r"^[\w-]+$")


def investigate_root(data_dir: Path) -> Path:
    return Path(data_dir) / "investigate"


def stills_dir(data_dir: Path, job_id: str, file_id: str) -> Path:
    return investigate_root(data_dir) / str(job_id) / str(file_id)


def still_url(job_id: str, file_id: str, name: str) -> str:
    return f"/api/admin/investigate/stills/{job_id}/{file_id}/{name}"


def resolve_still(data_dir: Path, job_id: str, file_id: str, name: str) -> Optional[Path]:
    if not SAFE_ID.match(str(job_id or "")) or not SAFE_ID.match(str(file_id or "")):
        return None
    if not SAFE_NAME.match(str(name or "")):
        return None
    path = (stills_dir(data_dir, job_id, file_id) / name).resolve()
    root = investigate_root(data_dir).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.is_file() else None
