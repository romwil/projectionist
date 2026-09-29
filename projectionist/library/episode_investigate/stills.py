"""Owner-only still cache under DATA_DIR/investigate."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SAFE_NAME = re.compile(r"^[\w.-]+$")
SAFE_ID = re.compile(r"^[\w-]+$")

# Keep the current Investigate job for review UI; purge everything else under
# DATA_DIR/investigate/ except the Identify test scratch folder.
KEEP_IDENTIFY_TEST_DIR = "identify-test"


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


def purge_old_investigate_jobs(data_dir: Path, *, keep_job_id: str) -> int:
    """Remove prior job trees (stills + Identify WAVs). Keep ``keep_job_id`` for review UI."""
    root = investigate_root(data_dir)
    if not root.is_dir():
        return 0
    keep = str(keep_job_id or "").strip()
    removed = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name == keep or name == KEEP_IDENTIFY_TEST_DIR:
            continue
        try:
            shutil.rmtree(child)
            removed += 1
        except OSError as error:
            logger.info("investigate purge skipped path=%s error=%s", child, error)
    if removed:
        logger.info("investigate purge removed=%s keep=%s", removed, keep or "(none)")
    return removed
