"""Shared test infrastructure for CuratorX tests.

Provides fixtures and helpers that eliminate copy-pasted setup across test files.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pytest

from curatorx.agent.tools import ToolRegistry
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database


# ---------------------------------------------------------------------------
# Dataset constants — canonical test items with explicit defaults
# ---------------------------------------------------------------------------

UNWATCHED_HIGH_RATED: Dict[str, Any] = {
    "rating_key": "unwatched_high",
    "media_type": "movie",
    "title": "Unwatched High Rated",
    "year": 2018,
    "genres": ["Drama", "Thriller"],
    "vote_average": 8.5,
    "runtime_minutes": 120,
    "view_count": 0,
    "last_viewed_at": None,
    "file_size": 2_000_000_000,
}

WATCHED_HIGH_RATED: Dict[str, Any] = {
    "rating_key": "watched_high",
    "media_type": "movie",
    "title": "Watched High Rated",
    "year": 2015,
    "genres": ["Action", "Sci-Fi"],
    "vote_average": 8.2,
    "runtime_minutes": 140,
    "view_count": 3,
    "last_viewed_at": 1700000000,
    "file_size": 3_000_000_000,
}

UNWATCHED_LOW_RATED: Dict[str, Any] = {
    "rating_key": "unwatched_low",
    "media_type": "movie",
    "title": "Unwatched Low Rated",
    "year": 2020,
    "genres": ["Horror"],
    "vote_average": 4.2,
    "runtime_minutes": 90,
    "view_count": 0,
    "last_viewed_at": None,
    "file_size": 1_500_000_000,
}

NULL_RATING: Dict[str, Any] = {
    "rating_key": "null_rating",
    "media_type": "movie",
    "title": "No Rating Movie",
    "year": 2019,
    "genres": ["Comedy"],
    "vote_average": None,
    "runtime_minutes": 105,
    "view_count": 0,
    "last_viewed_at": None,
    "file_size": 1_200_000_000,
}

BOUNDARY_RUNTIME_120: Dict[str, Any] = {
    "rating_key": "boundary_120",
    "media_type": "movie",
    "title": "Exactly Two Hours",
    "year": 2021,
    "genres": ["Drama"],
    "vote_average": 7.0,
    "runtime_minutes": 120,
    "view_count": 0,
    "last_viewed_at": None,
    "file_size": 2_500_000_000,
}

NULL_RUNTIME: Dict[str, Any] = {
    "rating_key": "null_runtime",
    "media_type": "movie",
    "title": "No Runtime Movie",
    "year": 2017,
    "genres": ["Documentary"],
    "vote_average": 7.5,
    "runtime_minutes": None,
    "view_count": 0,
    "last_viewed_at": None,
    "file_size": 800_000_000,
}

NULL_YEAR: Dict[str, Any] = {
    "rating_key": "null_year",
    "media_type": "movie",
    "title": "Unknown Year Movie",
    "year": None,
    "genres": ["Mystery"],
    "vote_average": 6.5,
    "runtime_minutes": 95,
    "view_count": 1,
    "last_viewed_at": None,
    "file_size": 1_000_000_000,
}

STALE_WATCHED: Dict[str, Any] = {
    "rating_key": "stale_watched",
    "media_type": "movie",
    "title": "Stale Watched Movie",
    "year": 2005,
    "genres": ["Drama"],
    "vote_average": 6.0,
    "runtime_minutes": 130,
    "view_count": 1,
    "last_viewed_at": 1500000000,  # ~2017
    "file_size": 4_000_000_000,
}

SHOW_ITEM: Dict[str, Any] = {
    "rating_key": "show_1",
    "media_type": "show",
    "title": "Test TV Show",
    "year": 2022,
    "genres": ["Drama", "Crime"],
    "vote_average": 8.8,
    "runtime_minutes": 55,
    "view_count": 5,
    "last_viewed_at": 1700000000,
    "file_size": 10_000_000_000,
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def seed_library(db: Database, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Seed library_items with explicit defaults for every nullable column.

    Returns the list of inserted item dicts (with defaults applied) for
    cross-referencing in assertions.
    """
    defaults: Dict[str, Any] = {
        "vote_average": None,
        "runtime_minutes": None,
        "last_viewed_at": None,
        "year": None,
        "genres": [],
        "view_count": 0,
        "media_type": "movie",
        "file_size": 0,
        "summary": "",
    }
    inserted: List[Dict[str, Any]] = []
    for item in items:
        full_item = {**defaults, **item}
        if "title" not in full_item:
            raise ValueError("title is required for seed_library items")
        db.upsert_library_item(full_item)
        inserted.append(full_item)
    return inserted


def make_tool_registry(
    db: Database,
    *,
    tmdb_api_key: str = "fake-tmdb-key",
    lens_id: str = DEFAULT_LENS_ID,
    **overrides: Any,
) -> ToolRegistry:
    """Build a ToolRegistry with test-safe defaults."""
    settings_kwargs: Dict[str, Any] = {
        "tmdb_api_key": tmdb_api_key,
        "tautulli_url": "",
        "tautulli_api_key": "",
    }
    settings_kwargs.update(overrides)
    settings = Settings(**settings_kwargs)
    return ToolRegistry(db, settings, lens_id)


async def execute_tool(
    registry: ToolRegistry,
    tool_name: str,
    args_dict: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Call a tool and return parsed JSON result."""
    raw = await registry.execute(tool_name, args_dict or {})
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_db(tmp_path: Path) -> Database:
    """Ephemeral SQLite DB with schema bootstrapped."""
    return Database(tmp_path / "test.db")
