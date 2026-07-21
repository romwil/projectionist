"""Facets, plot text, and library counts.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import sqlite3
from typing import (
    Dict,
    List,
    Sequence,
    Tuple,
)

from ._shared import (
    run_with_db_lock_retry,
)


class LibraryQueryMixin:
    def replace_facets_of_type(
        self,
        facet_type: str,
        rows: Sequence[Tuple[int, str, str]],
    ) -> int:
        """Replace all facets of one type (e.g. motif) without touching other types."""
        cleaned_type = str(facet_type or "").strip().lower()
        if not cleaned_type:
            return 0
        normalized = [
            (int(item_id), cleaned_type, str(value).strip())
            for item_id, _ftype, value in rows
            if str(value or "").strip()
        ]

        def _write() -> int:
            with self.connect() as conn:
                conn.execute(
                    "DELETE FROM library_facets WHERE facet_type = ?",
                    (cleaned_type,),
                )
                if normalized:
                    conn.executemany(
                        """
                        INSERT INTO library_facets (item_id, facet_type, facet_value)
                        VALUES (?, ?, ?)
                        """,
                        normalized,
                    )
            return len(normalized)

        return run_with_db_lock_retry(_write, label="replace_facets_of_type")

    def facet_values_for_items(
        self,
        item_ids: Sequence[int],
        facet_type: str,
    ) -> Dict[int, List[str]]:
        """Return ``item_id → [facet_value, ...]`` for one facet type."""
        ids = [int(i) for i in item_ids if i is not None]
        cleaned_type = str(facet_type or "").strip().lower()
        out: Dict[int, List[str]] = {i: [] for i in ids}
        if not ids or not cleaned_type:
            return out
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT item_id, facet_value
                FROM library_facets
                WHERE facet_type = ?
                  AND item_id IN ({placeholders})
                ORDER BY facet_value ASC
                """,
                (cleaned_type, *ids),
            ).fetchall()
        for row in rows:
            item_id = int(row["item_id"])
            value = str(row["facet_value"] or "").strip()
            if value and item_id in out:
                out[item_id].append(value)
        return out

    def plot_text_for_items(self, item_ids: Sequence[int]) -> Dict[int, str]:
        """Return ``item_id → layered plot text`` for motif Why? / hybrid match excerpts."""
        ids = [int(i) for i in item_ids if i is not None]
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
            overview_select = (
                "tmdb_overview" if "tmdb_overview" in cols else "'' AS tmdb_overview"
            )
            tagline_select = "tagline" if "tagline" in cols else "'' AS tagline"
            logline_select = (
                "llm_logline" if "llm_logline" in cols else "'' AS llm_logline"
            )
            synopsis_select = (
                "long_synopsis" if "long_synopsis" in cols else "'' AS long_synopsis"
            )
            rows = conn.execute(
                f"""
                SELECT id, summary, {overview_select}, {tagline_select},
                       {logline_select}, {synopsis_select}
                FROM library_items
                WHERE id IN ({placeholders})
                """,
                ids,
            ).fetchall()
        out: Dict[int, str] = {}
        for row in rows:
            parts = [
                str(row["summary"] or "").strip(),
                str(row["tmdb_overview"] or "").strip(),
                str(row["tagline"] or "").strip(),
                str(row["long_synopsis"] or "").strip(),
                str(row["llm_logline"] or "").strip(),
            ]
            out[int(row["id"])] = "\n".join(part for part in parts if part)
        return out

    def credit_person_ids_by_item(self, item_ids: Sequence[int]) -> Dict[int, set[int]]:
        """Map library item_id → set of local people.id for Jaccard surprise scoring."""
        ids = [int(i) for i in item_ids if i is not None]
        if not ids:
            return {}
        out: Dict[int, set[int]] = {i: set() for i in ids}
        placeholders = ", ".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT item_id, person_id FROM credits
                WHERE item_id IN ({placeholders})
                """,
                ids,
            ).fetchall()
        for row in rows:
            out.setdefault(int(row["item_id"]), set()).add(int(row["person_id"]))
        return out

    def embedding_content_hashes(self) -> Dict[int, str]:
        """Return item_id → content_hash for rows that have a stored hash."""
        with self.connect() as conn:
            cols = self._table_columns(conn, "embeddings")
            if "content_hash" not in cols:
                return {}
            rows = conn.execute(
                """
                SELECT item_id, content_hash FROM embeddings
                WHERE content_hash IS NOT NULL AND content_hash != ''
                """
            ).fetchall()
            return {int(row["item_id"]): str(row["content_hash"]) for row in rows}

    def library_counts(self) -> Dict[str, int]:
        with self.connect() as conn:
            movies = conn.execute(
                "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'movie'"
            ).fetchone()["cnt"]
            shows = conn.execute(
                "SELECT COUNT(*) AS cnt FROM library_items WHERE media_type = 'show'"
            ).fetchone()["cnt"]
            total = conn.execute("SELECT COUNT(*) AS cnt FROM library_items").fetchone()["cnt"]
            return {"movies": int(movies), "shows": int(shows), "items": int(total)}

    def all_library_items(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM library_items ORDER BY title").fetchall()
            return list(rows)

