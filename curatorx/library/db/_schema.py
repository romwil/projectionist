"""Schema creation, migrations, and default/seed data.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import (
    Optional,
)

from ._shared import (
    ACTIVE_CONTEXT_CONFIG_KEY,
    ACTIVE_LENS_CONFIG_KEY,
    BOOTSTRAP_OWNER_ID,
    BUILTIN_PERSONA_SEEDS,
    CURATOR_NAME_CONFIG_KEY,
    DEFAULT_CONTEXT_HASH,
    DEFAULT_LENS_ID,
    DEFAULT_PERSONA_ID,
    SCHEMA,
    run_with_db_lock_retry,
)


class SchemaMigrationsMixin:
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
            self._migrate_grooming_action_log(conn)
            self._migrate_weekly_digests(conn)
            self._migrate_media_issues(conn)
            self._migrate_persona_templates(conn)
            self._migrate_recommendations(conn)
            self._migrate_notifications(conn)
            self._migrate_taste_engagement(conn)
            self._migrate_access_requests(conn)
            self._migrate_saved_library(conn)
            self._migrate_library_metadata_enrichment(conn)
            self._migrate_people_credits(conn)
            self._migrate_plot_text_columns(conn)
            self._migrate_long_synopsis_columns(conn)
            self._migrate_embeddings_model(conn)
            self._migrate_item_neighbors(conn)
            self._migrate_title_relations(conn)
            self._migrate_curator_memory(conn)
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

    def _migrate_curator_memory(self, conn: sqlite3.Connection) -> None:
        """Install the v1.8.29 dual-scope memory model and migrate preferences."""
        user_cols = self._table_columns(conn, "users")
        if "is_youth" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_youth INTEGER NOT NULL DEFAULT 0")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_entities (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL CHECK (entity_type IN ('person','company','title','location','other')),
                name TEXT NOT NULL,
                external_ids_json TEXT NOT NULL DEFAULT '{}',
                library_item_id INTEGER,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                archived_at REAL,
                UNIQUE(entity_type, name)
            );
            CREATE TABLE IF NOT EXISTS memory_snapshots (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES memory_entities(id),
                payload_json TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                fetched_at REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_relations (
                id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL REFERENCES memory_entities(id),
                target_entity_id TEXT NOT NULL REFERENCES memory_entities(id),
                relation_type TEXT NOT NULL,
                snapshot_id TEXT REFERENCES memory_snapshots(id),
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_insights (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES memory_entities(id),
                insight TEXT NOT NULL,
                citations_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                archived_at REAL
            );
            CREATE TABLE IF NOT EXISTS memory_entity_activity (
                entity_id TEXT PRIMARY KEY REFERENCES memory_entities(id),
                discussion_count INTEGER NOT NULL DEFAULT 0,
                last_discussed_at REAL
            );
            CREATE TABLE IF NOT EXISTS user_memory_notes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                archived_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_user_memory_notes_user ON user_memory_notes(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS user_memory_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                target_id TEXT,
                created_at REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        # Preference facts are retained only as a rollback compatibility source.
        # The id prefix makes this migration idempotent on every startup.
        pref_cols = self._table_columns(conn, "preference_facts")
        if "user_id" in pref_cols:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_memory_notes
                    (id, user_id, kind, text, metadata_json, created_at, updated_at)
                SELECT 'pref-' || id, user_id, 'preference', text,
                       json_object('signal_type', signal_type, 'weight', weight,
                                   'tmdb_id', tmdb_id, 'tvdb_id', tvdb_id, 'media_type', media_type),
                       created_at, created_at
                FROM preference_facts
                WHERE user_id IS NOT NULL
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

    def _migrate_long_synopsis_columns(self, conn: sqlite3.Connection) -> None:
        """Optional longer plot text from Wikipedia/OMDb (never overwrites Plex/TMDB).

        Written only by ``long_synopsis_enrichment`` via ``set_long_synopsis``.
        Not part of library upsert — sync cannot clobber or invent these fields.
        """
        cols = self._table_columns(conn, "library_items")
        for name, typedef in {
            "long_synopsis": "TEXT DEFAULT ''",
            "synopsis_source": "TEXT DEFAULT ''",
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
                "watchlist_last_pull_total": "INTEGER",
                "watchlist_last_pull_added": "INTEGER",
                "watchlist_last_pull_updated": "INTEGER",
                "watchlist_last_pull_unresolved": "INTEGER",
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
        cols = self._table_columns(conn, "curated_lists")
        if "list_kind" not in cols:
            conn.execute(
                "ALTER TABLE curated_lists ADD COLUMN list_kind TEXT NOT NULL DEFAULT 'list'"
            )
        conn.execute(
            "UPDATE curated_lists SET list_kind = 'list' "
            "WHERE list_kind IS NULL OR list_kind NOT IN ('list', 'playlist', 'course')"
        )
        # Collections/courses (M4): owner can publish a list to household members and
        # sequence it as an ordered "course" with a note per step.
        if "visibility" not in cols:
            conn.execute(
                "ALTER TABLE curated_lists ADD COLUMN visibility TEXT NOT NULL DEFAULT 'private'"
            )
        if "published_at" not in cols:
            conn.execute("ALTER TABLE curated_lists ADD COLUMN published_at REAL")
        conn.execute(
            "UPDATE curated_lists SET visibility = 'private' "
            "WHERE visibility IS NULL OR visibility NOT IN ('private', 'published')"
        )
        item_cols = self._table_columns(conn, "curated_list_items")
        if "note" not in item_cols:
            conn.execute("ALTER TABLE curated_list_items ADD COLUMN note TEXT NOT NULL DEFAULT ''")

    def _migrate_grooming_action_log(self, conn: sqlite3.Connection) -> None:
        """Reversible action log for destructive bulk grooming (M4 safe undo)."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS grooming_action_log (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                actor_user_id TEXT,
                summary TEXT NOT NULL DEFAULT '',
                item_count INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                undone_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_grooming_action_log_created
            ON grooming_action_log(created_at DESC);
            """
        )

    def _migrate_weekly_digests(self, conn: sqlite3.Connection) -> None:
        """Weekly library digest snapshots (M4 in-app digest)."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS weekly_digests (
                id TEXT PRIMARY KEY,
                week_start REAL NOT NULL,
                generated_at REAL NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_digests_week_start
            ON weekly_digests(week_start);
            CREATE INDEX IF NOT EXISTS idx_weekly_digests_generated
            ON weekly_digests(generated_at DESC);
            """
        )

    def _migrate_media_issues(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS media_issues (
                id TEXT PRIMARY KEY,
                reporter_user_id TEXT,
                rating_key TEXT,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                media_type TEXT NOT NULL CHECK (media_type IN ('movie', 'show')),
                title TEXT NOT NULL,
                code TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'approved', 'repairing', 'resolved', 'rejected')),
                repair_action TEXT NOT NULL DEFAULT '',
                repair_log TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                resolved_at REAL,
                FOREIGN KEY (reporter_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_media_issues_status ON media_issues(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_media_issues_reporter ON media_issues(reporter_user_id);
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

    def _migrate_notifications(self, conn: sqlite3.Connection) -> None:
        """Generalized notification inbox + per-user mail/channel prefs."""
        user_cols = self._table_columns(conn, "users")
        if user_cols:
            notify_cols = {
                "notification_email": "TEXT",
                "notify_channel_inbox": "INTEGER NOT NULL DEFAULT 1",
                "notify_channel_email": "INTEGER NOT NULL DEFAULT 0",
                "newsletter_opt_in": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, typedef in notify_cols.items():
                if name not in user_cols:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_notifications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (
                    kind IN ('recommendation', 'arrival', 'access-request', 'digest', 'nudge')
                ),
                title TEXT NOT NULL,
                body TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                media_type TEXT,
                tmdb_id INTEGER,
                tvdb_id INTEGER,
                rating_key TEXT,
                year INTEGER,
                poster_url TEXT,
                from_user_id TEXT,
                related_id TEXT,
                created_at REAL NOT NULL,
                seen_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (from_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_user_notifications_user
                ON user_notifications(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_user_notifications_unread
                ON user_notifications(user_id, seen_at);
            CREATE INDEX IF NOT EXISTS idx_user_notifications_related
                ON user_notifications(user_id, kind, related_id);
            """
        )

    def _migrate_taste_engagement(self, conn: sqlite3.Connection) -> None:
        """Member taste overrides, weekly rails, and engagement substrate (P3c)."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_taste_profile (
                user_id TEXT NOT NULL,
                cluster_tag TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 0.5,
                explicit_lock INTEGER NOT NULL DEFAULT 0,
                last_updated REAL NOT NULL,
                PRIMARY KEY (user_id, cluster_tag),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_taste_profile_user
                ON user_taste_profile(user_id, weight DESC);

            CREATE TABLE IF NOT EXISTS user_weekly_rails (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                week_bucket INTEGER NOT NULL,
                title TEXT NOT NULL,
                voice_line TEXT,
                items_json TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL,
                UNIQUE (user_id, week_bucket),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_weekly_rails_user
                ON user_weekly_rails(user_id, week_bucket DESC);

            CREATE TABLE IF NOT EXISTS engagement_badges (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                criteria_json TEXT NOT NULL DEFAULT '{}',
                youth_safe INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_badges (
                user_id TEXT NOT NULL,
                badge_id TEXT NOT NULL,
                earned_at REAL NOT NULL,
                PRIMARY KEY (user_id, badge_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (badge_id) REFERENCES engagement_badges(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_streaks (
                user_id TEXT NOT NULL,
                streak_kind TEXT NOT NULL,
                current_count INTEGER NOT NULL DEFAULT 0,
                best_count INTEGER NOT NULL DEFAULT 0,
                last_event_at REAL,
                PRIMARY KEY (user_id, streak_kind),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS engagement_challenges (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                target_count INTEGER NOT NULL DEFAULT 5,
                youth_safe INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_challenge_progress (
                user_id TEXT NOT NULL,
                challenge_id TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                completed_at REAL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, challenge_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (challenge_id) REFERENCES engagement_challenges(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS engagement_explainers (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                body_md TEXT NOT NULL DEFAULT '',
                related_tag TEXT,
                youth_safe INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_course_progress (
                user_id TEXT NOT NULL,
                list_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                completed_at REAL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, list_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        self._seed_engagement_defaults(conn)

    def _seed_engagement_defaults(self, conn: sqlite3.Connection) -> None:
        """Insert default badges, challenges, and explainers (idempotent)."""
        import time as _time

        now = _time.time()
        badges = (
            (
                "badge-first-review",
                "first-review",
                "First review",
                "You rated a title — taste starts here.",
                '{"event":"review","min_count":1}',
                1,
            ),
            (
                "badge-rate-5",
                "rate-5",
                "Five stars of opinions",
                "Rated five titles. Your lens is sharpening.",
                '{"event":"review","min_count":5}',
                1,
            ),
            (
                "badge-genre-explorer",
                "genre-explorer",
                "Genre explorer",
                "Touched three different genres in reviews.",
                '{"event":"genre_diversity","min_count":3}',
                1,
            ),
            (
                "badge-course-starter",
                "course-starter",
                "Course starter",
                "Began a curated cinema course.",
                '{"event":"course_progress","min_count":1}',
                1,
            ),
            (
                "badge-chat-streak-3",
                "chat-streak-3",
                "Three-day chat streak",
                "Talked with the curator three days in a row.",
                '{"event":"chat_streak","min_count":3}',
                1,
            ),
            (
                "badge-story-explorer",
                "story-explorer",
                "Story explorer",
                "Asked the curator about three different titles.",
                '{"event":"chat_streak","min_count":2}',
                1,
            ),
            (
                "badge-family-picks",
                "family-picks",
                "Family picks starter",
                "Rated three age-friendly titles.",
                '{"event":"review","min_count":3}',
                1,
            ),
        )
        for badge_id, slug, name, description, criteria, youth_safe in badges:
            conn.execute(
                """
                INSERT OR IGNORE INTO engagement_badges (
                    id, slug, name, description, criteria_json, youth_safe, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (badge_id, slug, name, description, criteria, youth_safe, now),
            )
        challenges = (
            (
                "challenge-rate-3",
                "rate-3-films",
                "rate_n",
                "Rate 3 films",
                "Share stars on three titles you liked.",
                3,
                1,
            ),
            (
                "challenge-rate-5",
                "rate-5-films",
                "rate_n",
                "Rate 5 films",
                "Leave a star rating on five titles you have watched.",
                5,
                1,
            ),
            (
                "challenge-rate-10",
                "rate-10-films",
                "rate_n",
                "Rate 10 films",
                "A deeper pass — ten ratings to tune your taste profile.",
                10,
                0,
            ),
        )
        # Adult-only challenge: flip youth_safe if an older seed already inserted it.
        conn.execute(
            "UPDATE engagement_challenges SET youth_safe = 0 WHERE slug = 'rate-10-films'"
        )
        for challenge_id, slug, kind, title, description, target, youth_safe in challenges:
            conn.execute(
                """
                INSERT OR IGNORE INTO engagement_challenges (
                    id, slug, kind, title, description, target_count, youth_safe, active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (challenge_id, slug, kind, title, description, target, youth_safe, now),
            )
        explainers = (
            (
                "explainer-taste-weights",
                "taste-weights",
                "How taste weights work",
                (
                    "CuratorX learns cluster tags (genres, moods, eras) from your reviews "
                    "and chat feedback. **Locked** weights stay put when the scheduler "
                    "refreshes — unlock to let telemetry drift again."
                ),
                "taste",
                1,
            ),
            (
                "explainer-cinema-courses",
                "cinema-courses",
                "What is a cinema course?",
                (
                    "A **course** is a curated list your owner published in order, with a "
                    "short note on each step — like a film-school syllabus for your shelves."
                ),
                "course",
                1,
            ),
            (
                "explainer-weekly-rail",
                "weekly-for-you",
                "Your weekly For you rail",
                (
                    "Once a week CuratorX picks unwatched titles that match your taste "
                    "clusters and writes a short persona-voiced *why* for each pick."
                ),
                "rail",
                1,
            ),
            (
                "explainer-ask-curator",
                "ask-the-curator",
                "Ask the curator (Youth)",
                (
                    "You can ask for something fun to watch, a movie like one you loved, "
                    "or a gentle surprise. The curator only suggests titles that fit your "
                    "household's Youth rating rules."
                ),
                "youth",
                1,
            ),
            (
                "explainer-youth-ratings",
                "youth-content-ratings",
                "Why some titles stay hidden",
                (
                    "Youth mode hides titles without a content rating and anything above "
                    "the max rating your owner set — so Explore and Chat stay age-friendly."
                ),
                "youth",
                1,
            ),
        )
        for explainer_id, slug, title, body, tag, youth_safe in explainers:
            conn.execute(
                """
                INSERT OR IGNORE INTO engagement_explainers (
                    id, slug, title, body_md, related_tag, youth_safe, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (explainer_id, slug, title, body, tag, youth_safe, now),
            )

    def _migrate_access_requests(self, conn: sqlite3.Connection) -> None:
        """CuratorX-owned guest request-access queue (Delight Phase 4)."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS access_requests (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                email TEXT,
                message TEXT,
                status TEXT NOT NULL CHECK (
                    status IN ('pending', 'approved', 'denied')
                ),
                created_at REAL NOT NULL,
                resolved_at REAL,
                resolved_by TEXT,
                created_user_id TEXT,
                FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (created_user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_access_requests_status
                ON access_requests(status, created_at DESC);
            """
        )

    def _migrate_saved_library(self, conn: sqlite3.Connection) -> None:
        """Saved curator responses, private to the user who saved them."""
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS saved_library_pages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                source_session_id TEXT,
                source_message_id TEXT,
                persona_id TEXT,
                summary TEXT,
                searchable_text TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_saved_library_pages_user_created
                ON saved_library_pages(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_saved_library_pages_user_name
                ON saved_library_pages(user_id, name);
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(saved_library_pages)").fetchall()}
        if "persona_id" not in columns:
            conn.execute("ALTER TABLE saved_library_pages ADD COLUMN persona_id TEXT")
        if "summary" not in columns:
            conn.execute("ALTER TABLE saved_library_pages ADD COLUMN summary TEXT")

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

