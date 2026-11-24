"""Playback-engine HTTP routes (ENG-001+).

File paths stay off playback plans and the saved playability report. The
owner quality-target list names the file for that title. Owners store path
mappings; members can ask what the engine can read for a title.
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


def household_media_source(settings: Settings, db: Any):
    """The source for this process.

    A fixture directory is the automated playback test. It never calls Plex.
    Every other process uses the household Plex source.
    """
    from projectionist.engine.fixture_source import try_fixture_media_source

    fixture = try_fixture_media_source()
    if fixture is not None:
        return fixture
    return plex_media_source(settings, db)


def plex_media_source(settings: Settings, db: Any) -> PlexMediaSource:
    """The household media source. Plex is the first one that can transcode."""
    engine = getattr(settings, "engine", None)
    mappings = list(getattr(engine, "path_mappings", []) or [])
    return PlexMediaSource(
        mappings=mappings,
        path_lookup=lambda key: plex_part_paths(settings, key),
        identity_lookup=lambda key: identity_from_db(db, key),
    )


def describe_title(
    settings: Settings,
    db: Any,
    data_dir: Path,
    rating_key: str,
    *,
    background: bool = False,
    source: Any = None,
    on_step: Optional[Callable[[str], None]] = None,
):
    """Locate a title and probe it.

    Play uses the default: normal priority, and it does not wait on caption
    extraction. The library walk and caption prep pass ``background`` so their
    ffprobe shares the low-priority slot with extraction. Pass ``source`` when
    the same object should also answer a source-transcode plan. ``on_step``
    hears ``waking_disk`` before the file is opened and ``probing`` around the
    probe itself.
    """
    chosen = source if source is not None else household_media_source(settings, db)
    if on_step is not None:
        on_step("waking_disk")
        on_step("probing")
    return chosen.locate(
        rating_key,
        cache_dir=Path(data_dir) / "engine" / "probes",
        runner=subprocess.run,
        background=background,
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
    from projectionist.engine.quality import title_is_replaced
    from projectionist.engine.tries import failed_try_keys

    source = household_media_source(_settings(), _db())
    asset = describe_title(_settings(), _db(), _dir(), key, source=source)
    body = plan_playback(
        asset,
        chosen,
        source=source,
        failed_tries=failed_try_keys(_dir()),
        ready_copy=_ready_copy(key),
        replaced=title_is_replaced(_dir(), key),
    )
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
    # The client is about to play a preroll. Preparation starts with this post.
    preroll: bool = False


class PlaybackProgressBody(BaseModel):
    time_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class FirstFrameBody(BaseModel):
    """Whether the try showed a picture. Clients that cannot say yet may omit the call."""

    arrived: bool = False


def _profile_from_body(raw: Any):
    from projectionist.engine.profiles import known_profile_ids, named_profile, profile_from_mapping

    if isinstance(raw, str) or raw is None:
        chosen = named_profile(str(raw or "apple-tv-4k-3"))
        if chosen is None:
            names = ", ".join(known_profile_ids())
            raise HTTPException(
                status_code=400, detail=f"Unknown device profile. Use one of: {names}."
            )
        return chosen
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Device profile must be a name or an object.")
    return profile_from_mapping(raw)


@router.post("/api/playback/sessions")
def open_playback_session(
    payload: PlaybackSessionPayload,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Open an engine session. Remux, direct, and audio-only plans get a token URL.

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
    source = household_media_source(_settings(), _db())
    asset = describe_title(
        _settings(),
        _db(),
        _dir(),
        str(playable.get("rating_key") or key),
        source=source,
    )
    if payload.start_over:
        offset = 0
    elif payload.offset_ms is not None:
        offset = int(payload.offset_ms)
    else:
        offset = int(playable.get("view_offset_ms") or 0)
    from projectionist.engine.caption_prep import has_unprepared_text, note_caption_titles
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
    if has_unprepared_text(asset, data_dir=_dir()):
        note_caption_titles([asset.rating_key], data_dir=_dir(), reason="play", force=True)
    session = open_engine_session(
        asset,
        profile,
        user_id=str(getattr(user, "id", "") or ""),
        title=str(playable.get("title") or ""),
        poster_url=str(playable.get("poster_url") or ""),
        backdrop_url=str(playable.get("backdrop_url") or ""),
        duration_ms=int(playable.get("duration_ms") or 0),
        view_offset_ms=offset,
        data_dir=_dir(),
        force_reason=force_reason,
        captions=[] if force_reason else renditions,
        source=source,
        ready_copy=_ready_copy(str(playable.get("rating_key") or key)),
        warm=bool(payload.preroll),
    )
    return _session_body(session, user)


def _session_body(session: Any, user: Any, *, handoff: bool = False) -> dict[str, Any]:
    """Session read, including a preroll hand-off sample and a library switch."""
    from projectionist.engine.session import note_handoff

    if handoff:
        note_handoff(session)
    body = session.public()
    if session.library_fallback and not session.library_session_id:
        started = _start_library_fallback(session, user)
        if started:
            body = session.public()
            body["stream_url"] = started.get("stream_url") or ""
            body["library_session_id"] = session.library_session_id
    elif session.library_session_id:
        body["stream_url"] = (
            f"/api/library/playback/{session.library_session_id}/index.m3u8"
        )
    return body


def _start_library_fallback(session: Any, user: Any) -> Optional[dict[str, Any]]:
    """Start the library transcode at the resume point once the engine has given up."""
    from projectionist.library.playback import PlaybackError as LibraryPlaybackError
    from projectionist.library.playback import start_playback

    try:
        if int(session.view_offset_ms or 0) <= 0:
            started = start_playback(
                _db(),
                _settings(),
                rating_key=session.rating_key,
                user=user,
                start_over=True,
            )
        else:
            started = start_playback(
                _db(),
                _settings(),
                rating_key=session.rating_key,
                user=user,
                offset_ms=int(session.view_offset_ms),
            )
    except (LibraryPlaybackError, OSError) as error:
        logger.info(
            "warm start library fallback did not start for %s: %s",
            session.rating_key,
            error,
        )
        return None
    from projectionist.engine.warmup import set_step

    session.library_session_id = str(started.get("session_id") or "")
    set_step(session, "waiting_on_plex")
    return started


def _stop_library_fallback(session: Any, user: Any) -> None:
    if not session.library_session_id:
        return
    from projectionist.library.playback import PlaybackError as LibraryPlaybackError
    from projectionist.library.playback import get_session, stop_playback

    try:
        library = get_session(
            session.library_session_id,
            user_id=str(getattr(user, "id", "") or ""),
        )
        stop_playback(_db(), library)
    except (LibraryPlaybackError, OSError) as error:
        logger.info(
            "warm start library fallback did not stop for %s: %s",
            session.library_session_id,
            error,
        )


@router.get("/api/playback/warmup-lines")
def playback_warmup_lines(user=Depends(get_current_user_dep)) -> dict[str, Any]:
    """Versioned joke lines, one pool per playback step. Clients cache this."""
    del user
    from projectionist.engine.warmup import load_warmup_lines

    return load_warmup_lines()


@router.get("/api/playback/sessions/{session_id}")
def read_playback_session(
    session_id: str,
    handoff: bool = False,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    from projectionist.engine.session import get_engine_session

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    return _session_body(session, user, handoff=handoff)


@router.post("/api/playback/sessions/{session_id}/progress")
def playback_session_progress(
    session_id: str,
    payload: PlaybackProgressBody,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Write Continue Watching for an engine session. Does not touch a Plex transcode."""
    from projectionist.engine.session import get_engine_session, note_playback_progress
    from projectionist.library.playback import update_local_view_offset

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    note_playback_progress(session, int(payload.time_ms))
    update_local_view_offset(
        _db(), session.rating_key, int(payload.time_ms), int(payload.duration_ms)
    )
    return {
        "ok": True,
        "session_id": session.session_id,
        "plan": session.plan,
        "reason": session.reason,
    }


@router.post("/api/playback/sessions/{session_id}/first-frame")
def record_playback_first_frame(
    session_id: str,
    payload: FirstFrameBody,
    user=Depends(get_current_user_dep),
) -> dict[str, Any]:
    """Remember whether a try showed a picture. Other plans are not stored.

    The title and profile come from the session, so a client cannot write a
    different pair. A client that cannot report yet may omit the call.
    """
    from projectionist.engine.session import get_engine_session
    from projectionist.engine.tries import record_first_frame

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    stored = session.plan == "try"
    if stored:
        record_first_frame(
            _dir(),
            rating_key=session.rating_key,
            profile_id=session.profile_id,
            arrived=bool(payload.arrived),
        )
    return {
        "ok": True,
        "stored": stored,
        "arrived": bool(payload.arrived),
        "rating_key": session.rating_key,
        "profile": session.profile_id,
    }


@router.post("/api/playback/sessions/{session_id}/stop")
def close_playback_session(session_id: str, user=Depends(get_current_user_dep)) -> dict[str, Any]:
    from projectionist.engine.session import get_engine_session, stop_engine_session

    try:
        session = get_engine_session(session_id, user_id=str(getattr(user, "id", "") or ""))
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    _stop_library_fallback(session, user)
    return stop_engine_session(session)


@router.get("/api/playback/sessions/{session_id}/{token}/{asset_path:path}")
def playback_session_media(session_id: str, token: str, asset_path: str):
    """Playlist and segments. The token in the path is the credential."""
    from fastapi.responses import FileResponse

    from projectionist.engine.session import (
        note_session_media,
        resolve_session_file,
        session_for_token,
    )

    try:
        session = session_for_token(session_id, token)
        note_session_media(session, asset_path)
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


class PlayabilityPayload(BaseModel):
    """Optional browser profile. The same object a session already accepts."""

    profile: Any = None


class EngineSettingPayload(BaseModel):
    play_through_projectionist: bool = False


class QualityCeilingPayload(BaseModel):
    quality_ceiling: str = ""


class QualityTargetPayload(BaseModel):
    rating_key: str = ""


class CopyRequestPayload(BaseModel):
    rating_key: str = ""


class CopiesPayload(BaseModel):
    """Owner folder and disk budget for copies made ahead of time."""

    output_dir: str = ""
    budget_gib: float = 200


@router.get("/api/playback/playability")
def get_playability_report(
    view: str = "",
    profile: str = "",
    tier: str = "",
    limit: int = 40,
    offset: int = 0,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """The last library playability report. Owner only.

    ``view=progress`` is what Settings polls while a walk is running: shares
    and counts, without the per-profile title rows. ``above_target`` is the
    list of titles above the quality ceiling, including each file path.
    ``profile`` and ``tier`` together return one page of tier rows. The saved
    report still holds every title and does not store file paths.
    """
    del user
    from projectionist.engine.playability import (
        load_playability_report,
        playability_progress,
        playability_title_page,
    )

    report = load_playability_report(_dir())
    if str(profile or "") and str(tier or ""):
        return playability_title_page(
            report,
            profile=profile,
            tier=tier,
            limit=limit,
            offset=offset,
        )
    if str(view or "") == "progress":
        body = playability_progress(report)
    else:
        body = dict(report)
    body["quality_ceiling"] = _quality_ceiling()
    body["above_target"] = _above_target(report)
    return body


@router.post("/api/playback/playability")
def refresh_playability_report(
    payload: PlayabilityPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """Dry-run the planner across the library and store the report.

    A profile name limits the run to that named profile. A profile object is
    this browser, kept beside the named profiles. Nothing is transcoded.
    """
    del user
    from projectionist.engine.playability import (
        PlayabilityProfileError,
        profiles_for_report,
        request_owner_report,
    )

    try:
        profiles = profiles_for_report(payload.profile)
    except PlayabilityProfileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return request_owner_report(
        _db(),
        _settings(),
        _dir(),
        profiles=profiles,
        locate=lambda key: describe_title(_settings(), _db(), _dir(), key, background=True),
    )


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


def _quality_ceiling() -> str:
    from projectionist.engine.quality import normalize_quality_ceiling

    return normalize_quality_ceiling(getattr(_settings().engine, "quality_ceiling", ""))


def _title_path(rating_key: str) -> str:
    from projectionist.engine.source import read_location

    saved = read_location(_dir() / "engine" / "probes", rating_key)
    if not isinstance(saved, dict):
        return ""
    return str(saved.get("local_path") or saved.get("source_path") or "")


def _above_target(report: dict[str, Any]) -> dict[str, Any]:
    from projectionist.engine.quality import above_quality_target, load_replaced_titles

    return above_quality_target(
        report,
        ceiling=_quality_ceiling(),
        replaced=load_replaced_titles(_dir()),
        paths={
            str(row.get("rating_key") or ""): _title_path(str(row.get("rating_key") or ""))
            for block in report.get("profiles") or []
            if isinstance(block, dict)
            for row in block.get("titles") or []
            if isinstance(row, dict) and str(row.get("rating_key") or "")
        },
    )


def _save_quality_ceiling(ceiling: str) -> str:
    from dataclasses import asdict

    existing = _settings()
    current = asdict(existing.engine)
    current["quality_ceiling"] = ceiling
    updated = Settings.from_mapping({**asdict(existing), "engine": current})
    save_settings(_dir(), updated)
    return str(updated.engine.quality_ceiling)


@router.get("/api/playback/quality-ceiling")
def get_quality_ceiling(user=Depends(require_role("owner"))) -> dict[str, Any]:
    """The household quality ceiling. Owner only. Default 1080p."""
    del user
    return {"quality_ceiling": _quality_ceiling()}


@router.put("/api/playback/quality-ceiling")
def put_quality_ceiling(
    payload: QualityCeilingPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """Save the ceiling. The next playability read uses it. No restart."""
    del user
    from projectionist.engine.quality import parse_quality_ceiling

    try:
        ceiling = parse_quality_ceiling(payload.quality_ceiling)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"quality_ceiling": _save_quality_ceiling(ceiling)}


@router.post("/api/playback/quality-target/copy")
def copy_for_quality_target(
    payload: QualityTargetPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """Queue one 1080p copy on the existing overnight path. Does not encode the library."""
    del user
    from projectionist.engine.copies import remember_copy_request
    from projectionist.engine.playability import load_playability_report

    try:
        key = validate_rating_key(payload.rating_key)
        remember_copy_request(_dir(), key)
    except (PlaybackError, ValueError) as error:
        detail = getattr(error, "message", None) or str(error)
        status = int(getattr(error, "status_code", 400) or 400)
        raise HTTPException(status_code=status, detail=detail) from error
    folder = str(getattr(_settings().engine, "copy_output_dir", "") or "").strip()
    message = "Queued a 1080p copy for the overnight pass."
    if not folder:
        message = (
            "Queued a 1080p copy. Choose a folder under Copies made ahead "
            "before that pass can write the file."
        )
    return {
        "rating_key": key,
        "requested": True,
        "message": message,
        "above_target": _above_target(load_playability_report(_dir())),
    }


@router.post("/api/playback/quality-target/replaced")
def mark_quality_target_replaced(
    payload: QualityTargetPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """The title is replaced, so it is no longer above the quality target."""
    del user
    from projectionist.engine.playability import load_playability_report
    from projectionist.engine.quality import mark_title_replaced

    try:
        key = validate_rating_key(payload.rating_key)
        mark_title_replaced(_dir(), key)
    except (PlaybackError, ValueError) as error:
        detail = getattr(error, "message", None) or str(error)
        status = int(getattr(error, "status_code", 400) or 400)
        raise HTTPException(status_code=status, detail=detail) from error
    return {
        "rating_key": key,
        "replaced": True,
        "above_target": _above_target(load_playability_report(_dir())),
    }


def _ready_copy(rating_key: str):
    from projectionist.engine.copies import ready_copy_asset

    folder = str(getattr(_settings().engine, "copy_output_dir", "") or "").strip()
    if not folder:
        return None
    return ready_copy_asset(Path(folder), rating_key)


def _copy_library_paths() -> list[Path]:
    settings = _settings()
    found: list[Path] = []
    for raw in (
        getattr(settings, "movies_root", ""),
        getattr(settings, "tv_root", ""),
    ):
        text = str(raw or "").strip()
        if text:
            found.append(Path(text))
    for row in list(getattr(settings.engine, "path_mappings", []) or []):
        if isinstance(row, dict):
            source = str(row.get("from") or "").strip()
            if source:
                found.append(Path(source))
    try:
        from projectionist.library.episode_investigate.path_map import plex_library_locations

        for kind in ("movie", "show"):
            for item in plex_library_locations(settings, section_type=kind):
                text = str(item or "").strip()
                if text:
                    found.append(Path(text))
    except Exception:  # noqa: BLE001 — a missing Plex answer is a path we cannot check
        logger.info("copy folder check could not read Plex library paths")
    return found


def _copy_titles() -> list[dict[str, Any]]:
    from projectionist.engine.playability import load_playability_report

    report = load_playability_report(_dir())
    ahead = report.get("copy_ahead") if isinstance(report, dict) else None
    rows = ahead.get("titles") if isinstance(ahead, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


@router.post("/api/playback/copies/requests")
def request_copy(payload: CopyRequestPayload, user=Depends(get_current_user_dep)) -> dict[str, Any]:
    """Remember a title for the overnight copy pass. Does not start an encode."""
    del user
    from projectionist.engine.copies import remember_copy_request
    from projectionist.library.playback import PREPARE_FOR_SCREEN

    try:
        key = validate_rating_key(payload.rating_key)
        saved = remember_copy_request(_dir(), key)
    except (PlaybackError, ValueError) as error:
        detail = getattr(error, "message", None) or str(error)
        status = int(getattr(error, "status_code", 400) or 400)
        raise HTTPException(status_code=status, detail=detail) from error
    return {"rating_key": key, "requested": True, "rating_keys": saved, "message": PREPARE_FOR_SCREEN}


@router.get("/api/playback/copies")
def get_copies(user=Depends(require_role("owner"))) -> dict[str, Any]:
    """Queue and used space for copies made ahead of time. No source paths."""
    del user
    from projectionist.engine.copies import describe_copies

    engine = _settings().engine
    folder = str(engine.copy_output_dir or "")
    view = describe_copies(
        _copy_titles(),
        Path(folder) if folder else None,
        budget_bytes=int(engine.copy_budget_bytes),
    )
    view["output_dir"] = folder
    return view


@router.put("/api/playback/copies")
def put_copies(payload: CopiesPayload, user=Depends(require_role("owner"))) -> dict[str, Any]:
    """Save the output folder and budget. Refuse a folder inside a Plex library."""
    del user
    from dataclasses import asdict

    from projectionist.engine.copies import DEFAULT_BUDGET_BYTES, copy_folder_problem

    folder = str(payload.output_dir or "").strip()
    if not folder:
        raise HTTPException(status_code=400, detail="Choose a folder for the copies.")
    problem = copy_folder_problem(Path(folder), _copy_library_paths())
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    try:
        gib = float(payload.budget_gib)
    except (TypeError, ValueError):
        gib = 0
    if gib <= 0:
        raise HTTPException(status_code=400, detail="The disk budget has to be greater than zero.")
    budget = int(gib * 1024 * 1024 * 1024)
    if budget <= 0:
        budget = DEFAULT_BUDGET_BYTES
    existing = _settings()
    current = asdict(existing.engine)
    current["copy_output_dir"] = folder
    current["copy_budget_bytes"] = budget
    updated = Settings.from_mapping({**asdict(existing), "engine": current})
    save_settings(_dir(), updated)
    return get_copies(user=None)


@router.delete("/api/playback/copies/{rating_key}")
def delete_copy(rating_key: str, user=Depends(require_role("owner"))) -> dict[str, Any]:
    """Remove one ready copy. The source file stays where it is."""
    del user
    from projectionist.engine.copies import remove_copy

    try:
        key = validate_rating_key(rating_key)
    except PlaybackError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    folder = str(_settings().engine.copy_output_dir or "").strip()
    if folder:
        try:
            remove_copy(Path(folder), key)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    return get_copies(user=None)


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
