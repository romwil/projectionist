"""Library item upserts, people/credits, enrichment queues.

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
)

from ._shared import (
    run_with_db_lock_retry,
)


class LibraryItemsMixin:
    def _library_item_params(self, item: Mapping[str, Any], now: float) -> tuple:
        return (
            item.get("rating_key"),
            item["media_type"],
            item["title"],
            item.get("year"),
            item.get("summary", ""),
            json.dumps(item.get("genres", [])),
            json.dumps(item.get("cast", [])),
            json.dumps(item.get("directors", [])),
            json.dumps(item.get("keywords", [])),
            item.get("tmdb_id"),
            item.get("tvdb_id"),
            item.get("imdb_id"),
            item.get("poster_url", ""),
            item.get("backdrop_url", ""),
            item.get("view_count", 0),
            item.get("added_at"),
            item.get("last_viewed_at"),
            item.get("file_size", 0),
            int(bool(item.get("in_radarr"))),
            int(bool(item.get("in_sonarr"))),
            item.get("runtime_minutes"),
            item.get("content_rating", ""),
            item.get("vote_average"),
            item.get("original_language", ""),
            json.dumps(item.get("countries", [])),
            item.get("season_count"),
            item.get("leaf_count"),
            item.get("viewed_leaf_count"),
            item.get("unwatched_episode_count", 0),
            item.get("total_episode_count", 0),
            item.get("last_episode_watched_at"),
            item.get("last_episode_sync_at"),
            item.get("view_offset_ms"),
            item.get("duration_ms"),
            item.get("plex_user_rating_stars"),
            item.get("release_date") or None,
            item.get("first_air_date") or None,
            item.get("last_air_date") or None,
            item.get("tmdb_collection_id"),
            item.get("collection_name", "") or "",
            item.get("status", "") or "",
            json.dumps(item.get("networks", [])),
            json.dumps(item.get("production_companies", [])),
            item.get("tmdb_overview", "") or "",
            item.get("tagline", "") or "",
            item.get("llm_logline", "") or "",
            now,
        )

    _UPSERT_LIBRARY_ITEM_SQL = """
                INSERT INTO library_items (
                    rating_key, media_type, title, year, summary, genres, cast, directors,
                    keywords, tmdb_id, tvdb_id, imdb_id, poster_url, backdrop_url,
                    view_count, added_at, last_viewed_at, file_size, in_radarr, in_sonarr,
                    runtime_minutes, content_rating, vote_average, original_language, countries,
                    season_count, leaf_count, viewed_leaf_count,
                    unwatched_episode_count, total_episode_count,
                    last_episode_watched_at, last_episode_sync_at, view_offset_ms, duration_ms,
                    plex_user_rating_stars,
                    release_date, first_air_date, last_air_date,
                    tmdb_collection_id, collection_name, status,
                    networks, production_companies,
                    tmdb_overview, tagline, llm_logline,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    media_type=excluded.media_type,
                    title=excluded.title,
                    year=excluded.year,
                    summary=excluded.summary,
                    genres=excluded.genres,
                    cast=excluded.cast,
                    directors=excluded.directors,
                    keywords=excluded.keywords,
                    tmdb_id=excluded.tmdb_id,
                    tvdb_id=excluded.tvdb_id,
                    imdb_id=excluded.imdb_id,
                    poster_url=excluded.poster_url,
                    backdrop_url=excluded.backdrop_url,
                    view_count=excluded.view_count,
                    added_at=COALESCE(excluded.added_at, library_items.added_at),
                    last_viewed_at=excluded.last_viewed_at,
                    file_size=excluded.file_size,
                    in_radarr=excluded.in_radarr,
                    in_sonarr=excluded.in_sonarr,
                    runtime_minutes=excluded.runtime_minutes,
                    content_rating=excluded.content_rating,
                    vote_average=COALESCE(excluded.vote_average, library_items.vote_average),
                    original_language=CASE
                        WHEN excluded.original_language != '' THEN excluded.original_language
                        ELSE library_items.original_language
                    END,
                    countries=CASE
                        WHEN excluded.countries != '[]' THEN excluded.countries
                        ELSE library_items.countries
                    END,
                    season_count=excluded.season_count,
                    leaf_count=excluded.leaf_count,
                    viewed_leaf_count=excluded.viewed_leaf_count,
                    unwatched_episode_count=excluded.unwatched_episode_count,
                    total_episode_count=excluded.total_episode_count,
                    last_episode_watched_at=excluded.last_episode_watched_at,
                    last_episode_sync_at=excluded.last_episode_sync_at,
                    view_offset_ms=excluded.view_offset_ms,
                    duration_ms=excluded.duration_ms,
                    plex_user_rating_stars=excluded.plex_user_rating_stars,
                    release_date=COALESCE(excluded.release_date, library_items.release_date),
                    first_air_date=COALESCE(excluded.first_air_date, library_items.first_air_date),
                    last_air_date=COALESCE(excluded.last_air_date, library_items.last_air_date),
                    tmdb_collection_id=COALESCE(
                        excluded.tmdb_collection_id, library_items.tmdb_collection_id
                    ),
                    collection_name=CASE
                        WHEN excluded.collection_name != '' THEN excluded.collection_name
                        ELSE library_items.collection_name
                    END,
                    status=CASE
                        WHEN excluded.status != '' THEN excluded.status
                        ELSE library_items.status
                    END,
                    networks=CASE
                        WHEN excluded.networks != '[]' THEN excluded.networks
                        ELSE library_items.networks
                    END,
                    production_companies=CASE
                        WHEN excluded.production_companies != '[]' THEN excluded.production_companies
                        ELSE library_items.production_companies
                    END,
                    tmdb_overview=CASE
                        WHEN excluded.tmdb_overview != '' THEN excluded.tmdb_overview
                        ELSE library_items.tmdb_overview
                    END,
                    tagline=CASE
                        WHEN excluded.tagline != '' THEN excluded.tagline
                        ELSE library_items.tagline
                    END,
                    llm_logline=CASE
                        WHEN excluded.llm_logline != '' THEN excluded.llm_logline
                        ELSE library_items.llm_logline
                    END,
                    updated_at=excluded.updated_at
                """

    def _upsert_library_item_on_conn(
        self, conn: sqlite3.Connection, item: Mapping[str, Any], *, now: Optional[float] = None
    ) -> int:
        stamp = time.time() if now is None else now
        conn.execute(self._UPSERT_LIBRARY_ITEM_SQL, self._library_item_params(item, stamp))
        row = conn.execute(
            "SELECT id FROM library_items WHERE rating_key = ?",
            (item.get("rating_key"),),
        ).fetchone()
        return int(row["id"]) if row else 0

    def upsert_library_item(self, item: Mapping[str, Any]) -> int:
        def _write() -> int:
            with self.connect() as conn:
                item_id = self._upsert_library_item_on_conn(conn, item)
                structured = item.get("structured_credits")
                if structured is not None and item_id:
                    self._upsert_credits_for_item_on_conn(conn, item_id, structured)
                return item_id

        return run_with_db_lock_retry(_write, label="upsert_library_item")

    def upsert_library_items(self, items: Sequence[Mapping[str, Any]]) -> List[int]:
        """Upsert many library rows in a single transaction (one commit).

        When an item mapping includes ``structured_credits`` (list of credit dicts
        from TMDB), those rows are dual-written into ``people`` / ``credits`` after
        the library row upsert — same transaction.
        """
        if not items:
            return []

        def _write() -> List[int]:
            now = time.time()
            ids: List[int] = []
            with self.connect() as conn:
                for item in items:
                    item_id = self._upsert_library_item_on_conn(conn, item, now=now)
                    ids.append(item_id)
                    structured = item.get("structured_credits")
                    if structured is not None and item_id:
                        self._upsert_credits_for_item_on_conn(conn, item_id, structured)
            return ids

        return run_with_db_lock_retry(_write, label="upsert_library_items")

    def upsert_person(
        self,
        *,
        tmdb_person_id: int,
        name: str,
        profile_url: str = "",
    ) -> int:
        """Insert or update a TMDB person; returns local ``people.id``."""

        def _write() -> int:
            with self.connect() as conn:
                return self._upsert_person_on_conn(
                    conn,
                    tmdb_person_id=tmdb_person_id,
                    name=name,
                    profile_url=profile_url,
                )

        return run_with_db_lock_retry(_write, label="upsert_person")

    def _upsert_person_on_conn(
        self,
        conn: sqlite3.Connection,
        *,
        tmdb_person_id: int,
        name: str,
        profile_url: str = "",
    ) -> int:
        now = time.time()
        conn.execute(
            """
            INSERT INTO people (tmdb_person_id, name, profile_url, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tmdb_person_id) DO UPDATE SET
                name=excluded.name,
                profile_url=CASE
                    WHEN excluded.profile_url != '' THEN excluded.profile_url
                    ELSE people.profile_url
                END
            """,
            (int(tmdb_person_id), str(name or "").strip() or "Unknown", profile_url or "", now),
        )
        row = conn.execute(
            "SELECT id FROM people WHERE tmdb_person_id = ?",
            (int(tmdb_person_id),),
        ).fetchone()
        return int(row["id"]) if row else 0

    def upsert_credits_for_item(
        self,
        item_id: int,
        credits: Sequence[Mapping[str, Any]],
    ) -> int:
        """Replace all credits for ``item_id`` with ``credits``; returns row count."""

        def _write() -> int:
            with self.connect() as conn:
                return self._upsert_credits_for_item_on_conn(conn, item_id, credits)

        return run_with_db_lock_retry(_write, label="upsert_credits_for_item")

    def _upsert_credits_for_item_on_conn(
        self,
        conn: sqlite3.Connection,
        item_id: int,
        credits: Sequence[Mapping[str, Any]],
    ) -> int:
        conn.execute("DELETE FROM credits WHERE item_id = ?", (int(item_id),))
        written = 0
        for entry in credits:
            tmdb_person_id = entry.get("tmdb_person_id")
            if tmdb_person_id is None:
                continue
            try:
                person_tmdb = int(tmdb_person_id)
            except (TypeError, ValueError):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            person_id = self._upsert_person_on_conn(
                conn,
                tmdb_person_id=person_tmdb,
                name=name,
                profile_url=str(entry.get("profile_url") or ""),
            )
            if not person_id:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO credits (
                    item_id, person_id, department, job, character, billing_order
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(item_id),
                    person_id,
                    str(entry.get("department") or ""),
                    str(entry.get("job") or ""),
                    str(entry.get("character") or ""),
                    int(entry.get("billing_order") or 0),
                ),
            )
            written += 1
        return written

    def list_credits_for_item(self, item_id: int) -> List[sqlite3.Row]:
        """Return credits for a library item joined with person identity."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        c.item_id,
                        c.person_id,
                        c.department,
                        c.job,
                        c.character,
                        c.billing_order,
                        p.tmdb_person_id,
                        p.name,
                        p.profile_url
                    FROM credits c
                    JOIN people p ON p.id = c.person_id
                    WHERE c.item_id = ?
                    ORDER BY c.billing_order ASC, p.name ASC
                    """,
                    (int(item_id),),
                ).fetchall()
            )

    def list_library_titles_for_person(
        self,
        *,
        person_id: Optional[int] = None,
        tmdb_person_id: Optional[int] = None,
    ) -> List[sqlite3.Row]:
        """In-library titles linked to a person (by local id or TMDB person id)."""
        if person_id is None and tmdb_person_id is None:
            return []
        with self.connect() as conn:
            if person_id is not None:
                return list(
                    conn.execute(
                        """
                        SELECT DISTINCT
                            li.*,
                            c.department,
                            c.job,
                            c.character,
                            c.billing_order
                        FROM credits c
                        JOIN library_items li ON li.id = c.item_id
                        WHERE c.person_id = ?
                        ORDER BY li.year DESC, li.title ASC
                        """,
                        (int(person_id),),
                    ).fetchall()
                )
            return list(
                conn.execute(
                    """
                    SELECT DISTINCT
                        li.*,
                        c.department,
                        c.job,
                        c.character,
                        c.billing_order
                    FROM credits c
                    JOIN people p ON p.id = c.person_id
                    JOIN library_items li ON li.id = c.item_id
                    WHERE p.tmdb_person_id = ?
                    ORDER BY li.year DESC, li.title ASC
                    """,
                    (int(tmdb_person_id),),  # type: ignore[arg-type]
                ).fetchall()
            )

    _METADATA_ENRICHMENT_WHERE = """
        tmdb_id IS NOT NULL
        AND (
          (media_type = 'movie' AND (release_date IS NULL OR release_date = ''))
          OR (media_type = 'show' AND (first_air_date IS NULL OR first_air_date = ''))
          OR tmdb_overview IS NULL OR tmdb_overview = ''
        )
    """

    def items_needing_metadata_enrichment(self, *, limit: int = 25) -> List[sqlite3.Row]:
        """Library rows with a TMDB id but missing dates and/or plot text (trickle backlog)."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    f"""
                    SELECT id, rating_key, media_type, title, tmdb_id,
                           release_date, first_air_date, last_air_date,
                           tmdb_overview, tagline
                    FROM library_items
                    WHERE {self._METADATA_ENRICHMENT_WHERE}
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
            )

    def count_items_needing_metadata_enrichment(self) -> int:
        """Count titles still waiting on the metadata enrichment trickle."""
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM library_items WHERE {self._METADATA_ENRICHMENT_WHERE}"
            ).fetchone()
            return int(row["cnt"] if row else 0)

