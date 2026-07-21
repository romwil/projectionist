"""SQLite database for library index, chat, preferences, lenses, and embeddings."""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Callable, Optional, TypeVar

def _optional_int_col(row: sqlite3.Row, keys: set, name: str) -> Optional[int]:
    """Read an optional integer column that may be missing on older schemas."""
    if name in keys and row[name] is not None:
        try:
            return int(row[name])
        except (TypeError, ValueError):
            return None
    return None


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

logger = logging.getLogger("curatorx.library.db")
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

