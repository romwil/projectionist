"""Optional sqlite-vec ANN prefilter for neighbor rebuild / semantic search.

Default Docker / Unraid installs do **not** require the extension. When the
``sqlite-vec`` package (or a loadable ``vec0`` extension) is unavailable —
or when ``PROJECTIONIST_SQLITE_VEC=0`` (or legacy ``CURATORX_SQLITE_VEC=0``) —
callers fall back to full exact cosine scans. ``item_neighbors`` remains the
UI/agent read cache either way.
"""

from __future__ import annotations

import logging
import os
import struct
from typing import Any, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

VEC_TABLE = "vec_embeddings"
# Env: unset/empty = auto (use when package loads); 0/false/off = force off; 1/true/on = prefer on.
_ENV_FLAG = "PROJECTIONIST_SQLITE_VEC"

_capability_cache: Optional[dict[str, Any]] = None


def _env_prefers_vec() -> bool:
    from projectionist.envcompat import resolve_env

    raw = (resolve_env(_ENV_FLAG) or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    return True


def _serialize_f32(vector: Sequence[float]) -> bytes:
    values = [float(x) for x in vector]
    return struct.pack(f"{len(values)}f", *values)


def reset_vec_capability_cache() -> None:
    """Test helper — clear memoized capability probe."""
    global _capability_cache
    _capability_cache = None


def vec_capability() -> dict[str, Any]:
    """Return capability status (memoized for the process).

    Keys: ``available`` (bool), ``reason`` (str), ``version`` (optional str).
    """
    global _capability_cache
    if _capability_cache is not None:
        return dict(_capability_cache)

    if not _env_prefers_vec():
        _capability_cache = {
            "available": False,
            "reason": f"{_ENV_FLAG}=0 (disabled)",
            "version": None,
        }
        return dict(_capability_cache)

    try:
        import sqlite_vec  # type: ignore[import-untyped]
    except ImportError:
        _capability_cache = {
            "available": False,
            "reason": "sqlite-vec package not installed",
            "version": None,
        }
        return dict(_capability_cache)

    import sqlite3

    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            row = conn.execute("SELECT vec_version()").fetchone()
            version = str(row[0]) if row else ""
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — capability probe must never raise
        _capability_cache = {
            "available": False,
            "reason": f"sqlite-vec load failed: {exc}",
            "version": None,
        }
        return dict(_capability_cache)

    _capability_cache = {
        "available": True,
        "reason": "ok",
        "version": version,
    }
    return dict(_capability_cache)


def vec_available() -> bool:
    return bool(vec_capability().get("available"))


def load_vec_on_connection(conn: Any) -> bool:
    """Load sqlite-vec onto an open connection. Returns False on any failure."""
    if not vec_available():
        return False
    try:
        import sqlite_vec  # type: ignore[import-untyped]

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:
        logger.debug("sqlite-vec load on connection failed", exc_info=True)
        return False


def _detect_dims(embeddings: Sequence[Tuple[int, Sequence[float]]]) -> int:
    for _, vector in embeddings:
        if vector:
            return len(vector)
    return 0


def ensure_vec_index(
    db: Any,
    embeddings: Sequence[Tuple[int, Sequence[float]]],
) -> bool:
    """Create/rebuild the shadow ``vec_embeddings`` table from JSON embeddings.

    Returns True when the index is ready for ANN queries. Never raises for
    missing extension — returns False instead.
    """
    if not embeddings or not vec_available():
        return False
    dims = _detect_dims(embeddings)
    if dims <= 0:
        return False

    try:
        with db.connect() as conn:
            if not load_vec_on_connection(conn):
                return False
            # Drop + recreate keeps dims aligned after embedding-model changes.
            conn.execute(f"DROP TABLE IF EXISTS {VEC_TABLE}")
            conn.execute(
                f"CREATE VIRTUAL TABLE {VEC_TABLE} USING vec0(embedding float[{dims}])"
            )
            for item_id, vector in embeddings:
                if not vector or len(vector) != dims:
                    continue
                conn.execute(
                    f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (?, ?)",
                    (int(item_id), _serialize_f32(vector)),
                )
        return True
    except Exception:
        logger.warning("sqlite-vec index rebuild failed; falling back to exact scan", exc_info=True)
        return False


def ann_candidate_ids(
    db: Any,
    query_vector: Sequence[float],
    *,
    limit: int = 200,
    exclude_ids: Optional[set[int]] = None,
    embeddings: Optional[Sequence[Tuple[int, Sequence[float]]]] = None,
) -> Optional[List[int]]:
    """Return ANN-prefiltered item ids, or ``None`` when vec is unavailable.

    When ``None``, callers must scan all embeddings with exact cosine.
    Pass ``embeddings`` to (re)build the shadow index before querying.
    """
    if not query_vector or not vec_available():
        return None
    capped = max(1, min(int(limit or 200), 2000))
    if embeddings is not None and not ensure_vec_index(db, embeddings):
        return None

    try:
        with db.connect() as conn:
            if not load_vec_on_connection(conn):
                return None
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'virtual') AND name=?",
                (VEC_TABLE,),
            ).fetchone()
            if exists is None:
                return None
            rows = conn.execute(
                f"""
                SELECT rowid
                FROM {VEC_TABLE}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (_serialize_f32(query_vector), capped),
            ).fetchall()
    except Exception:
        logger.debug("sqlite-vec ANN query failed; falling back to exact scan", exc_info=True)
        return None

    exclude = exclude_ids or set()
    out: List[int] = []
    for row in rows:
        item_id = int(row[0])
        if item_id in exclude:
            continue
        out.append(item_id)
    return out
