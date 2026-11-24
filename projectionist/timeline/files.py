"""Timeline file identity (TML-001).

A fingerprint is the hash of size, modification time, and duration. The same
numbers are the same version. Events live on that row and are not returned
from the file record.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

_MAX = 2**62


class TimelineError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = int(status_code)


def _key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or len(text) > 80 or any(ch in text for ch in "/\\\n\r"):
        raise TimelineError("That title is not available.")
    return text


def _count(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > _MAX:
        raise TimelineError(f"{label} is not a usable number.")
    return value


def file_fingerprint(*, size: int, mtime_ns: int, duration_ms: int) -> str:
    counted = (
        _count(size, "Size"),
        _count(mtime_ns, "Modification time"),
        _count(duration_ms, "Duration"),
    )
    blob = f"{counted[0]}:{counted[1]}:{counted[2]}".encode()
    return hashlib.sha256(blob).hexdigest()


def _public(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "rating_key": str(row["rating_key"]),
        "file_fingerprint": str(row["file_fingerprint"]),
        "duration_ms": int(row["duration_ms"]),
        "built_at": row["built_at"],
    }


def record_timeline_file(
    db: Any,
    *,
    rating_key: str,
    size: int,
    mtime_ns: int,
    duration_ms: int,
) -> dict[str, Any]:
    key = _key(rating_key)
    fingerprint = file_fingerprint(size=size, mtime_ns=mtime_ns, duration_ms=duration_ms)
    duration = _count(duration_ms, "Duration")

    def _write() -> dict[str, Any]:
        with db.connect() as conn:
            from projectionist.library.db._shared import begin_immediate

            begin_immediate(conn)
            existing = conn.execute(
                """
                SELECT id, rating_key, file_fingerprint, duration_ms, built_at
                FROM timeline_files
                WHERE rating_key = ? AND file_fingerprint = ?
                """,
                (key, fingerprint),
            ).fetchone()
            if existing is not None:
                return _public(existing)
            now = time.time()
            cursor = conn.execute(
                """
                INSERT INTO timeline_files (
                    rating_key, file_fingerprint, duration_ms, built_at, build_version
                ) VALUES (?, ?, ?, ?, 1)
                """,
                (key, fingerprint, duration, now),
            )
            return {
                "id": int(cursor.lastrowid),
                "rating_key": key,
                "file_fingerprint": fingerprint,
                "duration_ms": duration,
                "built_at": now,
            }

    return db.run_write(_write, label="timeline_file")


def list_timeline_files(db: Any, rating_key: str) -> dict[str, Any]:
    key = _key(rating_key)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, rating_key, file_fingerprint, duration_ms, built_at
            FROM timeline_files
            WHERE rating_key = ?
            ORDER BY id
            """,
            (key,),
        ).fetchall()
    return {"files": [_public(row) for row in rows]}
