"""Library item lookups, *arr presence/queue, facets/FTS, episodes.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from ._shared import (
    run_with_db_lock_retry,
)


class LibraryLookupMixin:
    def library_item_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM library_items WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type),
            ).fetchone()

    def library_item_by_rating_key(self, rating_key: str) -> Optional[sqlite3.Row]:
        key = str(rating_key or "").strip()
        if not key:
            return None
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM library_items WHERE rating_key = ?",
                (key,),
            ).fetchone()

    def library_item_by_id(self, item_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM library_items WHERE id = ?",
                (item_id,),
            ).fetchone()

    def library_item_by_tvdb(self, tvdb_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM library_items WHERE tvdb_id = ? AND media_type = 'show'",
                (tvdb_id,),
            ).fetchone()

    def library_item_by_title(self, title: str, *, media_type: Optional[str] = None) -> Optional[sqlite3.Row]:
        pattern = f"%{title.strip().lower()}%"
        with self.connect() as conn:
            if media_type:
                return conn.execute(
                    """
                    SELECT * FROM library_items
                    WHERE lower(title) LIKE ? AND media_type = ?
                    ORDER BY length(title) ASC
                    LIMIT 1
                    """,
                    (pattern, media_type),
                ).fetchone()
            return conn.execute(
                """
                SELECT * FROM library_items
                WHERE lower(title) LIKE ?
                ORDER BY length(title) ASC
                LIMIT 1
                """,
                (pattern,),
            ).fetchone()

    def library_shows(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM library_items WHERE media_type = 'show' ORDER BY title"
                ).fetchall()
            )

    def update_library_item_rating_key(self, show_id: int, rating_key: str) -> bool:
        key = str(rating_key or "").strip()
        if not key:
            return False
        now = time.time()
        with self.connect() as conn:
            conflict = conn.execute(
                """
                SELECT id FROM library_items
                WHERE rating_key = ? AND id != ?
                """,
                (key, show_id),
            ).fetchone()
            if conflict:
                return False
            cursor = conn.execute(
                """
                UPDATE library_items
                SET rating_key = ?, updated_at = ?
                WHERE id = ?
                """,
                (key, now, show_id),
            )
            return cursor.rowcount > 0

    def set_arr_presence(
        self,
        *,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        in_radarr: Optional[bool] = None,
        in_sonarr: Optional[bool] = None,
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            if tmdb_id is not None and in_radarr is not None:
                cursor = conn.execute(
                    """
                    UPDATE library_items
                    SET in_radarr = ?, updated_at = ?
                    WHERE tmdb_id = ? AND media_type = 'movie'
                    """,
                    (int(bool(in_radarr)), now, tmdb_id),
                )
                return int(cursor.rowcount)
            if tvdb_id is not None and in_sonarr is not None:
                cursor = conn.execute(
                    """
                    UPDATE library_items
                    SET in_sonarr = ?, updated_at = ?
                    WHERE tvdb_id = ? AND media_type = 'show'
                    """,
                    (int(bool(in_sonarr)), now, tvdb_id),
                )
                return int(cursor.rowcount)
        return 0

    def record_arr_queue(
        self,
        *,
        media_type: str,
        source: str,
        title: str = "",
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Remember a confirmed Radarr/Sonarr/Seerr add so gap tools won't re-pitch it."""
        if tmdb_id is None and tvdb_id is None:
            return
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM arr_queued_titles
                WHERE media_type = ?
                  AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                  AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                """,
                (
                    media_type,
                    int(tmdb_id) if tmdb_id is not None else None,
                    int(tvdb_id) if tvdb_id is not None else None,
                ),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    """
                    UPDATE arr_queued_titles
                    SET title = COALESCE(NULLIF(?, ''), title),
                        source = ?,
                        session_id = COALESCE(?, session_id),
                        queued_at = ?
                    WHERE id = ?
                    """,
                    (str(title or ""), str(source or ""), session_id, now, str(existing["id"])),
                )
                return
            conn.execute(
                """
                INSERT INTO arr_queued_titles (
                    id, media_type, tmdb_id, tvdb_id, title, source, session_id, queued_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    media_type,
                    int(tmdb_id) if tmdb_id is not None else None,
                    int(tvdb_id) if tvdb_id is not None else None,
                    str(title or ""),
                    str(source or ""),
                    session_id,
                    now,
                ),
            )

    def queued_tmdb_ids(self, media_type: str = "movie") -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tmdb_id FROM arr_queued_titles
                WHERE media_type = ? AND tmdb_id IS NOT NULL
                """,
                (media_type,),
            ).fetchall()
            return {int(row["tmdb_id"]) for row in rows}

    def queued_tvdb_ids(self) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tvdb_id FROM arr_queued_titles
                WHERE media_type = 'show' AND tvdb_id IS NOT NULL
                """
            ).fetchall()
            return {int(row["tvdb_id"]) for row in rows}

    def list_recent_arr_queue(self, *, limit: int = 40) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT media_type, tmdb_id, tvdb_id, title, source, session_id, queued_at
                FROM arr_queued_titles
                ORDER BY queued_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit or 40), 100)),),
            ).fetchall()
        return [
            {
                "media_type": str(row["media_type"]),
                "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
                "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
                "title": str(row["title"] or ""),
                "source": str(row["source"] or ""),
                "session_id": str(row["session_id"]) if row["session_id"] is not None else None,
                "queued_at": float(row["queued_at"]),
            }
            for row in rows
        ]

    def is_arr_queued(
        self,
        *,
        media_type: str,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
    ) -> bool:
        clauses: List[str] = ["media_type = ?"]
        params: List[Any] = [media_type]
        if tmdb_id is not None:
            clauses.append("tmdb_id = ?")
            params.append(int(tmdb_id))
        elif tvdb_id is not None:
            clauses.append("tvdb_id = ?")
            params.append(int(tvdb_id))
        else:
            return False
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT 1 FROM arr_queued_titles WHERE {' AND '.join(clauses)} LIMIT 1",
                params,
            ).fetchone()
        return row is not None

    def clear_library_facets(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM library_facets")

    def add_library_facet(self, item_id: int, facet_type: str, facet_value: str) -> None:
        cleaned = str(facet_value or "").strip()
        if not cleaned:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_facets (item_id, facet_type, facet_value)
                VALUES (?, ?, ?)
                """,
                (item_id, facet_type, cleaned),
            )

    def replace_library_facets(self, rows: Sequence[Tuple[int, str, str]]) -> int:
        """Bulk-replace sync-managed facets; preserve idle-derived types like ``motif``."""

        def _write() -> int:
            with self.connect() as conn:
                # Motifs/themes come from idle tasks — do not wipe them on sync rebuild.
                conn.execute(
                    "DELETE FROM library_facets WHERE facet_type NOT IN ('motif', 'theme')"
                )
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO library_facets (item_id, facet_type, facet_value)
                        VALUES (?, ?, ?)
                        """,
                        rows,
                    )
            return len(rows)

        return run_with_db_lock_retry(_write, label="replace_library_facets")

    def clear_library_fts(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM library_fts")

    def upsert_library_fts_row(
        self,
        item_id: int,
        title: str,
        summary: str,
        cast_text: str,
        directors_text: str,
        keywords_text: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO library_fts (
                    item_id, title, summary, cast_text, directors_text, keywords_text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item_id, title, summary, cast_text, directors_text, keywords_text),
            )

    def replace_library_fts(self, rows: Sequence[Tuple[int, str, str, str, str, str]]) -> int:
        """Delete all FTS rows and bulk-insert ``rows`` in a single transaction."""

        def _write() -> int:
            with self.connect() as conn:
                conn.execute("DELETE FROM library_fts")
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO library_fts (
                            item_id, title, summary, cast_text, directors_text, keywords_text
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
            return len(rows)

        return run_with_db_lock_retry(_write, label="replace_library_fts")

    _UPSERT_LIBRARY_EPISODE_SQL = """
                INSERT INTO library_episodes (
                    show_item_id, rating_key, season_number, episode_number, title,
                    runtime_minutes, view_count, last_viewed_at, file_size, aired_at,
                    view_offset_ms, duration_ms, plex_user_rating_stars
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    show_item_id=excluded.show_item_id,
                    season_number=excluded.season_number,
                    episode_number=excluded.episode_number,
                    title=excluded.title,
                    runtime_minutes=excluded.runtime_minutes,
                    view_count=excluded.view_count,
                    last_viewed_at=excluded.last_viewed_at,
                    file_size=excluded.file_size,
                    aired_at=excluded.aired_at,
                    view_offset_ms=excluded.view_offset_ms,
                    duration_ms=excluded.duration_ms,
                    plex_user_rating_stars=excluded.plex_user_rating_stars
                """

    @staticmethod
    def _library_episode_params(episode: Mapping[str, Any]) -> tuple:
        return (
            episode["show_item_id"],
            episode.get("rating_key"),
            episode.get("season_number"),
            episode.get("episode_number"),
            episode.get("title", ""),
            episode.get("runtime_minutes"),
            episode.get("view_count", 0),
            episode.get("last_viewed_at"),
            episode.get("file_size", 0),
            episode.get("aired_at"),
            episode.get("view_offset_ms"),
            episode.get("duration_ms"),
            episode.get("plex_user_rating_stars"),
        )

    def delete_episodes_for_show(self, show_item_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM library_episodes WHERE show_item_id = ?", (show_item_id,))

    def upsert_library_episode(self, episode: Mapping[str, Any]) -> int:
        with self.connect() as conn:
            conn.execute(self._UPSERT_LIBRARY_EPISODE_SQL, self._library_episode_params(episode))
            row = conn.execute(
                "SELECT id FROM library_episodes WHERE rating_key = ?",
                (episode.get("rating_key"),),
            ).fetchone()
            return int(row["id"]) if row else 0

    def upsert_library_episodes(self, episodes: Sequence[Mapping[str, Any]]) -> int:
        """Upsert many episode rows in a single transaction (one commit)."""
        if not episodes:
            return 0

        def _write() -> int:
            with self.connect() as conn:
                conn.executemany(
                    self._UPSERT_LIBRARY_EPISODE_SQL,
                    [self._library_episode_params(episode) for episode in episodes],
                )
            return len(episodes)

        return run_with_db_lock_retry(_write, label="upsert_library_episodes")

    def replace_library_episodes_for_show(
        self,
        show_item_id: int,
        episodes: Sequence[Mapping[str, Any]],
    ) -> int:
        """Delete a show's episodes, upsert replacements, and refresh rollups in one commit."""

        def _write() -> int:
            with self.connect() as conn:
                conn.execute(
                    "DELETE FROM library_episodes WHERE show_item_id = ?",
                    (show_item_id,),
                )
                if episodes:
                    conn.executemany(
                        self._UPSERT_LIBRARY_EPISODE_SQL,
                        [self._library_episode_params(episode) for episode in episodes],
                    )
                self._update_show_episode_rollups_on_conn(conn, show_item_id)
            return len(episodes)

        return run_with_db_lock_retry(_write, label="replace_library_episodes_for_show")

    def show_episode_view_counts(self, show_item_id: int) -> Tuple[int, int]:
        """Return (total_episodes, viewed_episodes) for incremental sync checks."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN COALESCE(view_count, 0) > 0 THEN 1 ELSE 0 END) AS viewed
                FROM library_episodes
                WHERE show_item_id = ?
                """,
                (show_item_id,),
            ).fetchone()
        return int(row["total"] or 0), int(row["viewed"] or 0)

    def _update_show_episode_rollups_on_conn(
        self, conn: sqlite3.Connection, show_item_id: int
    ) -> None:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN view_count IS NULL OR view_count = 0 THEN 1 ELSE 0 END) AS unwatched,
                MAX(last_viewed_at) AS last_watched
            FROM library_episodes
            WHERE show_item_id = ?
            """,
            (show_item_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE library_items
            SET total_episode_count = ?,
                unwatched_episode_count = ?,
                last_episode_watched_at = ?,
                last_episode_sync_at = ?
            WHERE id = ?
            """,
            (
                int(row["total"] or 0),
                int(row["unwatched"] or 0),
                row["last_watched"],
                time.time(),
                show_item_id,
            ),
        )

    def update_show_episode_rollups(self, show_item_id: int) -> None:
        with self.connect() as conn:
            self._update_show_episode_rollups_on_conn(conn, show_item_id)

    def owned_tmdb_ids(self, media_type: str) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT tmdb_id FROM library_items WHERE media_type = ? AND tmdb_id IS NOT NULL",
                (media_type,),
            ).fetchall()
            return {int(r["tmdb_id"]) for r in rows}

    def owned_tvdb_ids(self) -> set[int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT tvdb_id FROM library_items WHERE media_type = 'show' AND tvdb_id IS NOT NULL"
            ).fetchall()
            return {int(r["tvdb_id"]) for r in rows}

    def search_keyword(self, query: str, *, limit: int = 20) -> List[sqlite3.Row]:
        pattern = f"%{query.lower()}%"
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM library_items
                    WHERE lower(title) LIKE ? OR lower(summary) LIKE ? OR lower(genres) LIKE ?
                    ORDER BY view_count DESC, title
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit),
                ).fetchall()
            )

    def get_embeddings(self) -> List[Tuple[int, List[float]]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT item_id, vector FROM embeddings"
            ).fetchall()
            return [(int(r["item_id"]), json.loads(r["vector"])) for r in rows]

