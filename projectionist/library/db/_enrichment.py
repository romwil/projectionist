"""Embeddings, neighbors, relations, loglines, and synopses.

Behavior-preserving split of the original ``projectionist.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``projectionist/library/db/__init__.py``.
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

        self.run_write(_write, label="set_embeddings")

    def set_neighbors(
        self,
        item_id: int,
        neighbors: Sequence[
            Tuple[int, float, float]
            | Tuple[int, float, float, int]
            | Tuple[int, float, float, int, Optional[str]]
        ],
    ) -> None:
        """Replace neighbor rows for ``item_id``.

        Each neighbor is ``(neighbor_id, score, surprise_score)`` or
        ``(neighbor_id, score, surprise_score, explainable[, plot_link_json])``.
        Cosine-only peers should pass ``explainable=0``.
        """
        seed = int(item_id)
        rows: list[Tuple[int, int, float, float, int, Optional[str]]] = []
        for entry in neighbors:
            neighbor_id = int(entry[0])
            if neighbor_id == seed:
                continue
            score = float(entry[1])
            surprise_score = float(entry[2])
            explainable = int(entry[3]) if len(entry) >= 4 else 0
            plot_link_json = (
                str(entry[4]).strip() or None
                if len(entry) >= 5 and entry[4] is not None
                else None
            )
            rows.append(
                (seed, neighbor_id, score, surprise_score, 1 if explainable else 0, plot_link_json)
            )

        def _write() -> None:
            with self.connect() as conn:
                cols = self._table_columns(conn, "item_neighbors")
                conn.execute("DELETE FROM item_neighbors WHERE item_id = ?", (seed,))
                if not rows:
                    return
                if "explainable" in cols:
                    conn.executemany(
                        """
                        INSERT INTO item_neighbors
                            (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                else:
                    conn.executemany(
                        """
                        INSERT INTO item_neighbors (item_id, neighbor_id, score, surprise_score)
                        VALUES (?, ?, ?, ?)
                        """,
                        [(r[0], r[1], r[2], r[3]) for r in rows],
                    )

        self.run_write(_write, label="set_neighbors")

    def remove_neighbor_edge(self, item_id: int, neighbor_id: int) -> bool:
        """Delete one cached neighbor edge. Returns True if a row was removed."""

        def _write() -> bool:
            with self.connect() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM item_neighbors
                    WHERE item_id = ? AND neighbor_id = ?
                    """,
                    (int(item_id), int(neighbor_id)),
                )
                return int(cursor.rowcount or 0) > 0

        return bool(self.run_write(_write, label="remove_neighbor_edge"))

    def get_neighbors(
        self,
        item_id: int,
        *,
        mode: str = "similar",
        limit: int = 20,
        explainable_only: bool = False,
    ) -> List[sqlite3.Row]:
        """Return cached neighbors ordered by cosine (``similar``) or surprise score.

        Pass ``explainable_only=True`` for More Like This / relations (named plot
        link only). Raw cosine rows remain available for annotate / diagnostics.
        """
        capped = min(max(1, int(limit or 20)), 100)
        order_col = "surprise_score" if str(mode or "").strip().lower() == "surprising" else "score"
        with self.connect() as conn:
            cols = self._table_columns(conn, "item_neighbors")
            has_explainable = "explainable" in cols
            explainable_select = (
                "n.explainable, n.plot_link_json," if has_explainable else "0 AS explainable, NULL AS plot_link_json,"
            )
            explainable_clause = ""
            if explainable_only and has_explainable:
                explainable_clause = "AND COALESCE(n.explainable, 0) = 1"
            elif explainable_only and not has_explainable:
                # Pre-migration schema cannot prove a named link — return nothing.
                return []
            return list(
                conn.execute(
                    f"""
                    SELECT
                        n.item_id,
                        n.neighbor_id,
                        n.score,
                        n.surprise_score,
                        {explainable_select}
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
                        li.tmdb_overview,
                        li.tagline,
                        li.long_synopsis,
                        li.llm_logline,
                        li.genres,
                        li.keywords,
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
                    {explainable_clause}
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
        """Replace all rows for the given relation types in one transaction.

        Only inserts edges whose ``from_id`` / ``to_id`` both exist in
        ``library_items`` so a full rebuild never trips FOREIGN KEY failures
        from stale neighbor/credit caches.
        """

        def _write() -> int:
            total = 0
            with self.connect() as conn:
                existing_ids = {
                    int(row["id"])
                    for row in conn.execute("SELECT id FROM library_items").fetchall()
                }
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
                        and int(from_id) in existing_ids
                        and int(to_id) in existing_ids
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

        return self.run_write(_write, label="replace_relations_of_types")

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

    def embedding_item_ids(self) -> List[int]:
        """Return stored embedding item ids, ascending — **without** decoding vectors.

        ``get_embeddings()`` JSON-decodes every vector; callers that only need the
        id set (e.g. the neighbor refresh rotation) must use this instead.
        """
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT item_id FROM embeddings ORDER BY item_id ASC"
            ).fetchall()
            return [int(row["item_id"]) for row in rows]

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

    def item_ids_needing_neighbor_explanation(self, *, limit: int = 50) -> List[int]:
        """Seeds with neighbor rows that have not been scored for explainability yet.

        After migration 57, legacy rows default to ``explainable=0`` with a NULL
        ``plot_link_json``. Annotating them is cheaper than a full cosine refresh.
        """
        capped = max(1, int(limit))
        with self.connect() as conn:
            cols = self._table_columns(conn, "item_neighbors")
            if "explainable" not in cols:
                return []
            rows = conn.execute(
                """
                SELECT DISTINCT n.item_id AS item_id
                FROM item_neighbors n
                WHERE EXISTS (
                    SELECT 1 FROM item_neighbors u
                    WHERE u.item_id = n.item_id AND u.plot_link_json IS NULL
                )
                ORDER BY n.item_id ASC
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

        self.run_write(_write, label="set_llm_logline")

    _LONG_SYNOPSIS_WHERE = """
        (long_synopsis IS NULL OR long_synopsis = '')
        AND (
          (summary IS NOT NULL AND summary != '')
          OR (tmdb_overview IS NOT NULL AND tmdb_overview != '')
          OR title IS NOT NULL
        )
    """

    def items_needing_long_synopsis(
        self, *, limit: int = 10, skip_parked: bool = True, now: Optional[float] = None
    ) -> List[sqlite3.Row]:
        """Rows still missing optional ``long_synopsis`` (Wikipedia/OMDb backlog).

        By default titles that are inside a retry backoff window, or whose retries
        are exhausted, are skipped so one stubborn title cannot starve the queue.
        """
        from projectionist.library.knowledge_fetch import KIND_SYNOPSIS, parked_sql

        park_sql, park_params = (
            parked_sql(KIND_SYNOPSIS, now=now) if skip_parked else ("", ())
        )
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
                    {park_sql}
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (*park_params, max(1, int(limit))),
                ).fetchall()
            )

    def count_items_needing_long_synopsis(
        self, *, include_exhausted: bool = False, now: Optional[float] = None
    ) -> int:
        """Count titles still waiting on the optional long-synopsis trickle.

        Titles whose automatic retrieval is exhausted are not "waiting" (they are
        owner-visible exceptions); pass ``include_exhausted=True`` for the raw gap.
        """
        from projectionist.library.knowledge_fetch import KIND_SYNOPSIS, exhausted_sql

        ex_sql, ex_params = (
            ("", ()) if include_exhausted else exhausted_sql(KIND_SYNOPSIS, now=now)
        )
        with self.connect() as conn:
            cols = self._table_columns(conn, "library_items")
            if "long_synopsis" not in cols:
                return 0
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM library_items "
                f"WHERE {self._LONG_SYNOPSIS_WHERE} {ex_sql}",
                tuple(ex_params),
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

        self.run_write(_write, label="set_long_synopsis")

