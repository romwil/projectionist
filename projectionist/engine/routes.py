"""Playback-engine HTTP routes (ENG-001+).

File paths never appear in responses. Owners store path mappings; members can
ask what the engine can read for a title.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.config_store import Settings, save_settings
from projectionist.engine.pathmap import PathMapError, normalize_mappings
from projectionist.engine.source import PlexMediaSource, public_media
from projectionist.library.playback import PlaybackError, validate_rating_key
from projectionist.web.auth import get_current_user_dep, require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playback-engine"])

_settings_factory: Optional[Callable[[], Settings]] = None
_db_factory: Optional[Callable[[], Any]] = None
_data_dir: Optional[Path] = None


class PathMappingsPayload(BaseModel):
    mappings: list[dict[str, str]] = Field(default_factory=list)


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("engine routes not registered")
    return _settings_factory()


def _db():
    if _db_factory is None:
        raise RuntimeError("engine routes not registered")
    return _db_factory()


def _dir() -> Path:
    if _data_dir is None:
        raise RuntimeError("engine routes not registered")
    return Path(_data_dir)


def plex_part_paths(settings: Settings, rating_key: str) -> list[str]:
    url = str(getattr(settings, "plex_url", "") or "").strip()
    token = str(getattr(settings, "plex_token", "") or "").strip()
    if not url or not token:
        return []
    from projectionist.connectors.plex import PlexClient

    client = PlexClient(url, token, timeout=10)
    return list(client.media_file_paths(rating_key, include_leaves=True))


def identity_from_db(db: Any, rating_key: str) -> dict[str, Any]:
    if db is None:
        return {}
    try:
        item = db.library_item_by_rating_key(rating_key)
    except Exception:  # noqa: BLE001 — identity is optional
        return {}
    if item is None:
        return {}
    keys = set(item.keys()) if hasattr(item, "keys") else set()
    tmdb = item["tmdb_id"] if "tmdb_id" in keys else None
    imdb = item["imdb_id"] if "imdb_id" in keys else ""
    return {"tmdb_id": tmdb, "imdb_id": str(imdb or "")}


def describe_title(settings: Settings, db: Any, data_dir: Path, rating_key: str):
    engine = getattr(settings, "engine", None)
    mappings = list(getattr(engine, "path_mappings", []) or [])
    source = PlexMediaSource(
        mappings=mappings,
        path_lookup=lambda key: plex_part_paths(settings, key),
        identity_lookup=lambda key: identity_from_db(db, key),
    )
    return source.locate(
        rating_key,
        cache_dir=Path(data_dir) / "engine" / "probes",
        runner=subprocess.run,
    )


def _replace_mappings(settings: Settings, mappings: list[dict[str, str]]) -> Settings:
    from dataclasses import asdict

    current = asdict(settings.engine)
    current["path_mappings"] = mappings
    updated = Settings.from_mapping({**asdict(settings), "engine": current})
    save_settings(_dir(), updated)
    return updated


@router.get("/api/playback/path-mappings")
def get_path_mappings(user=Depends(require_role("owner"))) -> dict[str, Any]:
    del user
    return {"mappings": list(_settings().engine.path_mappings)}


@router.put("/api/playback/path-mappings")
def put_path_mappings(
    payload: PathMappingsPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    del user
    try:
        mappings = normalize_mappings(payload.mappings)
    except PathMapError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    updated = _replace_mappings(_settings(), mappings)
    logger.info("engine path mappings updated count=%s", len(updated.engine.path_mappings))
    return {"mappings": list(updated.engine.path_mappings)}


@router.get("/api/playback/media/{rating_key}")
def playback_media(rating_key: str, user=Depends(get_current_user_dep)) -> dict[str, Any]:
    del user
    try:
        key = validate_rating_key(rating_key)
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    asset = describe_title(_settings(), _db(), _dir(), key)
    return public_media(asset)


def register_engine_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
    db_factory: Callable[[], Any],
    data_dir: Path,
) -> None:
    """Attach the playback-engine router. Call once from the app factory."""
    global _settings_factory, _db_factory, _data_dir
    _settings_factory = settings_factory
    _db_factory = db_factory
    _data_dir = Path(data_dir)
    app.include_router(router)
