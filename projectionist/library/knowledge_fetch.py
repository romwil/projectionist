"""Retry/backoff ledger for automatic knowledge retrieval (plot, metadata, embeddings).

Product rule: a *missing* plot (or similar knowledge) is **work to do**, not an
exception. The scheduled trickle tasks (``long_synopsis_enrichment``,
``metadata_enrichment``, ``semantic_embeddings``) already know how to fetch it;
they now also remember what happened so they can:

* back off per title (a title Wikipedia has never heard of is not retried every
  cycle, and cannot starve the head of the queue);
* stop hammering an upstream that is down or rejecting us (run-level breaker);
* escalate to Admin → Library knowledge **only** when retrieval was tried and
  failed enough times that the owner needs to know (``exhausted``).

Nothing here talks to the network. It is pure policy + a small SQLite ledger
(``knowledge_fetch_state``), so tests can drive it with a fake clock.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

KIND_SYNOPSIS = "synopsis"
KIND_METADATA = "metadata"
KIND_EMBEDDING = "embedding"

#: Deficit kinds that the scheduler fills automatically. They only become owner
#: exceptions once their retries are exhausted.
AUTO_RETRIEVED_KINDS = frozenset({KIND_SYNOPSIS, KIND_METADATA, KIND_EMBEDDING})

OUTCOME_MISS = "miss"  # upstream answered; it has nothing for this title
OUTCOME_ERROR = "error"  # transient failure (timeout, 5xx, 429, network)
OUTCOME_HARD = "hard"  # permanent: unknown id (404/410), no usable key/id

_DAY = 86400
#: Delay after the Nth consecutive miss (1-indexed). Exhausted after the last one.
MISS_BACKOFF_SECONDS: Tuple[int, ...] = (1 * _DAY, 3 * _DAY, 7 * _DAY)
#: Delay after the Nth consecutive transient error. Exhausted after the last one.
ERROR_BACKOFF_SECONDS: Tuple[int, ...] = (3600, 6 * 3600, _DAY, 3 * _DAY, 7 * _DAY)
MAX_MISS_ATTEMPTS = len(MISS_BACKOFF_SECONDS)
MAX_ERROR_ATTEMPTS = len(ERROR_BACKOFF_SECONDS)
#: Hold items for this long when the *run* hit a wall (breaker) — no strike counted.
DEFER_SECONDS = 3600
#: Consecutive transient errors in one run before the task stops fetching.
BREAKER_THRESHOLD = 3
#: An exhausted title gets one more automatic look after this long (catalogs grow).
EXHAUSTED_RECHECK_SECONDS = 30 * _DAY


def _clock(now: Optional[float]) -> float:
    return float(now) if now is not None else time.time()


def backoff_for(outcome: str, attempts: int) -> Tuple[int, bool]:
    """Return ``(delay_seconds, exhausted)`` after *attempts* strikes of *outcome*."""
    attempts = max(1, int(attempts))
    if outcome == OUTCOME_HARD:
        return EXHAUSTED_RECHECK_SECONDS, True
    if outcome == OUTCOME_MISS:
        schedule, limit = MISS_BACKOFF_SECONDS, MAX_MISS_ATTEMPTS
    else:
        schedule, limit = ERROR_BACKOFF_SECONDS, MAX_ERROR_ATTEMPTS
    delay = schedule[min(attempts, len(schedule)) - 1]
    return delay, attempts >= limit


def classify_error(error: BaseException) -> str:
    """Map an upstream exception to ``hard`` / ``auth`` / ``transient``.

    ``hard``: the upstream answered and says this id does not exist (404/410).
    ``auth``: our credentials are rejected (401/403) — a setup problem, never a
    per-title failure, so the run stops and nothing is blamed on titles.
    """
    text = str(error)
    for code in ("HTTP 404", "HTTP 410"):
        if code in text:
            return "hard"
    for code in ("HTTP 401", "HTTP 403"):
        if code in text:
            return "auth"
    return "transient"


def parked_sql(kind: str, *, now: Optional[float] = None, table: str = "library_items") -> Tuple[str, Tuple[Any, ...]]:
    """SQL ``AND NOT EXISTS (...)`` fragment excluding titles that are parked.

    Parked = exhausted (until the long recheck) or still inside a backoff window.
    """
    t = _clock(now)
    return (
        f"""
        AND NOT EXISTS (
            SELECT 1 FROM knowledge_fetch_state s
            WHERE s.item_id = {table}.id AND s.kind = ?
              AND (
                (s.exhausted = 1 AND s.last_attempt_at > ?)
                OR (s.exhausted = 0 AND s.next_retry_at > ?)
              )
        )
        """,
        (kind, t - EXHAUSTED_RECHECK_SECONDS, t),
    )


def exhausted_sql(kind: str, *, now: Optional[float] = None, table: str = "library_items") -> Tuple[str, Tuple[Any, ...]]:
    """SQL ``AND NOT EXISTS`` fragment excluding titles that are exhausted (not backoff)."""
    t = _clock(now)
    return (
        f"""
        AND NOT EXISTS (
            SELECT 1 FROM knowledge_fetch_state s
            WHERE s.item_id = {table}.id AND s.kind = ?
              AND s.exhausted = 1 AND s.last_attempt_at > ?
        )
        """,
        (kind, t - EXHAUSTED_RECHECK_SECONDS),
    )


def get_state(db: Any, item_id: int, kind: str) -> Optional[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_fetch_state WHERE item_id = ? AND kind = ?",
            (int(item_id), kind),
        ).fetchone()
    return dict(row) if row else None


def record_failure(
    db: Any,
    item_id: int,
    kind: str,
    outcome: str,
    detail: str = "",
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Record one failed attempt; returns the stored state (``exhausted`` set when due)."""
    t = _clock(now)
    outcome = outcome if outcome in {OUTCOME_MISS, OUTCOME_ERROR, OUTCOME_HARD} else OUTCOME_ERROR
    safe_detail = str(detail or "")[:300]

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT attempts, last_outcome FROM knowledge_fetch_state "
                "WHERE item_id = ? AND kind = ?",
                (int(item_id), kind),
            ).fetchone()
            prior = int(row["attempts"]) if row else 0
            # Strikes of a different outcome do not stack: a miss after errors
            # starts the miss ladder over (the upstream is reachable now).
            if row and str(row["last_outcome"] or "") != outcome:
                prior = 0
            attempts = prior + 1
            delay, exhausted = backoff_for(outcome, attempts)
            conn.execute(
                """
                INSERT INTO knowledge_fetch_state
                    (item_id, kind, attempts, last_outcome, last_detail,
                     last_attempt_at, next_retry_at, exhausted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id, kind) DO UPDATE SET
                    attempts = excluded.attempts,
                    last_outcome = excluded.last_outcome,
                    last_detail = excluded.last_detail,
                    last_attempt_at = excluded.last_attempt_at,
                    next_retry_at = excluded.next_retry_at,
                    exhausted = excluded.exhausted
                """,
                (int(item_id), kind, attempts, outcome, safe_detail, t, t + delay, int(exhausted)),
            )
            return {
                "item_id": int(item_id),
                "kind": kind,
                "attempts": attempts,
                "last_outcome": outcome,
                "last_detail": safe_detail,
                "last_attempt_at": t,
                "next_retry_at": t + delay,
                "exhausted": exhausted,
            }

    return db.run_write(_write, label="knowledge_fetch_record_failure")


def defer(
    db: Any,
    item_ids: Iterable[int],
    kind: str,
    *,
    seconds: int = DEFER_SECONDS,
    now: Optional[float] = None,
) -> int:
    """Hold titles briefly without counting a strike (the *run* was blocked, not the title)."""
    ids = [int(i) for i in item_ids]
    if not ids:
        return 0
    t = _clock(now)

    def _write() -> int:
        with db.connect() as conn:
            for item_id in ids:
                conn.execute(
                    """
                    INSERT INTO knowledge_fetch_state
                        (item_id, kind, attempts, last_outcome, last_attempt_at,
                         next_retry_at, exhausted)
                    VALUES (?, ?, 0, 'deferred', ?, ?, 0)
                    ON CONFLICT(item_id, kind) DO UPDATE SET
                        next_retry_at = MAX(knowledge_fetch_state.next_retry_at, excluded.next_retry_at)
                    WHERE knowledge_fetch_state.exhausted = 0
                    """,
                    (item_id, kind, t, t + int(seconds)),
                )
        return len(ids)

    return int(db.run_write(_write, label="knowledge_fetch_defer") or 0)


def clear(db: Any, item_ids: Iterable[int], kind: str) -> int:
    """Forget failure state (success, or an owner-initiated retry)."""
    ids = [int(i) for i in item_ids]
    if not ids:
        return 0

    def _write() -> int:
        with db.connect() as conn:
            conn.executemany(
                "DELETE FROM knowledge_fetch_state WHERE item_id = ? AND kind = ?",
                [(i, kind) for i in ids],
            )
        return len(ids)

    return int(db.run_write(_write, label="knowledge_fetch_clear") or 0)


def parked_ids(db: Any, kind: str, *, now: Optional[float] = None) -> Set[int]:
    """Item ids currently parked (backoff or exhausted) for *kind*."""
    t = _clock(now)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT item_id FROM knowledge_fetch_state
            WHERE kind = ?
              AND ((exhausted = 1 AND last_attempt_at > ?)
                   OR (exhausted = 0 AND next_retry_at > ?))
            """,
            (kind, t - EXHAUSTED_RECHECK_SECONDS, t),
        ).fetchall()
    return {int(r["item_id"]) for r in rows}


def list_exhausted(
    db: Any,
    kind: Optional[str] = None,
    *,
    limit: int = 100,
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Titles whose automatic retrieval gave up — the only real "exceptions"."""
    t = _clock(now)
    clauses = ["s.exhausted = 1", "s.last_attempt_at > ?"]
    params: List[Any] = [t - EXHAUSTED_RECHECK_SECONDS]
    if kind:
        clauses.append("s.kind = ?")
        params.append(kind)
    params.append(max(1, min(int(limit), 1000)))
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT s.item_id, s.kind, s.attempts, s.last_outcome, s.last_detail,
                   s.last_attempt_at, li.title, li.tmdb_id, li.media_type
            FROM knowledge_fetch_state s
            JOIN library_items li ON li.id = s.item_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.last_attempt_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return [dict(r) for r in rows]


def gap_is_open(db: Any, kind: str, item_id: int) -> bool:
    """True when the knowledge for *item_id* is still actually missing."""
    with db.connect() as conn:
        if kind == KIND_SYNOPSIS:
            row = conn.execute(
                "SELECT 1 FROM library_items WHERE id = ? "
                "AND TRIM(COALESCE(long_synopsis, '')) = ''",
                (int(item_id),),
            ).fetchone()
        elif kind == KIND_METADATA:
            row = conn.execute(
                f"SELECT 1 FROM library_items WHERE id = ? AND {db._METADATA_ENRICHMENT_WHERE}",
                (int(item_id),),
            ).fetchone()
        elif kind == KIND_EMBEDDING:
            row = conn.execute(
                "SELECT 1 FROM library_items li WHERE li.id = ? "
                "AND NOT EXISTS (SELECT 1 FROM embeddings e WHERE e.item_id = li.id)",
                (int(item_id),),
            ).fetchone()
        else:
            return False
    return row is not None


@dataclass
class FetchRunTracker:
    """Per-run bookkeeping shared by the retrieval tasks.

    Feed it one outcome per title. It decides what counts as a strike against
    the title, when the upstream looks unhealthy (breaker), and flushes the
    ledger once at the end of the run.

    Strike rules:

    * ``success``      → ledger cleared.
    * ``miss``         → upstream answered with nothing: a miss strike.
    * ``hard``         → upstream says the id is unknown: exhausted at once.
    * transient error  → remembered; only becomes an error strike if the run
      also saw the upstream answer *and* the breaker never tripped. Otherwise the
      title is merely deferred (the run was blocked, not the title).
    * ``auth`` error   → trips the breaker immediately; never blames titles.
    """

    db: Any
    kind: str
    now: Optional[float] = None
    breaker_threshold: int = BREAKER_THRESHOLD
    reachable: bool = False
    tripped: bool = False
    trip_reason: str = ""
    streak: int = 0
    successes: List[int] = field(default_factory=list)
    transient: List[Tuple[int, str]] = field(default_factory=list)
    newly_exhausted: List[Dict[str, Any]] = field(default_factory=list)
    misses: int = 0
    errors: int = 0

    def success(self, item_id: int) -> None:
        self.reachable = True
        self.streak = 0
        self.successes.append(int(item_id))

    def miss(self, item_id: int, detail: str = "no result") -> None:
        self.reachable = True
        self.streak = 0
        self.misses += 1
        state = record_failure(self.db, item_id, self.kind, OUTCOME_MISS, detail, now=self.now)
        if state["exhausted"]:
            self.newly_exhausted.append(state)

    def error(self, item_id: int, exc: BaseException) -> bool:
        """Record an exception. Returns True when the run should stop."""
        self.errors += 1
        category = classify_error(exc)
        detail = str(exc)[:300]
        if category == "hard":
            self.reachable = True
            self.streak = 0
            state = record_failure(self.db, item_id, self.kind, OUTCOME_HARD, detail, now=self.now)
            self.newly_exhausted.append(state)
            return False
        self.transient.append((int(item_id), detail))
        if category == "auth":
            self.tripped = True
            self.trip_reason = "upstream rejected our credentials"
            return True
        self.streak += 1
        if self.streak >= self.breaker_threshold:
            self.tripped = True
            self.trip_reason = f"{self.streak} consecutive upstream errors"
            return True
        return False

    def finish(self) -> Dict[str, Any]:
        """Flush the ledger. Safe to call exactly once, even when interrupted."""
        if self.successes:
            clear(self.db, self.successes, self.kind)
        if self.transient:
            if self.reachable and not self.tripped:
                for item_id, detail in self.transient:
                    state = record_failure(
                        self.db, item_id, self.kind, OUTCOME_ERROR, detail, now=self.now
                    )
                    if state["exhausted"]:
                        self.newly_exhausted.append(state)
            else:
                defer(self.db, [i for i, _ in self.transient], self.kind, now=self.now)
        self.transient = []
        self.successes = []
        return {
            "breaker_tripped": self.tripped,
            "breaker_reason": self.trip_reason,
            "misses": self.misses,
            "errors": self.errors,
            "newly_exhausted": len(self.newly_exhausted),
        }


def exceptions_summary(db: Any, kinds: Sequence[str] = tuple(sorted(AUTO_RETRIEVED_KINDS))) -> Dict[str, int]:
    """Counts of exhausted titles by kind (for diagnostics)."""
    out: Dict[str, int] = {}
    for kind in kinds:
        out[kind] = len(list_exhausted(db, kind, limit=1000))
    return out
