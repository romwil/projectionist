"""Live Channels HTTP routes (admin craft + household on-now/stream).

Extracted from web/app.py (H1/M8 incremental carve). Registered via
``register_live_channels_routes`` so app.py stays the composition root.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projectionist.config_store import Settings, save_settings
from projectionist.live_channels.stream_warm import get_stream_warm_scheduler
from projectionist.web.auth import get_current_user_dep, require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-channels"])

_settings_factory: Optional[Callable[[], Settings]] = None
_db_factory: Optional[Callable[[], Any]] = None
_safe_error_detail_fn: Optional[Callable[..., str]] = None
DATA_DIR = None


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("live_channels routes not registered")
    return _settings_factory()


def _db():
    if _db_factory is None:
        raise RuntimeError("live_channels routes not registered")
    return _db_factory()


def _safe_error_detail(error: Exception, context: str = "") -> str:
    if _safe_error_detail_fn is None:
        raise RuntimeError("live_channels routes not registered")
    return _safe_error_detail_fn(error, context)



@router.get("/api/admin/live-channels/status")
def live_channels_status_endpoint(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Owner-only Live Channels flag + Tunarr reachability snapshot."""
    del user
    from projectionist.live_channels.status import build_live_channels_status

    return build_live_channels_status(_settings())


@router.get("/api/admin/live-channels/starter-pack")
def live_channels_starter_pack_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner-only library-aware starter channel proposals."""
    from projectionist.live_channels.starter_pack import propose_starter_pack_from_db

    settings = _settings()
    return propose_starter_pack_from_db(
        _db(),
        settings=settings,
        owner_user_id=str(user.id),
    )


class LiveChannelsPreflightPayload(BaseModel):
    plex_pass_confirmed: Optional[bool] = None


class LiveChannelsLifecyclePayload(BaseModel):
    action: Literal["start", "stop", "pull", "ensure_running"] = "ensure_running"


class LiveChannelsPublishStartersPayload(BaseModel):
    recipes: List[Dict[str, Any]] = Field(default_factory=list)
    wire_plex: bool = True
    # Default true: enable Tunarr libraries, scan, and fill existing empty
    # stations with scanned program IDs (flex-only shells cannot play in Plex).
    fill_programming: bool = True
    confirm: bool = False


class LiveChannelsFromCollectionPayload(BaseModel):
    collection_id: str = ""
    collection_title: str = ""
    channel_number: int = 0
    name: str = ""
    programming_mode: str = "sequential"
    media_scope: str = "both"
    craft_filters: Dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False
    # sync=true only for tests / diagnostics (default = background job).
    sync: bool = False


class LiveChannelsFromShowPayload(BaseModel):
    """Create one nonstop station from a single TV show."""

    show_rating_key: str = ""
    show_title: str = ""
    # Projectionist library item id — resolves rating_key + title server-side.
    show_item_id: int = 0
    channel_number: int = 0
    name: str = ""
    programming_mode: str = "sequential"
    confirm: bool = False
    # sync=true only for tests / diagnostics (default = background job).
    sync: bool = False


class LiveChannelsPublishChannelPayload(BaseModel):
    """Craft-form publish: one ChannelRecipe-shaped body."""

    recipe: Dict[str, Any] = Field(default_factory=dict)
    name: str = ""
    number: int = 0
    source: str = "motif"
    programming_mode: str = ""
    media_scope: str = "both"
    motif: str = ""
    cluster_tag: str = ""
    collection_id: str = ""
    collection_title: str = ""
    youth_safe: bool = False
    summary: str = ""
    craft_filters: Dict[str, Any] = Field(default_factory=dict)
    wire_plex: bool = True
    fill_programming: bool = True
    confirm: bool = False
    sync: bool = False


class LiveChannelsCraftPreviewPayload(BaseModel):
    media_scope: str = "both"
    collection_id: str = ""
    source: str = ""
    craft_filters: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)


class LiveChannelsEngineSettingsPayload(BaseModel):
    pad_flex_max_minutes: Optional[int] = None
    exclusion_collection_name: Optional[str] = None
    exclusion_collection_id: Optional[str] = None
    auto_refresh_stations_after_sync: Optional[bool] = None
    subtitles_enabled_default: Optional[bool] = None
    subtitle_language_primary: Optional[str] = None
    subtitle_language_fallback: Optional[str] = None
    confirm: bool = False


class LiveChannelsRefillChannelPayload(BaseModel):
    recipe: Dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class LiveChannelsStationSettingsPayload(BaseModel):
    media_scope: str = "both"
    subtitles_enabled: Optional[bool] = None
    # Craft definition (optional). When present, replaces stored station_meta fields.
    # Empty craft_filters clears decade/genre/theme/rating. Refill applies the lineup.
    motif: Optional[str] = None
    cluster_tag: Optional[str] = None
    craft_filters: Optional[Dict[str, Any]] = None
    confirm: bool = False


class LiveChannelsDownloadSubtitlesPayload(BaseModel):
    language: str = ""
    confirm: bool = False


class LiveChannelsContinuityPayload(BaseModel):
    confirm: bool = False
    rescan: bool = True
    repair: bool = True
    refill_lineups: bool = True
    sync: bool = False  # tests / diagnostics only — default is background job


@router.post("/api/admin/live-channels/preflight")
def live_channels_preflight_endpoint(
    payload: Optional[LiveChannelsPreflightPayload] = None,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner preflight checklist for the Live Channels enable flow."""
    del user
    from projectionist.live_channels.preflight import run_preflight

    body = payload or LiveChannelsPreflightPayload()
    settings = _settings()
    if body.plex_pass_confirmed is not None:
        tunarr = asdict(settings.tunarr)
        tunarr["plex_pass_confirmed"] = bool(body.plex_pass_confirmed)
        updated = Settings.from_mapping({**asdict(settings), "tunarr": tunarr})
        save_settings(DATA_DIR, updated)
        settings = updated
    return run_preflight(
        settings,
        data_dir=DATA_DIR,
        owner_confirmed_plex_pass=body.plex_pass_confirmed,
    )


@router.get("/api/admin/live-channels/lifecycle-status")
def live_channels_lifecycle_status_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner progress + ready probe for Step 2 (Start the broadcast engine)."""
    del user
    from projectionist.live_channels.lifecycle_progress import build_lifecycle_status

    return build_lifecycle_status(_settings())


@router.post("/api/admin/live-channels/lifecycle")
def live_channels_lifecycle_endpoint(
    payload: LiveChannelsLifecyclePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner Docker lifecycle: pull / start / stop / ensure_running."""
    del user
    from projectionist.live_channels.docker import (
        lifecycle_from_settings,
        resolve_config_volume,
    )
    from projectionist.live_channels.lifecycle_progress import (
        make_phase_callback,
        mark_waiting_after_lifecycle,
        progress_store,
    )

    settings = _settings()
    life = lifecycle_from_settings(settings)
    volume = resolve_config_volume(settings, DATA_DIR)
    action = str(payload.action or "ensure_running").strip().lower()
    on_phase = None
    if action in {"ensure_running", "start", "pull"}:
        store = progress_store()
        store.begin(container_name=life.container_name)
        on_phase = make_phase_callback(store)
    if action == "pull":
        result = life.pull(on_phase=on_phase)
    elif action == "stop":
        result = life.stop(keep_volume=True)
    elif action == "start":
        result = life.start(config_volume=volume, on_phase=on_phase)
    else:
        result = life.ensure_running(config_volume=volume, on_phase=on_phase)
    if action in {"ensure_running", "start", "pull"}:
        mark_waiting_after_lifecycle(result.to_dict())

    detail = result.detail or {}
    url_hint = str(detail.get("url_hint") or "").strip()
    public_url_hint = str(detail.get("public_url_hint") or "").strip()
    if not url_hint or not public_url_hint:
        start_payload = detail.get("start") if isinstance(detail.get("start"), dict) else {}
        start_detail = (
            start_payload.get("detail") if isinstance(start_payload.get("detail"), dict) else {}
        )
        if not url_hint:
            url_hint = str(start_detail.get("url_hint") or "").strip()
        if not public_url_hint:
            public_url_hint = str(start_detail.get("public_url_hint") or "").strip()

    if result.ok and result.status == "running":
        tunarr = asdict(settings.tunarr)
        changed = False
        # API URL: sibling DNS for Projectionist→Tunarr (may be host.docker.internal).
        if url_hint and not str(tunarr.get("url") or "").strip():
            tunarr["url"] = url_hint
            changed = True
        # Always refresh API URL port when we know the published host port.
        detail_host_port = detail.get("host_port")
        if detail_host_port is None and isinstance(detail.get("start"), dict):
            start_detail = detail.get("start", {}).get("detail") or {}
            if isinstance(start_detail, dict):
                detail_host_port = start_detail.get("host_port")
        if detail_host_port and url_hint:
            # Keep sibling host; rewrite port to the actual published mapping.
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url_hint if "://" in url_hint else f"http://{url_hint}")
            replaced = parsed._replace(netloc=f"{parsed.hostname}:{int(detail_host_port)}")
            rewritten = urlunparse(replaced).rstrip("/")
            if rewritten and rewritten != str(tunarr.get("url") or "").rstrip("/"):
                # Only auto-rewrite when current url is empty or docker sibling.
                current = str(tunarr.get("url") or "")
                if (not current) or "host.docker.internal" in current or current.rstrip("/") == url_hint.rstrip("/"):
                    tunarr["url"] = rewritten
                    changed = True
        if detail_host_port:
            try:
                port_i = int(detail_host_port)
            except (TypeError, ValueError):
                port_i = 0
            if port_i and int(tunarr.get("host_port") or 0) != port_i:
                tunarr["host_port"] = port_i
                changed = True
        detail_hdhr = detail.get("hdhr_port")
        if detail_hdhr is None and isinstance(detail.get("start"), dict):
            start_detail = detail.get("start", {}).get("detail") or {}
            if isinstance(start_detail, dict):
                detail_hdhr = start_detail.get("hdhr_port")
        if detail_hdhr:
            try:
                hdhr_i = int(detail_hdhr)
            except (TypeError, ValueError):
                hdhr_i = 0
            if hdhr_i and int(tunarr.get("hdhr_port") or 0) != hdhr_i:
                tunarr["hdhr_port"] = hdhr_i
                changed = True
        # Plex-facing LAN URL — never host.docker.internal; fill when empty.
        if public_url_hint and not str(tunarr.get("public_url") or "").strip():
            from projectionist.live_channels.plex_attach import is_docker_only_host

            host = public_url_hint.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
            if not is_docker_only_host(host):
                tunarr["public_url"] = public_url_hint.rstrip("/")
                changed = True
        if changed:
            updated = Settings.from_mapping({**asdict(settings), "tunarr": tunarr})
            save_settings(DATA_DIR, updated)
            settings = updated

    payload_out = result.to_dict()
    payload_out["tunarr_url"] = str(settings.tunarr.url or "")
    payload_out["tunarr_public_url"] = str(settings.tunarr.public_url or "")
    payload_out["host_port"] = int(getattr(settings.tunarr, "host_port", 0) or 0)
    payload_out["hdhr_port"] = int(getattr(settings.tunarr, "hdhr_port", 0) or 0)
    payload_out["config_volume"] = volume

    # With media binds, prefer Tunarr direct file reads (not Plex HTTP parts).
    if result.ok and result.status == "running":
        media_binds = list(getattr(settings.tunarr, "media_binds", None) or [])
        api_url = str(settings.tunarr.url or url_hint or "").strip()
        if media_binds and api_url:
            try:
                from projectionist.connectors.tunarr import TunarrClient

                payload_out["plex_stream"] = TunarrClient(
                    api_url, timeout=8
                ).ensure_plex_stream_path_direct()
            except Exception:  # noqa: BLE001 — best-effort; lifecycle still succeeded
                pass
        # Start-over deep playheads + warm HLS so the first Plex tune does not
        # race "Stream not ready yet" / 0-byte MPEG-TS.
        if api_url and settings.features.live_channels_enabled:
            try:
                from projectionist.live_channels.publish import (
                    prepare_channels_for_playback,
                    resolve_channel_icon_url,
                    tunarr_client_from_settings,
                )

                payload_out["playback_prepare"] = prepare_channels_for_playback(
                    tunarr_client_from_settings(settings),
                    settings=settings,
                    icon_url=resolve_channel_icon_url(settings),
                )
            except Exception:  # noqa: BLE001 — lifecycle still succeeded
                pass
    return payload_out


@router.post("/api/admin/live-channels/starters/publish")
def live_channels_publish_starters_endpoint(
    payload: LiveChannelsPublishStartersPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Publish selected starter recipes to Tunarr (owner confirm-gated)."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Publishing starters requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        publish_recipes,
        tunarr_client_from_settings,
        wire_plex_media_source,
    )
    from projectionist.live_channels.starter_pack import propose_starter_pack_from_db

    try:
        client = tunarr_client_from_settings(settings)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    wire: Dict[str, Any] = {"ok": False, "skipped": True}
    if payload.wire_plex and settings.plex_url and settings.plex_token:
        try:
            wire = wire_plex_media_source(
                client,
                plex_url=settings.plex_url,
                plex_token=settings.plex_token,
                settings=settings,
            )
        except Exception as error:  # noqa: BLE001
            wire = {"ok": False, "message": str(error)[:240]}

    recipes = list(payload.recipes or [])
    if not recipes:
        pack = propose_starter_pack_from_db(
            _db(),
            settings=settings,
            owner_user_id=str(user.id),
        )
        recipes = list(pack.get("proposals") or [])

    try:
        result = publish_recipes(
            client,
            recipes,
            fill_programming=bool(payload.fill_programming),
            settings=settings,
        )
    except Exception as error:  # noqa: BLE001
        tunarr = asdict(settings.tunarr)
        tunarr["last_error"] = str(error)[:240]
        save_settings(
            DATA_DIR,
            Settings.from_mapping({**asdict(settings), "tunarr": tunarr}),
        )
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not publish starters to Tunarr"),
        ) from error

    result["media_source"] = wire
    return _finalize_live_channels_publish(settings, result)


def _finalize_live_channels_publish(
    settings: Settings,
    result: Dict[str, Any],
    *,
    on_phase: Any = None,
) -> Dict[str, Any]:
    """Persist publish timestamps, refresh Plex channel map, append note."""
    from projectionist.live_channels.plex_attach import refresh_plex_live_tv_channels

    def _phase(phase: str, message: str = "") -> None:
        if on_phase is not None:
            try:
                on_phase(phase, message)
            except Exception:  # noqa: BLE001
                pass

    tunarr = asdict(settings.tunarr)
    if result.get("ok") or result.get("count_published") or result.get("count_programming_updated"):
        tunarr["last_publish_at"] = str(result.get("published_at") or "")
        tunarr["last_error"] = ""
    elif result.get("errors"):
        first = result["errors"][0] if result["errors"] else {}
        tunarr["last_error"] = str(
            (first.get("error") if isinstance(first, dict) else "") or "publish failed"
        )[:240]

    plex_sync: Dict[str, Any] = {"ok": False, "skipped": True}
    if result.get("ok") or result.get("count_published") or result.get("count_programming_updated"):
        _phase("plex_sync", "Refreshing Plex Live TV channel map…")
        try:
            plex_sync = refresh_plex_live_tv_channels(settings)
        except Exception as error:  # noqa: BLE001
            plex_sync = {
                "ok": False,
                "attach_needed": True,
                "mapped": 0,
                "expected": 0,
                "message": str(error)[:200],
                "error": str(error)[:200],
            }
        note = str(result.get("note") or "").rstrip()
        sync_msg = str(plex_sync.get("message") or plex_sync.get("error") or "")
        mapped = int(plex_sync.get("mapped") or 0)
        expected = int(plex_sync.get("expected") or 0)
        if plex_sync.get("ok") and sync_msg:
            result["note"] = f"{note} {sync_msg}".strip() if note else sync_msg
        elif not plex_sync.get("ok"):
            # Never silent: incomplete map or missing device is a hard publish warning.
            if expected and mapped < expected:
                hint = (
                    sync_msg
                    or f"Plex mapped only {mapped}/{expected} Tunarr channels — "
                    "use Repair Plex tuner/guide."
                )
            else:
                hint = (
                    sync_msg
                    or "Plex Live TV sync failed — use Repair Plex tuner/guide."
                )
            result["note"] = f"{note} {hint}".strip() if note else hint
            result["plex_sync_failed"] = True
        elif sync_msg:
            result["note"] = f"{note} Plex sync: {sync_msg}".strip() if note else sync_msg

        # Persist last mapping snapshot for Admin status even when publish succeeds.
        if plex_sync.get("mapped") is not None or plex_sync.get("expected") is not None:
            tunarr["last_plex_mapped"] = int(plex_sync.get("mapped") or 0)
            tunarr["last_plex_expected"] = int(plex_sync.get("expected") or 0)
            tunarr["last_plex_sync_ok"] = bool(plex_sync.get("ok"))
            tunarr["last_plex_sync_message"] = str(
                plex_sync.get("message") or plex_sync.get("error") or ""
            )[:240]

    # Persist station_meta (collection_id / programming_mode) written during publish.
    tunarr["station_meta"] = dict(getattr(settings.tunarr, "station_meta", None) or {})
    save_settings(DATA_DIR, Settings.from_mapping({**asdict(settings), "tunarr": tunarr}))
    result["plex_sync"] = plex_sync
    return result


@router.get("/api/admin/live-channels/publish/status")
def live_channels_publish_status_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner progress poll for collection / craft publish jobs."""
    del user
    from projectionist.live_channels.publish_progress import build_publish_job_status

    return build_publish_job_status()


@router.post("/api/admin/live-channels/channels/from-collection")
def live_channels_from_collection_endpoint(
    payload: LiveChannelsFromCollectionPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Publish a collection/list as a Tunarr channel (async by default)."""
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Creating a channel from a collection requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        publish_collection_channel,
        tunarr_client_from_settings,
    )
    from projectionist.live_channels.publish_progress import (
        make_phase_callback,
        progress_store,
        start_publish_job,
    )

    def _run(settings_obj: Settings, on_phase: Any) -> Dict[str, Any]:
        on_phase("matching", "Loading collection rating keys…")
        client = tunarr_client_from_settings(settings_obj)
        on_phase("publishing", "Publishing collection station…")
        result = publish_collection_channel(
            client,
            collection_id=payload.collection_id,
            collection_title=payload.collection_title,
            channel_number=payload.channel_number,
            name=payload.name,
            programming_mode=payload.programming_mode,
            craft_filters=payload.craft_filters or {},
            media_scope=payload.media_scope or "both",
            settings=settings_obj,
        )
        on_phase("warming", "Preparing streams…")
        return _finalize_live_channels_publish(settings_obj, result, on_phase=on_phase)

    if payload.sync:
        store = progress_store()
        if not store.begin(mode="collection"):
            raise HTTPException(status_code=409, detail="Publish already running.")
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings, on_phase)
        except ValueError as error:
            store.set_error(str(error))
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400])
            raise HTTPException(
                status_code=502,
                detail=_safe_error_detail(error, "Could not create channel from collection"),
            ) from error
        store.set_done(str(result.get("note") or "Publish finished."), result=result)
        return {**result, "accepted": True, "async": False}

    settings_snapshot = Settings.from_mapping(asdict(settings))

    def _runner() -> None:
        store = progress_store()
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings_snapshot, on_phase)
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400] or "Publish failed.")
            return
        store.set_done(str(result.get("note") or "Publish finished."), result=result)

    accepted = start_publish_job(_runner, mode="collection")
    if not accepted.get("accepted"):
        raise HTTPException(
            status_code=409,
            detail=str(accepted.get("message") or "Publish already running."),
        )
    return {
        "ok": True,
        "accepted": True,
        "async": True,
        "busy": True,
        "phase": accepted.get("phase"),
        "percent": accepted.get("percent"),
        "message": accepted.get("message")
        or "Publish started — progress updates below.",
        "mode": "collection",
    }


@router.post("/api/admin/live-channels/channels/from-show")
def live_channels_from_show_endpoint(
    payload: LiveChannelsFromShowPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Publish one TV show as a nonstop Tunarr channel (async by default)."""
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Creating a channel from a show requires confirm=true",
        )
    if not str(payload.show_rating_key or "").strip() and int(payload.show_item_id or 0) <= 0:
        raise HTTPException(
            status_code=400,
            detail="A show ratingKey or library item id is required",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        publish_show_channel,
        tunarr_client_from_settings,
    )
    from projectionist.live_channels.publish_progress import (
        make_phase_callback,
        progress_store,
        start_publish_job,
    )

    def _run(settings_obj: Settings, on_phase: Any) -> Dict[str, Any]:
        on_phase("matching", "Resolving show episodes…")
        client = tunarr_client_from_settings(settings_obj)
        on_phase("publishing", "Publishing show station…")
        result = publish_show_channel(
            client,
            show_rating_key=payload.show_rating_key,
            show_title=payload.show_title,
            show_item_id=payload.show_item_id,
            channel_number=payload.channel_number,
            name=payload.name,
            programming_mode=payload.programming_mode,
            settings=settings_obj,
        )
        on_phase("warming", "Preparing streams…")
        return _finalize_live_channels_publish(settings_obj, result, on_phase=on_phase)

    if payload.sync:
        store = progress_store()
        if not store.begin(mode="show"):
            raise HTTPException(status_code=409, detail="Publish already running.")
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings, on_phase)
        except ValueError as error:
            store.set_error(str(error))
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400])
            raise HTTPException(
                status_code=502,
                detail=_safe_error_detail(error, "Could not create channel from show"),
            ) from error
        store.set_done(str(result.get("note") or "Publish finished."), result=result)
        return {**result, "accepted": True, "async": False}

    settings_snapshot = Settings.from_mapping(asdict(settings))

    def _runner() -> None:
        store = progress_store()
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings_snapshot, on_phase)
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400] or "Publish failed.")
            return
        store.set_done(str(result.get("note") or "Publish finished."), result=result)

    accepted = start_publish_job(_runner, mode="show")
    if not accepted.get("accepted"):
        raise HTTPException(
            status_code=409,
            detail=str(accepted.get("message") or "Publish already running."),
        )
    return {
        "ok": True,
        "accepted": True,
        "async": True,
        "busy": True,
        "phase": accepted.get("phase"),
        "percent": accepted.get("percent"),
        "message": accepted.get("message")
        or "Publish started — progress updates below.",
        "mode": "show",
    }


@router.post("/api/admin/live-channels/craft-preview")
def live_channels_craft_preview_endpoint(
    payload: LiveChannelsCraftPreviewPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Preview match count for additive craft filters before publish."""
    del user
    from projectionist.live_channels.filters import preview_craft_match_count

    filters = payload.craft_filters or payload.filters or {}
    return preview_craft_match_count(
        _db(),
        filters=filters,
        media_scope=payload.media_scope or "both",
        collection_id=payload.collection_id or "",
        source=payload.source or "",
        settings=_settings(),
    )


@router.patch("/api/admin/live-channels/engine-settings")
def live_channels_engine_settings_endpoint(
    payload: LiveChannelsEngineSettingsPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner pad / exclusion / auto-refresh settings for Live Channels."""
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Updating Live Channels engine settings requires confirm=true",
        )
    settings = _settings()
    tunarr = asdict(settings.tunarr)
    if payload.pad_flex_max_minutes is not None:
        try:
            minutes = int(payload.pad_flex_max_minutes)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail="pad_flex_max_minutes must be an integer") from error
        tunarr["pad_flex_max_minutes"] = max(0, min(minutes, 30))
    if payload.exclusion_collection_name is not None:
        tunarr["exclusion_collection_name"] = str(
            payload.exclusion_collection_name or "NoLive"
        ).strip() or "NoLive"
    if payload.exclusion_collection_id is not None:
        tunarr["exclusion_collection_id"] = str(payload.exclusion_collection_id or "").strip()
    if payload.auto_refresh_stations_after_sync is not None:
        tunarr["auto_refresh_stations_after_sync"] = bool(
            payload.auto_refresh_stations_after_sync
        )
    if payload.subtitles_enabled_default is not None:
        tunarr["subtitles_enabled_default"] = bool(payload.subtitles_enabled_default)
    if payload.subtitle_language_primary is not None:
        from projectionist.library.subtitles import normalize_subtitle_language

        tunarr["subtitle_language_primary"] = normalize_subtitle_language(
            payload.subtitle_language_primary, default="en"
        )
    if payload.subtitle_language_fallback is not None:
        from projectionist.library.subtitles import normalize_subtitle_language

        raw = str(payload.subtitle_language_fallback or "").strip()
        tunarr["subtitle_language_fallback"] = (
            normalize_subtitle_language(raw, default="") if raw else ""
        )
    updated = Settings.from_mapping({**asdict(settings), "tunarr": tunarr})
    save_settings(DATA_DIR, updated)
    return {
        "ok": True,
        "pad_flex_max_minutes": int(updated.tunarr.pad_flex_max_minutes),
        "exclusion_collection_name": str(updated.tunarr.exclusion_collection_name or "NoLive"),
        "exclusion_collection_id": str(updated.tunarr.exclusion_collection_id or ""),
        "auto_refresh_stations_after_sync": bool(
            updated.tunarr.auto_refresh_stations_after_sync
        ),
        "subtitles_enabled_default": bool(
            getattr(updated.tunarr, "subtitles_enabled_default", False)
        ),
        "subtitle_language_primary": str(
            getattr(updated.tunarr, "subtitle_language_primary", "en") or "en"
        ),
        "subtitle_language_fallback": str(
            getattr(updated.tunarr, "subtitle_language_fallback", "") or ""
        ),
    }


@router.get("/api/admin/live-channels/craft-options")
def live_channels_craft_options_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Motifs / taste / collections + next channel number for the craft form."""
    from projectionist.live_channels.craft import build_craft_options
    from projectionist.live_channels.publish import tunarr_client_from_settings

    settings = _settings()
    existing_numbers: List[int] = []
    if settings.features.live_channels_enabled and str(settings.tunarr.url or "").strip():
        try:
            client = tunarr_client_from_settings(settings)
            for ch in client.list_channels():
                if isinstance(ch, dict) and ch.get("number") is not None:
                    existing_numbers.append(int(ch["number"]))
        except Exception:  # noqa: BLE001
            existing_numbers = []
    return build_craft_options(
        _db(),
        settings=settings,
        owner_user_id=str(user.id),
        existing_channel_numbers=existing_numbers,
    )


@router.post("/api/admin/live-channels/channels/publish")
def live_channels_publish_channel_endpoint(
    payload: LiveChannelsPublishChannelPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Craft + publish one custom station to Tunarr (async by default)."""
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Publishing a channel requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        publish_custom_channel,
        tunarr_client_from_settings,
        wire_plex_media_source,
    )
    from projectionist.live_channels.publish_progress import (
        make_phase_callback,
        progress_store,
        start_publish_job,
    )

    recipe_body = dict(payload.recipe or {})
    if not recipe_body:
        recipe_body = {
            "name": payload.name,
            "number": payload.number,
            "source": payload.source,
            "programming_mode": payload.programming_mode,
            "media_scope": payload.media_scope or "both",
            "motif": payload.motif,
            "cluster_tag": payload.cluster_tag,
            "collection_id": payload.collection_id,
            "collection_title": payload.collection_title,
            "youth_safe": payload.youth_safe,
            "summary": payload.summary,
            "craft_filters": payload.craft_filters or {},
        }
    elif payload.media_scope and not recipe_body.get("media_scope"):
        recipe_body["media_scope"] = payload.media_scope
    if payload.craft_filters and not recipe_body.get("craft_filters"):
        recipe_body["craft_filters"] = payload.craft_filters

    def _run(settings_obj: Settings, on_phase: Any) -> Dict[str, Any]:
        client = tunarr_client_from_settings(settings_obj)
        wire: Dict[str, Any] = {"ok": False, "skipped": True}
        if payload.wire_plex and settings_obj.plex_url and settings_obj.plex_token:
            on_phase("wiring", "Wiring Plex media source…")
            try:
                wire = wire_plex_media_source(
                    client,
                    plex_url=settings_obj.plex_url,
                    plex_token=settings_obj.plex_token,
                    settings=settings_obj,
                )
            except Exception as error:  # noqa: BLE001
                wire = {"ok": False, "message": str(error)[:240]}
        on_phase("publishing", "Publishing station…")
        result = publish_custom_channel(
            client,
            recipe_body,
            fill_programming=bool(payload.fill_programming),
            channel_number_base=int(
                getattr(settings_obj.tunarr, "channel_number_base", 100) or 100
            ),
            settings=settings_obj,
        )
        result["media_source"] = wire
        on_phase("warming", "Preparing streams…")
        return _finalize_live_channels_publish(settings_obj, result, on_phase=on_phase)

    if payload.sync:
        try:
            tunarr_client_from_settings(settings)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        store = progress_store()
        if not store.begin(mode="craft"):
            raise HTTPException(status_code=409, detail="Publish already running.")
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings, on_phase)
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400])
            tunarr = asdict(settings.tunarr)
            tunarr["last_error"] = str(error)[:240]
            save_settings(
                DATA_DIR,
                Settings.from_mapping({**asdict(settings), "tunarr": tunarr}),
            )
            raise HTTPException(
                status_code=502,
                detail=_safe_error_detail(error, "Could not publish channel to Tunarr"),
            ) from error
        store.set_done(str(result.get("note") or "Publish finished."), result=result)
        return {**result, "accepted": True, "async": False}

    settings_snapshot = Settings.from_mapping(asdict(settings))

    def _runner() -> None:
        store = progress_store()
        on_phase = make_phase_callback(store)
        try:
            result = _run(settings_snapshot, on_phase)
        except Exception as error:  # noqa: BLE001
            store.set_error(str(error)[:400] or "Publish failed.")
            return
        store.set_done(str(result.get("note") or "Publish finished."), result=result)

    accepted = start_publish_job(_runner, mode="craft")
    if not accepted.get("accepted"):
        raise HTTPException(
            status_code=409,
            detail=str(accepted.get("message") or "Publish already running."),
        )
    return {
        "ok": True,
        "accepted": True,
        "async": True,
        "busy": True,
        "phase": accepted.get("phase"),
        "percent": accepted.get("percent"),
        "message": accepted.get("message")
        or "Publish started — progress updates below.",
        "mode": "craft",
    }


@router.post("/api/admin/live-channels/channels/{channel_id}/refill")
def live_channels_refill_channel_endpoint(
    channel_id: str,
    payload: Optional[LiveChannelsRefillChannelPayload] = None,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Re-fill an existing station lineup from the library (confirm-gated)."""
    del user
    body = payload or LiveChannelsRefillChannelPayload()
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Refilling a channel requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        refill_channel_lineup,
        tunarr_client_from_settings,
    )

    try:
        client = tunarr_client_from_settings(settings)
        result = refill_channel_lineup(
            client,
            channel_id,
            recipe_payload=body.recipe or None,
            settings=settings,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not refill channel lineup"),
        ) from error

    tunarr = asdict(settings.tunarr)
    if result.get("ok"):
        tunarr["last_publish_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tunarr["last_error"] = ""
    # Persist station_meta / continuity id mutations from refill.
    save_settings(DATA_DIR, Settings.from_mapping({**asdict(settings), "tunarr": tunarr}))
    return result


@router.patch("/api/admin/live-channels/channels/{channel_id}/settings")
def live_channels_station_settings_endpoint(
    channel_id: str,
    payload: LiveChannelsStationSettingsPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Update Projectionist-side station settings (scope, captions, craft filters).

    Saves ``station_meta`` only — does **not** rewrite the Tunarr lineup. Owner
    should Refill after changing decade/genre/theme/scope so the guide matches.
    """
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Updating station settings requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.filters import normalize_craft_filters
    from projectionist.live_channels.publish import (
        apply_channel_subtitles_enabled,
        resolve_media_scope,
        resolve_subtitles_enabled,
        set_station_meta,
        set_station_media_scope,
        station_craft_snapshot,
        tunarr_client_from_settings,
    )
    from projectionist.live_channels.recipes import normalize_media_scope

    cid = str(channel_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="channel_id is required")
    scope = normalize_media_scope(payload.media_scope)
    set_station_media_scope(settings, cid, scope)
    craft_touched = (
        payload.craft_filters is not None
        or payload.motif is not None
        or payload.cluster_tag is not None
    )
    notes: List[str] = [
        f"Station media scope set to {scope}.",
    ]
    if craft_touched:
        craft_payload = (
            normalize_craft_filters(payload.craft_filters or {}).to_dict()
            if payload.craft_filters is not None
            else None
        )
        set_station_meta(
            settings,
            cid,
            craft_filters=craft_payload,
            motif=payload.motif,
            cluster_tag=payload.cluster_tag,
        )
        notes.append("Craft filters saved.")
    notes.append("Refill to apply filters and scope to the lineup.")
    subtitles_enabled = None
    if payload.subtitles_enabled is not None:
        subtitles_enabled = bool(payload.subtitles_enabled)
        set_station_meta(settings, cid, subtitles_enabled=subtitles_enabled)
    # Verify channel exists on Tunarr when reachable; push captions flag when set.
    try:
        client = tunarr_client_from_settings(settings)
        found = any(
            str(ch.get("id") or ch.get("uuid") or "") == cid
            for ch in client.list_channels()
            if isinstance(ch, Mapping)
        )
        if not found:
            raise HTTPException(status_code=404, detail="Channel not found on Tunarr")
        if subtitles_enabled is not None:
            apply_channel_subtitles_enabled(client, cid, enabled=subtitles_enabled)
            notes.append(
                "Show captions when the station has them."
                if subtitles_enabled
                else "Station captions off — Live encode won’t carry subtitle tracks."
            )
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not verify channel on Tunarr"),
        ) from error

    tunarr = asdict(settings.tunarr)
    save_settings(DATA_DIR, Settings.from_mapping({**asdict(settings), "tunarr": tunarr}))
    craft = station_craft_snapshot(settings, cid)
    return {
        "ok": True,
        "channel_id": cid,
        "media_scope": resolve_media_scope(settings, channel_id=cid),
        "subtitles_enabled": resolve_subtitles_enabled(settings, channel_id=cid),
        "motif": craft.get("motif") or "",
        "cluster_tag": craft.get("cluster_tag") or "",
        "craft_filters": dict(craft.get("craft_filters") or {}),
        "source": craft.get("source") or "",
        "refill_required": True,
        "message": " ".join(notes),
    }


@router.get("/api/admin/live-channels/continuity/status")
def live_channels_continuity_status_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner progress poll for Repair continuity / Rescan filler."""
    del user
    from projectionist.live_channels.continuity_progress import (
        build_continuity_job_status,
    )

    return build_continuity_job_status()


@router.post("/api/admin/live-channels/continuity/repair")
def live_channels_continuity_repair_endpoint(
    payload: Optional[LiveChannelsContinuityPayload] = None,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Start rescan + continuity repair as a background job (confirm-gated).

    Remount / force-scan / attach / refill / warm often exceeds reverse-proxy
    timeouts when run synchronously. The owner UI polls
    ``GET …/continuity/status`` for stage progress.

    Pass ``sync=true`` in the JSON body only for tests / diagnostics.
    """
    del user
    body = payload or LiveChannelsContinuityPayload()
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Continuity repair requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.continuity_progress import (
        ContinuityRepairError,
        execute_continuity_repair,
        make_phase_callback,
        progress_store,
        start_continuity_repair_job,
    )

    mode = "rescan" if body.rescan and not body.repair else "repair"
    if body.rescan and body.repair:
        mode = "repair"

    # Optional sync path for unit tests / curl diagnostics.
    sync = bool(getattr(body, "sync", False))
    if sync:
        store = progress_store()
        if not store.begin(mode=mode):
            raise HTTPException(
                status_code=409,
                detail="Continuity repair already running.",
            )
        on_phase = make_phase_callback(store)
        try:
            result = execute_continuity_repair(
                settings,
                data_dir=DATA_DIR,
                rescan=bool(body.rescan),
                repair=bool(body.repair),
                refill_lineups=bool(body.refill_lineups),
                on_phase=on_phase,
                save_settings_fn=save_settings,
            )
        except ContinuityRepairError as error:
            store.set_error(error.message)
            raise HTTPException(status_code=error.status_code, detail=error.message) from error
        except Exception as error:  # noqa: BLE001 — clear busy; avoid stuck 409
            store.set_error(str(error)[:400] or "Continuity repair failed.")
            raise HTTPException(
                status_code=500,
                detail=_safe_error_detail(error, "Continuity repair failed"),
            ) from error
        store.set_done(str(result.get("message") or "Continuity update finished."), result=result)
        return {**result, "accepted": True, "async": False}

    settings_snapshot = Settings.from_mapping(asdict(settings))

    def _runner() -> None:
        store = progress_store()
        on_phase = make_phase_callback(store)
        try:
            result = execute_continuity_repair(
                settings_snapshot,
                data_dir=DATA_DIR,
                rescan=bool(body.rescan),
                repair=bool(body.repair),
                refill_lineups=bool(body.refill_lineups),
                on_phase=on_phase,
                save_settings_fn=save_settings,
            )
        except ContinuityRepairError as error:
            store.set_error(error.message)
            return
        store.set_done(
            str(result.get("message") or "Continuity update finished."),
            result=result,
        )

    accepted = start_continuity_repair_job(_runner, mode=mode)
    if not accepted.get("accepted"):
        raise HTTPException(
            status_code=409,
            detail=str(accepted.get("message") or "Continuity repair already running."),
        )
    return {
        "ok": True,
        "accepted": True,
        "async": True,
        "busy": True,
        "phase": accepted.get("phase"),
        "percent": accepted.get("percent"),
        "message": accepted.get("message")
        or "Continuity repair started — progress updates below.",
        "mode": mode,
    }


@router.delete("/api/admin/live-channels/channels/{channel_id}")
def live_channels_delete_channel_endpoint(
    channel_id: str,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Delete a Tunarr station (owner manage path)."""
    del user
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    from projectionist.live_channels.publish import (
        delete_published_channel,
        tunarr_client_from_settings,
    )

    try:
        client = tunarr_client_from_settings(settings)
        return delete_published_channel(client, channel_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not delete channel"),
        ) from error


@router.get("/api/admin/live-channels/plex-attach")
def live_channels_plex_attach_endpoint(
    request: Request,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Plex Live TV attach checklist — add Tunarr as an *additional* tuner."""
    del user
    from projectionist.live_channels.plex_attach import (
        build_plex_attach,
        probe_existing_plex_livetv,
        probe_tuner_discovery,
    )

    settings = _settings()
    api_url = str(settings.tunarr.url or "")
    discovery = probe_tuner_discovery(api_url)
    existing = probe_existing_plex_livetv(settings)
    forwarded = str(request.headers.get("x-forwarded-host") or "").strip()
    request_host = forwarded or str(request.headers.get("host") or "").strip()
    attach = build_plex_attach(
        settings,
        request_host=request_host,
        discovery_ok=bool(discovery.get("ok")) if discovery else None,
        existing_livetv=existing,
        discovery_base_url=api_url,
    )
    attach["discovery"] = {
        "ok": discovery.get("ok"),
        "message": discovery.get("message") or "",
        "probed_base": api_url,
    }
    return attach


def _persist_plex_guide_attach(settings: Settings, result: Dict[str, Any]) -> None:
    tunarr = asdict(settings.tunarr)
    tunarr["last_guide_attach_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    tunarr["last_guide_attach_ok"] = bool(result.get("ok"))
    tunarr["last_guide_attach_message"] = str(
        result.get("message") or result.get("error") or ""
    )[:240]
    tunarr["last_guide_attach_dvr_key"] = str(result.get("dvr_key") or "")
    tunarr["last_plex_mapped"] = int(result.get("mapped") or 0)
    tunarr["last_plex_expected"] = int(result.get("expected") or 0)
    tunarr["last_plex_sync_ok"] = bool(result.get("ok"))
    tunarr["last_plex_sync_message"] = tunarr["last_guide_attach_message"]
    save_settings(
        DATA_DIR,
        Settings.from_mapping({**asdict(settings), "tunarr": tunarr}),
    )


@router.post("/api/admin/live-channels/plex-attach-guide")
def live_channels_plex_attach_guide_endpoint(
    request: Request,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Attach Tunarr XMLTV to Plex via PMS API (separate DVR; OTA left alone)."""
    del user
    from projectionist.live_channels.plex_attach import attach_tunarr_xmltv_to_plex
    from projectionist.live_channels.publish import (
        prepare_channels_for_playback,
        resolve_channel_icon_url,
        tunarr_client_from_settings,
    )

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    forwarded = str(request.headers.get("x-forwarded-host") or "").strip()
    request_host = forwarded or str(request.headers.get("host") or "").strip()
    prepare: Dict[str, Any] = {"ok": False, "skipped": True}
    try:
        prepare = prepare_channels_for_playback(
            tunarr_client_from_settings(settings),
            settings=settings,
            icon_url=resolve_channel_icon_url(settings),
        )
    except Exception:  # noqa: BLE001 — attach can still proceed
        prepare = {"ok": False, "skipped": True}
    result = attach_tunarr_xmltv_to_plex(settings, request_host=request_host)
    result["labels"] = prepare.get("labels") or {}
    result["prepare"] = prepare
    _persist_plex_guide_attach(settings, result)
    if not result.get("ok"):
        detail = str(
            result.get("error")
            or result.get("message")
            or "Could not attach Tunarr guide in Plex"
        )
        mapped = result.get("mapped")
        expected = result.get("expected")
        if expected and mapped is not None:
            detail = f"{detail} (Mapped {mapped}/{expected})"
        raise HTTPException(status_code=400, detail=detail)
    return result


@router.post("/api/admin/live-channels/plex-repair")
def live_channels_plex_repair_endpoint(
    request: Request,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Recreate Tunarr HDHR device + XMLTV DVR and force full channel remap."""
    del user
    from projectionist.live_channels.plex_attach import repair_plex_tunarr_livetv
    from projectionist.live_channels.publish import (
        prepare_channels_for_playback,
        resolve_channel_icon_url,
        tunarr_client_from_settings,
    )

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    forwarded = str(request.headers.get("x-forwarded-host") or "").strip()
    request_host = forwarded or str(request.headers.get("host") or "").strip()
    try:
        prepare_channels_for_playback(
            tunarr_client_from_settings(settings),
            settings=settings,
            icon_url=resolve_channel_icon_url(settings),
        )
    except Exception:  # noqa: BLE001
        pass
    result = repair_plex_tunarr_livetv(settings, request_host=request_host)
    _persist_plex_guide_attach(settings, result)
    if not result.get("ok"):
        detail = str(
            result.get("error")
            or result.get("message")
            or "Could not repair Tunarr in Plex"
        )
        mapped = result.get("mapped")
        expected = result.get("expected")
        if expected and mapped is not None:
            detail = f"{detail} (Mapped {mapped}/{expected})"
        raise HTTPException(status_code=400, detail=detail)
    return result


@router.post("/api/admin/live-channels/prepare-playback")
def live_channels_prepare_playback_endpoint(
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Start-over deep playheads + warm HLS/MPEG-TS so Plex Live TV can tune."""
    del user
    from projectionist.live_channels.publish import (
        prepare_channels_for_playback,
        resolve_channel_icon_url,
        tunarr_client_from_settings,
    )

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    try:
        client = tunarr_client_from_settings(settings)
        result = prepare_channels_for_playback(
            client,
            settings=settings,
            icon_url=resolve_channel_icon_url(settings),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not prepare Live Channels playback"),
        ) from error
    result["scheduler"] = get_stream_warm_scheduler().last_status()
    return result


@router.get("/api/admin/live-channels/tunarr-logs")
def live_channels_tunarr_logs_endpoint(
    lines: int = 200,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Recent Tunarr / broadcast-engine logs for the Admin Live Channels panel."""
    del user
    from projectionist.live_channels.logs import fetch_tunarr_logs

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    return fetch_tunarr_logs(settings, lines=lines)


@router.get("/api/live-channels/on-now")
def live_channels_on_now_endpoint(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    """Household-readable guide snapshot (channel name + now/next). Empty-safe.

    Owners and members may call this. Youth accounts filter rated titles via the
    existing rating gate when Tunarr programs carry content ratings. Dual-watch
    CTA: Projectionist /live primary, Plex Live TV secondary.
    """
    from projectionist.live_channels.guide import build_on_now_snapshot
    from projectionist.live_channels.nudges import maybe_deliver_live_channels_ready_nudge
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    settings = _settings()
    youth_ceiling = None
    if youth_gate_active(user):
        youth_ceiling = resolve_youth_max_rating(settings)
    snapshot = build_on_now_snapshot(settings, youth_max_rating=youth_ceiling)
    # Soft, deduped ready nudge for opt-in members (never blocks the response).
    try:
        maybe_deliver_live_channels_ready_nudge(
            _db(),
            settings,
            ready=bool(snapshot.get("ready")),
            channel_count=int(snapshot.get("count") or 0),
        )
    except Exception:  # noqa: BLE001
        logger.debug("Live Channels ready nudge skipped", exc_info=True)
    return snapshot


@router.get("/api/live-channels/guide")
def live_channels_guide_endpoint(
    hours: float = 6.0,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Wider channel × time guide for the Projectionist `/live` EPG (1–12 hours)."""
    from projectionist.live_channels.guide import build_guide_snapshot
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    settings = _settings()
    youth_ceiling = None
    if youth_gate_active(user):
        youth_ceiling = resolve_youth_max_rating(settings)
    return build_guide_snapshot(
        settings,
        youth_max_rating=youth_ceiling,
        hours=hours,
    )


@router.get("/api/live-channels/channels/{channel_id}/subtitles")
def live_channels_channel_subtitles_endpoint(
    channel_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Richer `/live` CC metadata for the now-playing airing (Plex tracks when mapped)."""
    from projectionist.live_channels.guide import build_on_now_snapshot
    from projectionist.library.subtitles import live_subtitles_payload
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    cid = str(channel_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="channel_id is required")
    youth_ceiling = None
    if youth_gate_active(user):
        youth_ceiling = resolve_youth_max_rating(settings)
    snap = build_on_now_snapshot(settings, youth_max_rating=youth_ceiling)
    channel = next(
        (c for c in snap.get("channels") or [] if str(c.get("id")) == cid),
        None,
    )
    now = channel.get("now") if isinstance(channel, Mapping) else None
    payload = live_subtitles_payload(settings, channel_id=cid, now_program=now)
    # Attach proxy URLs for fetchable Plex sidecar streams (LivePlayer TextTrack).
    streams = []
    for row in payload.get("plex_streams") or []:
        if not isinstance(row, Mapping):
            continue
        item = dict(row)
        stream_id = str(item.get("id") or "").strip()
        if stream_id and item.get("key"):
            item["proxy_url"] = (
                f"/api/library/items/{payload.get('plex_rating_key')}/subtitles/"
                f"{stream_id}/file"
            )
        streams.append(item)
    payload["plex_streams"] = streams
    return payload


@router.post("/api/live-channels/channels/{channel_id}/subtitles/download")
def live_channels_channel_subtitles_download_endpoint(
    channel_id: str,
    payload: LiveChannelsDownloadSubtitlesPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Ask Plex to download preferred-language subs for the now-playing library title."""
    from projectionist.live_channels.guide import build_on_now_snapshot
    from projectionist.library.subtitles import download_preferred_subtitles
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Asking Plex for subtitles requires confirm=true",
        )
    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    cid = str(channel_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="channel_id is required")
    youth_ceiling = None
    if youth_gate_active(user):
        youth_ceiling = resolve_youth_max_rating(settings)
    snap = build_on_now_snapshot(settings, youth_max_rating=youth_ceiling)
    channel = next(
        (c for c in snap.get("channels") or [] if str(c.get("id")) == cid),
        None,
    )
    now = channel.get("now") if isinstance(channel, Mapping) else None
    rating_key = str((now or {}).get("plex_rating_key") or "").strip()
    if not rating_key:
        return {
            "ok": False,
            "downloaded": False,
            "message": "This airing isn’t mapped to a Plex library title, so Projectionist can’t ask Plex for subtitles.",
            "reason": "no_plex_mapping",
        }
    prefer_sdh = bool(getattr(user, "is_youth", False))
    return download_preferred_subtitles(
        settings,
        rating_key,
        language=str(payload.language or ""),
        prefer_sdh=prefer_sdh,
    )


class LiveChannelsTunePayload(BaseModel):
    channel_id: str = ""


@router.post("/api/live-channels/tune")
def live_channels_tune_endpoint(
    payload: LiveChannelsTunePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Warm a station for Projectionist `/live` at the live edge (no start-over).

    Channel leave→rejoin must not shift ``startTime`` / force-align into flex.
    Background start-over after surfing away was landing Continuity filler while
    the OSD still showed the mid-episode guide slot.
    """
    from projectionist.live_channels.guide import (
        build_on_now_snapshot,
        youth_allows_channel_now,
    )
    from projectionist.live_channels.publish import (
        prepare_channels_for_playback,
        resolve_channel_icon_url,
        tunarr_client_from_settings,
    )
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    channel_id = str(payload.channel_id or "").strip()
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id is required")

    youth_ceiling = None
    if youth_gate_active(user):
        youth_ceiling = resolve_youth_max_rating(settings)
        snap = build_on_now_snapshot(settings, youth_max_rating=None)
        target = next(
            (c for c in snap.get("channels") or [] if str(c.get("id")) == channel_id),
            None,
        )
        if target and not youth_allows_channel_now(target, max_rating=youth_ceiling or ""):
            raise HTTPException(
                status_code=403,
                detail="This channel’s current program is above your youth rating limit.",
            )

    try:
        client = tunarr_client_from_settings(settings)
        result = prepare_channels_for_playback(
            client,
            settings=settings,
            channel_ids=[channel_id],
            icon_url=resolve_channel_icon_url(settings),
            # Live edge only — never start-over on channel surf / rejoin.
            align_playhead=False,
            # Never re-warm under an already-watching session.
            skip_active_sessions=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Could not tune Live Channel"),
        ) from error
    result["channel_id"] = channel_id
    result["stream_url"] = f"/api/live-channels/stream/{channel_id}/index.m3u8"
    return result


@router.get("/api/live-channels/stream/{channel_id}/index.m3u8")
@router.get("/api/live-channels/stream/{channel_id}/master.m3u8")
def live_channels_stream_master(
    channel_id: str,
    user=Depends(get_current_user_dep),
) -> Response:
    """Auth’d HLS master playlist proxy (session required; no Tunarr LAN leak)."""
    return _live_channels_stream_response(channel_id, "index.m3u8", user=user)


@router.get("/api/live-channels/stream/{channel_id}/{path:path}")
def live_channels_stream_path(
    channel_id: str,
    path: str,
    user=Depends(get_current_user_dep),
) -> Response:
    """Auth’d HLS media playlist / segment proxy under a channel."""
    return _live_channels_stream_response(channel_id, path, user=user)


def _live_channels_stream_response(
    channel_id: str,
    relative_path: str,
    *,
    user,
) -> Response:
    from projectionist.live_channels.guide import (
        build_on_now_snapshot,
        youth_allows_channel_now,
    )
    from projectionist.live_channels.stream_proxy import (
        iter_chunked,
        proxy_channel_stream,
    )
    from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_gate_active

    settings = _settings()
    if not settings.features.live_channels_enabled:
        raise HTTPException(status_code=400, detail="Live Channels is not enabled")
    cid = str(channel_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="channel_id is required")

    if youth_gate_active(user):
        ceiling = resolve_youth_max_rating(settings)
        # Only gate the master/media playlist entry — segment fetches reuse the same
        # session after the viewer passed the program check.
        if str(relative_path or "").endswith(".m3u8"):
            snap = build_on_now_snapshot(settings, youth_max_rating=None)
            target = next(
                (c for c in snap.get("channels") or [] if str(c.get("id")) == cid),
                None,
            )
            if target and not youth_allows_channel_now(target, max_rating=ceiling or ""):
                raise HTTPException(
                    status_code=403,
                    detail="This channel’s current program is above your youth rating limit.",
                )

    try:
        asset = proxy_channel_stream(settings, cid, relative_path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Live stream unavailable"),
        ) from error

    headers = {
        "Cache-Control": "no-store",
        "Access-Control-Expose-Headers": "Content-Type",
    }
    return StreamingResponse(
        iter_chunked(asset["body"]),
        media_type=str(asset.get("media_type") or "application/octet-stream"),
        status_code=int(asset.get("status") or 200),
        headers=headers,
    )



def register_live_channels_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
    db_factory: Callable[[], Any],
    safe_error_detail: Callable[..., str],
    data_dir,
) -> None:
    """Attach Live Channels routes to the FastAPI app."""
    global _settings_factory, _db_factory, _safe_error_detail_fn, DATA_DIR
    _settings_factory = settings_factory
    _db_factory = db_factory
    _safe_error_detail_fn = safe_error_detail
    DATA_DIR = data_dir
    app.include_router(router)
