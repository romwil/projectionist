"""Ordered SQLite schema migrations (Architecture A — M2).

Historical ``_migrate_*`` helpers remain the implementation bodies; this module
is the source of truth for *order* and *applied versions* via ``schema_version``.
New integrity steps (orphan cleanup, FK readiness, stub drops) land here as
numbered migrations rather than more ad-hoc boot calls.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import TYPE_CHECKING, Callable, List, Sequence, Tuple

from ._shared import SCHEMA

if TYPE_CHECKING:
    from ._schema import SchemaMigrationsMixin

logger = logging.getLogger(__name__)

MigrationFn = Callable[["SchemaMigrationsMixin", sqlite3.Connection], None]
Migration = Tuple[int, str, MigrationFn]


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at REAL NOT NULL
        )
        """
    )


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {int(row[0]) for row in rows}


def _record_version(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_version (version, name, applied_at)
        VALUES (?, ?, ?)
        """,
        (version, name, time.time()),
    )


def _cleanup_fk_orphans(db: "SchemaMigrationsMixin", conn: sqlite3.Connection) -> None:
    """Delete rows that would violate declared FOREIGN KEY clauses (M1 audit)."""
    del db
    statements: Sequence[str] = (
        "DELETE FROM chat_messages WHERE session_id NOT IN (SELECT id FROM chat_sessions)",
        "DELETE FROM message_feedback WHERE message_id NOT IN (SELECT id FROM chat_messages)",
        "DELETE FROM message_feedback WHERE session_id NOT IN (SELECT id FROM chat_sessions)",
        "DELETE FROM message_feedback WHERE user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users)",
        "DELETE FROM lens_taste_profile WHERE lens_id NOT IN (SELECT lens_id FROM curation_lenses)",
        "DELETE FROM interaction_telemetry WHERE lens_id NOT IN (SELECT lens_id FROM curation_lenses)",
        "DELETE FROM system_telemetry_stream WHERE associated_context_hash IS NOT NULL "
        "AND associated_context_hash NOT IN (SELECT context_hash FROM derived_contexts)",
        "DELETE FROM memory_snapshots WHERE entity_id NOT IN (SELECT id FROM memory_entities)",
        "DELETE FROM memory_relations WHERE source_entity_id NOT IN (SELECT id FROM memory_entities)",
        "DELETE FROM memory_relations WHERE target_entity_id NOT IN (SELECT id FROM memory_entities)",
        "DELETE FROM memory_insights WHERE entity_id NOT IN (SELECT id FROM memory_entities)",
        "DELETE FROM memory_entity_activity WHERE entity_id NOT IN (SELECT id FROM memory_entities)",
        "DELETE FROM user_memory_notes WHERE user_id NOT IN (SELECT id FROM users)",
        "DELETE FROM library_episodes WHERE item_id NOT IN (SELECT id FROM library_items)",
    )
    _run_orphan_deletes(conn, statements)


def _cleanup_library_graph_fk_orphans(
    db: "SchemaMigrationsMixin", conn: sqlite3.Connection
) -> None:
    """Remove library-graph orphans that break title_relations rebuild under FK ON.

    Migration 34 cleaned chat/memory/episodes but not item_neighbors / credits /
    title_relations / embeddings. Legacy rows (written before PRAGMA foreign_keys=ON)
    made ``title_relations_refresh`` fail with FOREIGN KEY constraint failed.
    """
    del db
    statements: Sequence[str] = (
        "DELETE FROM item_neighbors WHERE item_id NOT IN (SELECT id FROM library_items)",
        "DELETE FROM item_neighbors WHERE neighbor_id NOT IN (SELECT id FROM library_items)",
        "DELETE FROM title_relations WHERE from_id NOT IN (SELECT id FROM library_items)",
        "DELETE FROM title_relations WHERE to_id NOT IN (SELECT id FROM library_items)",
        "DELETE FROM credits WHERE item_id NOT IN (SELECT id FROM library_items)",
        "DELETE FROM credits WHERE person_id NOT IN (SELECT id FROM people)",
        "DELETE FROM embeddings WHERE item_id NOT IN (SELECT id FROM library_items)",
    )
    _run_orphan_deletes(conn, statements)


def _run_orphan_deletes(conn: sqlite3.Connection, statements: Sequence[str]) -> None:
    for sql in statements:
        try:
            cursor = conn.execute(sql)
            if cursor.rowcount:
                logger.info(
                    "FK orphan cleanup: %s → removed %s row(s)",
                    sql.split()[2],
                    cursor.rowcount,
                )
        except sqlite3.Error as error:
            logger.debug("FK orphan cleanup skipped (%s): %s", sql.split()[2], error)


def _rename_credential_marker(db: "SchemaMigrationsMixin", conn: sqlite3.Connection) -> None:
    """Rename service_integrations.api_token_encrypted → credential_marker."""
    cols = db._table_columns(conn, "service_integrations")
    if "api_token_encrypted" in cols and "credential_marker" not in cols:
        conn.execute(
            "ALTER TABLE service_integrations RENAME COLUMN api_token_encrypted TO credential_marker"
        )
        logger.info("Renamed service_integrations.api_token_encrypted → credential_marker")
    elif "credential_marker" not in cols and "api_token_encrypted" not in cols:
        conn.execute("ALTER TABLE service_integrations ADD COLUMN credential_marker TEXT")
    # Recreate view so it references credential_marker (CREATE VIEW IF NOT EXISTS is sticky).
    conn.execute("DROP VIEW IF EXISTS integration_profiles")
    conn.execute(
        """
        CREATE VIEW integration_profiles AS
        SELECT
            service_name AS service_id,
            base_url AS endpoint_url,
            credential_marker AS credential_encrypted,
            connection_status AS verification_state,
            last_tested_at AS synchronized_at
        FROM service_integrations
        """
    )

def _drop_agent_blueprints(db: "SchemaMigrationsMixin", conn: sqlite3.Connection) -> None:
    del db
    conn.execute("DROP TABLE IF EXISTS agent_blueprints")
    logger.info("Dropped unused agent_blueprints table")


def _build_migrations() -> List[Migration]:
    def wrap(method_name: str) -> MigrationFn:
        def _run(db: "SchemaMigrationsMixin", conn: sqlite3.Connection) -> None:
            getattr(db, method_name)(conn)

        return _run

    return [
        (1, "chat_lens_columns", wrap("_migrate_chat_lens_columns")),
        (2, "chat_thread_columns", wrap("_migrate_chat_thread_columns")),
        (3, "service_integrations_certified", wrap("_migrate_service_integrations_certified")),
        (4, "context_tables", wrap("_migrate_context_tables")),
        (5, "persona_columns", wrap("_migrate_persona_columns")),
        (6, "library_intelligence", wrap("_migrate_library_intelligence")),
        (7, "library_indexes", wrap("_migrate_library_indexes")),
        (8, "phase0_tables", wrap("_migrate_phase0_tables")),
        (9, "multi_user_columns_pre_phase4", wrap("_migrate_multi_user_columns")),
        (10, "phase4_tables", wrap("_migrate_phase4_tables")),
        (11, "multi_user_columns_post_phase4", wrap("_migrate_multi_user_columns")),
        (12, "rating_prompt_user_scope", wrap("_migrate_rating_prompt_user_scope")),
        (13, "embeddings_content_hash", wrap("_migrate_embeddings_content_hash")),
        (14, "curated_lists", wrap("_migrate_curated_lists")),
        (15, "grooming_action_log", wrap("_migrate_grooming_action_log")),
        (16, "weekly_digests", wrap("_migrate_weekly_digests")),
        (17, "media_issues", wrap("_migrate_media_issues")),
        (18, "persona_templates", wrap("_migrate_persona_templates")),
        (19, "recommendations", wrap("_migrate_recommendations")),
        (20, "notifications", wrap("_migrate_notifications")),
        (21, "taste_engagement", wrap("_migrate_taste_engagement")),
        (22, "access_requests", wrap("_migrate_access_requests")),
        (23, "invites", wrap("_migrate_invites")),
        (24, "saved_library", wrap("_migrate_saved_library")),
        (25, "library_metadata_enrichment", wrap("_migrate_library_metadata_enrichment")),
        (26, "people_credits", wrap("_migrate_people_credits")),
        (27, "plot_text_columns", wrap("_migrate_plot_text_columns")),
        (28, "long_synopsis_columns", wrap("_migrate_long_synopsis_columns")),
        (29, "embeddings_model", wrap("_migrate_embeddings_model")),
        (30, "item_neighbors", wrap("_migrate_item_neighbors")),
        (31, "title_relations", wrap("_migrate_title_relations")),
        (32, "curator_memory", wrap("_migrate_curator_memory")),
        (33, "ephemeral_plex_collections", wrap("_migrate_ephemeral_plex_collections")),
        (34, "fk_orphan_cleanup", _cleanup_fk_orphans),
        (35, "credential_marker_rename", _rename_credential_marker),
        (36, "drop_agent_blueprints", _drop_agent_blueprints),
        (37, "library_graph_fk_orphan_cleanup", _cleanup_library_graph_fk_orphans),
    ]


MIGRATIONS: List[Migration] = _build_migrations()
CURRENT_SCHEMA_VERSION = MIGRATIONS[-1][0] if MIGRATIONS else 0


def run_migrations(db: "SchemaMigrationsMixin", conn: sqlite3.Connection) -> None:
    """Apply SCHEMA bootstrap + ordered migrations; record versions."""
    _ensure_schema_version_table(conn)
    conn.executescript(SCHEMA)
    applied = _applied_versions(conn)
    for version, name, fn in MIGRATIONS:
        if version in applied:
            continue
        logger.debug("Applying schema migration %s: %s", version, name)
        fn(db, conn)
        _record_version(conn, version, name)
        applied.add(version)
    db._seed_defaults(conn)
    # Idempotent data backfill: custom singleton persona → shared template.
    # Must run every boot (not only migration 18) so values written after the
    # first open still migrate on the next Database() open.
    db._migrate_legacy_persona_to_template(conn)
