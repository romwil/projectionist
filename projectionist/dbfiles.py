"""Choose the household SQLite file without creating or deleting one.

Opening SQLite on a path that does not exist (``sqlite3.connect``, or the
``sqlite3`` CLI) creates a 0-byte file before any page is written. A query
against that empty file still leaves it at 0 bytes. ``docker exec`` runs as
root and does not go through the entrypoint, so that 0-byte file is
``root:root`` mode 644. When ``/config`` is already uid 1000 the entrypoint
does not rewrite the tree; it chowns only the stray file and names it.

This module only reads headers when choosing a file. It never creates,
deletes, or overwrites one. An empty or non-SQLite candidate is skipped with
a warning. Two real databases refuse startup instead of guessing.
``open_existing_database`` opens a file that is already there with
``mode=rw``, which does not create a missing path.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Canonical name, then legacy names. Preference is not a tie-break: more than
# one usable file is an error.
DATABASE_NAMES = ("projectionist.db", "curatorx.db", "mediacurator.db")
SQLITE_MAGIC = b"SQLite format 3\x00"
SQLITE_HEADER_BYTES = 100


class AmbiguousDatabaseError(RuntimeError):
    """The data directory holds more than one real SQLite database."""


def open_existing_database(
    path: Path,
    *,
    timeout: float,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open ``path`` read-write. A missing path raises and is not created.

    The default ``sqlite3.connect(path)`` uses ``mode=rwc`` and creates a
    0-byte file before any page is written. ``mode=rw`` refuses a path that
    is not already a file, which is what a diagnostic one-liner needs.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    quoted = quote(path.resolve().as_posix(), safe="/")
    return sqlite3.connect(
        f"file:{quoted}?mode=rw",
        uri=True,
        timeout=timeout,
        check_same_thread=check_same_thread,
    )


def is_usable_sqlite(path: Path) -> bool:
    """True when ``path`` is a file with a SQLite header.

    Does not open the database, so a missing path stays missing. A 0-byte
    file, a directory, and any other contents are not usable.
    """
    if not path.is_file():
        return False
    try:
        if path.stat().st_size < SQLITE_HEADER_BYTES:
            return False
        with path.open("rb") as handle:
            return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def resolve_database_path(data_dir: Path) -> Path:
    """Return the one database to open, or the canonical path for a new install.

    Skips candidates that are missing, empty, or not SQLite, and logs one
    warning per skipped file that is actually on disk. When two or more real
    databases are present, raises ``AmbiguousDatabaseError`` and leaves every
    file where it is. The ancient ``mediacurator.db`` name is renamed to
    ``projectionist.db`` only when that canonical path does not already exist.
    """
    data_dir = Path(data_dir)
    canonical = data_dir / DATABASE_NAMES[0]
    usable: list[Path] = []
    skipped: list[Path] = []
    for name in DATABASE_NAMES:
        candidate = data_dir / name
        if is_usable_sqlite(candidate):
            usable.append(candidate)
        elif candidate.exists():
            skipped.append(candidate)

    if len(usable) > 1:
        if len(usable) == 2:
            listed = f"{usable[0].name} and {usable[1].name} are both real databases"
        else:
            listed = f"{', '.join(path.name for path in usable)} are all real databases"
        raise AmbiguousDatabaseError(
            f"Refusing to start: {listed} in {data_dir}. "
            "Projectionist will not guess which one to open. "
            "Move the extra file out of the data directory."
        )

    for path in skipped:
        logger.warning(
            "Skipping database file %s: it is empty or not a SQLite database",
            path,
        )

    if not usable:
        return canonical

    chosen = usable[0]
    if chosen.name == "mediacurator.db" and not canonical.exists():
        chosen.rename(canonical)
        return canonical
    return chosen
