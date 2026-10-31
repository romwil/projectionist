"""Owner Admin settings + SQLite snapshot download (arch M10 residual)."""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def resolve_db_path(data_dir: Path) -> Path:
    """Mirror JobManager path resolution for backup targets."""
    canonical = data_dir / "projectionist.db"
    curatorx_legacy = data_dir / "curatorx.db"
    ancient = data_dir / "mediacurator.db"
    if canonical.exists():
        return canonical
    if curatorx_legacy.exists():
        return curatorx_legacy
    if ancient.exists():
        return ancient
    return canonical


def build_admin_snapshot_zip(data_dir: Path) -> Tuple[bytes, str, Dict[str, Any]]:
    """WAL-safe DB backup + settings.json into a zip. Secrets stay encrypted-at-rest as stored."""
    data_dir = Path(data_dir)
    settings_path = data_dir / "settings.json"
    db_path = resolve_db_path(data_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    filename = f"projectionist-snapshot-{stamp}.zip"

    buf = io.BytesIO()
    meta: Dict[str, Any] = {
        "settings_included": False,
        "db_included": False,
        "db_name": db_path.name if db_path.exists() else "",
        "generated_at": stamp,
    }
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if settings_path.is_file():
            zf.write(settings_path, arcname="settings.json")
            meta["settings_included"] = True
        if db_path.is_file():
            # Offline snapshot via sqlite backup API (safe with WAL).
            tmp = data_dir / f".snapshot-backup-{stamp}.db"
            try:
                src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                try:
                    dst = sqlite3.connect(str(tmp))
                    try:
                        src.backup(dst)
                    finally:
                        dst.close()
                finally:
                    src.close()
                zf.write(tmp, arcname=db_path.name)
                meta["db_included"] = True
            finally:
                try:
                    tmp.unlink(missing_ok=True)
                except TypeError:
                    if tmp.exists():
                        tmp.unlink()
        readme = (
            "Projectionist Admin snapshot\n"
            "============================\n"
            "Contains settings.json (secrets encrypted at rest when a secrets key is set)\n"
            "and a WAL-safe copy of the library SQLite database.\n"
            "Restore: stop Projectionist, replace files under DATA_DIR /config, restart.\n"
            "Keep PROJECTIONIST_SECRETS_KEY (or session secret) with this backup.\n"
        )
        zf.writestr("README.txt", readme)
    return buf.getvalue(), filename, meta


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
