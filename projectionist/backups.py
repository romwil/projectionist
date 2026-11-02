"""On-box household backups and restore (PERF-002, OPS-009).

``household_backup`` (scheduler) writes a snapshot zip under
``DATA_DIR/backups`` every day and keeps the newest few. The zip is the same
shape as Admin → Backup → Download: ``settings.json`` plus a WAL-safe copy of
the SQLite database made with SQLite's online ``backup()`` API.

Restore is offline. Stop Projectionist, then run::

    python -m projectionist.backups restore --data-dir /config --from /config/backups/<zip> --yes

Restore checks the zip, runs ``PRAGMA integrity_check`` on the database copy,
moves the current files into ``DATA_DIR/backups/pre-restore-<stamp>/`` (nothing
is deleted), and only then puts the snapshot in place. Nothing is uploaded
anywhere; backups stay on the same disk as the data unless you copy them off.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
AUTO_PREFIX = "projectionist-auto-"
DEFAULT_KEEP = 7
DB_NAMES = ("projectionist.db", "curatorx.db", "mediacurator.db")
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")

README_TEXT = (
    "Projectionist snapshot\n"
    "======================\n"
    "Contains settings.json (secrets encrypted at rest when a secrets key is set)\n"
    "and a WAL-safe copy of the library SQLite database.\n"
    "Restore: stop Projectionist, then run\n"
    "  python -m projectionist.backups restore --data-dir /config --from <this zip> --yes\n"
    "Keep PROJECTIONIST_SECRETS_KEY (or the session secret) with this backup;\n"
    "without it, saved service keys cannot be decrypted after a restore.\n"
)


class RestoreError(RuntimeError):
    """A snapshot could not be restored; nothing in the data dir was changed."""


def resolve_db_path(data_dir: Path) -> Path:
    """Mirror JobManager path resolution: canonical name, then legacy names."""
    data_dir = Path(data_dir)
    for name in DB_NAMES:
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    return data_dir / DB_NAMES[0]


def backup_dir(data_dir: Path) -> Path:
    return Path(data_dir) / BACKUP_DIR_NAME


def _stamp(now: Optional[float] = None) -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() if now is None else now))


def write_snapshot_zip(data_dir: Path, target: IO[bytes], *, stamp: Optional[str] = None) -> Dict[str, Any]:
    """Write settings.json + an online SQLite copy into ``target`` as a zip."""
    data_dir = Path(data_dir)
    settings_path = data_dir / "settings.json"
    db_path = resolve_db_path(data_dir)
    stamp = stamp or _stamp()
    meta: Dict[str, Any] = {
        "settings_included": False,
        "db_included": False,
        "db_name": db_path.name if db_path.exists() else "",
        "generated_at": stamp,
    }
    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if settings_path.is_file():
            zf.write(settings_path, arcname="settings.json")
            meta["settings_included"] = True
        if db_path.is_file():
            with tempfile.TemporaryDirectory(dir=data_dir, prefix=".snapshot-") as tmp_dir:
                tmp = Path(tmp_dir) / db_path.name
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
        zf.writestr("README.txt", README_TEXT)
        zf.writestr("manifest.json", json.dumps(meta, sort_keys=True))
    return meta


def create_snapshot_file(
    data_dir: Path,
    *,
    prefix: str = AUTO_PREFIX,
    now: Optional[float] = None,
) -> Path:
    """Write one snapshot zip into ``DATA_DIR/backups`` (owner-only file mode)."""
    target_dir = backup_dir(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(now)
    final = target_dir / f"{prefix}{stamp}.zip"
    fd, tmp_name = tempfile.mkstemp(dir=target_dir, prefix=".partial-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as handle:
            write_snapshot_zip(data_dir, handle, stamp=stamp)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, final)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return final


def list_snapshots(data_dir: Path, *, prefix: str = AUTO_PREFIX) -> List[Path]:
    """Snapshot zips with ``prefix``, newest first."""
    target_dir = backup_dir(data_dir)
    if not target_dir.is_dir():
        return []
    files = [p for p in target_dir.glob(f"{prefix}*.zip") if p.is_file()]
    return sorted(files, key=lambda p: p.name, reverse=True)


def prune_snapshots(data_dir: Path, *, keep: int = DEFAULT_KEEP, prefix: str = AUTO_PREFIX) -> List[Path]:
    """Delete all but the newest ``keep`` automatic snapshots. Returns removed paths."""
    removed: List[Path] = []
    for old in list_snapshots(data_dir, prefix=prefix)[max(1, int(keep)):]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            logger.warning("Could not prune old backup %s", old.name, exc_info=True)
    return removed


def latest_snapshot_at(data_dir: Path) -> Optional[float]:
    """mtime of the newest automatic snapshot, or None."""
    snapshots = list_snapshots(data_dir)
    if not snapshots:
        return None
    try:
        return snapshots[0].stat().st_mtime
    except OSError:
        return None


def _db_member(names: Sequence[str]) -> Optional[str]:
    for name in DB_NAMES:
        if name in names:
            return name
    return None


def _check_sqlite(path: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        raise RestoreError(f"The database in this snapshot is not readable: {error}") from error
    if not row or str(row[0]).lower() != "ok":
        raise RestoreError("The database in this snapshot failed SQLite's integrity check.")


def restore_snapshot(zip_path: Path, data_dir: Path, *, now: Optional[float] = None) -> Dict[str, Any]:
    """Replace the data dir's settings.json and database with a snapshot's copies.

    The server must be stopped first. Current files move to
    ``backups/pre-restore-<stamp>/``; nothing is deleted.
    """
    zip_path = Path(zip_path)
    data_dir = Path(data_dir)
    if not zip_path.is_file():
        raise RestoreError(f"Snapshot not found: {zip_path}")
    if not data_dir.is_dir():
        raise RestoreError(f"Data directory not found: {data_dir}")
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as error:
        raise RestoreError("This file is not a Projectionist snapshot zip.") from error
    with archive, tempfile.TemporaryDirectory(dir=data_dir, prefix=".restore-") as staging_name:
        names = archive.namelist()
        db_name = _db_member(names)
        if db_name is None:
            raise RestoreError("This snapshot has no database file in it.")
        staging = Path(staging_name)
        archive.extract(db_name, staging)
        has_settings = "settings.json" in names
        if has_settings:
            archive.extract("settings.json", staging)
            try:
                json.loads((staging / "settings.json").read_text(encoding="utf-8"))
            except ValueError as error:
                raise RestoreError("settings.json in this snapshot is not valid JSON.") from error
        _check_sqlite(staging / db_name)

        aside = backup_dir(data_dir) / f"pre-restore-{_stamp(now)}"
        aside.mkdir(parents=True, exist_ok=False)
        moved: List[str] = []
        current = [data_dir / name for name in DB_NAMES]
        current += [Path(f"{p}{suffix}") for p in list(current) for suffix in SQLITE_SIDECARS]
        if has_settings:
            current.append(data_dir / "settings.json")
        for path in current:
            if path.exists():
                shutil.move(str(path), str(aside / path.name))
                moved.append(path.name)
        os.replace(staging / db_name, data_dir / db_name)
        if has_settings:
            os.replace(staging / "settings.json", data_dir / "settings.json")
            os.chmod(data_dir / "settings.json", 0o600)
    logger.warning("Restored %s into %s; previous files are in %s", zip_path.name, data_dir, aside)
    return {
        "restored_db": db_name,
        "restored_settings": has_settings,
        "previous_files_dir": str(aside),
        "previous_files": moved,
    }


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m projectionist.backups",
        description="Create, list, or restore on-box Projectionist snapshots.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create", "list", "restore"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/config"))
        if name == "restore":
            cmd.add_argument("--from", dest="source", required=True, help="Snapshot zip to restore")
            cmd.add_argument(
                "--yes",
                action="store_true",
                help="Confirm that Projectionist is stopped and the data dir may be replaced",
            )
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)
    if args.command == "create":
        print(create_snapshot_file(data_dir, prefix="projectionist-manual-"))
        return 0
    if args.command == "list":
        for prefix in (AUTO_PREFIX, "projectionist-manual-"):
            for path in list_snapshots(data_dir, prefix=prefix):
                print(path)
        return 0
    if not args.yes:
        print(
            "Restore replaces settings.json and the database in "
            f"{data_dir}. Stop Projectionist first, then re-run with --yes.",
            file=sys.stderr,
        )
        return 2
    try:
        result = restore_snapshot(Path(args.source), data_dir)
    except RestoreError as error:
        print(f"Restore refused: {error}", file=sys.stderr)
        return 1
    print(f"Restored {result['restored_db']}. Previous files: {result['previous_files_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
