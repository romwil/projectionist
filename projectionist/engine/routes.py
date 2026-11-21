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


@router.get("/api/playback/plan")
def playback_plan(
    rating_key: str = "",
    profile: str = "apple-tv-4k-3",
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Dry-run the planner. The response records the plan and why. No file paths."""
    del user
    from projectionist.engine.planner import plan_playback
    from projectionist.engine.profiles import known_profile_ids, named_profile

    try:
        key = validate_rating_key(rating_key)
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    chosen = named_profile(profile)
    if chosen is None:
        names = ", ".join(known_profile_ids())
        raise HTTPException(
            status_code=400,
            detail=f"Unknown device profile. Use one of: {names}.",
        )
    asset = describe_title(_settings(), _db(), _dir(), key)
    body = plan_playback(asset, chosen)
    body["rating_key"] = key
    return body


class PlaybackSessionPayload(BaseModel):
    rating_key: str = ""
    profile: Any = "apple-tv-4k-3"
    start_over: bool = False
    offset_ms: Optional[int] = None
    # Clients that can play an engine playlist set this. Everyone else gets
    # the library path, including when the household switch is on.
    engine_opt_in: bool = False


class PlaybackProgressBody(BaseModel):
    time_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


def _profile_from_body(raw: Any):
    from projectionist.engine.profiles import (
        DeviceProfile,
        VideoCapability,
        known_profile_ids,
        named_profile,
    )

    if isinstance(raw, str) or raw is None:
        chosen = named_profile(str(raw or "apple-tv-4k-3"))
        if chosen is None:
            names = ", ".join(known_profile_ids())
            raise HTTPException(status_code=400, detail=f"Unknown device profile. Use one of: {names}.")
        return chosen
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Device profile must be a name or an object.")
    video = []
    for item in raw.get("video") or []:
        if not isinstance(item, dict):
            continue
        video.append(
            VideoCapability(
                codec=str(item.get("codec") or ""),
                max_level=str(item.get("max_level") or ""),
                hdr=[str(name) for name in (item.get("hdr") or [])],
            )
        )
    return DeviceProfile(
        id=str(raw.get("id") or "custom"),
        containers=[str(name) for name in (raw.get("containers") or [])],
        video=video,
        audio=[str(name) for name in (raw.get("audio") or [])],
        captions=[str(name) for name in (raw.get("captions") or ["webvtt"])],
    )


@router.post("/api/playback/sessions")
def open_playback_session(
    payload: PlaybackSessionPayload,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Open an engine session. Remux and direct plans get a token URL. Other plans record why.

    A client that does not set ``engine_opt_in`` gets the library path. No probe,
    no remux, and no playlist URL.
    """
    from projectionist.engine.session import (
        assert_session_allowed,
        declined_engine_session,
        open_engine_session,
    )
    from projectionist.library.playback import YouthBlockedError, resolve_playable_item

    try:
        key = validate_rating_key(payload.rating_key)
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    if not payload.engine_opt_in:
        return declined_engine_session(key)
    profile = _profile_from_body(payload.profile)
    try:
        playable = resolve_playable_item(_db(), key)
        assert_session_allowed(user, _settings(), playable)
    except YouthBlockedError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    asset = describe_title(_settings(), _db(), _dir(), str(playable.get("rating_key") or key))
    if payload.start_over:
        offset = 0
    elif payload.offset_ms is not None:
        offset = int(payload.offset_ms)
    else:
        offset = int(playable.get("view_offset_ms") or 0)
    from projectionist.engine.captions import caption_fallback_reason, prepare_webvtt_renditions
    from projectionist.library.subtitle_cache import title_subtitle_context

    language = str(title_subtitle_context(_db(), asset.rating_key).get("original_language") or "")
    renditions = prepare_webvtt_renditions(
        asset,
        title_language=language,
        settings=_settings(),
        data_dir=_dir(),
    )
    force_reason = caption_fallback_reason(
        asset,
        title_language=language,
        settings=_settings(),
        data_dir=_dir(),
        renditions=renditions,
    )
    session = open_engine_session(
        asset,
        profile,
        user_id=str(getattr(user, "id", "") or ""),
        title=str(playable.get("title") or ""),
        duration_ms=int(playable.get("duration_ms") or 0),
        view_offset_ms=offset,
        data_dir=_dir(),
        force_reason=force_reason,
        captions=[] if force_reason else renditions,
    )
    return session.public()


@router.get("/api/playback/sessions/{session_id}")
def read_playback_session(session_id: str, user=Depends(get_current_user_dep)) -> dict[str, Any]:
    from projectionist.engine.session import get_engine_session

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return session.public()


@router.post("/api/playback/sessions/{session_id}/progress")
def playback_session_progress(
    session_id: str,
    payload: PlaybackProgressBody,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Write Continue Watching for an engine session. Does not touch a Plex transcode."""
    from projectionist.engine.session import get_engine_session
    from projectionist.library.playback import update_local_view_offset

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    update_local_view_offset(_db(), session.rating_key, int(payload.time_ms), int(payload.duration_ms))
    return {"ok": True, "session_id": session.session_id, "plan": session.plan, "reason": session.reason}


@router.post("/api/playback/sessions/{session_id}/stop")
def close_playback_session(session_id: str, user=Depends(get_current_user_dep)) -> dict[str, Any]:
    from projectionist.engine.session import get_engine_session, stop_engine_session

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return stop_engine_session(session)


@router.get("/api/playback/sessions/{session_id}/{token}/{asset_path:path}")
def playback_session_media(session_id: str, token: str, asset_path: str):
    """Playlist and segments. The token in the path is the credential."""
    from fastapi.responses import FileResponse

    from projectionist.engine.session import resolve_session_file, session_for_token

    try:
        session = session_for_token(session_id, token)
        path = resolve_session_file(session, asset_path)
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    media_type = "application/octet-stream"
    if path.suffix == ".m3u8":
        media_type = "application/vnd.apple.mpegurl"
    elif path.suffix == ".m4s":
        media_type = "video/iso.segment"
    elif path.suffix == ".mp4":
        media_type = "video/mp4"
    elif path.suffix == ".vtt":
        media_type = "text/vtt"
    return FileResponse(path, media_type=media_type, filename=path.name)


class EngineSettingPayload(BaseModel):
    play_through_projectionist: bool = False


@router.get("/api/playback/engine-setting")
def get_engine_setting(user=Depends(require_role("owner"))) -> dict[str, Any]:
    del user
    return {
        "play_through_projectionist": bool(_settings().engine.play_through_projectionist),
    }


@router.put("/api/playback/engine-setting")
def put_engine_setting(
    payload: EngineSettingPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """Household switch for the web player. The next play picks it up. No restart."""
    del user
    from dataclasses import asdict

    existing = _settings()
    current = asdict(existing.engine)
    current["play_through_projectionist"] = bool(payload.play_through_projectionist)
    updated = Settings.from_mapping({**asdict(existing), "engine": current})
    save_settings(_dir(), updated)
    return {
        "play_through_projectionist": bool(updated.engine.play_through_projectionist),
    }


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
