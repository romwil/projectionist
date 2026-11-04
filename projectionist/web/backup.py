"""Owner Admin settings + SQLite snapshot download (arch M10 residual)."""

from __future__ import annotations

import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def resolve_db_path(data_dir: Path) -> Path:
    """Mirror JobManager path resolution for backup targets."""
    from projectionist.backups import resolve_db_path as _resolve

    return _resolve(data_dir)


def build_admin_snapshot_zip(data_dir: Path) -> Tuple[bytes, str, Dict[str, Any]]:
    """WAL-safe DB backup + settings.json into a zip. Secrets stay encrypted-at-rest as stored."""
    from projectionist.backups import write_snapshot_zip

    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    buf = io.BytesIO()
    meta = write_snapshot_zip(Path(data_dir), buf, stamp=stamp)
    return buf.getvalue(), f"projectionist-snapshot-{stamp}.zip", meta


HOUSEHOLD_BACKUP_LOG_KEY = "household_backup_log"
HOUSEHOLD_BACKUP_LOG_LIMIT = 50


def record_household_backup(db: Any, *, actor_id: str, now: float | None = None) -> Dict[str, Any]:
    """Append one audit entry (who, when) for a full household backup download."""
    entry = {"actor_id": actor_id, "ts": time.time() if now is None else float(now)}
    try:
        existing = json.loads(db.get_sync_state(HOUSEHOLD_BACKUP_LOG_KEY) or "[]")
    except (TypeError, ValueError):
        existing = []
    if not isinstance(existing, list):
        existing = []
    log = (existing + [entry])[-HOUSEHOLD_BACKUP_LOG_LIMIT:]
    db.set_sync_state(HOUSEHOLD_BACKUP_LOG_KEY, json.dumps(log))
    from projectionist.security_audit import HOUSEHOLD_BACKUP, audit

    audit(db, HOUSEHOLD_BACKUP, actor_id=actor_id)
    logger.info("Household backup downloaded by actor=%s", actor_id)
    return entry


def household_backup_log(db: Any) -> list:
    try:
        log = json.loads(db.get_sync_state(HOUSEHOLD_BACKUP_LOG_KEY) or "[]")
    except (TypeError, ValueError):
        return []
    return log if isinstance(log, list) else []
