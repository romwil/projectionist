"""SQLite database for library index, chat, preferences, lenses, and embeddings.

This package is a behavior-preserving refactor of the former single-file
``curatorx/library/db.py``. The public surface is unchanged: ``Database`` and the
module-level constants/helpers are re-exported here, so existing imports such as
``from curatorx.library.db import Database, DEFAULT_LENS_ID`` continue to resolve.
The former one class is now composed from topic mixins (see the ``_*.py``
modules) purely for maintainability; method resolution is unaffected because
every method name is unique across the mixins.
"""

from __future__ import annotations

# ``time`` is imported here so tests that patch ``curatorx.library.db.time.sleep``
# (the SQLite lock-retry backoff) keep working against the package.
import time  # noqa: F401

from ._shared import (
    ACTIVE_CONTEXT_CONFIG_KEY,
    ACTIVE_LENS_CONFIG_KEY,
    BOOTSTRAP_OWNER_ID,
    BUILTIN_PERSONA_IDS,
    BUILTIN_PERSONA_SEEDS,
    CURATOR_NAME_CONFIG_KEY,
    DEFAULT_CONTEXT_HASH,
    DEFAULT_LENS_ID,
    DEFAULT_PERSONA_ID,
    SCHEMA,
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_LOCK_RETRIES,
    SQLITE_LOCK_RETRY_BASE_DELAY_S,
    SQLITE_SYNCHRONOUS,
    T,
    _is_db_locked,
    _optional_int_col,
    logger,
    run_with_db_lock_retry,
)
from ._schema import SchemaMigrationsMixin
from ._users import UsersAuthMixin
from ._library_items import LibraryItemsMixin
from ._enrichment import EnrichmentMixin
from ._library_query import LibraryQueryMixin
from ._grooming import GroomingDigestMixin
from ._library_lookup import LibraryLookupMixin
from ._memory import MemoryMixin
from ._telemetry import TelemetryConfigMixin
from ._persona import PersonaLensesMixin
from ._chat import ChatThreadsMixin
from ._saved_library import SavedLibraryMixin
from ._watchlist import WatchlistMixin
from ._recommendations import RecommendationsMixin
from ._notifications import NotificationsMixin
from ._engagement import EngagementMixin
from ._access_requests import AccessRequestsMixin
from ._curated_lists import CuratedListsMixin
from ._media_issues import MediaIssuesMixin


class Database(
    SchemaMigrationsMixin,
    UsersAuthMixin,
    LibraryItemsMixin,
    EnrichmentMixin,
    LibraryQueryMixin,
    GroomingDigestMixin,
    LibraryLookupMixin,
    MemoryMixin,
    TelemetryConfigMixin,
    PersonaLensesMixin,
    ChatThreadsMixin,
    SavedLibraryMixin,
    WatchlistMixin,
    RecommendationsMixin,
    NotificationsMixin,
    EngagementMixin,
    AccessRequestsMixin,
    CuratedListsMixin,
    MediaIssuesMixin,
):
    """Composed database facade — identical public API to the pre-split class."""


__all__ = [
    "Database",
    "run_with_db_lock_retry",
    "T",
    "_is_db_locked",
    "_optional_int_col",
    "logger",
    "ACTIVE_CONTEXT_CONFIG_KEY",
    "ACTIVE_LENS_CONFIG_KEY",
    "BOOTSTRAP_OWNER_ID",
    "BUILTIN_PERSONA_IDS",
    "BUILTIN_PERSONA_SEEDS",
    "CURATOR_NAME_CONFIG_KEY",
    "DEFAULT_CONTEXT_HASH",
    "DEFAULT_LENS_ID",
    "DEFAULT_PERSONA_ID",
    "SCHEMA",
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_LOCK_RETRIES",
    "SQLITE_LOCK_RETRY_BASE_DELAY_S",
    "SQLITE_SYNCHRONOUS",
]
