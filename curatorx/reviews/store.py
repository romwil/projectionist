"""Personal title reviews and rating prompt queue."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.connectors.plex import normalize_stars
from curatorx.library.db import Database
from curatorx.models.schemas import PreferenceSignal
from curatorx.preferences.store import remember_preference

COMPLETION_THRESHOLD = 85.0
RE_PROMPT_COOLDOWN_SECONDS = 30 * 86400


def _completion_pct(view_offset_ms: Optional[int], duration_ms: Optional[int]) -> Optional[float]:
    if not view_offset_ms or not duration_ms or duration_ms <= 0:
        return None
    return min(100.0, (float(view_offset_ms) / float(duration_ms)) * 100.0)


def _row_to_review(row: Mapping[str, Any]) -> Dict[str, Any]:
    tags_raw = row["review_tags"] if "review_tags" in row.keys() else "[]"
    try:
        tags = json.loads(str(tags_raw or "[]"))
    except json.JSONDecodeError:
        tags = []
    if not isinstance(tags, list):
        tags = []
    return {
        "id": str(row["id"]),
        "rating_key": str(row["rating_key"]) if row["rating_key"] is not None else None,
        "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
        "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
        "media_type": str(row["media_type"]),
        "title": str(row["title"]),
        "stars": float(row["stars"]) if row["stars"] is not None else None,
        "review_text": str(row["review_text"] or ""),
        "review_tags": [str(tag) for tag in tags],
        "prompted_by": str(row["prompted_by"] or "user"),
        "session_id": str(row["session_id"]) if row["session_id"] is not None else None,
        "lens_id": str(row["lens_id"]) if row["lens_id"] is not None else None,
        "plex_rating_synced": bool(int(row["plex_rating_synced"] or 0)),
        "plex_synced_at": float(row["plex_synced_at"]) if row["plex_synced_at"] is not None else None,
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def _row_to_prompt(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "rating_key": str(row["rating_key"]),
        "media_type": str(row["media_type"]),
        "title": str(row["title"]),
        "completion_pct": float(row["completion_pct"]),
        "detected_at": float(row["detected_at"]),
        "prompted_at": float(row["prompted_at"]) if row["prompted_at"] is not None else None,
        "dismissed_at": float(row["dismissed_at"]) if row["dismissed_at"] is not None else None,
        "review_id": str(row["review_id"]) if row["review_id"] is not None else None,
    }


def _can_queue_prompt(conn, rating_key: str, *, now: float) -> bool:
    review = conn.execute(
        "SELECT 1 FROM user_title_reviews WHERE rating_key = ?",
        (rating_key,),
    ).fetchone()
    if review is not None:
        return False

    existing = conn.execute(
        "SELECT dismissed_at FROM rating_prompt_queue WHERE rating_key = ?",
        (rating_key,),
    ).fetchone()
    if existing is not None and existing["dismissed_at"] is not None:
        dismissed_at = float(existing["dismissed_at"])
        if now - dismissed_at < RE_PROMPT_COOLDOWN_SECONDS:
            return False
    return True


def _upsert_prompt(
    conn,
    *,
    rating_key: str,
    media_type: str,
    title: str,
    completion_pct: float,
    now: float,
) -> None:
    prompt_id = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO rating_prompt_queue (
            id, rating_key, media_type, title, completion_pct, detected_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(rating_key) DO UPDATE SET
            media_type=excluded.media_type,
            title=excluded.title,
            completion_pct=excluded.completion_pct,
            detected_at=excluded.detected_at,
            dismissed_at=NULL,
            review_id=NULL
        """,
        (prompt_id, rating_key, media_type, title, completion_pct, now),
    )


def _tautulli_completion_pct(metadata: Mapping[str, Any]) -> Optional[float]:
    view_offset = metadata.get("view_offset")
    if view_offset is None:
        view_offset = metadata.get("viewOffset")
    duration = metadata.get("duration")
    if view_offset is None or duration is None:
        return None
    try:
        view_ms = int(view_offset)
        duration_ms = int(duration)
    except (TypeError, ValueError):
        return None
    return _completion_pct(view_ms, duration_ms)


def queue_rating_prompt(
    db: Database,
    *,
    rating_key: str,
    media_type: str,
    title: str,
    completion_pct: float,
) -> bool:
    """Insert or refresh a near-completion rating prompt. Returns True if queued."""
    now = time.time()
    with db.connect() as conn:
        if not _can_queue_prompt(conn, rating_key, now=now):
            return False
        _upsert_prompt(
            conn,
            rating_key=rating_key,
            media_type=media_type,
            title=title,
            completion_pct=completion_pct,
            now=now,
        )
    return True


def mark_prompts_surfaced(db: Database, prompt_ids: List[str]) -> int:
    """Set prompted_at when review prompts are shown in chat."""
    ids = [str(prompt_id).strip() for prompt_id in prompt_ids if str(prompt_id).strip()]
    if not ids:
        return 0
    now = time.time()
    placeholders = ", ".join("?" for _ in ids)
    with db.connect() as conn:
        cursor = conn.execute(
            f"""
            UPDATE rating_prompt_queue
            SET prompted_at = ?
            WHERE id IN ({placeholders})
              AND prompted_at IS NULL
              AND dismissed_at IS NULL
            """,
            [now, *ids],
        )
    return int(cursor.rowcount)


def scan_for_rating_prompts(db: Database, settings: Optional[Settings] = None) -> int:
    """Detect near-complete watches and enqueue rating prompts."""
    now = time.time()
    queued = 0
    queued_keys: set[str] = set()
    tautulli_client = None
    if settings and settings.tautulli_url and settings.tautulli_api_key:
        try:
            from curatorx.connectors.tautulli import TautulliClient

            tautulli_client = TautulliClient(settings.tautulli_url, settings.tautulli_api_key)
        except Exception:
            tautulli_client = None

    def _try_queue(
        conn,
        *,
        rating_key: str,
        media_type: str,
        title: str,
        completion_pct: float,
    ) -> bool:
        nonlocal queued
        if rating_key in queued_keys:
            return False
        if not _can_queue_prompt(conn, rating_key, now=now):
            return False
        _upsert_prompt(
            conn,
            rating_key=rating_key,
            media_type=media_type,
            title=title,
            completion_pct=completion_pct,
            now=now,
        )
        queued_keys.add(rating_key)
        queued += 1
        return True

    with db.connect() as conn:
        movie_rows = conn.execute(
            """
            SELECT rating_key, media_type, title, view_offset_ms, duration_ms
            FROM library_items
            WHERE media_type = 'movie'
              AND rating_key IS NOT NULL AND rating_key != ''
              AND view_offset_ms IS NOT NULL AND view_offset_ms > 0
              AND duration_ms IS NOT NULL AND duration_ms > 0
            """
        ).fetchall()
        for row in movie_rows:
            rating_key = str(row["rating_key"])
            pct = _completion_pct(row["view_offset_ms"], row["duration_ms"])
            if (pct is None or pct < COMPLETION_THRESHOLD) and tautulli_client is not None:
                try:
                    metadata = tautulli_client.get_metadata(rating_key)
                    pct = _tautulli_completion_pct(metadata)
                except RuntimeError:
                    pct = None
            if pct is None or pct < COMPLETION_THRESHOLD:
                continue
            _try_queue(
                conn,
                rating_key=rating_key,
                media_type=str(row["media_type"]),
                title=str(row["title"]),
                completion_pct=pct,
            )

        episode_rows = conn.execute(
            """
            SELECT
                e.rating_key,
                e.season_number,
                e.episode_number,
                e.view_offset_ms,
                e.duration_ms,
                s.title AS show_title,
                s.media_type
            FROM library_episodes e
            JOIN library_items s ON s.id = e.show_item_id
            WHERE e.rating_key IS NOT NULL AND e.rating_key != ''
              AND e.view_offset_ms IS NOT NULL AND e.view_offset_ms > 0
              AND e.duration_ms IS NOT NULL AND e.duration_ms > 0
            """
        ).fetchall()
        for row in episode_rows:
            rating_key = str(row["rating_key"])
            pct = _completion_pct(row["view_offset_ms"], row["duration_ms"])
            if (pct is None or pct < COMPLETION_THRESHOLD) and tautulli_client is not None:
                try:
                    metadata = tautulli_client.get_metadata(rating_key)
                    pct = _tautulli_completion_pct(metadata)
                except RuntimeError:
                    pct = None
            if pct is None or pct < COMPLETION_THRESHOLD:
                continue
            season = int(row["season_number"] or 0)
            episode = int(row["episode_number"] or 0)
            title = f"{row['show_title']} — S{season:02d}E{episode:02d}"
            _try_queue(
                conn,
                rating_key=rating_key,
                media_type=str(row["media_type"]),
                title=title,
                completion_pct=pct,
            )

        if tautulli_client is not None:
            tautulli_rows = conn.execute(
                """
                SELECT rating_key, media_type, title, view_offset_ms, duration_ms
                FROM library_items
                WHERE media_type = 'movie'
                  AND rating_key IS NOT NULL AND rating_key != ''
                  AND (
                    view_offset_ms IS NULL OR view_offset_ms <= 0
                    OR duration_ms IS NULL OR duration_ms <= 0
                  )
                """
            ).fetchall()
            for row in tautulli_rows:
                rating_key = str(row["rating_key"])
                if rating_key in queued_keys:
                    continue
                try:
                    metadata = tautulli_client.get_metadata(rating_key)
                    pct = _tautulli_completion_pct(metadata)
                except RuntimeError:
                    continue
                if pct is None or pct < COMPLETION_THRESHOLD:
                    continue
                _try_queue(
                    conn,
                    rating_key=rating_key,
                    media_type=str(row["media_type"]),
                    title=str(row["title"]),
                    completion_pct=pct,
                )
    return queued


def save_review(
    db: Database,
    *,
    stars: float | int,
    title: str,
    media_type: str,
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    review_text: str = "",
    review_tags: Optional[List[str]] = None,
    prompted_by: str = "user",
    session_id: Optional[str] = None,
    lens_id: Optional[str] = None,
    prompt_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    stars = normalize_stars(stars)

    now = time.time()
    tags = review_tags or []
    review_id = uuid.uuid4().hex

    with db.connect() as conn:
        existing = None
        if rating_key:
            if user_id is None:
                existing = conn.execute(
                    "SELECT id FROM user_title_reviews WHERE rating_key = ?",
                    (rating_key,),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT id FROM user_title_reviews
                    WHERE rating_key = ? AND (user_id = ? OR user_id IS NULL)
                    ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END
                    LIMIT 1
                    """,
                    (rating_key, user_id, user_id),
                ).fetchone()
        if existing is None and tmdb_id is not None:
            if user_id is None:
                existing = conn.execute(
                    "SELECT id FROM user_title_reviews WHERE tmdb_id = ? AND media_type = ?",
                    (tmdb_id, media_type),
                ).fetchone()
            else:
                existing = conn.execute(
                    """
                    SELECT id FROM user_title_reviews
                    WHERE tmdb_id = ? AND media_type = ?
                      AND (user_id = ? OR user_id IS NULL)
                    ORDER BY CASE WHEN user_id = ? THEN 0 ELSE 1 END
                    LIMIT 1
                    """,
                    (tmdb_id, media_type, user_id, user_id),
                ).fetchone()

        if existing is not None:
            review_id = str(existing["id"])
            conn.execute(
                """
                UPDATE user_title_reviews
                SET stars = ?,
                    review_text = ?,
                    review_tags = ?,
                    prompted_by = ?,
                    session_id = ?,
                    lens_id = ?,
                    title = ?,
                    rating_key = COALESCE(?, rating_key),
                    tmdb_id = COALESCE(?, tmdb_id),
                    tvdb_id = COALESCE(?, tvdb_id),
                    user_id = COALESCE(user_id, ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    stars,
                    review_text,
                    json.dumps(tags),
                    prompted_by,
                    session_id,
                    lens_id,
                    title,
                    rating_key,
                    tmdb_id,
                    tvdb_id,
                    user_id,
                    now,
                    review_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_title_reviews (
                    id, rating_key, tmdb_id, tvdb_id, media_type, title,
                    stars, review_text, review_tags, prompted_by,
                    session_id, lens_id, created_at, updated_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    rating_key,
                    tmdb_id,
                    tvdb_id,
                    media_type,
                    title,
                    stars,
                    review_text,
                    json.dumps(tags),
                    prompted_by,
                    session_id,
                    lens_id,
                    now,
                    now,
                    user_id,
                ),
            )

        if prompt_id:
            conn.execute(
                """
                UPDATE rating_prompt_queue
                SET review_id = ?, prompted_at = ?, dismissed_at = NULL
                WHERE id = ?
                """,
                (review_id, now, prompt_id),
            )
        elif rating_key:
            conn.execute(
                """
                UPDATE rating_prompt_queue
                SET review_id = ?, prompted_at = ?
                WHERE rating_key = ? AND dismissed_at IS NULL
                """,
                (review_id, now, rating_key),
            )

        row = conn.execute(
            "SELECT * FROM user_title_reviews WHERE id = ?",
            (review_id,),
        ).fetchone()

    saved = _row_to_review(row)

    preference_bits = []
    if review_text.strip():
        preference_bits.append(review_text.strip())
    if tags:
        preference_bits.append(", ".join(tags))
    if preference_bits:
        remember_preference(
            db,
            PreferenceSignal(
                signal_type="explicit",
                text=f"Rated {title} {stars}/5: {' — '.join(preference_bits)}",
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                media_type=media_type,  # type: ignore[arg-type]
                lens_id=lens_id,
            ),
            user_id=user_id,
        )

    return saved


def get_reviews(
    db: Database,
    *,
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
    title: Optional[str] = None,
    min_stars: Optional[int] = None,
    limit: int = 50,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if user_id is not None:
        clauses.append("(user_id = ? OR user_id IS NULL)")
        params.append(user_id)
    if rating_key:
        clauses.append("rating_key = ?")
        params.append(rating_key)
    if tmdb_id is not None:
        clauses.append("tmdb_id = ?")
        params.append(tmdb_id)
    if media_type:
        clauses.append("media_type = ?")
        params.append(media_type)
    if title:
        clauses.append("title LIKE ?")
        params.append(f"%{title}%")
    if min_stars is not None:
        clauses.append("stars >= ?")
        params.append(min_stars)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))

    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM user_title_reviews
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_review(row) for row in rows]


def list_pending_prompts(db: Database, *, limit: int = 10) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM rating_prompt_queue
            WHERE dismissed_at IS NULL
              AND review_id IS NULL
            ORDER BY completion_pct DESC, detected_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 50)),),
        ).fetchall()
    return [_row_to_prompt(row) for row in rows]


def list_titles_to_rate(db: Database, *, limit: int = 10) -> List[Dict[str, Any]]:
    """Return near-complete prompts plus recently viewed unrated library titles."""
    capped = max(1, min(int(limit or 10), 50))
    suggestions: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    for prompt in list_pending_prompts(db, limit=capped):
        rating_key = str(prompt["rating_key"])
        seen_keys.add(rating_key)
        suggestions.append(
            {
                "id": str(prompt["id"]),
                "title": prompt["title"],
                "rating_key": rating_key,
                "media_type": prompt["media_type"],
                "completion_pct": prompt.get("completion_pct"),
                "poster_url": None,
                "reason": "near_complete",
            }
        )

    if len(suggestions) >= capped:
        return suggestions[:capped]

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT rating_key, media_type, title, view_count, last_viewed_at, poster_url
            FROM library_items
            WHERE view_count > 0
              AND rating_key IS NOT NULL AND rating_key != ''
              AND rating_key NOT IN (
                  SELECT rating_key FROM user_title_reviews
                  WHERE rating_key IS NOT NULL
              )
            ORDER BY last_viewed_at DESC
            LIMIT ?
            """,
            (capped,),
        ).fetchall()

    for row in rows:
        rating_key = str(row["rating_key"])
        if rating_key in seen_keys:
            continue
        seen_keys.add(rating_key)
        suggestions.append(
            {
                "id": f"viewed-unrated-{rating_key}",
                "title": str(row["title"]),
                "rating_key": rating_key,
                "media_type": str(row["media_type"]),
                "completion_pct": 100.0,
                "poster_url": str(row["poster_url"]) if row["poster_url"] else None,
                "view_count": int(row["view_count"] or 0),
                "reason": "watched_no_review",
            }
        )
        if len(suggestions) >= capped:
            break
    return suggestions[:capped]


def dismiss_prompt(db: Database, prompt_id: str) -> Dict[str, Any]:
    now = time.time()
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM rating_prompt_queue WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Prompt not found")
        conn.execute(
            "UPDATE rating_prompt_queue SET dismissed_at = ? WHERE id = ?",
            (now, prompt_id),
        )
        row = conn.execute(
            "SELECT * FROM rating_prompt_queue WHERE id = ?",
            (prompt_id,),
        ).fetchone()
    return _row_to_prompt(row)
