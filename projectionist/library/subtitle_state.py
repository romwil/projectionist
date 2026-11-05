"""Per-title ledger for the household subtitle cache (``subtitle_state``).

One row per movie or episode and household language. The idle task and the
owner backfill read it to pick unfinished titles, so a restart resumes where it
left off instead of starting over. Admin → Scheduled Tasks reads the same rows
for done / remaining / last error.

Statuses:

* ``cached`` — a usable file is in ``DATA_DIR/subtitles``. Done.
* ``none_found`` — Plex and OpenSubtitles both answered with nothing usable.
  Rechecked after :data:`NONE_FOUND_RECHECK_SECONDS` (catalogs grow).
* ``no_key`` — Plex had nothing and OpenSubtitles is not configured. Picked up
  again as soon as a key is set.
* ``retry`` — a network error, timeout, or bad body. Retried after a backoff.
* ``failed`` — :data:`MAX_FAILURES` errors in a row. Parked until the recheck.

Nothing here talks to the network.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

STATUS_CACHED = "cached"
STATUS_NONE_FOUND = "none_found"
STATUS_NO_KEY = "no_key"
STATUS_RETRY = "retry"
STATUS_FAILED = "failed"

_DAY = 86400
NONE_FOUND_RECHECK_SECONDS = 30 * _DAY
ERROR_BACKOFF_SECONDS = (3600, 6 * 3600, _DAY, 3 * _DAY)
MAX_FAILURES = len(ERROR_BACKOFF_SECONDS) + 1

_CANDIDATES_SQL = """
    SELECT rating_key, 0 AS kind_order, id AS row_id FROM library_items
    WHERE media_type = 'movie' AND rating_key IS NOT NULL AND rating_key != ''
    UNION ALL
    SELECT rating_key, 1 AS kind_order, id AS row_id FROM library_episodes
    WHERE rating_key IS NOT NULL AND rating_key != ''
"""


def _clock(now: Optional[float]) -> float:
    return float(now) if now is not None else time.time()


def _upsert(
    db: Any,
    rating_key: str,
    language: str,
    *,
    status: str,
    source: str = "",
    failures: int = 0,
    retry_after: float = 0.0,
    last_error: str = "",
    now: float,
    label: str,
) -> None:
    def _write() -> None:
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO subtitle_state
                    (rating_key, language, status, source, failures, retry_after,
                     last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rating_key, language) DO UPDATE SET
                    status = excluded.status,
                    source = excluded.source,
                    failures = excluded.failures,
                    retry_after = excluded.retry_after,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    str(rating_key),
                    str(language),
                    status,
                    source,
                    int(failures),
                    float(retry_after),
                    str(last_error or "")[:300],
                    now,
                ),
            )

    db.run_write(_write, label=label)


def get_state(db: Any, rating_key: str, language: str) -> Optional[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM subtitle_state WHERE rating_key = ? AND language = ?",
            (str(rating_key), str(language)),
        ).fetchone()
    return dict(row) if row else None


def record_cached(
    db: Any, rating_key: str, language: str, *, source: str, now: Optional[float] = None
) -> None:
    _upsert(
        db,
        rating_key,
        language,
        status=STATUS_CACHED,
        source=source,
        now=_clock(now),
        label="subtitle_state_cached",
    )


def record_none_found(
    db: Any,
    rating_key: str,
    language: str,
    *,
    no_key: bool = False,
    now: Optional[float] = None,
) -> None:
    t = _clock(now)
    _upsert(
        db,
        rating_key,
        language,
        status=STATUS_NO_KEY if no_key else STATUS_NONE_FOUND,
        retry_after=0.0 if no_key else t + NONE_FOUND_RECHECK_SECONDS,
        now=t,
        label="subtitle_state_none_found",
    )


def record_failure(
    db: Any,
    rating_key: str,
    language: str,
    error: str,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Count one failed attempt. The title is never marked done by a failure."""
    t = _clock(now)
    prior = get_state(db, rating_key, language) or {}
    previous = int(prior.get("failures") or 0) if prior.get("status") in {
        STATUS_RETRY,
        STATUS_FAILED,
    } else 0
    failures = previous + 1
    if failures >= MAX_FAILURES:
        status = STATUS_FAILED
        retry_after = t + NONE_FOUND_RECHECK_SECONDS
    else:
        status = STATUS_RETRY
        retry_after = t + ERROR_BACKOFF_SECONDS[failures - 1]
    _upsert(
        db,
        rating_key,
        language,
        status=status,
        failures=failures,
        retry_after=retry_after,
        last_error=error,
        now=t,
        label="subtitle_state_failure",
    )
    return {"status": status, "failures": failures, "retry_after": retry_after}


def _pending_clause() -> str:
    # ``no_key`` waits for a key; everything else waits for its retry time.
    return (
        "s.rating_key IS NULL "
        "OR (s.status = 'no_key' AND :configured = 1) "
        "OR (s.status IN ('retry', 'none_found', 'failed') AND s.retry_after <= :now)"
    )


def pending_keys(
    db: Any,
    language: str,
    *,
    limit: int,
    opensubtitles_configured: bool,
    prefer: Sequence[str] = (),
    exclude: Iterable[str] = (),
    now: Optional[float] = None,
) -> List[str]:
    """Unfinished titles, preferred keys (upcoming Live lineup) first."""
    t = _clock(now)
    skip = {str(key) for key in exclude}
    params = {"lang": str(language), "configured": 1 if opensubtitles_configured else 0, "now": t}
    out: List[str] = []
    with db.connect() as conn:
        wanted = [str(k) for k in prefer if str(k) and str(k) not in skip]
        for key in dict.fromkeys(wanted):
            if len(out) >= limit:
                return out
            row = conn.execute(
                f"""
                SELECT c.rating_key FROM ({_CANDIDATES_SQL}) c
                LEFT JOIN subtitle_state s
                    ON s.rating_key = c.rating_key AND s.language = :lang
                WHERE c.rating_key = :key AND ({_pending_clause()})
                """,
                {**params, "key": key},
            ).fetchone()
            if row:
                out.append(str(row["rating_key"]))
        skip.update(out)
        fetch = limit - len(out) + len(skip)
        rows = conn.execute(
            f"""
            SELECT c.rating_key FROM ({_CANDIDATES_SQL}) c
            LEFT JOIN subtitle_state s
                ON s.rating_key = c.rating_key AND s.language = :lang
            WHERE {_pending_clause()}
            ORDER BY c.kind_order, c.row_id
            LIMIT :fetch
            """,
            {**params, "fetch": max(1, fetch)},
        ).fetchall()
    for row in rows:
        if len(out) >= limit:
            break
        key = str(row["rating_key"])
        if key in skip:
            continue
        out.append(key)
    return out


def backlog_summary(
    db: Any,
    language: str,
    *,
    opensubtitles_configured: bool,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Done / remaining / last error for the Scheduled Tasks card."""
    t = _clock(now)
    params = {"lang": str(language), "configured": 1 if opensubtitles_configured else 0, "now": t}
    with db.connect() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM ({_CANDIDATES_SQL})").fetchone()[0])
        remaining = int(
            conn.execute(
                f"""
                SELECT COUNT(*) FROM ({_CANDIDATES_SQL}) c
                LEFT JOIN subtitle_state s
                    ON s.rating_key = c.rating_key AND s.language = :lang
                WHERE {_pending_clause()}
                """,
                params,
            ).fetchone()[0]
        )
        counts = {
            str(row["status"]): int(row["n"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM subtitle_state WHERE language = ? GROUP BY status",
                (str(language),),
            ).fetchall()
        }
        last = conn.execute(
            """
            SELECT rating_key, last_error, updated_at FROM subtitle_state
            WHERE language = ? AND last_error != ''
            ORDER BY updated_at DESC LIMIT 1
            """,
            (str(language),),
        ).fetchone()
    return {
        "language": str(language),
        "total": total,
        "remaining": remaining,
        "done": max(0, total - remaining),
        "cached": counts.get(STATUS_CACHED, 0),
        "none_found": counts.get(STATUS_NONE_FOUND, 0) + counts.get(STATUS_NO_KEY, 0),
        "retrying": counts.get(STATUS_RETRY, 0),
        "failed": counts.get(STATUS_FAILED, 0),
        "last_error": str(last["last_error"]) if last else "",
        "last_error_rating_key": str(last["rating_key"]) if last else "",
        "last_error_at": float(last["updated_at"]) if last else None,
    }


def count_pending(db: Any, language: str, *, opensubtitles_configured: bool) -> int:
    return int(
        backlog_summary(db, language, opensubtitles_configured=opensubtitles_configured)[
            "remaining"
        ]
    )
