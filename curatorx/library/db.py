"""SQLite database for library index, chat, preferences, lenses, and embeddings."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterable, List, Mapping, Optional, Sequence, Tuple, TypeVar

DEFAULT_LENS_ID = "general"
DEFAULT_CONTEXT_HASH = "general"
DEFAULT_PERSONA_ID = "current_profile"
BOOTSTRAP_OWNER_ID = "bootstrap-owner"
ACTIVE_LENS_CONFIG_KEY = "active_lens_id"
ACTIVE_CONTEXT_CONFIG_KEY = "active_context_hash"
CURATOR_NAME_CONFIG_KEY = "curator_name"

# Busy wait before OperationalError on contended locks (Unraid volume latency).
SQLITE_BUSY_TIMEOUT_MS = 30_000
# WAL + NORMAL is durable enough for this app and much kinder under concurrent readers.
SQLITE_SYNCHRONOUS = "NORMAL"
SQLITE_LOCK_RETRIES = 6
SQLITE_LOCK_RETRY_BASE_DELAY_S = 0.05

logger = logging.getLogger(__name__)
T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rating_key TEXT UNIQUE,
    media_type TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    summary TEXT DEFAULT '',
    genres TEXT DEFAULT '[]',
    cast TEXT DEFAULT '[]',
    directors TEXT DEFAULT '[]',
    keywords TEXT DEFAULT '[]',
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    imdb_id TEXT,
    poster_url TEXT DEFAULT '',
    backdrop_url TEXT DEFAULT '',
    view_count INTEGER DEFAULT 0,
    added_at INTEGER,
    last_viewed_at INTEGER,
    file_size INTEGER DEFAULT 0,
    in_radarr INTEGER DEFAULT 0,
    in_sonarr INTEGER DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_library_tmdb ON library_items(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_library_tvdb ON library_items(tvdb_id);
CREATE INDEX IF NOT EXISTS idx_library_type ON library_items(media_type);
CREATE INDEX IF NOT EXISTS idx_library_year ON library_items(year);
CREATE INDEX IF NOT EXISTS idx_library_media_year ON library_items(media_type, year);

CREATE TABLE IF NOT EXISTS embeddings (
    item_id INTEGER PRIMARY KEY,
    vector TEXT NOT NULL,
    content_hash TEXT,
    FOREIGN KEY(item_id) REFERENCES library_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS preference_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL,
    text TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    media_type TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    lens_id TEXT NOT NULL DEFAULT 'general',
    thread_title TEXT DEFAULT 'New conversation',
    context_hash TEXT DEFAULT 'general'
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    blocks_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    lens_id TEXT NOT NULL DEFAULT 'general',
    FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pending_actions (
    token TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS curator_system_config (
    config_key TEXT PRIMARY KEY,
    config_value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_integrations (
    service_name TEXT PRIMARY KEY,
    base_url TEXT,
    api_token_encrypted TEXT,
    connection_status TEXT DEFAULT 'unverified',
    last_tested_at DATETIME,
    certified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS curator_persona_metrics (
    metric_id TEXT PRIMARY KEY DEFAULT 'current_profile',
    curator_name TEXT DEFAULT 'Curator',
    persona_identity TEXT DEFAULT '',
    val_bro_prof REAL DEFAULT 0.5,
    val_dipl_snark REAL DEFAULT 0.5,
    val_pass_auto REAL DEFAULT 0.5,
    persona_preset_id TEXT,
    persona_prompt_override TEXT,
    last_modified DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curation_lenses (
    lens_id TEXT PRIMARY KEY,
    lens_name TEXT NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lens_taste_profile (
    lens_id TEXT NOT NULL,
    cluster_tag TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    explicit_lock INTEGER DEFAULT 0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lens_id, cluster_tag),
    FOREIGN KEY (lens_id) REFERENCES curation_lenses(lens_id)
);

CREATE TABLE IF NOT EXISTS interaction_telemetry (
    id TEXT PRIMARY KEY,
    title_id TEXT NOT NULL,
    lens_id TEXT NOT NULL,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    watch_duration_seconds INTEGER DEFAULT 0,
    completion_percentage REAL DEFAULT 0.0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lens_id) REFERENCES curation_lenses(lens_id)
);

CREATE TABLE IF NOT EXISTS agent_blueprints (
    blueprint_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    cron_schedule TEXT NOT NULL,
    active_lens_id TEXT,
    instructions_json TEXT,
    is_enabled INTEGER DEFAULT 1,
    last_run_status TEXT,
    last_run_timestamp DATETIME,
    FOREIGN KEY (active_lens_id) REFERENCES curation_lenses(lens_id)
);

CREATE TABLE IF NOT EXISTS derived_contexts (
    context_hash TEXT PRIMARY KEY,
    inferred_label TEXT DEFAULT 'General Exploration',
    thematic_centroid_json TEXT,
    interaction_density INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_telemetry_stream (
    id TEXT PRIMARY KEY,
    media_node_id TEXT,
    associated_context_hash TEXT,
    event_class TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (associated_context_hash) REFERENCES derived_contexts(context_hash)
);

CREATE VIEW IF NOT EXISTS integration_profiles AS
SELECT
    service_name AS service_id,
    base_url AS endpoint_url,
    api_token_encrypted AS credential_encrypted,
    connection_status AS verification_state,
    last_tested_at AS synchronized_at
FROM service_integrations;
"""


def _is_db_locked(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    return "locked" in message or "busy" in message


def run_with_db_lock_retry(operation: Callable[[], T], *, label: str = "db") -> T:
    """Retry transient SQLite lock/busy errors with exponential backoff."""
    delay = SQLITE_LOCK_RETRY_BASE_DELAY_S
    last_exc: Optional[BaseException] = None
    for attempt in range(SQLITE_LOCK_RETRIES):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if not _is_db_locked(exc) or attempt >= SQLITE_LOCK_RETRIES - 1:
                raise
            logger.warning(
                "SQLite %s locked (attempt %s/%s); retrying in %.2fs: %s",
                label,
                attempt + 1,
                SQLITE_LOCK_RETRIES,
                delay,
                exc,
            )
            time.sleep(delay)
            delay = min(delay * 2, 1.5)
    assert last_exc is not None
    raise last_exc


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._bootstrap_owner_ready = False
        self._init_schema()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_chat_lens_columns(conn)
            self._migrate_chat_thread_columns(conn)
            self._migrate_service_integrations_certified(conn)
            self._migrate_phase3_tables(conn)
            self._migrate_persona_columns(conn)
            self._migrate_library_intelligence(conn)
            self._migrate_library_indexes(conn)
            self._migrate_phase0_tables(conn)
            self._migrate_multi_user_columns(conn)
            self._migrate_phase4_tables(conn)
            self._migrate_embeddings_content_hash(conn)
            self._seed_defaults(conn)

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def _migrate_chat_lens_columns(self, conn: sqlite3.Connection) -> None:
        session_cols = self._table_columns(conn, "chat_sessions")
        if "lens_id" not in session_cols:
            conn.execute(
                f"ALTER TABLE chat_sessions ADD COLUMN lens_id TEXT NOT NULL DEFAULT '{DEFAULT_LENS_ID}'"
            )
        message_cols = self._table_columns(conn, "chat_messages")
        if "lens_id" not in message_cols:
            conn.execute(
                f"ALTER TABLE chat_messages ADD COLUMN lens_id TEXT NOT NULL DEFAULT '{DEFAULT_LENS_ID}'"
            )
        conn.execute(
            "UPDATE chat_sessions SET lens_id = ? WHERE lens_id IS NULL OR lens_id = ''",
            (DEFAULT_LENS_ID,),
        )
        conn.execute(
            "UPDATE chat_messages SET lens_id = ? WHERE lens_id IS NULL OR lens_id = ''",
            (DEFAULT_LENS_ID,),
        )

    def _migrate_chat_thread_columns(self, conn: sqlite3.Connection) -> None:
        session_cols = self._table_columns(conn, "chat_sessions")
        if "thread_title" not in session_cols:
            conn.execute(
                "ALTER TABLE chat_sessions ADD COLUMN thread_title TEXT DEFAULT 'New conversation'"
            )
        if "context_hash" not in session_cols:
            conn.execute(
                f"ALTER TABLE chat_sessions ADD COLUMN context_hash TEXT DEFAULT '{DEFAULT_CONTEXT_HASH}'"
            )
        conn.execute(
            "UPDATE chat_sessions SET thread_title = 'New conversation' WHERE thread_title IS NULL OR thread_title = ''"
        )
        conn.execute(
            "UPDATE chat_sessions SET context_hash = ? WHERE context_hash IS NULL OR context_hash = ''",
            (DEFAULT_CONTEXT_HASH,),
        )

    def _migrate_service_integrations_certified(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, "service_integrations")
        if "certified" not in cols:
            conn.execute(
                "ALTER TABLE service_integrations ADD COLUMN certified INTEGER DEFAULT 0"
            )
            conn.execute(
                """
                UPDATE service_integrations
                SET certified = 1
                WHERE connection_status = 'verified'
                """
            )

    def _migrate_phase0_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL CHECK (role IN ('owner', 'member', 'guest')),
                plex_user_id TEXT UNIQUE,
                plex_token_enc TEXT,
                seerr_user_id INTEGER,
                seerr_permissions INTEGER,
                oidc_sub TEXT UNIQUE,
                avatar_url TEXT,
                created_at REAL NOT NULL,
                last_login_at REAL
            );

            CREATE TABLE IF NOT EXISTS message_feedback (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT,
                feedback_type TEXT NOT NULL CHECK (feedback_type IN ('helpful', 'not_helpful')),
                excerpt TEXT DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE(message_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_message_feedback_session ON message_feedback(session_id);
            """
        )

    def _migrate_library_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_library_year ON library_items(year)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_media_year ON library_items(media_type, year)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_library_added_at ON library_items(added_at)")

    def _migrate_library_intelligence(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, "library_items")
        new_columns = {
            "runtime_minutes": "INTEGER",
            "content_rating": "TEXT DEFAULT ''",
            "vote_average": "REAL",
            "original_language": "TEXT DEFAULT ''",
            "countries": "TEXT DEFAULT '[]'",
            "season_count": "INTEGER",
            "leaf_count": "INTEGER",
            "viewed_leaf_count": "INTEGER",
            "unwatched_episode_count": "INTEGER DEFAULT 0",
            "total_episode_count": "INTEGER DEFAULT 0",
            "last_episode_watched_at": "INTEGER",
            "last_episode_sync_at": "REAL",
            "added_at": "INTEGER",
        }
        for name, typedef in new_columns.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE library_items ADD COLUMN {name} {typedef}")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS library_facets (
                item_id INTEGER NOT NULL,
                facet_type TEXT NOT NULL,
                facet_value TEXT NOT NULL,
                FOREIGN KEY(item_id) REFERENCES library_items(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_facets_lookup ON library_facets(facet_type, facet_value);
            CREATE INDEX IF NOT EXISTS idx_facets_item ON library_facets(item_id);

            CREATE TABLE IF NOT EXISTS library_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                show_item_id INTEGER NOT NULL,
                rating_key TEXT UNIQUE,
                season_number INTEGER,
                episode_number INTEGER,
                title TEXT,
                runtime_minutes INTEGER,
                view_count INTEGER DEFAULT 0,
                last_viewed_at INTEGER,
                file_size INTEGER DEFAULT 0,
                aired_at TEXT,
                FOREIGN KEY(show_item_id) REFERENCES library_items(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_show ON library_episodes(show_item_id);
            CREATE INDEX IF NOT EXISTS idx_episodes_unwatched ON library_episodes(show_item_id, view_count);

            CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(
                item_id UNINDEXED,
                title,
                summary,
                cast_text,
                directors_text,
                keywords_text,
                tokenize='porter'
            );
            """
        )

    def _migrate_persona_columns(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, "curator_persona_metrics")
        if "persona_identity" not in cols:
            conn.execute(
                "ALTER TABLE curator_persona_metrics ADD COLUMN persona_identity TEXT DEFAULT ''"
            )
        if "persona_preset_id" not in cols:
            conn.execute(
                "ALTER TABLE curator_persona_metrics ADD COLUMN persona_preset_id TEXT"
            )
        if "persona_prompt_override" not in cols:
            conn.execute(
                "ALTER TABLE curator_persona_metrics ADD COLUMN persona_prompt_override TEXT"
            )

    def _migrate_multi_user_columns(self, conn: sqlite3.Connection) -> None:
        session_cols = self._table_columns(conn, "chat_sessions")
        if "user_id" not in session_cols:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN user_id TEXT REFERENCES users(id)")
        pending_cols = self._table_columns(conn, "pending_actions")
        if "user_id" not in pending_cols:
            conn.execute("ALTER TABLE pending_actions ADD COLUMN user_id TEXT")
        review_cols = self._table_columns(conn, "user_title_reviews")
        if review_cols and "user_id" not in review_cols:
            conn.execute("ALTER TABLE user_title_reviews ADD COLUMN user_id TEXT")
        pref_cols = self._table_columns(conn, "preference_facts")
        if pref_cols and "user_id" not in pref_cols:
            conn.execute("ALTER TABLE preference_facts ADD COLUMN user_id TEXT")

    def _migrate_embeddings_content_hash(self, conn: sqlite3.Connection) -> None:
        cols = self._table_columns(conn, "embeddings")
        if "content_hash" not in cols:
            conn.execute("ALTER TABLE embeddings ADD COLUMN content_hash TEXT")

    def _migrate_phase4_tables(self, conn: sqlite3.Connection) -> None:
        item_cols = self._table_columns(conn, "library_items")
        for name, typedef in {
            "view_offset_ms": "INTEGER",
            "duration_ms": "INTEGER",
            "plex_user_rating_stars": "INTEGER",
        }.items():
            if name not in item_cols:
                conn.execute(f"ALTER TABLE library_items ADD COLUMN {name} {typedef}")

        episode_cols = self._table_columns(conn, "library_episodes")
        for name, typedef in {
            "view_offset_ms": "INTEGER",
            "duration_ms": "INTEGER",
            "plex_user_rating_stars": "INTEGER",
        }.items():
            if name not in episode_cols:
                conn.execute(f"ALTER TABLE library_episodes ADD COLUMN {name} {typedef}")

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_title_reviews (
                id TEXT PRIMARY KEY,
                rating_key TEXT,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                stars INTEGER CHECK (stars BETWEEN 1 AND 5),
                review_text TEXT DEFAULT '',
                review_tags TEXT DEFAULT '[]',
                prompted_by TEXT DEFAULT 'user',
                session_id TEXT,
                lens_id TEXT,
                plex_rating_synced INTEGER DEFAULT 0,
                plex_synced_at REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_reviews_rating_key ON user_title_reviews(rating_key);
            CREATE INDEX IF NOT EXISTS idx_reviews_tmdb ON user_title_reviews(tmdb_id, media_type);

            CREATE TABLE IF NOT EXISTS rating_prompt_queue (
                id TEXT PRIMARY KEY,
                rating_key TEXT NOT NULL,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                completion_pct REAL NOT NULL,
                detected_at REAL NOT NULL,
                prompted_at REAL,
                dismissed_at REAL,
                review_id TEXT,
                UNIQUE(rating_key)
            );

            CREATE TABLE IF NOT EXISTS arr_queued_titles (
                id TEXT PRIMARY KEY,
                media_type TEXT NOT NULL,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                title TEXT DEFAULT '',
                source TEXT NOT NULL,
                session_id TEXT,
                queued_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_arr_queued_tmdb ON arr_queued_titles(tmdb_id, media_type);
            CREATE INDEX IF NOT EXISTS idx_arr_queued_tvdb ON arr_queued_titles(tvdb_id, media_type);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_arr_queued_identity ON arr_queued_titles(
                media_type,
                COALESCE(tmdb_id, -1),
                COALESCE(tvdb_id, -1)
            );
            """
        )

    def _migrate_phase3_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS derived_contexts (
                context_hash TEXT PRIMARY KEY,
                inferred_label TEXT DEFAULT 'General Exploration',
                thematic_centroid_json TEXT,
                interaction_density INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS system_telemetry_stream (
                id TEXT PRIMARY KEY,
                media_node_id TEXT,
                associated_context_hash TEXT,
                event_class TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (associated_context_hash) REFERENCES derived_contexts(context_hash)
            );

            CREATE VIEW IF NOT EXISTS integration_profiles AS
            SELECT
                service_name AS service_id,
                base_url AS endpoint_url,
                api_token_encrypted AS credential_encrypted,
                connection_status AS verification_state,
                last_tested_at AS synchronized_at
            FROM service_integrations;

            CREATE TABLE IF NOT EXISTS watchlist_pins (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_watchlist_pins_user ON watchlist_pins(user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_pins_identity ON watchlist_pins(
                COALESCE(user_id, ''),
                media_type,
                COALESCE(tmdb_id, -1),
                COALESCE(tvdb_id, -1)
            );
            """
        )

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO curation_lenses (lens_id, lens_name, description)
            VALUES (?, 'General', 'Default curation lens for general conversation and discovery.')
            """,
            (DEFAULT_LENS_ID,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO derived_contexts (
                context_hash, inferred_label, thematic_centroid_json, interaction_density
            ) VALUES (?, 'General Exploration', NULL, 1)
            """,
            (DEFAULT_CONTEXT_HASH,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO curator_system_config (config_key, config_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (ACTIVE_CONTEXT_CONFIG_KEY, DEFAULT_CONTEXT_HASH),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO curator_persona_metrics (
                metric_id, curator_name, val_bro_prof, val_dipl_snark, val_pass_auto
            ) VALUES (?, 'Curator', 0.5, 0.5, 0.5)
            """,
            (DEFAULT_PERSONA_ID,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO curator_system_config (config_key, config_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (ACTIVE_LENS_CONFIG_KEY, DEFAULT_LENS_ID),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO curator_system_config (config_key, config_value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (CURATOR_NAME_CONFIG_KEY, "Curator"),
        )
        self.ensure_bootstrap_owner(conn)

    def ensure_bootstrap_owner(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Ensure the bootstrap owner row exists.

        When ``conn`` is omitted this opens a managed connection (one-level
        re-entry into the ``conn``-provided path — not unbounded recursion).
        After the owner is known to exist, subsequent no-arg calls are no-ops.
        """
        if conn is None and self._bootstrap_owner_ready:
            return

        def _ensure(active: sqlite3.Connection) -> None:
            existing = active.execute(
                "SELECT 1 AS ok FROM users WHERE id = ? LIMIT 1",
                (BOOTSTRAP_OWNER_ID,),
            ).fetchone()
            if existing is not None:
                return
            now = time.time()
            active.execute(
                """
                INSERT OR IGNORE INTO users (id, display_name, email, role, created_at)
                VALUES (?, 'Owner', NULL, 'owner', ?)
                """,
                (BOOTSTRAP_OWNER_ID, now),
            )

        if conn is not None:
            _ensure(conn)
            self._bootstrap_owner_ready = True
            return

        def _managed() -> None:
            with self.connect() as managed:
                _ensure(managed)

        run_with_db_lock_retry(_managed, label="ensure_bootstrap_owner")
        self._bootstrap_owner_ready = True

    def get_user(self, user_id: str) -> Optional[sqlite3.Row]:
        def _read() -> Optional[sqlite3.Row]:
            with self.connect() as conn:
                return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        return run_with_db_lock_retry(_read, label="get_user")

    def get_user_by_plex_id(self, plex_user_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE plex_user_id = ?",
                (plex_user_id,),
            ).fetchone()

    def count_users_with_role(self, role: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = ?",
                (role,),
            ).fetchone()
            return int(row["count"] or 0) if row else 0

    def count_users_with_plex_id(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE plex_user_id IS NOT NULL",
            ).fetchone()
            return int(row["count"] or 0) if row else 0

    def upsert_plex_user(
        self,
        *,
        user_id: str,
        display_name: str,
        email: Optional[str],
        plex_user_id: str,
        role: str,
        avatar_url: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        seerr_permissions: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, plex_user_id, avatar_url,
                    seerr_user_id, seerr_permissions, created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plex_user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = excluded.email,
                    avatar_url = excluded.avatar_url,
                    seerr_user_id = COALESCE(excluded.seerr_user_id, users.seerr_user_id),
                    seerr_permissions = COALESCE(excluded.seerr_permissions, users.seerr_permissions),
                    last_login_at = excluded.last_login_at
                """,
                (
                    user_id,
                    display_name,
                    email,
                    role,
                    plex_user_id,
                    avatar_url,
                    seerr_user_id,
                    seerr_permissions,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE plex_user_id = ?", (plex_user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def list_users(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def update_user_role(self, user_id: str, role: str) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def update_user_seerr(
        self,
        user_id: str,
        *,
        seerr_user_id: int,
        seerr_permissions: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                """
                UPDATE users
                SET seerr_user_id = ?, seerr_permissions = ?
                WHERE id = ?
                """,
                (seerr_user_id, seerr_permissions, user_id),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def _row_to_user(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "display_name": str(row["display_name"]),
            "email": str(row["email"]) if row["email"] is not None else None,
            "role": str(row["role"]),
            "plex_user_id": str(row["plex_user_id"]) if row["plex_user_id"] is not None else None,
            "seerr_user_id": int(row["seerr_user_id"]) if row["seerr_user_id"] is not None else None,
            "seerr_permissions": int(row["seerr_permissions"]) if row["seerr_permissions"] is not None else None,
            "avatar_url": str(row["avatar_url"]) if row["avatar_url"] is not None else None,
            "created_at": float(row["created_at"]),
            "last_login_at": float(row["last_login_at"]) if row["last_login_at"] is not None else None,
        }

    def get_chat_message(self, message_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()

    def upsert_message_feedback(
        self,
        *,
        feedback_id: str,
        message_id: str,
        session_id: str,
        user_id: Optional[str],
        feedback_type: str,
        excerpt: str,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO message_feedback (
                    id, message_id, session_id, user_id, feedback_type, excerpt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id, user_id) DO UPDATE SET
                    feedback_type = excluded.feedback_type,
                    excerpt = excluded.excerpt,
                    created_at = excluded.created_at
                """,
                (feedback_id, message_id, session_id, user_id, feedback_type, excerpt, now),
            )
            row = conn.execute(
                """
                SELECT * FROM message_feedback
                WHERE message_id = ? AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                )
                """,
                (message_id, user_id, user_id),
            ).fetchone()
        assert row is not None
        return {
            "id": str(row["id"]),
            "message_id": str(row["message_id"]),
            "session_id": str(row["session_id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "feedback": str(row["feedback_type"]),
            "excerpt": str(row["excerpt"] or ""),
            "created_at": float(row["created_at"]),
        }

    def list_message_feedback(
        self,
        session_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM message_feedback
                    WHERE session_id = ? AND user_id IS NULL
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM message_feedback
                    WHERE session_id = ? AND user_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_id, user_id),
                ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "message_id": str(row["message_id"]),
                "session_id": str(row["session_id"]),
                "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
                "feedback": str(row["feedback_type"]),
                "excerpt": str(row["excerpt"] or ""),
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ]

    def delete_message_feedback(
        self,
        message_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> bool:
        with self.connect() as conn:
            if user_id is None:
                cursor = conn.execute(
                    """
                    DELETE FROM message_feedback
                    WHERE message_id = ? AND user_id IS NULL
                    """,
                    (message_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM message_feedback
                    WHERE message_id = ? AND user_id = ?
                    """,
                    (message_id, user_id),
                )
            return cursor.rowcount > 0

    def ensure_seed_data(self) -> None:
        with self.connect() as conn:
            self._seed_defaults(conn)

    def _open_connection(self) -> sqlite3.Connection:
        # timeout is seconds; check_same_thread=False allows FastAPI worker threads
        # to share Database instances (each call still gets its own connection).
        conn = sqlite3.connect(
            self.path,
            timeout=SQLITE_BUSY_TIMEOUT_MS / 1000.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}")
        # WAL lets readers proceed while a writer commits; persistent on the DB file.
        conn.execute("PRAGMA journal_mode=WAL")
        # NORMAL with WAL is a common Unraid/NAS tradeoff: much less fsync cost than
        # FULL, with only a small window of loss on abrupt power failure mid-commit.
        conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}")
        return conn

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._open_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

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
                    plex_user_rating_stars, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                return self._upsert_library_item_on_conn(conn, item)

        return run_with_db_lock_retry(_write, label="upsert_library_item")

    def upsert_library_items(self, items: Sequence[Mapping[str, Any]]) -> List[int]:
        """Upsert many library rows in a single transaction (one commit)."""
        if not items:
            return []

        def _write() -> List[int]:
            now = time.time()
            ids: List[int] = []
            with self.connect() as conn:
                for item in items:
                    ids.append(self._upsert_library_item_on_conn(conn, item, now=now))
            return ids

        return run_with_db_lock_retry(_write, label="upsert_library_items")

    def set_embedding(self, item_id: int, vector: Sequence[float]) -> None:
        self.set_embeddings([(item_id, vector)])

    def set_embeddings(
        self,
        items: Sequence[Tuple[int, Sequence[float]]] | Sequence[Tuple[int, Sequence[float], str]],
    ) -> None:
        """Write many embedding vectors in a single transaction.

        Each item is ``(item_id, vector)`` or ``(item_id, vector, content_hash)``.
        """
        if not items:
            return

        normalized: list[Tuple[int, str, Optional[str]]] = []
        for entry in items:
            if len(entry) == 3:
                item_id, vector, content_hash = entry  # type: ignore[misc]
                normalized.append(
                    (int(item_id), json.dumps(list(vector)), str(content_hash or "") or None)
                )
            else:
                item_id, vector = entry  # type: ignore[misc]
                normalized.append((int(item_id), json.dumps(list(vector)), None))

        def _write() -> None:
            with self.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO embeddings (item_id, vector, content_hash) VALUES (?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        vector = excluded.vector,
                        content_hash = COALESCE(excluded.content_hash, embeddings.content_hash)
                    """,
                    normalized,
                )

        run_with_db_lock_retry(_write, label="set_embeddings")

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

    def library_item_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM library_items WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type),
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
        """Delete all facets and bulk-insert ``rows`` in a single transaction."""

        def _write() -> int:
            with self.connect() as conn:
                conn.execute("DELETE FROM library_facets")
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

    def add_preference(self, signal_type: str, text: str, **kwargs: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preference_facts (signal_type, text, weight, tmdb_id, tvdb_id, media_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_type,
                    text,
                    kwargs.get("weight", 1.0),
                    kwargs.get("tmdb_id"),
                    kwargs.get("tvdb_id"),
                    kwargs.get("media_type"),
                    time.time(),
                ),
            )

    def preference_facts(self, limit: int = 50) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM preference_facts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            )

    def export_training_corpus(self) -> Dict[str, Any]:
        with self.connect() as conn:
            feedback_rows = conn.execute(
                "SELECT * FROM message_feedback ORDER BY created_at ASC"
            ).fetchall()
            fact_rows = conn.execute(
                "SELECT * FROM preference_facts ORDER BY created_at ASC"
            ).fetchall()
            review_rows = conn.execute(
                "SELECT * FROM user_title_reviews ORDER BY created_at ASC"
            ).fetchall()
        return {
            "exported_at": time.time(),
            "message_feedback": [dict(row) for row in feedback_rows],
            "preference_facts": [dict(row) for row in fact_rows],
            "user_title_reviews": [dict(row) for row in review_rows],
        }

    def save_pending_action(
        self,
        token: str,
        action_type: str,
        payload: Mapping[str, Any],
        ttl_seconds: int = 600,
        *,
        user_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_actions
                    (token, action_type, payload_json, created_at, expires_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, action_type, json.dumps(dict(payload)), now, now + ttl_seconds, user_id),
            )

    def pop_pending_action(
        self,
        token: str,
        *,
        user_id: Optional[str] = None,
    ) -> Optional[Mapping[str, Any]]:
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT * FROM pending_actions WHERE token = ? AND expires_at > ?",
                    (token, now),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM pending_actions
                    WHERE token = ? AND expires_at > ?
                      AND (user_id IS NULL OR user_id = ?)
                    """,
                    (token, now, user_id),
                ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM pending_actions WHERE token = ?", (token,))
            return json.loads(row["payload_json"])

    def set_sync_state(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, time.time()),
            )

    def get_sync_state(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else None

    # --- System config ---

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT config_value FROM curator_system_config WHERE config_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return default
            return str(row["config_value"])

    def set_config(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curator_system_config (config_key, config_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(config_key) DO UPDATE SET
                    config_value=excluded.config_value,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, value),
            )

    def get_all_config(self) -> Dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT config_key, config_value FROM curator_system_config ORDER BY config_key"
            ).fetchall()
            return {str(r["config_key"]): str(r["config_value"]) for r in rows}

    def sync_llm_config(
        self,
        *,
        llm_provider: str,
        llm_base_url: str,
        llm_model: str,
    ) -> None:
        self.set_config("llm_provider", llm_provider)
        self.set_config("llm_base_url", llm_base_url)
        self.set_config("llm_model", llm_model)

    # --- Service integrations ---

    def upsert_service_integration(
        self,
        service_name: str,
        *,
        base_url: str = "",
        api_token_encrypted: str = "",
        connection_status: str = "unverified",
        last_tested_at: Optional[str] = None,
        certified: Optional[int] = None,
    ) -> None:
        tested_at = last_tested_at or time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        certified_value = 0 if certified is None else int(bool(certified))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO service_integrations (
                    service_name, base_url, api_token_encrypted, connection_status,
                    last_tested_at, certified
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_name) DO UPDATE SET
                    base_url=excluded.base_url,
                    api_token_encrypted=excluded.api_token_encrypted,
                    connection_status=excluded.connection_status,
                    last_tested_at=excluded.last_tested_at,
                    certified=excluded.certified
                """,
                (
                    service_name,
                    base_url,
                    api_token_encrypted,
                    connection_status,
                    tested_at,
                    certified_value,
                ),
            )

    def invalidate_service_certification(self, service_name: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE service_integrations
                SET certified = 0, connection_status = 'unverified'
                WHERE service_name = ?
                """,
                (service_name,),
            )

    def get_service_integration(self, service_name: str) -> Optional[sqlite3.Row]:
        def _read() -> Optional[sqlite3.Row]:
            with self.connect() as conn:
                return conn.execute(
                    "SELECT * FROM service_integrations WHERE service_name = ?",
                    (service_name,),
                ).fetchone()

        return run_with_db_lock_retry(_read, label="get_service_integration")

    def get_service_integrations(self) -> List[sqlite3.Row]:
        def _read() -> List[sqlite3.Row]:
            with self.connect() as conn:
                return list(
                    conn.execute(
                        "SELECT * FROM service_integrations ORDER BY service_name ASC"
                    ).fetchall()
                )

        return run_with_db_lock_retry(_read, label="get_service_integrations")

    def get_active_lens_id(self) -> str:
        return self.get_config(ACTIVE_LENS_CONFIG_KEY, DEFAULT_LENS_ID) or DEFAULT_LENS_ID

    def set_active_lens_id(self, lens_id: str) -> None:
        if not self.get_lens(lens_id):
            raise ValueError(f"Unknown lens_id: {lens_id}")
        self.set_config(ACTIVE_LENS_CONFIG_KEY, lens_id)

    # --- Derived contexts (Phase 3) ---

    def get_derived_context(self, context_hash: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM derived_contexts WHERE context_hash = ?",
                (context_hash,),
            ).fetchone()

    def get_active_derived_context(self) -> sqlite3.Row:
        active_hash = self.get_config(ACTIVE_CONTEXT_CONFIG_KEY, DEFAULT_CONTEXT_HASH) or DEFAULT_CONTEXT_HASH
        row = self.get_derived_context(active_hash)
        if row:
            return row
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO derived_contexts (
                    context_hash, inferred_label, thematic_centroid_json, interaction_density
                ) VALUES (?, 'General Exploration', NULL, 1)
                """,
                (DEFAULT_CONTEXT_HASH,),
            )
        row = self.get_derived_context(DEFAULT_CONTEXT_HASH)
        assert row is not None
        return row

    def update_derived_context_label(self, context_hash: str, label: str) -> None:
        cleaned = str(label or "").strip()
        if not cleaned:
            return
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE derived_contexts
                SET inferred_label = ?, last_active_at = CURRENT_TIMESTAMP
                WHERE context_hash = ?
                """,
                (cleaned, context_hash),
            )

    # --- Persona ---

    def get_persona(self, metric_id: str = DEFAULT_PERSONA_ID) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM curator_persona_metrics WHERE metric_id = ?",
                (metric_id,),
            ).fetchone()

    def upsert_persona(
        self,
        *,
        metric_id: str = DEFAULT_PERSONA_ID,
        curator_name: Optional[str] = None,
        persona_identity: Optional[str] = None,
        val_bro_prof: Optional[float] = None,
        val_dipl_snark: Optional[float] = None,
        val_pass_auto: Optional[float] = None,
        persona_preset_id: Optional[str] = ...,  # type: ignore[assignment]
        persona_prompt_override: Optional[str] = ...,  # type: ignore[assignment]
        clear_persona_override: bool = False,
    ) -> sqlite3.Row:
        current = self.get_persona(metric_id)
        name = curator_name if curator_name is not None else (current["curator_name"] if current else "Curator")
        identity = (
            persona_identity
            if persona_identity is not None
            else (str(current["persona_identity"] or "") if current and "persona_identity" in current.keys() else "")
        )
        bro = val_bro_prof if val_bro_prof is not None else (float(current["val_bro_prof"]) if current else 0.5)
        snark = val_dipl_snark if val_dipl_snark is not None else (float(current["val_dipl_snark"]) if current else 0.5)
        auto = val_pass_auto if val_pass_auto is not None else (float(current["val_pass_auto"]) if current else 0.5)

        if persona_preset_id is ...:
            preset_id = str(current["persona_preset_id"] or "") if current and "persona_preset_id" in current.keys() else None
            preset_id = preset_id or None
        else:
            preset_id = persona_preset_id

        if clear_persona_override:
            override = None
        elif persona_prompt_override is ...:
            override = (
                str(current["persona_prompt_override"])
                if current and current["persona_prompt_override"] is not None
                else None
            )
        else:
            override = persona_prompt_override

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curator_persona_metrics (
                    metric_id, curator_name, persona_identity, val_bro_prof, val_dipl_snark,
                    val_pass_auto, persona_preset_id, persona_prompt_override, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(metric_id) DO UPDATE SET
                    curator_name=excluded.curator_name,
                    persona_identity=excluded.persona_identity,
                    val_bro_prof=excluded.val_bro_prof,
                    val_dipl_snark=excluded.val_dipl_snark,
                    val_pass_auto=excluded.val_pass_auto,
                    persona_preset_id=excluded.persona_preset_id,
                    persona_prompt_override=excluded.persona_prompt_override,
                    last_modified=CURRENT_TIMESTAMP
                """,
                (metric_id, name, identity, bro, snark, auto, preset_id, override),
            )
        if curator_name is not None:
            self.set_config(CURATOR_NAME_CONFIG_KEY, name)
        persona = self.get_persona(metric_id)
        assert persona is not None
        return persona

    # --- Lenses ---

    def list_lenses(self) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM curation_lenses ORDER BY created_at ASC, lens_name ASC"
                ).fetchall()
            )

    def get_lens(self, lens_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM curation_lenses WHERE lens_id = ?",
                (lens_id,),
            ).fetchone()

    def create_lens(self, lens_id: str, lens_name: str, description: str = "") -> sqlite3.Row:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO curation_lenses (lens_id, lens_name, description)
                VALUES (?, ?, ?)
                """,
                (lens_id, lens_name, description),
            )
        lens = self.get_lens(lens_id)
        assert lens is not None
        return lens

    def update_lens(
        self,
        lens_id: str,
        *,
        lens_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> sqlite3.Row:
        current = self.get_lens(lens_id)
        if not current:
            raise ValueError(f"Unknown lens_id: {lens_id}")
        name = lens_name if lens_name is not None else current["lens_name"]
        desc = description if description is not None else (current["description"] or "")
        with self.connect() as conn:
            conn.execute(
                "UPDATE curation_lenses SET lens_name = ?, description = ? WHERE lens_id = ?",
                (name, desc, lens_id),
            )
        lens = self.get_lens(lens_id)
        assert lens is not None
        return lens

    # --- Lens taste profile ---

    def get_lens_taste_profile(self, lens_id: str) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM lens_taste_profile
                    WHERE lens_id = ?
                    ORDER BY weight DESC, cluster_tag ASC
                    """,
                    (lens_id,),
                ).fetchall()
            )

    def set_lens_taste_weight(
        self,
        lens_id: str,
        cluster_tag: str,
        weight: float,
        *,
        explicit_lock: Optional[bool] = None,
        respect_lock: bool = True,
    ) -> None:
        if not self.get_lens(lens_id):
            raise ValueError(f"Unknown lens_id: {lens_id}")
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM lens_taste_profile WHERE lens_id = ? AND cluster_tag = ?",
                (lens_id, cluster_tag),
            ).fetchone()
            if existing and respect_lock and int(existing["explicit_lock"]) == 1 and explicit_lock is None:
                return
            lock_value = (
                int(bool(explicit_lock))
                if explicit_lock is not None
                else (int(existing["explicit_lock"]) if existing else 0)
            )
            conn.execute(
                """
                INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, explicit_lock, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(lens_id, cluster_tag) DO UPDATE SET
                    weight=excluded.weight,
                    explicit_lock=excluded.explicit_lock,
                    last_updated=CURRENT_TIMESTAMP
                """,
                (lens_id, cluster_tag, weight, lock_value),
            )

    # --- Chat (lens-scoped) ---

    DEFAULT_THREAD_TITLE = "New conversation"

    def _preview_from_blocks(self, blocks_json: Optional[str]) -> str:
        if not blocks_json:
            return ""
        try:
            blocks = json.loads(blocks_json)
        except json.JSONDecodeError:
            return ""
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                content = str(block.get("content") or "").strip()
                if content:
                    return content[:120]
        return ""

    def _row_to_thread_summary(self, row: sqlite3.Row, *, message_count: int = 0, preview: str = "") -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "thread_title": str(row["thread_title"] or self.DEFAULT_THREAD_TITLE),
            "context_hash": str(row["context_hash"] or DEFAULT_CONTEXT_HASH),
            "lens_id": str(row["lens_id"] or DEFAULT_LENS_ID),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "message_count": message_count,
            "preview": preview,
        }

    def create_chat_thread(
        self,
        session_id: str,
        *,
        lens_id: str = DEFAULT_LENS_ID,
        context_hash: str = DEFAULT_CONTEXT_HASH,
        thread_title: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        resolved_lens = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        title = (thread_title or self.DEFAULT_THREAD_TITLE).strip() or self.DEFAULT_THREAD_TITLE
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved_lens, title, resolved_context, user_id),
            )
            row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        assert row is not None
        return self._row_to_thread_summary(row)

    def get_chat_thread(self, session_id: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM chat_sessions WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
                    (session_id, user_id),
                ).fetchone()
            if not row:
                return None
            count_row = conn.execute(
                "SELECT COUNT(*) AS count FROM chat_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            last_row = conn.execute(
                """
                SELECT blocks_json FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        preview = self._preview_from_blocks(last_row["blocks_json"] if last_row else None)
        return self._row_to_thread_summary(
            row,
            message_count=int(count_row["count"]) if count_row else 0,
            preview=preview,
        )

    def list_chat_threads(self, *, limit: int = 50, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT
                        s.*,
                        COUNT(m.id) AS message_count,
                        (
                            SELECT blocks_json FROM chat_messages
                            WHERE session_id = s.id
                            ORDER BY created_at DESC
                            LIMIT 1
                        ) AS last_blocks_json
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON m.session_id = s.id
                    GROUP BY s.id
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        s.*,
                        COUNT(m.id) AS message_count,
                        (
                            SELECT blocks_json FROM chat_messages
                            WHERE session_id = s.id
                            ORDER BY created_at DESC
                            LIMIT 1
                        ) AS last_blocks_json
                    FROM chat_sessions s
                    LEFT JOIN chat_messages m ON m.session_id = s.id
                    WHERE s.user_id = ?
                    GROUP BY s.id
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
        threads: List[Dict[str, Any]] = []
        for row in rows:
            preview = self._preview_from_blocks(row["last_blocks_json"])
            threads.append(
                self._row_to_thread_summary(
                    row,
                    message_count=int(row["message_count"] or 0),
                    preview=preview,
                )
            )
        return threads

    def update_thread_title(self, session_id: str, thread_title: str) -> Dict[str, Any]:
        title = thread_title.strip()
        if not title:
            raise ValueError("thread_title is required")
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if not existing:
                raise ValueError(f"Unknown session_id: {session_id}")
            conn.execute(
                "UPDATE chat_sessions SET thread_title = ?, updated_at = ? WHERE id = ?",
                (title, now, session_id),
            )
        thread = self.get_chat_thread(session_id)
        assert thread is not None
        return thread

    def maybe_auto_title_thread(self, session_id: str, first_message: str) -> None:
        text = first_message.strip()
        if not text:
            return
        title = text[:60] + ("…" if len(text) > 60 else "")
        with self.connect() as conn:
            row = conn.execute(
                "SELECT thread_title FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return
            current = str(row["thread_title"] or self.DEFAULT_THREAD_TITLE)
            if current != self.DEFAULT_THREAD_TITLE:
                return
            conn.execute(
                "UPDATE chat_sessions SET thread_title = ? WHERE id = ?",
                (title, session_id),
            )

    def delete_chat_thread(self, session_id: str, *, user_id: Optional[str] = None) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM chat_sessions WHERE id = ? AND (user_id IS NULL OR user_id = ?)",
                    (session_id, user_id),
                ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
            return True

    def ensure_chat_session(
        self,
        session_id: str,
        lens_id: str = DEFAULT_LENS_ID,
        *,
        context_hash: str = DEFAULT_CONTEXT_HASH,
        user_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        resolved = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved, self.DEFAULT_THREAD_TITLE, resolved_context, user_id),
            )
            if user_id is not None:
                conn.execute(
                    """
                    UPDATE chat_sessions
                    SET user_id = COALESCE(user_id, ?)
                    WHERE id = ?
                    """,
                    (user_id, session_id),
                )
            conn.execute(
                """
                UPDATE chat_sessions
                SET lens_id = ?, updated_at = ?, context_hash = COALESCE(context_hash, ?)
                WHERE id = ?
                """,
                (resolved, now, resolved_context, session_id),
            )

    def save_chat_message(
        self,
        session_id: str,
        message_id: str,
        role: str,
        blocks: Iterable[Mapping[str, Any]],
        lens_id: str = DEFAULT_LENS_ID,
    ) -> None:
        now = time.time()
        resolved = lens_id or DEFAULT_LENS_ID
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, session_id, role, blocks_json, created_at, lens_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, json.dumps(list(blocks)), now, resolved),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ?, lens_id = ? WHERE id = ?",
                (now, resolved, session_id),
            )

    def chat_history(
        self,
        session_id: str,
        limit: int = 50,
        lens_id: Optional[str] = None,
    ) -> List[Mapping[str, Any]]:
        with self.connect() as conn:
            if lens_id:
                rows = conn.execute(
                    """
                    SELECT * FROM chat_messages
                    WHERE session_id = ? AND lens_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, lens_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            messages = []
            for row in reversed(rows):
                messages.append(
                    {
                        "id": row["id"],
                        "role": row["role"],
                        "blocks": json.loads(row["blocks_json"]),
                        "created_at": row["created_at"],
                        "lens_id": row["lens_id"] if "lens_id" in row.keys() else DEFAULT_LENS_ID,
                    }
                )
            return messages

    def list_watchlist_pins(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM watchlist_pins
                    WHERE user_id IS NULL
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM watchlist_pins
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_watchlist_pin(row) for row in rows]

    def add_watchlist_pin(
        self,
        *,
        pin_id: str,
        user_id: Optional[str],
        tmdb_id: Optional[int],
        tvdb_id: Optional[int],
        media_type: str,
        title: str,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist_pins (
                    id, user_id, tmdb_id, tvdb_id, media_type, title, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (pin_id, user_id, tmdb_id, tvdb_id, media_type, title, now),
            )
            row = conn.execute(
                """
                SELECT * FROM watchlist_pins
                WHERE media_type = ?
                  AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                  AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                  AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                  )
                """,
                (media_type, tmdb_id, tvdb_id, user_id, user_id),
            ).fetchone()
        if row is None:
            raise ValueError("Could not save watchlist pin")
        return self._row_to_watchlist_pin(row)

    def delete_watchlist_pin(self, pin_id: str, *, user_id: Optional[str] = None) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    """
                    SELECT id FROM watchlist_pins
                    WHERE id = ? AND user_id IS NULL
                    """,
                    (pin_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM watchlist_pins WHERE id = ? AND user_id = ?",
                    (pin_id, user_id),
                ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM watchlist_pins WHERE id = ?", (pin_id,))
            return True

    def count_chat_sessions_last_days(self, days: int = 30) -> int:
        cutoff = time.time() - (days * 86400)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM chat_sessions WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
        return int(row["count"] or 0) if row else 0

    @staticmethod
    def _row_to_watchlist_pin(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "created_at": float(row["created_at"]),
        }
