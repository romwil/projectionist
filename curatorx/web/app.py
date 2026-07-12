"""FastAPI application for CuratorX."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from curatorx import __version__
from curatorx.agent.curator import CuratorAgent, stream_agent
from curatorx.agent.providers import LLMProviderError
from curatorx.agent.tools import (
    check_radarr_already_exists,
    check_sonarr_already_exists,
    execute_confirmed_action,
    mark_in_radarr,
    mark_in_sonarr,
)
from curatorx.config_store import (
    ANTHROPIC_MODEL_OPTIONS,
    LLM_MODEL_DEFAULTS,
    LLM_PROVIDER_DEFAULTS,
    Settings,
    load_dotenv_file,
    load_merged_settings,
    normalize_path_settings,
    normalize_settings_llm,
    plex_configuration_error,
    radarr_add_configuration_error,
    resolve_llm_model,
    resolve_plex_section,
    resolve_radarr_root_folder,
    resolve_sonarr_root_folder,
    save_settings,
    secret_field_sources,
    sonarr_add_configuration_error,
    seerr_configuration_error,
    plex_collections_configuration_error,
    uses_seerr_request_path,
    validate_arr_root_folder,
    validate_llm_settings,
)
from curatorx.connectors.plex import PlexClient
from curatorx.connectors.plex_collections import list_collections as list_plex_collections
from curatorx.connectors.radarr import RadarrClient
from curatorx.connectors.seerr import SeerrClient
from curatorx.connectors.sonarr import SonarrClient
from curatorx.library.db import DEFAULT_LENS_ID
from curatorx.library.health import compute_library_health
from curatorx.library.facets import ensure_library_facet_index
from curatorx.library.episodes import query_episodes, summarize_tv_progress
from curatorx.library.facets import library_facet_catalog
from curatorx.library.query import (
    aggregate_library,
    filters_from_mapping,
    library_overview,
    query_library,
    query_library_async,
)
from curatorx.library.titles import get_title_detail
from curatorx.models.schemas import (
    ActionConfirmRequest,
    ActiveLensPayload,
    ChatRequest,
    EngagementStreakResponse,
    Lens,
    LensCreate,
    LensUpdate,
    MessageFeedbackRequest,
    PersonaMetrics,
    PersonaMetricsUpdate,
    PersonaPresetSummary,
    PersonaPreviewResponse,
    PersonaUiCopy,
    PreferenceSignal,
    RatingPrompt,
    SystemConfigUpdate,
    UserReview,
    UserReviewCreate,
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistPin,
)
from curatorx.persona import (
    build_assembled_persona_prompt,
    build_rendered_behavioral_prompt,
    derive_persona_mode,
    get_preset,
    list_presets,
    persona_row_to_dict,
)
from curatorx.persona.presets import persona_ui_for, typing_phrases_for
from curatorx.preferences.purge import suggest_purge_candidates
from curatorx.preferences.store import remember_preference
from curatorx.reviews.store import (
    dismiss_prompt,
    get_reviews,
    list_pending_prompts,
    list_titles_to_rate,
    mark_prompts_surfaced,
    save_review,
)
from curatorx.reviews.plex_sync import sync_review_rating_to_plex
from curatorx.web.auth import (
    authenticate_plex_user,
    bootstrap_owner,
    clear_session_cookie,
    get_current_user_dep,
    require_role,
    set_session_cookie,
    sync_user_seerr_from_token,
    try_get_current_user,
)
from curatorx.web.jobs import get_job_manager, get_sync_scheduler
from curatorx.web.webhooks import register_webhook_routes
from curatorx.web.setup import (
    SECRET_FIELDS,
    build_certifications_status,
    build_setup_status,
    build_wizard_status,
    invalidate_certifications_on_settings_change,
    merge_secret_fields,
    record_service_integration,
    resolve_test_payload,
    sync_settings_to_db,
    normalize_plex_type,
    test_fanart,
    test_llm,
    test_plex,
    test_radarr,
    test_seerr,
    test_sonarr,
    test_tautulli,
    test_tmdb,
)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/config"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if os.environ.get("CURATORX_SKIP_DOTENV") != "1":
    load_dotenv_file()

from curatorx.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("CuratorX startup (version %s, data_dir=%s)", __version__, DATA_DIR)

    logger.info("Startup: initializing job manager…")
    manager = get_job_manager()
    logger.info("Startup: job manager ready")

    logger.info("Startup: ensuring seed data…")
    try:
        manager.db.ensure_seed_data()
        logger.info("Startup: seed data done")
    except Exception:  # noqa: BLE001
        logger.exception("Startup: seed data failed (continuing)")

    def _warm_library_facets() -> None:
        try:
            logger.info("Startup: background library facet index check…")
            rebuilt = ensure_library_facet_index(manager.db)
            logger.info("Startup: library facet index check done (rebuilt=%s)", rebuilt)
        except Exception:  # noqa: BLE001
            logger.exception("Startup: library facet index warm-up failed (non-fatal)")

    # Facet rebuild can block for a long time on large libraries — never await it here.
    threading.Thread(
        target=_warm_library_facets,
        daemon=True,
        name="library-facet-warmup",
    ).start()

    logger.info("Startup: starting sync scheduler…")
    get_sync_scheduler().start()
    logger.info("Job manager and sync scheduler ready")
    yield
    get_sync_scheduler().stop()
    logger.info("CuratorX shutdown complete")


app = FastAPI(title="CuratorX", version=__version__, lifespan=lifespan)


def _row_to_lens(row: Any) -> Lens:
    return Lens(
        lens_id=str(row["lens_id"]),
        lens_name=str(row["lens_name"]),
        description=str(row["description"] or ""),
        created_at=str(row["created_at"]) if row["created_at"] is not None else None,
    )


def _persona_dict(row: Any) -> dict[str, Any]:
    data = persona_row_to_dict(row)
    mode = derive_persona_mode(data)
    behavioral = build_rendered_behavioral_prompt(data)
    assembled = build_assembled_persona_prompt(data)
    return {
        **data,
        "persona_mode": mode,
        "behavioral_prompt": behavioral,
        "assembled_prompt": assembled,
    }


def _row_to_persona(row: Any) -> PersonaMetrics:
    data = _persona_dict(row)
    curator_name = str(data.get("curator_name") or "Curator")
    preset_id = str(data["persona_preset_id"]) if data.get("persona_preset_id") else None
    ui = persona_ui_for(preset_id, curator_name)
    return PersonaMetrics(
        metric_id=str(data.get("metric_id") or "current_profile"),
        curator_name=curator_name,
        persona_identity=str(data.get("persona_identity") or ""),
        val_bro_prof=float(data.get("val_bro_prof") or 0.5),
        val_dipl_snark=float(data.get("val_dipl_snark") or 0.5),
        val_pass_auto=float(data.get("val_pass_auto") or 0.5),
        persona_preset_id=preset_id,
        persona_prompt_override=str(data["persona_prompt_override"])
        if data.get("persona_prompt_override") is not None
        else None,
        persona_mode=str(data.get("persona_mode") or "sliders"),
        behavioral_prompt=str(data.get("behavioral_prompt") or ""),
        assembled_prompt=str(data.get("assembled_prompt") or ""),
        persona_ui=PersonaUiCopy(**ui),
        last_modified=str(data["last_modified"]) if data.get("last_modified") is not None else None,
    )


def _resolve_lens_id(lens_id: Optional[str]) -> str:
    db = _db()
    resolved = (lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID).strip() or DEFAULT_LENS_ID
    if not db.get_lens(resolved):
        raise HTTPException(status_code=404, detail=f"Unknown lens_id: {resolved}")
    return resolved


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
elif STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class FeatureFlagsPayload(BaseModel):
    multi_user_enabled: bool = False
    seerr_enabled: bool = False
    plex_collections_enabled: bool = False


class AuthSettingsPayload(BaseModel):
    mode: str = "disabled"
    plex_login_enabled: bool = True
    oidc_enabled: bool = False
    local_login_enabled: bool = False


class PlexLoginPayload(BaseModel):
    auth_token: str = Field(min_length=1)


class UserRoleUpdatePayload(BaseModel):
    role: str = Field(pattern="^(owner|member|guest)$")


class SeerrSyncPayload(BaseModel):
    auth_token: str = Field(min_length=1)


class SeerrSettingsPayload(BaseModel):
    url: str = ""
    api_key: str = ""
    link_on_login: bool = True
    require_linked_user_for_requests: bool = False


class SettingsPayload(BaseModel):
    plex_url: str = ""
    plex_token: str = ""
    plex_movie_section: str = ""
    plex_tv_section: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    movies_root: str = ""
    tv_root: str = ""
    radarr_root_folder: str = ""
    sonarr_root_folder: str = ""
    radarr_quality_profile_id: int = 1
    sonarr_quality_profile_id: int = 1
    tmdb_api_key: str = ""
    tvdb_api_key: str = ""
    fanart_api_key: str = ""
    tautulli_url: str = ""
    tautulli_api_key: str = ""
    llm_provider: str = "openai"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_embedding_model: str = ""
    llm_embedding_base_url: str = ""
    onboarding_complete: bool = False
    library_sync_interval_hours: int = Field(default=24, ge=1, le=168)
    library_sync_hour: Optional[int] = Field(default=None, ge=0, le=23)
    tv_page_size: int = Field(default=500, ge=50, le=2000)
    library_enrich_workers: int = Field(default=6, ge=1, le=16)
    sync_reviews_to_plex: bool = True
    features: FeatureFlagsPayload = Field(default_factory=FeatureFlagsPayload)
    auth: AuthSettingsPayload = Field(default_factory=AuthSettingsPayload)
    seerr: SeerrSettingsPayload = Field(default_factory=SeerrSettingsPayload)


class PlexCollectionProposePayload(BaseModel):
    title: str = Field(min_length=1)
    media_type: str
    rating_keys: List[str] = Field(default_factory=list)


class PlexCollectionItemsProposePayload(BaseModel):
    media_type: str
    rating_keys: List[str] = Field(min_length=1)
    collection_title: Optional[str] = None
    collection_rating_key: Optional[str] = None


class ThreadCreatePayload(BaseModel):
    thread_title: Optional[str] = None
    lens_id: Optional[str] = None
    context_hash: Optional[str] = None


class ThreadUpdatePayload(BaseModel):
    thread_title: str = Field(min_length=1, max_length=200)


class TestPayload(BaseModel):
    plex_url: str = ""
    plex_token: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    tmdb_api_key: str = ""
    fanart_api_key: str = ""
    tautulli_url: str = ""
    tautulli_api_key: str = ""
    llm_provider: str = "openai"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    seerr_url: str = ""
    seerr_api_key: str = ""


def _settings() -> Settings:
    return load_merged_settings(DATA_DIR)


def _mask_settings(settings: Settings) -> Dict[str, Any]:
    payload = asdict(settings)
    sources = secret_field_sources(DATA_DIR)
    for field in SECRET_FIELDS:
        payload[f"{field}_set"] = bool(getattr(settings, field))
        payload[f"{field}_source"] = sources.get(field, "")
        payload[field] = ""
    seerr_payload = dict(payload.get("seerr") or {})
    seerr_payload["api_key_set"] = bool(settings.seerr.api_key)
    seerr_payload["api_key"] = ""
    payload["seerr"] = seerr_payload
    return payload


def _db():
    return get_job_manager().db


register_webhook_routes(app, db_factory=_db, settings_factory=_settings)


def _features_payload(user=None, *, authenticated: bool = True) -> Dict[str, Any]:
    settings = _settings()
    if user is None:
        user = bootstrap_owner(_db())
    request_path = "seerr" if uses_seerr_request_path(settings, role=user.role) else "arr"
    payload: Dict[str, Any] = {
        "features": {
            "multi_user_enabled": settings.features.multi_user_enabled,
            "seerr_enabled": settings.features.seerr_enabled,
        },
        "auth": {
            "mode": settings.auth.mode,
            "plex_login_enabled": settings.auth.plex_login_enabled,
            "oidc_enabled": settings.auth.oidc_enabled,
            "local_login_enabled": settings.auth.local_login_enabled,
        },
        "seerr": {
            "link_on_login": settings.seerr.link_on_login,
            "require_linked_user_for_requests": settings.seerr.require_linked_user_for_requests,
        },
        "request_path": request_path,
        "authenticated": authenticated,
    }
    if authenticated and user is not None:
        payload["user"] = {
            "id": user.id,
            "display_name": user.display_name,
            "role": user.role,
            "seerr_user_id": user.seerr_user_id,
            "avatar_url": user.avatar_url,
        }
    else:
        payload["user"] = None
    return payload


def _message_text_excerpt(blocks: List[Mapping[str, Any]], *, limit: int = 500) -> str:
    parts: List[str] = []
    for block in blocks:
        if str(block.get("type") or "") == "text":
            content = str(block.get("content") or "").strip()
            if content:
                parts.append(content)
    text = " ".join(parts).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _serve_index() -> HTMLResponse:
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    fallback = STATIC_DIR / "index.html"
    if fallback.exists():
        return HTMLResponse(fallback.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>CuratorX</h1><p>Build the frontend with <code>npm run build</code>.</p>")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _serve_index()


@app.get("/config", response_class=HTMLResponse)
def config_page() -> HTMLResponse:
    return _serve_index()


@app.get("/title/{media_type}/{item_id}", response_class=HTMLResponse)
def title_page(media_type: str, item_id: str) -> HTMLResponse:
    return _serve_index()


@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return _serve_index()


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/features")
def get_features(request: Request) -> Dict[str, Any]:
    settings = _settings()
    db = _db()
    if settings.features.multi_user_enabled:
        user = try_get_current_user(request, db)
        if user is None:
            return _features_payload(None, authenticated=False)
        return _features_payload(user, authenticated=True)
    return _features_payload(bootstrap_owner(db), authenticated=True)


@app.get("/api/auth/me")
def auth_me(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return {"user": user.to_dict(), "authenticated": True}


@app.post("/api/auth/plex")
def auth_plex(payload: PlexLoginPayload, response: Response) -> Dict[str, Any]:
    user = authenticate_plex_user(payload.auth_token, _db())
    set_session_cookie(response, user.id)
    return {"user": user.to_dict(), "authenticated": True}


@app.post("/api/auth/logout")
def auth_logout(response: Response) -> Dict[str, bool]:
    clear_session_cookie(response)
    return {"logged_out": True}


@app.get("/api/users")
def list_users(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    items = _db().list_users()
    return {"items": items, "count": len(items)}


@app.patch("/api/users/{user_id}")
def patch_user_role(
    user_id: str,
    payload: UserRoleUpdatePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    if user_id == user.id and payload.role != "owner":
        raise HTTPException(status_code=400, detail="Cannot demote your own owner account")
    try:
        updated = _db().update_user_role(user_id, payload.role)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"user": updated}


@app.post("/api/users/{user_id}/sync-seerr")
def sync_user_seerr(
    user_id: str,
    payload: SeerrSyncPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    updated = sync_user_seerr_from_token(user_id, payload.auth_token, _db())
    return {"user": updated}


@app.get("/api/setup/status")
def setup_status() -> Dict[str, Any]:
    return build_setup_status(_settings(), _db())


@app.get("/api/setup/wizard")
def setup_wizard() -> Dict[str, Any]:
    return build_wizard_status(_settings(), _db())


@app.get("/api/setup/certifications")
def setup_certifications() -> Dict[str, Any]:
    return build_certifications_status(_db())


@app.get("/api/setup/llm-providers")
def llm_providers() -> Dict[str, Any]:
    return {
        "base_urls": LLM_PROVIDER_DEFAULTS,
        "models": LLM_MODEL_DEFAULTS,
        "anthropic_models": list(ANTHROPIC_MODEL_OPTIONS),
    }


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    return _mask_settings(_settings())


@app.put("/api/settings")
def put_settings(payload: SettingsPayload) -> Dict[str, Any]:
    settings_path = DATA_DIR / "settings.json"
    before = Settings.load(settings_path)
    existing = _settings()
    merged = merge_secret_fields(payload.model_dump(), existing)
    settings = normalize_path_settings(normalize_settings_llm(Settings.from_mapping(merged)))
    wizard_status = build_wizard_status(settings, _db())
    if not settings.onboarding_complete and wizard_status["onboarding_complete"]:
        settings = Settings.from_mapping({**asdict(settings), "onboarding_complete": True})
    invalidate_certifications_on_settings_change(_db(), before, settings, payload.model_dump())
    save_settings(DATA_DIR, settings)
    sync_settings_to_db(_db(), settings)
    return _mask_settings(settings)


@app.post("/api/setup/test/plex")
def api_test_plex(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_plex(resolved["plex_url"], resolved["plex_token"])
    record_service_integration(
        _db(),
        "plex",
        base_url=payload.plex_url or resolved["plex_url"],
        api_token=resolved["plex_token"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/radarr")
def api_test_radarr(payload: TestPayload) -> Dict[str, Any]:
    settings = _settings()
    resolved = resolve_test_payload(payload.model_dump(), settings)
    result = test_radarr(
        resolved["radarr_url"],
        resolved["radarr_api_key"],
        configured_root_folder=resolve_radarr_root_folder(settings),
    )
    record_service_integration(
        _db(),
        "radarr",
        base_url=resolved["radarr_url"],
        api_token=resolved["radarr_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/sonarr")
def api_test_sonarr(payload: TestPayload) -> Dict[str, Any]:
    settings = _settings()
    resolved = resolve_test_payload(payload.model_dump(), settings)
    result = test_sonarr(
        resolved["sonarr_url"],
        resolved["sonarr_api_key"],
        configured_root_folder=resolve_sonarr_root_folder(settings),
    )
    record_service_integration(
        _db(),
        "sonarr",
        base_url=resolved["sonarr_url"],
        api_token=resolved["sonarr_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/tmdb")
def api_test_tmdb(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_tmdb(resolved["tmdb_api_key"])
    record_service_integration(
        _db(),
        "tmdb",
        api_token=resolved["tmdb_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/fanart")
def api_test_fanart(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_fanart(resolved["fanart_api_key"])
    record_service_integration(
        _db(),
        "fanart",
        api_token=resolved["fanart_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/tautulli")
def api_test_tautulli(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_tautulli(resolved["tautulli_url"], resolved["tautulli_api_key"])
    record_service_integration(
        _db(),
        "tautulli",
        base_url=resolved["tautulli_url"],
        api_token=resolved["tautulli_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/seerr")
def api_test_seerr(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_seerr(resolved["seerr_url"], resolved["seerr_api_key"])
    record_service_integration(
        _db(),
        "seerr",
        base_url=resolved["seerr_url"],
        api_token=resolved["seerr_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/llm")
def api_test_llm(payload: TestPayload) -> Dict[str, Any]:
    resolved = resolve_test_payload(payload.model_dump(), _settings())
    result = test_llm(
        resolved["llm_provider"],
        resolved["llm_base_url"],
        resolved["llm_api_key"],
        resolved["llm_model"],
    )
    record_service_integration(
        _db(),
        "llm",
        base_url=resolved["llm_base_url"],
        api_token=resolved["llm_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.get("/api/plex/sections")
def plex_sections() -> List[Dict[str, str]]:
    settings = _settings()
    if not settings.plex_url or not settings.plex_token:
        raise HTTPException(status_code=400, detail="Plex not configured")
    client = PlexClient(settings.plex_url, settings.plex_token)
    return [
        {
            "key": s.key,
            "title": s.title,
            "type": normalize_plex_type(s.type),
        }
        for s in client.list_sections()
    ]


@app.get("/api/context/active")
def active_derived_context() -> Dict[str, Any]:
    row = _db().get_active_derived_context()
    return {
        "context_hash": str(row["context_hash"]),
        "inferred_label": str(row["inferred_label"] or "General Exploration"),
    }


@app.get("/api/jobs")
def list_jobs() -> List[Dict[str, Any]]:
    return [job.to_dict() for job in get_job_manager().list_jobs()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = get_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.post("/api/library/sync")
def start_library_sync() -> Dict[str, Any]:
    job = get_job_manager().start_sync(_settings())
    logger.info("Library sync queued job_id=%s", job.id)
    return job.to_dict()


@app.get("/api/library/stats")
def library_stats() -> Dict[str, Any]:
    db = _db()
    items = db.all_library_items()
    movies = sum(1 for i in items if i["media_type"] == "movie")
    shows = sum(1 for i in items if i["media_type"] == "show")
    return {
        "total": len(items),
        "movies": movies,
        "shows": shows,
        "last_sync": db.get_sync_state("last_sync"),
    }


@app.get("/api/library/health")
def library_health() -> Dict[str, Any]:
    return compute_library_health(_db())


@app.get("/api/library/purge-candidates")
def library_purge_candidates(limit: int = 12) -> Dict[str, Any]:
    cards = suggest_purge_candidates(_db(), _settings(), limit=min(max(1, limit), 25))
    return {
        "count": len(cards),
        "items": [card.model_dump() for card in cards],
    }


@app.get("/api/admin/export/training-corpus")
def export_training_corpus(user=Depends(require_role("owner"))) -> JSONResponse:
    del user
    payload = _db().export_training_corpus()
    filename = f"curatorx-training-corpus-{int(payload['exported_at'])}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/library/overview")
def library_overview_endpoint() -> Dict[str, Any]:
    return library_overview(_db())


@app.get("/api/library/query")
async def library_query_endpoint(
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    cast: Optional[str] = None,
    keywords: Optional[str] = None,
    countries: Optional[str] = None,
    content_ratings: Optional[str] = None,
    original_language: Optional[str] = None,
    query: Optional[str] = None,
    fts_query: Optional[str] = None,
    semantic_query: Optional[str] = None,
    unwatched_only: bool = False,
    min_view_count: Optional[int] = None,
    max_view_count: Optional[int] = None,
    stale_days: Optional[int] = None,
    recently_added_days: Optional[int] = None,
    added_from: Optional[str] = None,
    added_to: Optional[str] = None,
    last_viewed_from: Optional[str] = None,
    last_viewed_to: Optional[str] = None,
    runtime_min: Optional[int] = None,
    runtime_max: Optional[int] = None,
    vote_min: Optional[float] = None,
    vote_max: Optional[float] = None,
    file_size_min: Optional[int] = None,
    file_size_max: Optional[int] = None,
    in_radarr: Optional[bool] = None,
    in_sonarr: Optional[bool] = None,
    missing_tmdb_id: bool = False,
    in_progress_only: bool = False,
    sort: str = "title",
    offset: int = 0,
    limit: int = 25,
) -> Dict[str, Any]:
    filters = filters_from_mapping(
        {
            "media_type": media_type,
            "year_from": year_from,
            "year_to": year_to,
            "genres": genres,
            "directors": directors,
            "cast": cast,
            "keywords": keywords,
            "countries": countries,
            "content_ratings": content_ratings,
            "original_language": original_language,
            "query": query,
            "fts_query": fts_query,
            "semantic_query": semantic_query,
            "unwatched_only": unwatched_only,
            "min_view_count": min_view_count,
            "max_view_count": max_view_count,
            "stale_days": stale_days,
            "recently_added_days": recently_added_days,
            "added_from": added_from,
            "added_to": added_to,
            "last_viewed_from": last_viewed_from,
            "last_viewed_to": last_viewed_to,
            "runtime_min": runtime_min,
            "runtime_max": runtime_max,
            "vote_min": vote_min,
            "vote_max": vote_max,
            "file_size_min": file_size_min,
            "file_size_max": file_size_max,
            "in_radarr": in_radarr,
            "in_sonarr": in_sonarr,
            "missing_tmdb_id": missing_tmdb_id,
            "in_progress_only": in_progress_only,
            "sort": sort,
            "offset": offset,
            "limit": limit,
        }
    )
    if filters.semantic_query:
        return await query_library_async(_db(), filters, _settings())
    return query_library(_db(), filters)


@app.get("/api/library/aggregate")
def library_aggregate_endpoint(
    group_by: str,
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    keywords: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = group_by.strip().lower()
    allowed = {
        "decade",
        "year",
        "genre",
        "media_type",
        "director",
        "actor",
        "keyword",
        "country",
        "language",
        "content_rating",
        "runtime_bucket",
        "decade_genre",
    }
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="group_by must be decade, year, genre, media_type, director, actor, keyword, "
            "country, language, content_rating, runtime_bucket, or decade_genre",
        )
    filters = filters_from_mapping(
        {
            "media_type": media_type,
            "year_from": year_from,
            "year_to": year_to,
            "genres": genres,
            "directors": directors,
            "keywords": keywords,
        }
    )
    return aggregate_library(_db(), normalized, filters)  # type: ignore[arg-type]


@app.get("/api/library/facets")
def library_facets_endpoint(facet_type: str, limit: int = 50) -> Dict[str, Any]:
    try:
        return library_facet_catalog(_db(), facet_type, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/library/tv/episodes")
def library_tv_episodes_endpoint(
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    season: Optional[int] = None,
    unwatched_only: bool = False,
    offset: int = 0,
    limit: int = 25,
) -> Dict[str, Any]:
    return query_episodes(
        _db(),
        show=show,
        show_id=show_id,
        season=season,
        unwatched_only=unwatched_only,
        offset=offset,
        limit=limit,
    )


@app.get("/api/library/tv/progress")
def library_tv_progress_endpoint(
    group_by: str = "show",
    in_progress_only: bool = False,
    limit: int = 25,
) -> Dict[str, Any]:
    try:
        return summarize_tv_progress(
            _db(),
            group_by=group_by,
            in_progress_only=in_progress_only,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/lenses", response_model=List[Lens])
def list_lenses() -> List[Lens]:
    return [_row_to_lens(row) for row in _db().list_lenses()]


@app.get("/api/lenses/active", response_model=Lens)
def get_active_lens() -> Lens:
    lens_id = _db().get_active_lens_id()
    row = _db().get_lens(lens_id)
    if not row:
        raise HTTPException(status_code=404, detail="Active lens not found")
    return _row_to_lens(row)


@app.put("/api/lenses/active", response_model=Lens)
def set_active_lens(payload: ActiveLensPayload) -> Lens:
    try:
        _db().set_active_lens_id(payload.lens_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    row = _db().get_lens(payload.lens_id)
    assert row is not None
    return _row_to_lens(row)


@app.post("/api/lenses", response_model=Lens)
def create_lens(payload: LensCreate) -> Lens:
    lens_id = re.sub(r"[^a-z0-9_-]+", "-", payload.lens_id.strip().lower()).strip("-")
    if not lens_id:
        raise HTTPException(status_code=400, detail="Invalid lens_id")
    if _db().get_lens(lens_id):
        raise HTTPException(status_code=409, detail="Lens already exists")
    return _row_to_lens(_db().create_lens(lens_id, payload.lens_name.strip(), payload.description.strip()))


@app.put("/api/lenses/{lens_id}", response_model=Lens)
def update_lens(lens_id: str, payload: LensUpdate) -> Lens:
    if not _db().get_lens(lens_id):
        raise HTTPException(status_code=404, detail="Lens not found")
    try:
        row = _db().update_lens(
            lens_id,
            lens_name=payload.lens_name,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _row_to_lens(row)


@app.get("/api/persona/presets", response_model=List[PersonaPresetSummary])
def get_persona_presets() -> List[PersonaPresetSummary]:
    return [
        PersonaPresetSummary(
            id=preset.id,
            name=preset.name,
            description=preset.description,
            tagline=preset.tagline,
            val_bro_prof=preset.val_bro_prof,
            val_dipl_snark=preset.val_dipl_snark,
            val_pass_auto=preset.val_pass_auto,
            identity_blurb=preset.identity_blurb,
            behavioral_anchor=preset.behavioral_anchor,
            typing_phrases=list(preset.typing_phrases),
            composer_placeholders=list(preset.composer_placeholders),
            welcome_greeting=preset.welcome_greeting,
            welcome_starters=list(preset.welcome_starters),
            review_prompt_templates=dict(preset.review_prompt_templates),
            accent_hue=preset.accent_hue,
        )
        for preset in list_presets()
    ]


@app.get("/api/persona/preview", response_model=PersonaPreviewResponse)
def get_persona_preview(
    persona_identity: Optional[str] = None,
    val_bro_prof: Optional[float] = None,
    val_dipl_snark: Optional[float] = None,
    val_pass_auto: Optional[float] = None,
    persona_preset_id: Optional[str] = None,
    persona_prompt_override: Optional[str] = None,
    curator_name: Optional[str] = None,
) -> PersonaPreviewResponse:
    row = _db().get_persona()
    if not row:
        _db().ensure_seed_data()
        row = _db().get_persona()
    base = persona_row_to_dict(row)
    draft = {
        **base,
        "curator_name": curator_name if curator_name is not None else base.get("curator_name"),
        "persona_identity": persona_identity if persona_identity is not None else base.get("persona_identity"),
        "val_bro_prof": val_bro_prof if val_bro_prof is not None else base.get("val_bro_prof"),
        "val_dipl_snark": val_dipl_snark if val_dipl_snark is not None else base.get("val_dipl_snark"),
        "val_pass_auto": val_pass_auto if val_pass_auto is not None else base.get("val_pass_auto"),
        "persona_preset_id": persona_preset_id if persona_preset_id is not None else base.get("persona_preset_id"),
        "persona_prompt_override": (
            persona_prompt_override
            if persona_prompt_override is not None
            else base.get("persona_prompt_override")
        ),
    }
    mode = derive_persona_mode(draft)
    behavioral = build_rendered_behavioral_prompt(draft)
    assembled = build_assembled_persona_prompt(draft)
    return PersonaPreviewResponse(
        persona_mode=mode,
        behavioral_prompt=behavioral,
        assembled_prompt=assembled,
    )


@app.get("/api/persona", response_model=PersonaMetrics)
def get_persona() -> PersonaMetrics:
    row = _db().get_persona()
    if not row:
        _db().ensure_seed_data()
        row = _db().get_persona()
    if not row:
        raise HTTPException(status_code=500, detail="Persona seed failed")
    return _row_to_persona(row)


@app.put("/api/persona", response_model=PersonaMetrics)
def put_persona(payload: PersonaMetricsUpdate) -> PersonaMetrics:
    db = _db()
    provided = payload.model_fields_set
    clear_override = payload.clear_persona_override
    override = payload.persona_prompt_override

    if override is not None and not str(override).strip():
        clear_override = True
        override = None

    identity = payload.persona_identity if "persona_identity" in provided else None
    bro = payload.val_bro_prof if "val_bro_prof" in provided else None
    snark = payload.val_dipl_snark if "val_dipl_snark" in provided else None
    auto = payload.val_pass_auto if "val_pass_auto" in provided else None
    preset_id = payload.persona_preset_id if "persona_preset_id" in provided else None

    if payload.apply_preset:
        preset = get_preset(payload.apply_preset)
        if not preset:
            raise HTTPException(status_code=400, detail=f"Unknown persona preset: {payload.apply_preset}")
        preset_id = preset.id
        bro = preset.val_bro_prof
        snark = preset.val_dipl_snark
        auto = preset.val_pass_auto
        current = db.get_persona()
        if identity is None and current and not str(current["persona_identity"] or "").strip():
            identity = preset.identity_blurb
        clear_override = True

    slider_changed = any(value is not None for value in (bro, snark, auto))
    if slider_changed and not clear_override:
        current = db.get_persona()
        if current and str(current["persona_prompt_override"] or "").strip():
            raise HTTPException(
                status_code=409,
                detail="Custom behavioral prompt is active. Confirm slider change with clear_persona_override=true.",
            )

    upsert_kwargs: dict[str, Any] = {}
    if payload.curator_name is not None:
        upsert_kwargs["curator_name"] = payload.curator_name
    if identity is not None:
        upsert_kwargs["persona_identity"] = identity
    if bro is not None:
        upsert_kwargs["val_bro_prof"] = bro
    if snark is not None:
        upsert_kwargs["val_dipl_snark"] = snark
    if auto is not None:
        upsert_kwargs["val_pass_auto"] = auto
    if preset_id is not None or "persona_preset_id" in provided or payload.apply_preset:
        upsert_kwargs["persona_preset_id"] = preset_id
    if clear_override:
        upsert_kwargs["clear_persona_override"] = True
    elif "persona_prompt_override" in provided:
        upsert_kwargs["persona_prompt_override"] = override

    row = db.upsert_persona(**upsert_kwargs)
    return _row_to_persona(row)


@app.get("/api/system-config")
def get_system_config() -> Dict[str, str]:
    return _db().get_all_config()


@app.put("/api/system-config")
def put_system_config(payload: SystemConfigUpdate) -> Dict[str, str]:
    if not payload.values:
        raise HTTPException(status_code=400, detail="No config values provided")
    db = _db()
    for key, value in payload.values.items():
        key_clean = str(key).strip()
        if not key_clean:
            continue
        db.set_config(key_clean, str(value))
        if key_clean == "curator_name":
            db.upsert_persona(curator_name=str(value))
        if key_clean == "active_lens_id":
            try:
                db.set_active_lens_id(str(value))
            except ValueError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
    return db.get_all_config()


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> Dict[str, Any]:
    session_id = payload.session_id or uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    db = _db()
    db.ensure_chat_session(session_id, lens_id)
    settings = _settings()
    config_error = validate_llm_settings(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    try:
        return await CuratorAgent(db, settings, lens_id=lens_id).run(session_id, payload.message)
    except LLMProviderError as error:
        logger.warning("Chat LLM error for session %s: %s", session_id, error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        logger.exception("Chat request failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/chat/threads")
def list_chat_threads() -> List[Dict[str, Any]]:
    return _db().list_chat_threads()


@app.post("/api/chat/threads")
def create_chat_thread(payload: ThreadCreatePayload = ThreadCreatePayload()) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    context_hash = (payload.context_hash or "general").strip() or "general"
    thread = _db().create_chat_thread(
        session_id,
        lens_id=lens_id,
        context_hash=context_hash,
        thread_title=payload.thread_title,
    )
    return {"session_id": session_id, **thread}


@app.get("/api/chat/threads/{session_id}/messages")
def get_chat_thread_messages(session_id: str, limit: int = 100) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = db.chat_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages, "thread": thread}


@app.patch("/api/chat/threads/{session_id}")
def update_chat_thread(session_id: str, payload: ThreadUpdatePayload) -> Dict[str, Any]:
    try:
        return _db().update_thread_title(session_id, payload.thread_title)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.delete("/api/chat/threads/{session_id}")
def delete_chat_thread(session_id: str) -> Dict[str, bool]:
    if not _db().delete_chat_thread(session_id):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": True}


@app.post("/api/chat/messages/{message_id}/feedback")
def submit_message_feedback(
    message_id: str,
    payload: MessageFeedbackRequest,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(payload.session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    row = db.get_chat_message(message_id)
    if not row or str(row["session_id"]) != payload.session_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if str(row["role"]) != "assistant":
        raise HTTPException(status_code=400, detail="Feedback is only supported on assistant messages")

    if payload.feedback is None:
        deleted = db.delete_message_feedback(message_id, user_id=user.id)
        return {"saved": False, "deleted": deleted, "feedback": None}

    blocks = json.loads(str(row["blocks_json"]))
    excerpt = _message_text_excerpt(blocks)
    signal_type = "positive" if payload.feedback == "helpful" else "negative"
    remember_preference(
        db,
        PreferenceSignal(
            signal_type=signal_type,
            text=excerpt or f"Curator response marked {payload.feedback}",
            lens_id=str(row["lens_id"]) if row["lens_id"] is not None else None,
        ),
    )
    saved = db.upsert_message_feedback(
        feedback_id=uuid.uuid4().hex,
        message_id=message_id,
        session_id=payload.session_id,
        user_id=user.id,
        feedback_type=payload.feedback,
        excerpt=excerpt,
    )
    return {"saved": True, "deleted": False, "feedback": saved}


@app.delete("/api/chat/messages/{message_id}/feedback")
def delete_message_feedback(
    message_id: str,
    session_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    row = db.get_chat_message(message_id)
    if not row or str(row["session_id"]) != session_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if str(row["role"]) != "assistant":
        raise HTTPException(status_code=400, detail="Feedback is only supported on assistant messages")
    deleted = db.delete_message_feedback(message_id, user_id=user.id)
    return {"saved": False, "deleted": deleted, "feedback": None}


@app.get("/api/chat/threads/{session_id}/feedback")
def list_thread_feedback(
    session_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    items = db.list_message_feedback(session_id, user_id=user.id)
    return {"session_id": session_id, "items": items}


@app.get("/api/chat/stream")
async def chat_stream(
    message: str,
    session_id: Optional[str] = None,
    lens_id: Optional[str] = None,
) -> EventSourceResponse:
    sid = session_id or uuid.uuid4().hex
    resolved_lens = _resolve_lens_id(lens_id)

    async def event_generator():
        try:
            async for chunk in stream_agent(_db(), _settings(), sid, message, lens_id=resolved_lens):
                data = json.loads(chunk)
                yield {"event": data.get("type", "message"), "data": chunk.strip()}
        except Exception as error:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"error": str(error)})}

    return EventSourceResponse(event_generator())


@app.get("/api/title/{media_type}/{item_id}")
def title_detail(media_type: str, item_id: str, id_type: str = "tmdb") -> Dict[str, Any]:
    settings = _settings()
    db = _db()
    kwargs: Dict[str, Any] = {"media_type": media_type}
    if id_type == "rating_key":
        kwargs["rating_key"] = item_id
    elif media_type == "show" and id_type == "tvdb":
        kwargs["tvdb_id"] = int(item_id)
    else:
        kwargs["tmdb_id"] = int(item_id)
    detail = get_title_detail(db, settings, **kwargs)
    return detail.model_dump()


@app.post("/api/actions/propose")
def propose_action(payload: Dict[str, Any]) -> Dict[str, Any]:
    import uuid as uuid_mod

    action = payload.get("action")
    if action == "add_radarr":
        settings = _settings()
        config_error = radarr_add_configuration_error(settings)
        if config_error:
            raise HTTPException(status_code=400, detail=config_error)
        client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
        root_error = validate_arr_root_folder(
            "Radarr",
            resolve_radarr_root_folder(settings),
            client.root_folders(),
        )
        if root_error:
            raise HTTPException(status_code=400, detail=root_error)
        tmdb_id = int(payload["tmdb_id"])
        existing = check_radarr_already_exists(
            client,
            tmdb_id,
            title=str(payload.get("title") or ""),
        )
        if existing:
            mark_in_radarr(_db(), tmdb_id, title=str(payload.get("title") or ""))
            logger.info(
                "Skipped add_radarr tmdb_id=%s title=%r — already in Radarr",
                tmdb_id,
                payload.get("title", ""),
            )
            return existing
        token = uuid_mod.uuid4().hex
        _db().save_pending_action(
            token,
            "add_radarr",
            {"action": "add_radarr", "tmdb_id": tmdb_id, "title": payload.get("title", "")},
        )
        logger.info(
            "Proposed add_radarr tmdb_id=%s title=%r token=%s",
            payload["tmdb_id"],
            payload.get("title", ""),
            token[:8],
        )
        return {"confirmation_token": token}
    if action == "add_sonarr":
        settings = _settings()
        config_error = sonarr_add_configuration_error(settings)
        if config_error:
            raise HTTPException(status_code=400, detail=config_error)
        client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
        root_error = validate_arr_root_folder(
            "Sonarr",
            resolve_sonarr_root_folder(settings),
            client.root_folders(),
        )
        if root_error:
            raise HTTPException(status_code=400, detail=root_error)
        tvdb_id = int(payload["tvdb_id"])
        existing = check_sonarr_already_exists(
            client,
            tvdb_id,
            title=str(payload.get("title") or ""),
        )
        if existing:
            mark_in_sonarr(_db(), tvdb_id, title=str(payload.get("title") or ""))
            logger.info(
                "Skipped add_sonarr tvdb_id=%s title=%r — already in Sonarr",
                tvdb_id,
                payload.get("title", ""),
            )
            return existing
        token = uuid_mod.uuid4().hex
        _db().save_pending_action(
            token,
            "add_sonarr",
            {"action": "add_sonarr", "tvdb_id": tvdb_id, "title": payload.get("title", "")},
        )
        logger.info(
            "Proposed add_sonarr tvdb_id=%s title=%r token=%s",
            payload["tvdb_id"],
            payload.get("title", ""),
            token[:8],
        )
        return {"confirmation_token": token}
    if action == "request_seerr":
        settings = _settings()
        config_error = seerr_configuration_error(settings)
        if config_error:
            raise HTTPException(status_code=400, detail=config_error)
        media_type = str(payload.get("media_type") or "movie")
        tmdb_id = int(payload["tmdb_id"])
        token = uuid_mod.uuid4().hex
        pending = {
            "action": "request_seerr",
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": payload.get("title", ""),
        }
        if payload.get("tvdb_id") is not None:
            pending["tvdb_id"] = int(payload["tvdb_id"])
        _db().save_pending_action(token, "request_seerr", pending)
        logger.info(
            "Proposed request_seerr tmdb_id=%s media_type=%s title=%r token=%s",
            tmdb_id,
            media_type,
            payload.get("title", ""),
            token[:8],
        )
        return {"confirmation_token": token}
    raise HTTPException(status_code=400, detail="Unknown action")


@app.get("/api/requests")
def list_seerr_requests(
    take: int = 20,
    skip: int = 0,
    filter: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    settings = _settings()
    config_error = seerr_configuration_error(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    client = SeerrClient(settings.seerr.url, settings.seerr.api_key)
    requested_by = None
    if settings.features.multi_user_enabled and user.role != "owner":
        if user.seerr_user_id is None:
            raise HTTPException(status_code=403, detail="Seerr account not linked for this user")
        requested_by = user.seerr_user_id
    try:
        return client.list_requests(take=take, skip=skip, filter=filter, requested_by=requested_by)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/actions/confirm")
async def confirm_action(payload: ActionConfirmRequest) -> Dict[str, Any]:
    if not payload.confirmed:
        _db().pop_pending_action(payload.token)
        logger.info("Action cancelled token=%s", payload.token[:8])
        return {"cancelled": True}
    try:
        result = await execute_confirmed_action(_db(), _settings(), payload.token)
        logger.info("Action confirmed token=%s action=%s", payload.token[:8], result.get("action"))
        return {"ok": True, **result}
    except Exception as error:  # noqa: BLE001
        logger.exception("Action confirm failed token=%s", payload.token[:8])
        from curatorx.connectors.arr_errors import format_arr_http_error

        raise HTTPException(status_code=400, detail=format_arr_http_error(error)) from error


@app.get("/api/persona/typing-phrases")
def get_persona_typing_phrases() -> Dict[str, List[str]]:
    row = _db().get_persona()
    if not row:
        _db().ensure_seed_data()
        row = _db().get_persona()
    data = persona_row_to_dict(row)
    curator_name = str(data.get("curator_name") or "Curator")
    preset_id = str(data["persona_preset_id"]) if data.get("persona_preset_id") else None
    return {"phrases": typing_phrases_for(preset_id, curator_name)}


@app.get("/api/persona/ui-copy", response_model=PersonaUiCopy)
def get_persona_ui_copy() -> PersonaUiCopy:
    row = _db().get_persona()
    if not row:
        _db().ensure_seed_data()
        row = _db().get_persona()
    data = persona_row_to_dict(row)
    curator_name = str(data.get("curator_name") or "Curator")
    preset_id = str(data["persona_preset_id"]) if data.get("persona_preset_id") else None
    return PersonaUiCopy(**persona_ui_for(preset_id, curator_name))


@app.get("/api/engagement/streak", response_model=EngagementStreakResponse)
def get_engagement_streak() -> EngagementStreakResponse:
    count = _db().count_chat_sessions_last_days(30)
    return EngagementStreakResponse(session_count_30d=count, streak_visible=count >= 3)


@app.get("/api/watchlist", response_model=WatchlistListResponse)
def list_watchlist(user=Depends(get_current_user_dep)) -> WatchlistListResponse:
    user_id = user.id if _settings().features.multi_user_enabled else None
    items = _db().list_watchlist_pins(user_id=user_id)
    return WatchlistListResponse(
        items=[WatchlistPin(**item) for item in items],
        count=len(items),
    )


@app.post("/api/watchlist", response_model=WatchlistPin)
def add_watchlist_pin(
    payload: WatchlistCreate,
    user=Depends(get_current_user_dep),
) -> WatchlistPin:
    if not payload.tmdb_id and not payload.tvdb_id:
        raise HTTPException(status_code=400, detail="tmdb_id or tvdb_id is required")
    user_id = user.id if _settings().features.multi_user_enabled else None
    try:
        pin = _db().add_watchlist_pin(
            pin_id=str(uuid.uuid4()),
            user_id=user_id,
            tmdb_id=payload.tmdb_id,
            tvdb_id=payload.tvdb_id,
            media_type=payload.media_type,
            title=payload.title.strip(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return WatchlistPin(**pin)


@app.delete("/api/watchlist/{pin_id}")
def delete_watchlist_pin(
    pin_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    user_id = user.id if _settings().features.multi_user_enabled else None
    removed = _db().delete_watchlist_pin(pin_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist pin not found")
    return {"removed": True}


@app.post("/api/preferences")
def add_preference(payload: PreferenceSignal) -> Dict[str, bool]:
    remember_preference(_db(), payload)
    return {"saved": True}


@app.get("/api/reviews")
def list_reviews(
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
    title: Optional[str] = None,
    min_stars: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    items = get_reviews(
        _db(),
        rating_key=rating_key,
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=title,
        min_stars=min_stars,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@app.post("/api/reviews")
def create_review(
    payload: UserReviewCreate,
    user=Depends(get_current_user_dep),
):
    del user
    try:
        saved = save_review(
            _db(),
            stars=payload.stars,
            title=payload.title,
            media_type=payload.media_type,
            rating_key=payload.rating_key,
            tmdb_id=payload.tmdb_id,
            tvdb_id=payload.tvdb_id,
            review_text=payload.review_text,
            review_tags=payload.review_tags,
            prompted_by=payload.prompted_by,
            session_id=payload.session_id,
            lens_id=payload.lens_id,
            prompt_id=payload.prompt_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = _settings()
    saved = sync_review_rating_to_plex(
        _db(),
        settings,
        saved,
        replace_plex_rating=payload.replace_plex_rating,
    )
    if saved.get("reason") == "plex_rating_conflict":
        plex_stars = int(saved["plex_stars"])
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plex_rating_conflict",
                "plex_stars": plex_stars,
                "submitted_stars": int(saved["submitted_stars"]),
                "message": f"Plex has {plex_stars}★ — keep or replace?",
                "review": saved,
            },
        )
    return UserReview(**saved)


@app.get("/api/plex/collections")
def api_list_plex_collections(
    media_type: str = "movie",
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    settings = _settings()
    config_error = plex_collections_configuration_error(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    section_id = resolve_plex_section(settings, media_type)
    if not section_id:
        raise HTTPException(status_code=400, detail=f"Plex {media_type} library section is not configured")
    client = PlexClient(settings.plex_url, settings.plex_token)
    items = list_plex_collections(client, section_id)
    return {
        "items": [
            {
                "rating_key": item.rating_key,
                "title": item.title,
                "section_id": item.section_id,
                "media_type": item.media_type,
            }
            for item in items
        ],
        "count": len(items),
    }


@app.post("/api/plex/collections/propose")
def propose_plex_collection(
    payload: PlexCollectionProposePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    settings = _settings()
    config_error = plex_collections_configuration_error(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    media_type = payload.media_type.strip().lower()
    if media_type not in {"movie", "show"}:
        raise HTTPException(status_code=400, detail="media_type must be movie or show")
    section_id = resolve_plex_section(settings, media_type)
    if not section_id:
        raise HTTPException(status_code=400, detail=f"Plex {media_type} library section is not configured")
    token = uuid.uuid4().hex
    _db().save_pending_action(
        token,
        "create_plex_collection",
        {
            "action": "create_plex_collection",
            "title": payload.title,
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": list(payload.rating_keys),
        },
    )
    return {"confirmation_token": token}


@app.post("/api/plex/collections/{collection_key}/items/propose")
def propose_plex_collection_items(
    collection_key: str,
    payload: PlexCollectionItemsProposePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    settings = _settings()
    config_error = plex_collections_configuration_error(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    media_type = payload.media_type.strip().lower()
    if media_type not in {"movie", "show"}:
        raise HTTPException(status_code=400, detail="media_type must be movie or show")
    section_id = resolve_plex_section(settings, media_type)
    if not section_id:
        raise HTTPException(status_code=400, detail=f"Plex {media_type} library section is not configured")
    if not payload.collection_rating_key and not payload.collection_title:
        raise HTTPException(
            status_code=400,
            detail="collection_rating_key or collection_title is required",
        )
    token = uuid.uuid4().hex
    _db().save_pending_action(
        token,
        "add_to_plex_collection",
        {
            "action": "add_to_plex_collection",
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": list(payload.rating_keys),
            "collection_rating_key": str(payload.collection_rating_key or collection_key or "").strip(),
            "collection_title": str(payload.collection_title or "").strip(),
        },
    )
    return {"confirmation_token": token}


@app.get("/api/reviews/prompts")
def list_review_prompts(limit: int = 10) -> Dict[str, Any]:
    db = _db()
    items = list_pending_prompts(db, limit=limit)
    mark_prompts_surfaced(db, [str(item["id"]) for item in items])
    items = list_pending_prompts(db, limit=limit)
    return {
        "items": [RatingPrompt(**item) for item in items],
        "count": len(items),
    }


@app.get("/api/reviews/to-rate")
def list_titles_for_rating(limit: int = 10) -> Dict[str, Any]:
    """Last ~N viewed/near-complete titles without a personal review (batch rate UI)."""
    items = list_titles_to_rate(_db(), limit=limit)
    near_complete_ids = [
        str(item["id"])
        for item in items
        if item.get("reason") == "near_complete" and not str(item.get("id", "")).startswith("viewed-")
    ]
    if near_complete_ids:
        mark_prompts_surfaced(_db(), near_complete_ids)
    return {"items": items, "count": len(items)}


@app.post("/api/reviews/prompts/{prompt_id}/dismiss", response_model=RatingPrompt)
def dismiss_review_prompt(prompt_id: str) -> RatingPrompt:
    try:
        saved = dismiss_prompt(_db(), prompt_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return RatingPrompt(**saved)
