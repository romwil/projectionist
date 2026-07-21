"""Embeddings, neighbors, relations, loglines, and synopses.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import (
    Any,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from ._shared import (
    run_with_db_lock_retry,
)


class EnrichmentMixin:
    def set_embedding(self, item_id: int, vector: Sequence[float]) -> None:
        self.set_embeddings([(item_id, vector)])

    def set_embeddings(
        self,
        items: Sequence[Tuple[int, Sequence[float]]] | Sequence[Tuple[int, Sequence[float], str]],
        *,
        embedding_model: str = "",
    ) -> None:
        """Write many embedding vectors in a single transaction.

        Each item is ``(item_id, vector)`` or ``(item_id, vector, content_hash)``.
        ``embedding_model`` records which model produced the batch (empty keeps prior).
        """
        if not items:
            return

        model = str(embedding_model or "").strip()
        normalized: list[Tuple[int, str, Optional[str], str]] = []
        for entry in items:
            if len(entry) == 3:
                item_id, vector, content_hash = entry  # type: ignore[misc]
                normalized.append(
                    (int(item_id), json.dumps(list(vector)), str(content_hash or "") or None, model)
                )
            else:
                item_id, vector = entry  # type: ignore[misc]
                normalized.append((int(item_id), json.dumps(list(vector)), None, model))

        def _write() -> None:
            with self.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO embeddings (item_id, vector, content_hash, embedding_model)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        vector = excluded.vector,
                        content_hash = COALESCE(excluded.content_hash, embeddings.content_hash),
                        embedding_model = CASE
                            WHEN excluded.embedding_model != '' THEN excluded.embedding_model
                            ELSE embeddings.embedding_model
                        END
                    """,
                    normalized,
                )

        run_with_db_lock_retry(_write, label="set_embeddings")

    def set_neighbors(
        self,
        item_id: int,
        neighbors: Sequence[Tuple[int, float, float]],
    ) -> None:
        """Replace neighbor rows for ``item_id``.

        Each neighbor is ``(neighbor_id, score, surprise_score)``.
        """
        seed = int(item_id)
        rows = [
            (seed, int(neighbor_id), float(score), float(surprise_score))
            for neighbor_id, score, surprise_score in neighbors
            if int(neighbor_id) != seed
        ]

        def _write() -> None:
            with self.connect() as conn:
                conn.execute("DELETE FROM item_neighbors WHERE item_id = ?", (seed,))
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO item_neighbors (item_id, neighbor_id, score, surprise_score)
                        VALUES (?, ?, ?, ?)
                        """,
                        rows,
                    )

        run_with_db_lock_retry(_write, label="set_neighbors")

    def get_neighbors(
        self,
        item_id: int,
        *,
        mode: str = "similar",
        limit: int = 20,
    ) -> List[sqlite3.Row]:
        """Return cached neighbors ordered by cosine (``similar``) or surprise score."""
        capped = min(max(1, int(limit or 20)), 100)
        order_col = "surprise_score" if str(mode or "").strip().lower() == "surprising" else "score"
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"""
                    SELECT
                        n.item_id,
                        n.neighbor_id,
                        n.score,
                        n.surprise_score,
                        li.id,
                        li.rating_key,
                        li.media_type,
                        li.title,
                        li.year,
                        li.poster_url,
                        li.backdrop_url,
                        li.tmdb_id,
                        li.tvdb_id,
                        li.summary,
                        li.genres,
                        li.view_count,
                        li.view_offset_ms,
                        li.duration_ms,
                        li.unwatched_episode_count,
                        li.total_episode_count,
                        li.in_radarr,
                        li.in_sonarr,
                        li.runtime_minutes
                    FROM item_neighbors n
                    JOIN library_items li ON li.id = n.neighbor_id
                    WHERE n.item_id = ?
                    ORDER BY n.{order_col} DESC
                    LIMIT ?
                    """,
                    (int(item_id), capped),
                ).fetchall()
            )

    def replace_relations_of_types(
        self,
        by_type: Mapping[str, Sequence[Tuple[int, int, str, float, str]]],
    ) -> int:
        """Replace all rows for the given relation types in one transaction."""

        def _write() -> int:
            total = 0
            with self.connect() as conn:
                for relation, rows in by_type.items():
                    cleaned = str(relation or "").strip().lower()
                    if not cleaned:
                        continue
                    conn.execute(
                        "DELETE FROM title_relations WHERE relation = ?",
                        (cleaned,),
                    )
                    normalized = [
                        (
                            int(from_id),
                            int(to_id),
                            cleaned,
                            float(weight),
                            str(source or ""),
                        )
                        for from_id, to_id, _rel, weight, source in rows
                        if int(from_id) != int(to_id)
                    ]
                    if normalized:
                        conn.executemany(
                            """
                            INSERT INTO title_relations
                                (from_id, to_id, relation, weight, source)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(from_id, to_id, relation) DO UPDATE SET
                                weight = excluded.weight,
                                source = excluded.source
                            """,
                            normalized,
                        )
                    total += len(normalized)
            return total

        return run_with_db_lock_retry(_write, label="replace_relations_of_types")

    def list_title_relations(
        self,
        item_id: int,
        *,
        relation: Optional[str] = None,
        limit: int = 25,
    ) -> List[sqlite3.Row]:
        """Outgoing relations from ``item_id``, joined to the related title."""
        capped = min(max(1, int(limit or 25)), 100)
        params: list[Any] = [int(item_id)]
        relation_clause = ""
        if relation:
            relation_clause = "AND r.relation = ?"
            params.append(str(relation).strip().lower())
        params.append(capped)
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"""
                    SELECT
                        r.from_id,
                        r.to_id,
                        r.relation,
                        r.weight,
                        r.source,
                        li.id,
                        li.rating_key,
                        li.media_type,
                        li.title,
                        li.year,
                        li.poster_url,
                        li.backdrop_url,
                        li.tmdb_id,
                        li.tvdb_id
                    FROM title_relations r
                    JOIN library_items li ON li.id = r.to_id
                    WHERE r.from_id = ?
                    {relation_clause}
                    ORDER BY r.weight DESC, li.title ASC
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
            )

    _LLM_LOGLINE_WHERE = """
        (llm_logline IS NULL OR llm_logline = '')
        AND (
          (summary IS NOT NULL AND summary != '')
          OR (tmdb_overview IS NOT NULL AND tmdb_overview != '')
        )
    """

    def items_needing_llm_logline(self, *, limit: int = 10) -> List[sqlite3.Row]:
        """Rows with plot text but empty ``llm_logline`` (optional LLM enrichment backlog)."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"""
                    SELECT id, rating_key, media_type, title, year, summary,
                           tmdb_overview, tagline, llm_logline
                    FROM library_items
                    WHERE {self._LLM_LOGLINE_WHERE}
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
            )

    def count_items_needing_llm_logline(self) -> int:
        """Count titles still waiting on the LLM logline trickle."""
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM library_items WHERE {self._LLM_LOGLINE_WHERE}"
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def count_items_needing_embeddings(self) -> int:
        """Count titles with plot text that do not yet have an embedding row."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM library_items li
                WHERE TRIM(COALESCE(li.summary, '')) != ''
                  AND NOT EXISTS (
                    SELECT 1 FROM embeddings e WHERE e.item_id = li.id
                  )
                """
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def count_embeddings(self) -> int:
        """Count stored embedding vectors (used for neighbor full-pass ETA)."""
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM embeddings").fetchone()
            return int(row["cnt"] if row else 0)

    def count_items_missing_neighbors(self) -> int:
        """Count embedded titles that still have no ``item_neighbors`` rows.

        Used by ``plot_neighbors`` catch-up ETA — embeddings can be complete while
        the neighbor cache is still thin.
        """
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM embeddings e
                WHERE NOT EXISTS (
                    SELECT 1 FROM item_neighbors n WHERE n.item_id = e.item_id
                )
                """
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def item_ids_missing_neighbors(self, *, limit: int = 50) -> List[int]:
        """Return embedding item ids that still lack neighbor cache rows."""
        capped = max(1, int(limit))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.item_id AS item_id
                FROM embeddings e
                WHERE NOT EXISTS (
                    SELECT 1 FROM item_neighbors n WHERE n.item_id = e.item_id
                )
                ORDER BY e.item_id ASC
                LIMIT ?
                """,
                (capped,),
            ).fetchall()
            return [int(row["item_id"]) for row in rows]

    def set_llm_logline(self, item_id: int, logline: str) -> None:
        cleaned = str(logline or "").strip()
        if not cleaned:
            return

        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    """
                    UPDATE library_items
                    SET llm_logline = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (cleaned, time.time(), int(item_id)),
                )

        run_with_db_lock_retry(_write, label="set_llm_logline")

    _LONG_SYNOPSIS_WHERE = """
        (long_synopsis IS NULL OR long_synopsis = '')
        AND (
          (summary IS NOT NULL AND summary != '')
          OR (tmdb_overview IS NOT NULL AND tmdb_overview != '')
          OR title IS NOT NULL
        )
    """

    def items_needing_long_synopsis(self, *, limit: int = 10) -> List[sqlite3.Row]:
        """Rows still missing optional ``long_synopsis`` (Wikipedia/OMDb backlog)."""
        with self.connect() as conn:
            cols = self._table_columns(conn, "library_items")
            if "long_synopsis" not in cols:
                return []
            return list(
                conn.execute(
                    f"""
                    SELECT id, rating_key, media_type, title, year, imdb_id,
                           summary, tmdb_overview, tagline, long_synopsis, synopsis_source
                    FROM library_items
                    WHERE {self._LONG_SYNOPSIS_WHERE}
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
            )

    def count_items_needing_long_synopsis(self) -> int:
        """Count titles still waiting on the optional long-synopsis trickle."""
        with self.connect() as conn:
            cols = self._table_columns(conn, "library_items")
            if "long_synopsis" not in cols:
                return 0
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM library_items WHERE {self._LONG_SYNOPSIS_WHERE}"
            ).fetchone()
            return int(row["cnt"] if row else 0)

    def set_long_synopsis(self, item_id: int, synopsis: str, source: str) -> None:
        """Write optional long synopsis + provenance. Never clears existing non-empty text."""
        cleaned = str(synopsis or "").strip()
        provenance = str(source or "").strip().lower()
        if not cleaned or not provenance:
            return

        def _write() -> None:
            with self.connect() as conn:
                conn.execute(
                    """
                    UPDATE library_items
                    SET long_synopsis = CASE
                            WHEN long_synopsis IS NULL OR long_synopsis = ''
                            THEN ?
                            ELSE long_synopsis
                        END,
                        synopsis_source = CASE
                            WHEN synopsis_source IS NULL OR synopsis_source = ''
                            THEN ?
                            ELSE synopsis_source
                        END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (cleaned, provenance, time.time(), int(item_id)),
                )

        run_with_db_lock_retry(_write, label="set_long_synopsis")

