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

BUILTIN_PERSONA_IDS = {
    "classic-curator",
    "blunt-archivist",
    "enthusiastic-scout",
    "academic-critic",
    "night-owl-host",
}

BUILTIN_PERSONA_SEEDS: list[dict[str, object]] = [
    {
        "id": "classic-curator",
        "name": "Classic Curator",
        "val_bro_prof": 0.45, "val_dipl_snark": 0.28, "val_pass_auto": 0.42,
        "val_depth": 0.6, "val_obscurity": 0.4, "val_verbosity": 0.6, "val_formality": 0.5,
        "accent_color": "#8B6914",
    },
    {
        "id": "blunt-archivist",
        "name": "Blunt Archivist",
        "val_bro_prof": 0.78, "val_dipl_snark": 0.82, "val_pass_auto": 0.75,
        "val_depth": 0.8, "val_obscurity": 0.3, "val_verbosity": 0.3, "val_formality": 0.7,
        "accent_color": "#4A6178",
    },
    {
        "id": "enthusiastic-scout",
        "name": "Enthusiastic Scout",
        "val_bro_prof": 0.22, "val_dipl_snark": 0.35, "val_pass_auto": 0.68,
        "val_depth": 0.4, "val_obscurity": 0.5, "val_verbosity": 0.7, "val_formality": 0.2,
        "accent_color": "#C45224",
    },
    {
        "id": "academic-critic",
        "name": "Academic Critic",
        "val_bro_prof": 0.92, "val_dipl_snark": 0.55, "val_pass_auto": 0.38,
        "val_depth": 0.9, "val_obscurity": 0.7, "val_verbosity": 0.8, "val_formality": 0.8,
        "accent_color": "#6B3FA0",
    },
    {
        "id": "night-owl-host",
        "name": "Night Owl Host",
        "val_bro_prof": 0.25, "val_dipl_snark": 0.40, "val_pass_auto": 0.55,
        "val_depth": 0.3, "val_obscurity": 0.3, "val_verbosity": 0.4, "val_formality": 0.1,
        "accent_color": "#5C4FA0",
    },
]

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

CREATE TABLE IF NOT EXISTS persona_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('builtin', 'shared', 'private')),
    owner_user_id TEXT,
    val_bro_prof REAL DEFAULT 0.5,
    val_dipl_snark REAL DEFAULT 0.5,
    val_pass_auto REAL DEFAULT 0.5,
    val_depth REAL DEFAULT 0.5,
    val_obscurity REAL DEFAULT 0.5,
    val_verbosity REAL DEFAULT 0.5,
    val_formality REAL DEFAULT 0.5,
    system_prompt_override TEXT,
    accent_color TEXT,
    is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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
            self._migrate_context_tables(conn)
            self._migrate_persona_columns(conn)
            self._migrate_library_intelligence(conn)
            self._migrate_library_indexes(conn)
            self._migrate_phase0_tables(conn)
            self._migrate_multi_user_columns(conn)
            self._migrate_phase4_tables(conn)
            self._migrate_multi_user_columns(conn)  # reviews/prefs tables exist after phase4
            self._migrate_embeddings_content_hash(conn)
            self._migrate_curated_lists(conn)
            self._migrate_persona_templates(conn)
            self._migrate_recommendations(conn)
            self._migrate_library_metadata_enrichment(conn)
            self._migrate_people_credits(conn)
            self._migrate_plot_text_columns(conn)
            self._migrate_embeddings_model(conn)
            self._migrate_item_neighbors(conn)
            self._migrate_title_relations(conn)
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
        if "context_label" not in session_cols:
            conn.execute(
                "ALTER TABLE chat_sessions ADD COLUMN context_label TEXT DEFAULT 'General Exploration'"
            )
        conn.execute(
            "UPDATE chat_sessions SET thread_title = 'New conversation' WHERE thread_title IS NULL OR thread_title = ''"
        )
        conn.execute(
            "UPDATE chat_sessions SET context_hash = ? WHERE context_hash IS NULL OR context_hash = ''",
            (DEFAULT_CONTEXT_HASH,),
        )
        conn.execute(
            "UPDATE chat_sessions SET context_label = 'General Exploration' WHERE context_label IS NULL OR context_label = ''"
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
                disabled INTEGER NOT NULL DEFAULT 0,
                password_hash TEXT,
                auth_method TEXT DEFAULT 'plex',
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

    def _migrate_library_metadata_enrichment(self, conn: sqlite3.Connection) -> None:
        """Add full release/air dates, collections, status, networks, and companies.

        Explore "Recent Releases" and franchise shelves need true ISO dates and
        collection IDs — not just ``year``.  Columns are nullable so older rows
        stay honest until TMDB enrichment (sync or idle trickle) fills them.
        """
        cols = self._table_columns(conn, "library_items")
        new_columns = {
            "release_date": "TEXT",
            "first_air_date": "TEXT",
            "last_air_date": "TEXT",
            "tmdb_collection_id": "INTEGER",
            "collection_name": "TEXT DEFAULT ''",
            "status": "TEXT DEFAULT ''",
            "networks": "TEXT DEFAULT '[]'",
            "production_companies": "TEXT DEFAULT '[]'",
        }
        for name, typedef in new_columns.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE library_items ADD COLUMN {name} {typedef}")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_release_date ON library_items(release_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_first_air_date ON library_items(first_air_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_collection "
            "ON library_items(tmdb_collection_id)"
        )

    def _migrate_people_credits(self, conn: sqlite3.Connection) -> None:
        """Normalize cast/crew into people + credits (Stage 1 data platform).

        JSON ``cast`` / ``directors`` on ``library_items`` remain dual-written for
        backward compatibility; person pages and shared-crew queries use these tables.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_person_id INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                profile_url TEXT DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);

            CREATE TABLE IF NOT EXISTS credits (
                item_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                department TEXT NOT NULL DEFAULT '',
                job TEXT NOT NULL DEFAULT '',
                character TEXT NOT NULL DEFAULT '',
                billing_order INTEGER DEFAULT 0,
                PRIMARY KEY (item_id, person_id, department, job, character),
                FOREIGN KEY(item_id) REFERENCES library_items(id) ON DELETE CASCADE,
                FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_credits_person ON credits(person_id);
            CREATE INDEX IF NOT EXISTS idx_credits_item ON credits(item_id);
            """
        )

    def _migrate_plot_text_columns(self, conn: sqlite3.Connection) -> None:
        """Layered plot text for embeddings (Stage 2): TMDB overview/tagline + optional LLM logline.

        ``summary`` remains the Plex/local blurb.  ``tmdb_overview`` and ``tagline`` are
        filled from TMDB during sync/trickle.  ``llm_logline`` stays empty unless an LLM
        is configured and the optional idle task runs — never invent plot text.
        """
        cols = self._table_columns(conn, "library_items")
        for name, typedef in {
            "tmdb_overview": "TEXT DEFAULT ''",
            "tagline": "TEXT DEFAULT ''",
            "llm_logline": "TEXT DEFAULT ''",
        }.items():
            if name not in cols:
                conn.execute(f"ALTER TABLE library_items ADD COLUMN {name} {typedef}")

    def _migrate_embeddings_model(self, conn: sqlite3.Connection) -> None:
        """Record which embedding model produced each vector (hygiene for rebuilds)."""
        cols = self._table_columns(conn, "embeddings")
        if "embedding_model" not in cols:
            conn.execute("ALTER TABLE embeddings ADD COLUMN embedding_model TEXT DEFAULT ''")

    def _migrate_item_neighbors(self, conn: sqlite3.Connection) -> None:
        """Cached plot neighbors + surprise scores (Stage 3).

        v1 fills this via pure-Python cosine over stored embeddings (idle trickle).
        Future: optional sqlite-vec ANN index can prefilter candidates before scoring;
        keep this table as the read cache either way so Explore/Plot Lab stay cheap.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS item_neighbors (
                item_id INTEGER NOT NULL,
                neighbor_id INTEGER NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                surprise_score REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (item_id, neighbor_id),
                FOREIGN KEY(item_id) REFERENCES library_items(id) ON DELETE CASCADE,
                FOREIGN KEY(neighbor_id) REFERENCES library_items(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_neighbors_item_score
                ON item_neighbors(item_id, score DESC);
            CREATE INDEX IF NOT EXISTS idx_neighbors_item_surprise
                ON item_neighbors(item_id, surprise_score DESC);
            """
        )

    def _migrate_title_relations(self, conn: sqlite3.Connection) -> None:
        """Theme / franchise / crew relation graph (Stage 4 v1).

        Collection edges are built from ``tmdb_collection_id`` without an LLM.
        Optional mirrors: ``neighbor`` (from item_neighbors), ``shared_crew``.
        Optional LLM themes write ``relation='llm_theme'`` or ``facet_type='theme'``.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS title_relations (
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                relation TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (from_id, to_id, relation),
                FOREIGN KEY(from_id) REFERENCES library_items(id) ON DELETE CASCADE,
                FOREIGN KEY(to_id) REFERENCES library_items(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_title_relations_from
                ON title_relations(from_id, relation);
            CREATE INDEX IF NOT EXISTS idx_title_relations_to
                ON title_relations(to_id, relation);
            CREATE INDEX IF NOT EXISTS idx_title_relations_type
                ON title_relations(relation);
            """
        )

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
        user_cols = self._table_columns(conn, "users")
        if user_cols and "preferred_name" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN preferred_name TEXT")
        if user_cols and "disabled" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
        if user_cols:
            for name, typedef in {
                "watchlist_sync_enabled": "INTEGER NOT NULL DEFAULT 1",
                "watchlist_pull_on_login": "INTEGER NOT NULL DEFAULT 1",
                "watchlist_push_on_pin": "INTEGER NOT NULL DEFAULT 1",
                "watchlist_last_synced_at": "REAL",
            }.items():
                if name not in user_cols:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")
        pin_cols = self._table_columns(conn, "watchlist_pins")
        if pin_cols and "plex_rating_key" not in pin_cols:
            conn.execute("ALTER TABLE watchlist_pins ADD COLUMN plex_rating_key TEXT")
        if user_cols:
            for name, typedef in {
                "password_hash": "TEXT",
                "auth_method": "TEXT DEFAULT 'plex'",
            }.items():
                if name not in user_cols:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")

    def _migrate_curated_lists(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS curated_lists (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_curated_lists_user ON curated_lists(user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_curated_lists_name ON curated_lists(
                COALESCE(user_id, ''),
                name
            );

            CREATE TABLE IF NOT EXISTS curated_list_items (
                id TEXT PRIMARY KEY,
                list_id TEXT NOT NULL,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                library_item_id INTEGER,
                position INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (list_id) REFERENCES curated_lists(id) ON DELETE CASCADE,
                FOREIGN KEY (library_item_id) REFERENCES library_items(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_curated_list_items_list ON curated_list_items(list_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_curated_list_items_identity ON curated_list_items(
                list_id,
                media_type,
                COALESCE(tmdb_id, -1),
                COALESCE(tvdb_id, -1)
            );
            """
        )

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
                updated_at REAL NOT NULL,
                user_id TEXT
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

    def _migrate_context_tables(self, conn: sqlite3.Connection) -> None:
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

            CREATE TABLE IF NOT EXISTS purge_dismissals (
                rating_key TEXT PRIMARY KEY,
                dismissed_at REAL NOT NULL
            );
            """
        )

    def _migrate_persona_templates(self, conn: sqlite3.Connection) -> None:
        """Create persona_templates table, add persona_id to threads, default_persona_id to users.

        This migration enables per-conversation persona selection:
        - persona_templates holds reusable persona configurations (builtin presets,
          shared templates created by the owner, private per-user templates).
        - chat_sessions.persona_id links each conversation to a specific persona.
        - users.default_persona_id lets each user set their preferred default.
        - Existing curator_persona_metrics slider values are migrated to a shared
          template so they aren't lost.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS persona_templates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                visibility TEXT NOT NULL CHECK (visibility IN ('builtin', 'shared', 'private')),
                owner_user_id TEXT,
                val_bro_prof REAL DEFAULT 0.5,
                val_dipl_snark REAL DEFAULT 0.5,
                val_pass_auto REAL DEFAULT 0.5,
                val_depth REAL DEFAULT 0.5,
                val_obscurity REAL DEFAULT 0.5,
                val_verbosity REAL DEFAULT 0.5,
                val_formality REAL DEFAULT 0.5,
                system_prompt_override TEXT,
                accent_color TEXT,
                is_default INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            """
        )
        session_cols = self._table_columns(conn, "chat_sessions")
        if "persona_id" not in session_cols:
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN persona_id TEXT")
        user_cols = self._table_columns(conn, "users")
        if user_cols and "default_persona_id" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN default_persona_id TEXT")

        self._seed_builtin_persona_templates(conn)
        self._migrate_legacy_persona_to_template(conn)

    def _migrate_recommendations(self, conn: sqlite3.Connection) -> None:
        """Per-user UI font size + household title recommendations inbox."""
        user_cols = self._table_columns(conn, "users")
        if user_cols and "ui_font_size" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN ui_font_size TEXT NOT NULL DEFAULT 'medium'"
            )
        if user_cols and "ui_theme" not in user_cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN ui_theme TEXT NOT NULL DEFAULT 'system'"
            )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_recommendations (
                id TEXT PRIMARY KEY,
                from_user_id TEXT NOT NULL,
                to_user_id TEXT NOT NULL,
                media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'show')),
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                rating_key TEXT,
                title TEXT NOT NULL,
                year INTEGER,
                poster_url TEXT,
                message TEXT,
                created_at REAL NOT NULL,
                seen_at REAL,
                FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (to_user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_recommendations_to
                ON user_recommendations(to_user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_user_recommendations_unread
                ON user_recommendations(to_user_id, seen_at);
            """
        )

    def _seed_builtin_persona_templates(self, conn: sqlite3.Connection) -> None:
        """Insert the 5 built-in persona presets into persona_templates if absent."""
        for seed in BUILTIN_PERSONA_SEEDS:
            conn.execute(
                """
                INSERT OR IGNORE INTO persona_templates (
                    id, name, visibility, owner_user_id,
                    val_bro_prof, val_dipl_snark, val_pass_auto,
                    val_depth, val_obscurity, val_verbosity, val_formality,
                    accent_color
                ) VALUES (?, ?, 'builtin', NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seed["id"],
                    seed["name"],
                    seed["val_bro_prof"],
                    seed["val_dipl_snark"],
                    seed["val_pass_auto"],
                    seed["val_depth"],
                    seed["val_obscurity"],
                    seed["val_verbosity"],
                    seed["val_formality"],
                    seed.get("accent_color"),
                ),
            )

    def _migrate_legacy_persona_to_template(self, conn: sqlite3.Connection) -> None:
        """Copy existing singleton persona metrics into a shared persona template.

        If the user has customized the server-wide persona (non-default slider
        values or a custom prompt override), those values are preserved as a
        shared template owned by the bootstrap user.
        """
        row = conn.execute(
            "SELECT * FROM curator_persona_metrics WHERE metric_id = ?",
            (DEFAULT_PERSONA_ID,),
        ).fetchone()
        if row is None:
            return
        bro = float(row["val_bro_prof"])
        snark = float(row["val_dipl_snark"])
        auto = float(row["val_pass_auto"])
        override = row["persona_prompt_override"] if "persona_prompt_override" in row.keys() else None
        is_default = bro == 0.5 and snark == 0.5 and auto == 0.5 and not override
        if is_default:
            return
        migrated_id = "migrated-persona"
        existing = conn.execute(
            "SELECT id FROM persona_templates WHERE id = ?", (migrated_id,)
        ).fetchone()
        if existing:
            return
        name = str(row["curator_name"]) if "curator_name" in row.keys() else "Curator"
        conn.execute(
            """
            INSERT INTO persona_templates (
                id, name, visibility, owner_user_id,
                val_bro_prof, val_dipl_snark, val_pass_auto,
                val_depth, val_obscurity, val_verbosity, val_formality,
                system_prompt_override, is_default
            ) VALUES (?, ?, 'shared', ?, ?, ?, ?, 0.5, 0.5, 0.5, 0.5, ?, 1)
            """,
            (migrated_id, f"{name} (migrated)", BOOTSTRAP_OWNER_ID, bro, snark, auto, override),
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

    def set_user_disabled(self, user_id: str, disabled: bool) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                "UPDATE users SET disabled = ? WHERE id = ?",
                (1 if disabled else 0, user_id),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def delete_user(self, user_id: str) -> None:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

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

    def update_user_profile(
        self,
        user_id: str,
        *,
        preferred_name: Any = ...,
        ui_font_size: Any = ...,
        ui_theme: Any = ...,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            cols = self._table_columns(conn, "users")
            updates: List[str] = []
            params: List[Any] = []
            if preferred_name is not ...:
                cleaned = (preferred_name or "").strip() or None
                updates.append("preferred_name = ?")
                params.append(cleaned)
            if ui_font_size is not ...:
                cleaned_font = str(ui_font_size or "medium").strip().lower()
                if cleaned_font not in {"small", "medium", "large"}:
                    cleaned_font = "medium"
                if "ui_font_size" in cols:
                    updates.append("ui_font_size = ?")
                    params.append(cleaned_font)
            if ui_theme is not ...:
                cleaned_theme = str(ui_theme or "system").strip().lower()
                if cleaned_theme not in {"lights_up", "lights_down", "system"}:
                    cleaned_theme = "system"
                if "ui_theme" in cols:
                    updates.append("ui_theme = ?")
                    params.append(cleaned_theme)
            if updates:
                params.append(user_id)
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    tuple(params),
                )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def create_local_user(
        self,
        *,
        user_id: str,
        display_name: str,
        password_hash: str,
        role: str = "member",
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a user who authenticates via local password."""
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, password_hash, auth_method,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, 'local', ?, ?)
                """,
                (user_id, display_name, email, role, password_hash, now, now),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def get_user_by_display_name(self, display_name: str) -> Optional[sqlite3.Row]:
        """Look up a local user by display_name (used as username for local auth)."""
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE display_name = ? AND auth_method = 'local'",
                (display_name,),
            ).fetchone()

    def upsert_oidc_user(
        self,
        *,
        oidc_sub: str,
        display_name: str,
        email: Optional[str] = None,
        role: str = "member",
    ) -> Dict[str, Any]:
        """Create or update a user identified by OIDC subject claim."""
        now = time.time()
        user_id = f"oidc-{oidc_sub}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, oidc_sub, auth_method,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, 'oidc', ?, ?)
                ON CONFLICT(oidc_sub) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = excluded.email,
                    last_login_at = excluded.last_login_at
                """,
                (user_id, display_name, email, role, oidc_sub, now, now),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE oidc_sub = ?", (oidc_sub,)
            ).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def get_user_by_oidc_sub(self, oidc_sub: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE oidc_sub = ?", (oidc_sub,)
            ).fetchone()

    def set_user_plex_token_enc(self, user_id: str, token_enc: str) -> None:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                "UPDATE users SET plex_token_enc = ? WHERE id = ?",
                (token_enc, user_id),
            )

    def get_user_plex_token_enc(self, user_id: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT plex_token_enc FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None or row["plex_token_enc"] is None:
            return None
        return str(row["plex_token_enc"])

    def get_watchlist_sync_prefs(self, user_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return {
                "watchlist_sync_enabled": True,
                "watchlist_pull_on_login": True,
                "watchlist_push_on_pin": True,
                "watchlist_last_synced_at": None,
            }
        keys = set(row.keys())
        return {
            "watchlist_sync_enabled": (
                bool(int(row["watchlist_sync_enabled"]))
                if "watchlist_sync_enabled" in keys and row["watchlist_sync_enabled"] is not None
                else True
            ),
            "watchlist_pull_on_login": (
                bool(int(row["watchlist_pull_on_login"]))
                if "watchlist_pull_on_login" in keys and row["watchlist_pull_on_login"] is not None
                else True
            ),
            "watchlist_push_on_pin": (
                bool(int(row["watchlist_push_on_pin"]))
                if "watchlist_push_on_pin" in keys and row["watchlist_push_on_pin"] is not None
                else True
            ),
            "watchlist_last_synced_at": (
                float(row["watchlist_last_synced_at"])
                if "watchlist_last_synced_at" in keys and row["watchlist_last_synced_at"] is not None
                else None
            ),
        }

    def update_watchlist_sync_prefs(
        self,
        user_id: str,
        *,
        enabled: Optional[bool] = None,
        pull_on_login: Optional[bool] = None,
        push_on_pin: Optional[bool] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            if enabled is not None:
                conn.execute(
                    "UPDATE users SET watchlist_sync_enabled = ? WHERE id = ?",
                    (1 if enabled else 0, user_id),
                )
            if pull_on_login is not None:
                conn.execute(
                    "UPDATE users SET watchlist_pull_on_login = ? WHERE id = ?",
                    (1 if pull_on_login else 0, user_id),
                )
            if push_on_pin is not None:
                conn.execute(
                    "UPDATE users SET watchlist_push_on_pin = ? WHERE id = ?",
                    (1 if push_on_pin else 0, user_id),
                )
        return self.get_watchlist_sync_prefs(user_id)

    def mark_watchlist_synced(self, user_id: str, *, synced_at: Optional[float] = None) -> None:
        stamp = time.time() if synced_at is None else float(synced_at)
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET watchlist_last_synced_at = ? WHERE id = ?",
                (stamp, user_id),
            )

    def _row_to_user(self, row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        preferred_name = None
        if "preferred_name" in keys and row["preferred_name"] is not None:
            preferred_name = str(row["preferred_name"])
        ui_font_size = "medium"
        if "ui_font_size" in keys and row["ui_font_size"] is not None:
            cleaned = str(row["ui_font_size"]).strip().lower()
            if cleaned in {"small", "medium", "large"}:
                ui_font_size = cleaned
        ui_theme = "system"
        if "ui_theme" in keys and row["ui_theme"] is not None:
            cleaned_theme = str(row["ui_theme"]).strip().lower()
            if cleaned_theme in {"lights_up", "lights_down", "system"}:
                ui_theme = cleaned_theme
        disabled = False
        if "disabled" in keys and row["disabled"] is not None:
            disabled = bool(int(row["disabled"]))
        seerr_user_id = int(row["seerr_user_id"]) if row["seerr_user_id"] is not None else None
        return {
            "id": str(row["id"]),
            "display_name": str(row["display_name"]),
            "preferred_name": preferred_name,
            "ui_font_size": ui_font_size,
            "ui_theme": ui_theme,
            "email": str(row["email"]) if row["email"] is not None else None,
            "role": str(row["role"]),
            "disabled": disabled,
            "plex_user_id": str(row["plex_user_id"]) if row["plex_user_id"] is not None else None,
            "seerr_user_id": seerr_user_id,
            "seerr_linked": seerr_user_id is not None,
            "seerr_permissions": int(row["seerr_permissions"]) if row["seerr_permissions"] is not None else None,
            "avatar_url": str(row["avatar_url"]) if row["avatar_url"] is not None else None,
            "has_plex_token": bool(
                "plex_token_enc" in keys and row["plex_token_enc"]
            ),
            "auth_method": str(row["auth_method"]) if "auth_method" in keys and row["auth_method"] is not None else "plex",
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
            self._seed_builtin_persona_templates(conn)
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

    def items_needing_metadata_enrichment(self, *, limit: int = 25) -> List[sqlite3.Row]:
        """Library rows with a TMDB id but missing dates and/or plot text (trickle backlog)."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT id, rating_key, media_type, title, tmdb_id,
                           release_date, first_air_date, last_air_date,
                           tmdb_overview, tagline
                    FROM library_items
                    WHERE tmdb_id IS NOT NULL
                      AND (
                        (media_type = 'movie' AND (release_date IS NULL OR release_date = ''))
                        OR (media_type = 'show' AND (first_air_date IS NULL OR first_air_date = ''))
                        OR tmdb_overview IS NULL OR tmdb_overview = ''
                      )
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
            )

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

    def items_needing_llm_logline(self, *, limit: int = 10) -> List[sqlite3.Row]:
        """Rows with plot text but empty ``llm_logline`` (optional LLM enrichment backlog)."""
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT id, rating_key, media_type, title, year, summary,
                           tmdb_overview, tagline, llm_logline
                    FROM library_items
                    WHERE (llm_logline IS NULL OR llm_logline = '')
                      AND (
                        (summary IS NOT NULL AND summary != '')
                        OR (tmdb_overview IS NOT NULL AND tmdb_overview != '')
                      )
                    ORDER BY updated_at ASC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
            )

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

    def delete_library_items_by_rating_keys(self, rating_keys: List[str]) -> int:
        """Delete library items (and related episodes/embeddings) by rating_key list."""
        if not rating_keys:
            return 0
        keys = [str(k) for k in rating_keys if str(k).strip()]
        if not keys:
            return 0

        def _write() -> int:
            with self.connect() as conn:
                placeholders = ", ".join("?" for _ in keys)
                item_ids = [
                    row["id"]
                    for row in conn.execute(
                        f"SELECT id FROM library_items WHERE rating_key IN ({placeholders})",
                        keys,
                    ).fetchall()
                ]
                if not item_ids:
                    return 0
                id_ph = ", ".join("?" for _ in item_ids)
                conn.execute(
                    f"DELETE FROM library_episodes WHERE show_item_id IN ({id_ph})",
                    item_ids,
                )
                conn.execute(
                    f"DELETE FROM embeddings WHERE item_id IN ({id_ph})",
                    item_ids,
                )
                cursor = conn.execute(
                    f"DELETE FROM library_items WHERE id IN ({id_ph})",
                    item_ids,
                )
                return int(cursor.rowcount)

        return run_with_db_lock_retry(_write, label="delete_library_items")

    def dismiss_purge_candidates(self, rating_keys: List[str]) -> int:
        """Mark rating_keys as dismissed so they won't appear as purge candidates."""
        if not rating_keys:
            return 0
        keys = [str(k) for k in rating_keys if str(k).strip()]
        if not keys:
            return 0
        now = time.time()

        def _write() -> int:
            with self.connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO purge_dismissals (rating_key, dismissed_at)
                    VALUES (?, ?)
                    ON CONFLICT(rating_key) DO UPDATE SET dismissed_at = excluded.dismissed_at
                    """,
                    [(k, now) for k in keys],
                )
                return len(keys)

        return run_with_db_lock_retry(_write, label="dismiss_purge_candidates")

    def dismissed_purge_keys(self) -> set:
        """Return set of rating_keys that have been dismissed from purge."""
        with self.connect() as conn:
            try:
                rows = conn.execute("SELECT rating_key FROM purge_dismissals").fetchall()
                return {str(row["rating_key"]) for row in rows}
            except Exception:
                return set()

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

    def add_preference(self, signal_type: str, text: str, **kwargs: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preference_facts
                    (signal_type, text, weight, tmdb_id, tvdb_id, media_type, created_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_type,
                    text,
                    kwargs.get("weight", 1.0),
                    kwargs.get("tmdb_id"),
                    kwargs.get("tvdb_id"),
                    kwargs.get("media_type"),
                    time.time(),
                    kwargs.get("user_id"),
                ),
            )

    def preference_facts(self, limit: int = 50, *, user_id: Optional[str] = None) -> List[sqlite3.Row]:
        with self.connect() as conn:
            if user_id is None:
                return list(
                    conn.execute(
                        "SELECT * FROM preference_facts ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                )
            return list(
                conn.execute(
                    """
                    SELECT * FROM preference_facts
                    WHERE user_id = ? OR user_id IS NULL
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            )

    # --- Telemetry ---

    def insert_telemetry_event(
        self,
        *,
        event_id: str,
        event_class: str,
        payload_json: str,
        media_node_id: Optional[str] = None,
        associated_context_hash: Optional[str] = None,
    ) -> None:
        """Insert a single event into the telemetry stream table."""
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO system_telemetry_stream
                    (id, event_class, payload_json, media_node_id, associated_context_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, event_class, payload_json, media_node_id, associated_context_hash),
            )

    def telemetry_summary(self, *, hours: int = 24) -> Dict[str, Any]:
        """Return event counts grouped by event_class within the last *hours*."""
        cutoff = f"-{hours} hours"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_class, COUNT(*) AS count
                FROM system_telemetry_stream
                WHERE timestamp >= datetime('now', ?)
                GROUP BY event_class
                ORDER BY count DESC
                """,
                (cutoff,),
            ).fetchall()
        return {str(row["event_class"]): int(row["count"]) for row in rows}

    def telemetry_events(
        self,
        *,
        event_class: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return recent telemetry events, optionally filtered by class."""
        if event_class:
            rows = self._query(
                "SELECT * FROM system_telemetry_stream WHERE event_class = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (event_class, limit, offset),
            )
        else:
            rows = self._query(
                "SELECT * FROM system_telemetry_stream ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [dict(row) for row in rows]

    def _query(self, sql: str, params=()) -> List[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    # --- Data retention / pruning ---

    def prune_telemetry(self, retention_days: int) -> int:
        """Delete telemetry events older than *retention_days*. Returns rows deleted."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM system_telemetry_stream WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def prune_interaction_telemetry(self, retention_days: int) -> int:
        """Delete interaction telemetry older than *retention_days*. Returns rows deleted."""
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM interaction_telemetry WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def prune_daily_anniversaries(self, retention_days: int) -> int:
        """Delete daily anniversary entries older than *retention_days*. Returns rows deleted.

        The ``daily_anniversaries`` table is created lazily by the anniversary
        scanner task, so this method tolerates its absence.
        """
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='daily_anniversaries'"
            ).fetchone()
            if not exists:
                return 0
            cursor = conn.execute(
                "DELETE FROM daily_anniversaries WHERE scanned_date < date('now', ?)",
                (f"-{retention_days} days",),
            )
            return cursor.rowcount

    def vacuum(self) -> None:
        """Run VACUUM to reclaim space after large deletes.

        VACUUM cannot run inside a transaction, so we use a raw connection.
        """
        conn = self._open_connection()
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()

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

    # --- Derived contexts ---

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

    # --- Persona Templates ---

    _PERSONA_TEMPLATE_COLS = (
        "id, name, visibility, owner_user_id, "
        "val_bro_prof, val_dipl_snark, val_pass_auto, "
        "val_depth, val_obscurity, val_verbosity, val_formality, "
        "system_prompt_override, accent_color, is_default, created_at"
    )

    def _row_to_persona_template(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "visibility": str(row["visibility"]),
            "owner_user_id": row["owner_user_id"],
            "val_bro_prof": float(row["val_bro_prof"]),
            "val_dipl_snark": float(row["val_dipl_snark"]),
            "val_pass_auto": float(row["val_pass_auto"]),
            "val_depth": float(row["val_depth"]),
            "val_obscurity": float(row["val_obscurity"]),
            "val_verbosity": float(row["val_verbosity"]),
            "val_formality": float(row["val_formality"]),
            "system_prompt_override": row["system_prompt_override"],
            "accent_color": row["accent_color"],
            "is_default": bool(row["is_default"]),
            "created_at": str(row["created_at"]) if row["created_at"] else None,
        }

    def list_persona_templates(
        self,
        *,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return persona templates visible to a given user.

        Visibility rules:
        - ``builtin`` templates are always visible.
        - ``shared`` templates are always visible.
        - ``private`` templates are only visible to their owner.
        """
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates "
                    "WHERE visibility IN ('builtin', 'shared') "
                    "ORDER BY visibility ASC, name ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates "
                    "WHERE visibility IN ('builtin', 'shared') "
                    "   OR (visibility = 'private' AND owner_user_id = ?) "
                    "ORDER BY visibility ASC, name ASC",
                    (user_id,),
                ).fetchall()
        return [self._row_to_persona_template(row) for row in rows]

    def get_persona_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {self._PERSONA_TEMPLATE_COLS} FROM persona_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_persona_template(row)

    def create_persona_template(
        self,
        *,
        template_id: str,
        name: str,
        visibility: str = "shared",
        owner_user_id: Optional[str] = None,
        val_bro_prof: float = 0.5,
        val_dipl_snark: float = 0.5,
        val_pass_auto: float = 0.5,
        val_depth: float = 0.5,
        val_obscurity: float = 0.5,
        val_verbosity: float = 0.5,
        val_formality: float = 0.5,
        system_prompt_override: Optional[str] = None,
        accent_color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new persona template.

        Owner-created templates are ``shared`` (visible to all users);
        member-created templates are ``private`` (visible only to the creator).
        """
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO persona_templates (
                    id, name, visibility, owner_user_id,
                    val_bro_prof, val_dipl_snark, val_pass_auto,
                    val_depth, val_obscurity, val_verbosity, val_formality,
                    system_prompt_override, accent_color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id, name, visibility, owner_user_id,
                    val_bro_prof, val_dipl_snark, val_pass_auto,
                    val_depth, val_obscurity, val_verbosity, val_formality,
                    system_prompt_override, accent_color,
                ),
            )
        template = self.get_persona_template(template_id)
        assert template is not None
        return template

    def update_persona_template(
        self,
        template_id: str,
        *,
        name: Optional[str] = None,
        val_bro_prof: Optional[float] = None,
        val_dipl_snark: Optional[float] = None,
        val_pass_auto: Optional[float] = None,
        val_depth: Optional[float] = None,
        val_obscurity: Optional[float] = None,
        val_verbosity: Optional[float] = None,
        val_formality: Optional[float] = None,
        system_prompt_override: Optional[str] = ...,  # type: ignore[assignment]
        accent_color: Optional[str] = ...,  # type: ignore[assignment]
    ) -> Dict[str, Any]:
        """Update a custom persona template. Built-in templates are immutable."""
        current = self.get_persona_template(template_id)
        if current is None:
            raise ValueError(f"Unknown persona template: {template_id}")
        if current["visibility"] == "builtin":
            raise ValueError("Built-in persona templates are immutable")

        resolved = {
            "name": name if name is not None else current["name"],
            "val_bro_prof": val_bro_prof if val_bro_prof is not None else current["val_bro_prof"],
            "val_dipl_snark": val_dipl_snark if val_dipl_snark is not None else current["val_dipl_snark"],
            "val_pass_auto": val_pass_auto if val_pass_auto is not None else current["val_pass_auto"],
            "val_depth": val_depth if val_depth is not None else current["val_depth"],
            "val_obscurity": val_obscurity if val_obscurity is not None else current["val_obscurity"],
            "val_verbosity": val_verbosity if val_verbosity is not None else current["val_verbosity"],
            "val_formality": val_formality if val_formality is not None else current["val_formality"],
            "system_prompt_override": (
                system_prompt_override if system_prompt_override is not ... else current["system_prompt_override"]
            ),
            "accent_color": accent_color if accent_color is not ... else current["accent_color"],
        }
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE persona_templates SET
                    name = ?, val_bro_prof = ?, val_dipl_snark = ?, val_pass_auto = ?,
                    val_depth = ?, val_obscurity = ?, val_verbosity = ?, val_formality = ?,
                    system_prompt_override = ?, accent_color = ?
                WHERE id = ?
                """,
                (
                    resolved["name"],
                    resolved["val_bro_prof"], resolved["val_dipl_snark"], resolved["val_pass_auto"],
                    resolved["val_depth"], resolved["val_obscurity"],
                    resolved["val_verbosity"], resolved["val_formality"],
                    resolved["system_prompt_override"], resolved["accent_color"],
                    template_id,
                ),
            )
        updated = self.get_persona_template(template_id)
        assert updated is not None
        return updated

    def delete_persona_template(self, template_id: str) -> bool:
        """Delete a custom persona template. Built-in templates cannot be deleted."""
        current = self.get_persona_template(template_id)
        if current is None:
            return False
        if current["visibility"] == "builtin":
            raise ValueError("Built-in persona templates cannot be deleted")
        with self.connect() as conn:
            conn.execute("DELETE FROM persona_templates WHERE id = ?", (template_id,))
        return True

    def set_user_default_persona(self, user_id: str, persona_id: str) -> None:
        """Set a user's default persona template for new conversations."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET default_persona_id = ? WHERE id = ?",
                (persona_id, user_id),
            )

    def get_user_default_persona_id(self, user_id: str) -> Optional[str]:
        """Return the user's default persona template ID, or None."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT default_persona_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return row["default_persona_id"]

    def set_thread_persona(self, session_id: str, persona_id: Optional[str]) -> None:
        """Attach or update a persona template on a chat thread."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET persona_id = ? WHERE id = ?",
                (persona_id, session_id),
            )

    def get_thread_persona_id(self, session_id: str) -> Optional[str]:
        """Return the persona_id attached to a thread, or None."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT persona_id FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return row["persona_id"]

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
        persona_id = row["persona_id"] if "persona_id" in row.keys() else None
        context_label = row["context_label"] if "context_label" in row.keys() else "General Exploration"
        return {
            "id": str(row["id"]),
            "thread_title": str(row["thread_title"] or self.DEFAULT_THREAD_TITLE),
            "context_hash": str(row["context_hash"] or DEFAULT_CONTEXT_HASH),
            "context_label": str(context_label or "General Exploration"),
            "lens_id": str(row["lens_id"] or DEFAULT_LENS_ID),
            "persona_id": str(persona_id) if persona_id else None,
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
        persona_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        resolved_lens = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        title = (thread_title or self.DEFAULT_THREAD_TITLE).strip() or self.DEFAULT_THREAD_TITLE
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id, persona_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved_lens, title, resolved_context, user_id, persona_id),
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

    def update_thread_context_label(self, session_id: str, context_label: str) -> None:
        label = (context_label or "").strip() or "General Exploration"
        with self.connect() as conn:
            conn.execute(
                "UPDATE chat_sessions SET context_label = ? WHERE id = ?",
                (label, session_id),
            )

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
        persona_id: Optional[str] = None,
    ) -> None:
        now = time.time()
        resolved = lens_id or DEFAULT_LENS_ID
        resolved_context = context_hash or DEFAULT_CONTEXT_HASH
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_sessions (
                    id, created_at, updated_at, lens_id, thread_title, context_hash, user_id, persona_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, now, now, resolved, self.DEFAULT_THREAD_TITLE, resolved_context, user_id, persona_id),
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
        plex_rating_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            cols = self._table_columns(conn, "watchlist_pins")
            if "plex_rating_key" in cols:
                conn.execute(
                    """
                    INSERT INTO watchlist_pins (
                        id, user_id, tmdb_id, tvdb_id, media_type, title, created_at, plex_rating_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (pin_id, user_id, tmdb_id, tvdb_id, media_type, title, now, plex_rating_key),
                )
                if plex_rating_key:
                    conn.execute(
                        """
                        UPDATE watchlist_pins
                        SET plex_rating_key = COALESCE(plex_rating_key, ?)
                        WHERE media_type = ?
                          AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                          AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                          AND (
                            (user_id IS NULL AND ? IS NULL) OR user_id = ?
                          )
                        """,
                        (plex_rating_key, media_type, tmdb_id, tvdb_id, user_id, user_id),
                    )
            else:
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

    def set_watchlist_pin_plex_rating_key(self, pin_id: str, plex_rating_key: str) -> None:
        with self.connect() as conn:
            cols = self._table_columns(conn, "watchlist_pins")
            if "plex_rating_key" not in cols:
                return
            conn.execute(
                "UPDATE watchlist_pins SET plex_rating_key = ? WHERE id = ?",
                (plex_rating_key, pin_id),
            )

    def get_watchlist_pin(self, pin_id: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT * FROM watchlist_pins WHERE id = ?",
                    (pin_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM watchlist_pins WHERE id = ? AND user_id = ?",
                    (pin_id, user_id),
                ).fetchone()
        if row is None:
            return None
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
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        plex_rating_key = None
        if "plex_rating_key" in keys and row["plex_rating_key"] is not None:
            plex_rating_key = str(row["plex_rating_key"])
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "created_at": float(row["created_at"]),
            "plex_rating_key": plex_rating_key,
        }

    def create_recommendation(
        self,
        *,
        recommendation_id: str,
        from_user_id: str,
        to_user_id: str,
        media_type: str,
        title: str,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        rating_key: Optional[str] = None,
        year: Optional[int] = None,
        poster_url: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_recommendations (
                    id, from_user_id, to_user_id, media_type, tmdb_id, tvdb_id,
                    rating_key, title, year, poster_url, message, created_at, seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    recommendation_id,
                    from_user_id,
                    to_user_id,
                    media_type,
                    tmdb_id,
                    tvdb_id,
                    rating_key,
                    title,
                    year,
                    poster_url,
                    message,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM user_recommendations WHERE id = ?",
                (recommendation_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_recommendation(row)

    def list_recommendations_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT r.*,
                   COALESCE(fu.preferred_name, fu.display_name) AS from_display_name,
                   fu.avatar_url AS from_avatar_url
            FROM user_recommendations r
            LEFT JOIN users fu ON fu.id = r.from_user_id
            WHERE r.to_user_id = ?
        """
        params: List[Any] = [user_id]
        if unread_only:
            query += " AND r.seen_at IS NULL"
        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_recommendation(row) for row in rows]

    def count_unread_recommendations(self, user_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM user_recommendations
                WHERE to_user_id = ? AND seen_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def mark_recommendations_seen(
        self,
        user_id: str,
        *,
        recommendation_ids: Optional[Sequence[str]] = None,
        all_unread: bool = False,
    ) -> int:
        now = time.time()
        with self.connect() as conn:
            if all_unread:
                cursor = conn.execute(
                    """
                    UPDATE user_recommendations
                    SET seen_at = ?
                    WHERE to_user_id = ? AND seen_at IS NULL
                    """,
                    (now, user_id),
                )
                return int(cursor.rowcount or 0)
            ids = [str(i).strip() for i in (recommendation_ids or []) if str(i).strip()]
            if not ids:
                return 0
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"""
                UPDATE user_recommendations
                SET seen_at = ?
                WHERE to_user_id = ? AND seen_at IS NULL AND id IN ({placeholders})
                """,
                (now, user_id, *ids),
            )
            return int(cursor.rowcount or 0)

    @staticmethod
    def _row_to_recommendation(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return {
            "id": str(row["id"]),
            "from_user_id": str(row["from_user_id"]),
            "to_user_id": str(row["to_user_id"]),
            "media_type": str(row["media_type"]),
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "rating_key": str(row["rating_key"]) if row["rating_key"] is not None else None,
            "title": str(row["title"]),
            "year": int(row["year"]) if row["year"] is not None else None,
            "poster_url": str(row["poster_url"]) if row["poster_url"] is not None else None,
            "message": str(row["message"]) if row["message"] is not None else None,
            "created_at": float(row["created_at"]),
            "seen_at": float(row["seen_at"]) if row["seen_at"] is not None else None,
            "from_display_name": (
                str(row["from_display_name"])
                if "from_display_name" in keys and row["from_display_name"] is not None
                else None
            ),
            "from_avatar_url": (
                str(row["from_avatar_url"])
                if "from_avatar_url" in keys and row["from_avatar_url"] is not None
                else None
            ),
        }

    def list_curated_lists(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.user_id IS NULL
                    ORDER BY l.updated_at DESC, l.created_at DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.user_id = ?
                    ORDER BY l.updated_at DESC, l.created_at DESC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_curated_list(row) for row in rows]

    def get_curated_list(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        include_items: bool = False,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.id = ? AND l.user_id IS NULL
                    """,
                    (list_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT l.*, (
                        SELECT COUNT(*) FROM curated_list_items i WHERE i.list_id = l.id
                    ) AS item_count
                    FROM curated_lists l
                    WHERE l.id = ? AND l.user_id = ?
                    """,
                    (list_id, user_id),
                ).fetchone()
            if row is None:
                return None
            payload = self._row_to_curated_list(row)
            if include_items:
                items = conn.execute(
                    """
                    SELECT * FROM curated_list_items
                    WHERE list_id = ?
                    ORDER BY position ASC, created_at ASC
                    """,
                    (list_id,),
                ).fetchall()
                payload["items"] = [self._row_to_curated_list_item(item) for item in items]
            return payload

    def create_curated_list(
        self,
        *,
        list_id: str,
        user_id: Optional[str],
        name: str,
        description: str = "",
    ) -> Dict[str, Any]:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("name is required")
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM curated_lists
                WHERE name = ?
                  AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                  )
                """,
                (cleaned, user_id, user_id),
            ).fetchone()
            if existing is not None:
                raise ValueError("A list with that name already exists")
            conn.execute(
                """
                INSERT INTO curated_lists (id, user_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (list_id, user_id, cleaned, (description or "").strip(), now, now),
            )
            row = conn.execute(
                """
                SELECT l.*, 0 AS item_count
                FROM curated_lists l
                WHERE l.id = ?
                """,
                (list_id,),
            ).fetchone()
        assert row is not None
        return self._row_to_curated_list(row)

    def update_curated_list(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if name is None and description is None:
            raise ValueError("No list fields to update")
        cleaned_name = name.strip() if name is not None else None
        if cleaned_name is not None and not cleaned_name:
            raise ValueError("name cannot be empty")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                existing = conn.execute(
                    "SELECT * FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT * FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if existing is None:
                return None
            next_name = cleaned_name if cleaned_name is not None else str(existing["name"])
            next_description = (
                description.strip() if description is not None else str(existing["description"] or "")
            )
            if cleaned_name is not None and cleaned_name != str(existing["name"]):
                conflict = conn.execute(
                    """
                    SELECT id FROM curated_lists
                    WHERE name = ?
                      AND id != ?
                      AND (
                        (user_id IS NULL AND ? IS NULL) OR user_id = ?
                      )
                    """,
                    (cleaned_name, list_id, user_id, user_id),
                ).fetchone()
                if conflict is not None:
                    raise ValueError("A list with that name already exists")
            conn.execute(
                """
                UPDATE curated_lists
                SET name = ?, description = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_name, next_description, now, list_id),
            )
        return self.get_curated_list(list_id, user_id=user_id, include_items=False)

    def delete_curated_list(self, list_id: str, *, user_id: Optional[str] = None) -> bool:
        with self.connect() as conn:
            if user_id is None:
                row = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM curated_list_items WHERE list_id = ?", (list_id,))
            conn.execute("DELETE FROM curated_lists WHERE id = ?", (list_id,))
            return True

    def add_curated_list_item(
        self,
        *,
        item_id: str,
        list_id: str,
        user_id: Optional[str],
        tmdb_id: Optional[int],
        tvdb_id: Optional[int],
        media_type: str,
        title: str,
        library_item_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise ValueError("title is required")
        if media_type not in {"movie", "show"}:
            raise ValueError("media_type must be movie or show")
        if tmdb_id is None and tvdb_id is None:
            raise ValueError("tmdb_id or tvdb_id is required")
        now = time.time()
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                raise ValueError("List not found")
            resolved_library_id = library_item_id
            if resolved_library_id is None:
                if media_type == "movie" and tmdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'movie' AND tmdb_id = ? LIMIT 1",
                        (int(tmdb_id),),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
                elif media_type == "show" and tvdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = 'show' AND tvdb_id = ? LIMIT 1",
                        (int(tvdb_id),),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
                elif tmdb_id is not None:
                    lib = conn.execute(
                        "SELECT id FROM library_items WHERE media_type = ? AND tmdb_id = ? LIMIT 1",
                        (media_type, int(tmdb_id)),
                    ).fetchone()
                    if lib is not None:
                        resolved_library_id = int(lib["id"])
            position_row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM curated_list_items WHERE list_id = ?",
                (list_id,),
            ).fetchone()
            position = int(position_row["next_pos"] or 0) if position_row else 0
            conn.execute(
                """
                INSERT INTO curated_list_items (
                    id, list_id, tmdb_id, tvdb_id, media_type, title,
                    library_item_id, position, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                """,
                (
                    item_id,
                    list_id,
                    tmdb_id,
                    tvdb_id,
                    media_type,
                    cleaned_title,
                    resolved_library_id,
                    position,
                    now,
                ),
            )
            conn.execute(
                "UPDATE curated_lists SET updated_at = ? WHERE id = ?",
                (now, list_id),
            )
            row = conn.execute(
                """
                SELECT * FROM curated_list_items
                WHERE list_id = ?
                  AND media_type = ?
                  AND COALESCE(tmdb_id, -1) = COALESCE(?, -1)
                  AND COALESCE(tvdb_id, -1) = COALESCE(?, -1)
                """,
                (list_id, media_type, tmdb_id, tvdb_id),
            ).fetchone()
        if row is None:
            raise ValueError("Could not save list item")
        return self._row_to_curated_list_item(row)

    def delete_curated_list_item(
        self,
        list_id: str,
        item_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> bool:
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                return False
            row = conn.execute(
                "SELECT id FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "DELETE FROM curated_list_items WHERE id = ? AND list_id = ?",
                (item_id, list_id),
            )
            conn.execute(
                "UPDATE curated_lists SET updated_at = ? WHERE id = ?",
                (time.time(), list_id),
            )
            return True

    def find_curated_list_item(
        self,
        list_id: str,
        *,
        user_id: Optional[str] = None,
        item_id: Optional[str] = None,
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        media_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id IS NULL",
                    (list_id,),
                ).fetchone()
            else:
                owned = conn.execute(
                    "SELECT id FROM curated_lists WHERE id = ? AND user_id = ?",
                    (list_id, user_id),
                ).fetchone()
            if owned is None:
                return None
            if item_id:
                row = conn.execute(
                    "SELECT * FROM curated_list_items WHERE id = ? AND list_id = ?",
                    (item_id, list_id),
                ).fetchone()
                return self._row_to_curated_list_item(row) if row else None
            rows = conn.execute(
                "SELECT * FROM curated_list_items WHERE list_id = ? ORDER BY position ASC, created_at ASC",
                (list_id,),
            ).fetchall()
        for row in rows:
            item = self._row_to_curated_list_item(row)
            if media_type and item["media_type"] != media_type:
                continue
            if tmdb_id is not None and item.get("tmdb_id") == int(tmdb_id):
                return item
            if tvdb_id is not None and item.get("tvdb_id") == int(tvdb_id):
                return item
            if title and item["title"].strip().lower() == title.strip().lower():
                return item
        return None

    @staticmethod
    def _row_to_curated_list(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        item_count = int(row["item_count"]) if "item_count" in keys and row["item_count"] is not None else 0
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "item_count": item_count,
        }

    @staticmethod
    def _row_to_curated_list_item(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        library_item_id = None
        if "library_item_id" in keys and row["library_item_id"] is not None:
            library_item_id = int(row["library_item_id"])
        return {
            "id": str(row["id"]),
            "list_id": str(row["list_id"]),
            "tmdb_id": int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
            "tvdb_id": int(row["tvdb_id"]) if row["tvdb_id"] is not None else None,
            "media_type": str(row["media_type"]),
            "title": str(row["title"]),
            "library_item_id": library_item_id,
            "position": int(row["position"] or 0),
            "created_at": float(row["created_at"]),
        }
