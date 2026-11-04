"""Erasure ledger: deletions that a backup restore must re-apply (PRIV-006).

Snapshots under ``DATA_DIR/backups`` are taken before a member deletes their
data or the owner removes their account, so those zips still hold the rows.
Every erasure appends ``{user_id, kind, groups, at}`` to
``DATA_DIR/privacy-erasures.json``. The file lives beside the database, not
inside it, so restoring an older database cannot roll it back.
``projectionist.backups.restore_snapshot`` applies the ledger to the staged
database before it goes live: a removed account never comes back, and a
"Delete my data" is re-applied to any snapshot taken before it.

The ledger holds the random account id and a timestamp. It holds no name,
email, or content.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from projectionist.privacy import registry

logger = logging.getLogger(__name__)

LEDGER_NAME = "privacy-erasures.json"
KIND_ACCOUNT = "account"
KIND_DATA = "data"

_lock = threading.Lock()


def ledger_path(data_dir: Path) -> Path:
    return Path(data_dir) / LEDGER_NAME


def load_erasures(data_dir: Path) -> List[Dict[str, Any]]:
    path = ledger_path(data_dir)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.error("Erasure ledger %s is unreadable; restore will refuse until it is fixed", path)
        raise
    entries = payload.get("erasures") if isinstance(payload, dict) else None
    return [e for e in (entries or []) if isinstance(e, dict) and e.get("user_id")]


def record_erasure(
    data_dir: Path,
    user_id: str,
    *,
    kind: str,
    groups: Sequence[str] = (),
    at: Optional[float] = None,
) -> None:
    """Append one erasure. Written atomically with owner-only permissions."""
    entry = {
        "user_id": str(user_id),
        "kind": kind,
        "groups": list(groups),
        "at": float(time.time() if at is None else at),
    }
    data_dir = Path(data_dir)
    with _lock:
        try:
            entries = load_erasures(data_dir)
        except (OSError, ValueError):
            # Keep the unreadable file for the owner; restore refuses while it exists.
            aside = ledger_path(data_dir).with_suffix(f".unreadable-{int(time.time())}.json")
            os.replace(ledger_path(data_dir), aside)
            entries = []
        entries.append(entry)
        fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=".erasures-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "erasures": entries}, handle, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, ledger_path(data_dir))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def apply_erasures(
    db_path: Path,
    entries: Sequence[Dict[str, Any]],
    *,
    snapshot_at: Optional[float],
) -> Dict[str, Any]:
    """Re-apply ``entries`` to an offline database file, then VACUUM it.

    Account removals always apply. A data purge applies when the snapshot is
    older than the purge, or when the snapshot's age is unknown.
    """
    applied = 0
    rows = 0
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("BEGIN IMMEDIATE")
        for entry in entries:
            user_id = str(entry["user_id"])
            if entry.get("kind") == KIND_ACCOUNT:
                counts = registry.erase_user(conn, user_id, account=True)
            else:
                at = float(entry.get("at") or 0)
                if snapshot_at is not None and snapshot_at >= at:
                    continue
                groups = tuple(entry.get("groups") or registry.ERASE_ALL)
                counts = registry.erase_user(conn, user_id, groups=groups)
            applied += 1
            rows += sum(counts.values())
        conn.commit()
        if rows:
            conn.execute("VACUUM")
    finally:
        conn.close()
    return {"erasures_applied": applied, "rows_removed": rows}
