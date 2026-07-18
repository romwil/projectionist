"""FastAPI application for CuratorX."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import asyncio
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
from curatorx.connectors.plex import PlexClient, cached_machine_identifier, cached_plex_friendly_name
from curatorx.connectors.plex_collections import list_collections as list_plex_collections
from curatorx.connectors.radarr import RadarrClient
from curatorx.connectors.seerr import SeerrClient
from curatorx.connectors.sonarr import SonarrClient
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import DEFAULT_LENS_ID
from curatorx.library.health import compute_library_health
from curatorx.library.facets import ensure_library_facet_index
from curatorx.library.episodes import query_episodes, summarize_tv_progress
from curatorx.library.facets import library_facet_catalog
from curatorx.library.feeds import (
    feed_on_this_day,
    feed_recent_releases,
    feed_recently_added,
    neighbors_payload,
)
from curatorx.library.query import (
    aggregate_library,
    compute_knowledge_coverage,
    filters_from_mapping,
    library_overview,
    query_library,
    query_library_async,
)
from curatorx.library.search import row_to_title_card
from curatorx.library.titles import get_title_detail
from curatorx.library.watch_state import set_library_item_watched, sync_watched_to_plex
from curatorx.models.schemas import (
    ActionConfirmRequest,
    ActiveLensPayload,
    ChatRequest,
    CuratedList,
    CuratedListCollectionResponse,
    CuratedListCreate,
    CuratedListItem,
    CuratedListItemCreate,
    CuratedListUpdate,
    EngagementStreakResponse,
    Lens,
    LensCreate,
    LensUpdate,
    MessageFeedbackRequest,
    PersonaMetrics,
    PersonaMetricsUpdate,
    PersonaPresetSummary,
    PersonaPreviewResponse,
    PersonaTemplate,
    PersonaTemplateCreate,
    PersonaTemplateUpdate,
    PersonaUiCopy,
    PreferenceSignal,
    RatingPrompt,
    SystemConfigUpdate,
    UserReview,
    UserReviewCreate,
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistPin,
    WatchlistSyncRequest,
    WatchlistSyncSettingsUpdate,
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
from curatorx.preferences.store import remember_preference
from curatorx.scheduler.tasks.purge_candidates import (
    drop_cached_purge_keys,
    read_cached_purge_candidates,
    recompute_purge_candidates,
)
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
    authenticate_local_user,
    authenticate_plex_user,
    available_auth_methods,
    bootstrap_owner,
    clear_pin_nonce_cookie,
    clear_session_cookie,
    get_current_user_dep,
    handle_oidc_callback,
    multi_user_api_auth_middleware,
    poll_plex_pin_login,
    register_local_user,
    require_role,
    set_session_cookie,
    start_oidc_authorize,
    start_plex_pin_login,
    sync_user_seerr_from_token,
    try_get_current_user,
)
from curatorx.web.rate_limit import enforce_rate_limit
from curatorx.web.jobs import get_job_manager, get_sync_scheduler
from curatorx.scheduler import IdleScheduler
from curatorx.scheduler.tasks import register_all as register_scheduler_tasks
from curatorx.web.session_tokens import ensure_session_secret, has_usable_session_secret
from curatorx.web.library_privacy import sanitize_library_payload
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


def _safe_error_detail(error: Exception, context: str = "") -> str:
    """Return a sanitized, user-safe error message for HTTP responses.

    Security rationale: raw ``str(error)`` can leak internal file paths,
    stack traces, LLM provider API-key fragments, database connection
    strings, or other implementation details.  This helper logs the *full*
    error (with traceback) at ``logger.error`` level for server-side
    debugging, then returns a generic, context-specific message that never
    exposes internals to the client.
    """
    logger.error(
        "Request error (%s): %s",
        context or type(error).__name__,
        error,
        exc_info=True,
    )

    if isinstance(error, LLMProviderError):
        return "LLM provider error \u2014 check your API key and provider settings"

    if isinstance(error, (ConnectionError, OSError)):
        service = context or "the service"
        return f"Unable to reach {service} \u2014 check connection settings"

    if context:
        return context

    return "An error occurred while processing your request"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    build_info = "unknown"
    try:
        with open("/app/.build-info") as f:
            build_info = f.read().strip()
    except FileNotFoundError:
        pass
    logger.info("CuratorX startup (version %s, build %s, data_dir=%s)", __version__, build_info, DATA_DIR)

    logger.info("Startup: ensuring session secret…")
    try:
        ensure_session_secret(DATA_DIR)
        logger.info("Startup: session secret ready")
    except Exception:  # noqa: BLE001
        logger.exception("Startup: session secret bootstrap failed (continuing)")

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

    logger.info("Startup: initializing idle task scheduler…")
    idle_scheduler = IdleScheduler(manager.db, DATA_DIR)
    register_scheduler_tasks(idle_scheduler)
    idle_scheduler.start(asyncio.get_event_loop())
    app.state.idle_scheduler = idle_scheduler
    logger.info("Startup: idle task scheduler ready (%d tasks)", len(idle_scheduler._definitions))

    yield
    idle_scheduler.stop()
    get_sync_scheduler().stop()
    logger.info("CuratorX shutdown complete")


def _openapi_exposed() -> bool:
    """Expose Swagger/ReDoc only when explicitly enabled (pentest / dev)."""
    return os.environ.get("CURATORX_EXPOSE_OPENAPI", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


_openapi_url = "/openapi.json" if _openapi_exposed() else None
_docs_url = "/docs" if _openapi_exposed() else None
_redoc_url = "/redoc" if _openapi_exposed() else None

app = FastAPI(
    title="CuratorX",
    version=__version__,
    lifespan=lifespan,
    openapi_url=_openapi_url,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)
app.middleware("http")(multi_user_api_auth_middleware)


_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "0",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' https://image.tmdb.org https://artworks.thetvdb.com "
        "https://assets.fanart.tv data:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
        "frame-ancestors 'none'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Inject browser-security headers into every response.

    Security rationale:
      - X-Frame-Options: DENY blocks clickjacking via iframes.
      - X-Content-Type-Options: nosniff prevents MIME-sniffing attacks.
      - X-XSS-Protection: 0 disables the legacy XSS auditor (modern best
        practice — rely on CSP instead).
      - Content-Security-Policy restricts resource origins.
      - Referrer-Policy limits URL leakage in cross-origin navigations.
      - Permissions-Policy restricts sensitive browser APIs; microphone is
        allowed for voice-mode functionality.
    """
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


try:
    from curatorx.mcp.http import mount_mcp_http
    from curatorx.mcp.server import mcp as _mcp_server

    mount_mcp_http(app, _mcp_server)
except Exception:  # noqa: BLE001
    # Optional [mcp] extra may be absent in slim installs.
    pass


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
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_provider_name: str = "SSO"


class LocalRegisterPayload(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class LocalLoginPayload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class PlexLoginPayload(BaseModel):
    auth_token: str = Field(min_length=1)


class UserUpdatePayload(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(owner|member|guest)$")
    disabled: Optional[bool] = None


class AuthMeUpdatePayload(BaseModel):
    preferred_name: Optional[str] = Field(default=None, max_length=80)
    ui_font_size: Optional[str] = Field(default=None, pattern="^(small|medium|large)$")
    ui_theme: Optional[str] = Field(default=None, pattern="^(lights_up|lights_down|system)$")


class LibraryItemWatchedPayload(BaseModel):
    rating_key: str = Field(min_length=1, max_length=64)
    watched: bool = True


class RecommendPayload(BaseModel):
    to_user_ids: List[str] = Field(min_length=1)
    media_type: str = Field(pattern="^(movie|show)$")
    title: str = Field(min_length=1, max_length=300)
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    rating_key: Optional[str] = Field(default=None, max_length=64)
    year: Optional[int] = None
    poster_url: Optional[str] = Field(default=None, max_length=1000)
    message: Optional[str] = Field(default=None, max_length=280)


class RecommendationsSeenPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)
    all_unread: bool = False


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
    omdb_api_key: str = ""
    long_synopsis_source: str = ""
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
    mcp_api_key: str = ""
    mcp_full_api_key: str = ""
    mcp_tmdb_poster_size: str = "w500"
    mcp_tmdb_backdrop_size: str = "w1280"
    features: FeatureFlagsPayload = Field(default_factory=FeatureFlagsPayload)
    auth: AuthSettingsPayload = Field(default_factory=AuthSettingsPayload)
    seerr: SeerrSettingsPayload = Field(default_factory=SeerrSettingsPayload)


class McpKeyWhichPayload(BaseModel):
    which: Literal["privacy", "full"]


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
    persona_id: Optional[str] = None


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


def _resolve_test_payload(payload: TestPayload) -> Dict[str, Any]:
    try:
        return resolve_test_payload(payload.model_dump(), _settings())
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid test configuration"),
        ) from error


def _scoped_user_id(user) -> Optional[str]:
    """Return user.id when multi-user partitioning is active, else None."""
    if _settings().features.multi_user_enabled:
        return user.id
    return None


def _secret_hint(value: str) -> str:
    """Last-4 hint for owner UI; never a reversible echo of the secret."""
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "••••"
    return f"…{cleaned[-4:]}"


def _normalize_mcp_image_sizes(settings: Settings) -> Settings:
    from curatorx.privacy.schema import BACKDROP_SIZES, POSTER_SIZES

    poster = settings.mcp_tmdb_poster_size if settings.mcp_tmdb_poster_size in POSTER_SIZES else "w500"
    backdrop = (
        settings.mcp_tmdb_backdrop_size if settings.mcp_tmdb_backdrop_size in BACKDROP_SIZES else "w1280"
    )
    if poster == settings.mcp_tmdb_poster_size and backdrop == settings.mcp_tmdb_backdrop_size:
        return settings
    return Settings.from_mapping(
        {
            **asdict(settings),
            "mcp_tmdb_poster_size": poster,
            "mcp_tmdb_backdrop_size": backdrop,
        }
    )


def _validate_distinct_mcp_keys(settings: Settings) -> None:
    privacy = str(settings.mcp_api_key or "").strip()
    full = str(settings.mcp_full_api_key or "").strip()
    if privacy and full and privacy == full:
        raise HTTPException(
            status_code=400,
            detail=(
                "Privacy and full MCP keys must differ. "
                "Use separate secrets for CURATORX_MCP_API_KEY and CURATORX_MCP_FULL_API_KEY."
            ),
        )


def _mask_settings(settings: Settings) -> Dict[str, Any]:
    payload = asdict(settings)
    sources = secret_field_sources(DATA_DIR)
    for field in SECRET_FIELDS:
        raw = getattr(settings, field)
        payload[f"{field}_set"] = bool(raw)
        payload[f"{field}_source"] = sources.get(field, "")
        if field in {"mcp_api_key", "mcp_full_api_key"}:
            payload[f"{field}_hint"] = _secret_hint(str(raw or ""))
        payload[field] = ""
    seerr_payload = dict(payload.get("seerr") or {})
    seerr_payload["api_key_set"] = bool(settings.seerr.api_key)
    seerr_payload["api_key"] = ""
    payload["seerr"] = seerr_payload
    auth_payload = dict(payload.get("auth") or {})
    auth_payload["oidc_client_secret_set"] = bool(settings.auth.oidc_client_secret)
    auth_payload["oidc_client_secret"] = ""
    payload["auth"] = auth_payload
    return payload


def _db():
    return get_job_manager().db


def _telemetry():
    from curatorx.telemetry import TelemetryIngester

    return TelemetryIngester(_db())


def _idle_scheduler() -> Optional[IdleScheduler]:
    return getattr(app.state, "idle_scheduler", None)


def _sanitize_library_payload(payload: Any, user) -> Any:
    return sanitize_library_payload(payload, settings=_settings(), user=user)


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
            "oidc_provider_name": settings.auth.oidc_provider_name or "SSO",
        },
        "auth_methods": available_auth_methods(settings),
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
            "preferred_name": user.preferred_name,
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


@app.get("/explore", response_class=HTMLResponse)
@app.get("/explore/tags", response_class=HTMLResponse)
@app.get("/explore/plot-lab", response_class=HTMLResponse)
@app.get("/explore/section/{section_id}", response_class=HTMLResponse)
def explore_page(section_id: str = "") -> HTMLResponse:
    del section_id
    return _serve_index()


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_page() -> HTMLResponse:
    return _serve_index()


@app.get("/title/{media_type}/{item_id}", response_class=HTMLResponse)
def title_page(media_type: str, item_id: str) -> HTMLResponse:
    return _serve_index()


@app.get("/person/{tmdb_person_id}", response_class=HTMLResponse)
def person_page(tmdb_person_id: str) -> HTMLResponse:
    del tmdb_person_id
    return _serve_index()


@app.get("/tag/{tag_name}", response_class=HTMLResponse)
def tag_page(tag_name: str) -> HTMLResponse:
    del tag_name
    return _serve_index()


@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return _serve_index()


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> HTMLResponse:
    return _serve_index()


@app.get("/about", response_class=HTMLResponse)
def about_page() -> HTMLResponse:
    return _serve_index()


@app.get("/help", response_class=HTMLResponse)
def help_page() -> HTMLResponse:
    return _serve_index()


def _frontend_public_file(*parts: str) -> Path | None:
    """Resolve a Vite public asset from dist (prod) or public/ (local pre-build).

    When both exist (common after generate-release-notes without a rebuild),
    prefer the newer file so About stays current during local development.
    """
    candidates = [
        FRONTEND_DIST.joinpath(*parts),
        FRONTEND_DIST.parent.joinpath("public", *parts),
    ]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)


@app.get("/release-notes.json")
def release_notes_json() -> FileResponse:
    """Serve release notes copied into dist (Docker) or public/ (local generate)."""
    path = _frontend_public_file("release-notes.json")
    if path is None:
        raise HTTPException(status_code=404, detail="Release notes not found")
    return FileResponse(
        path,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=60"},
    )


@app.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    path = _frontend_public_file("favicon.svg")
    if path is None:
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/{section}", response_class=HTMLResponse)
def admin_page(section: str = "") -> HTMLResponse:
    del section
    return _serve_index()


@app.get("/settings", response_class=HTMLResponse)
@app.get("/settings/{section}", response_class=HTMLResponse)
def settings_page(section: str = "") -> HTMLResponse:
    del section
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


@app.get("/api/plex/machine-id")
def plex_machine_id(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    """Return the cached/fetched Plex machineIdentifier for Watch on Plex deep links."""
    settings = _settings()
    machine_id = cached_machine_identifier(settings.plex_url, settings.plex_token, timeout=5)
    return {"machine_id": machine_id}


@app.get("/api/auth/me")
def auth_me(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return {"user": user.to_dict(), "authenticated": True}


@app.patch("/api/auth/me")
def patch_auth_me(
    payload: AuthMeUpdatePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Self-service profile updates (preferred conversation name, UI prefs)."""
    from curatorx.web.avatars import resolve_avatar_url

    fields_set = getattr(payload, "model_fields_set", None) or getattr(payload, "__fields_set__", set())
    updates: Dict[str, Any] = {}
    if "preferred_name" in fields_set:
        updates["preferred_name"] = payload.preferred_name
    if "ui_font_size" in fields_set:
        updates["ui_font_size"] = payload.ui_font_size
    if "ui_theme" in fields_set:
        updates["ui_theme"] = payload.ui_theme
    if not updates:
        return {"user": user.to_dict(), "authenticated": True}
    try:
        updated = _db().update_user_profile(user.id, **updates)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "User not found"),
        ) from error
    # Prefer resolved local avatar path when a cached/uploaded file exists.
    updated["avatar_url"] = resolve_avatar_url(user.id, updated.get("avatar_url"))
    return {"user": updated, "authenticated": True}


@app.get("/api/auth/avatar/{user_id}")
def get_user_avatar(user_id: str, user=Depends(get_current_user_dep)) -> FileResponse:
    """Serve a locally stored avatar for an authenticated household user."""
    from curatorx.web.avatars import find_local_avatar_file, media_type_for_avatar, safe_user_id

    del user  # auth gate only
    try:
        safe_user_id(user_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    path = find_local_avatar_file(user_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(path, media_type=media_type_for_avatar(path))


@app.post("/api/auth/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Upload a profile picture; stored under DATA_DIR/avatars/{user_id}.*."""
    from curatorx.web.avatars import local_avatar_api_path, save_avatar_bytes

    raw = await file.read()
    try:
        api_path = save_avatar_bytes(user.id, raw, file.content_type or "")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    try:
        updated = _db().update_user_profile(user.id, avatar_url=api_path)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "User not found"),
        ) from error
    updated["avatar_url"] = local_avatar_api_path(user.id)
    return {"user": updated, "authenticated": True}


@app.post("/api/auth/plex/pin")
def auth_plex_pin_start(request: Request, response: Response) -> Dict[str, Any]:
    """Start Overseerr-style Plex PIN login; client opens auth_url and polls."""
    return start_plex_pin_login(request, response)


@app.get("/api/auth/plex/pin/{pin_id}")
def auth_plex_pin_poll(pin_id: int, request: Request, response: Response) -> Dict[str, Any]:
    """Poll Plex PIN. When authorized, upsert user and set session cookie."""
    user = poll_plex_pin_login(pin_id, request, _db())
    if user is None:
        return {"authenticated": False, "pending": True}
    clear_pin_nonce_cookie(response, request)
    set_session_cookie(response, user.id, request)
    return {"user": user.to_dict(), "authenticated": True, "pending": False}


@app.post("/api/auth/plex")
def auth_plex(payload: PlexLoginPayload, request: Request, response: Response) -> Dict[str, Any]:
    """Advanced fallback: sign in with a raw Plex auth token."""
    enforce_rate_limit(request, bucket="auth_plex_token", limit=10, window_seconds=60)
    user = authenticate_plex_user(payload.auth_token, _db())
    set_session_cookie(response, user.id, request)
    return {"user": user.to_dict(), "authenticated": True}


@app.post("/api/auth/local/register")
def auth_local_register(
    payload: LocalRegisterPayload,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Create a local-password account.  Owner-only unless bootstrapping."""
    enforce_rate_limit(request, bucket="auth_local_register", limit=5, window_seconds=60)
    db = _db()
    from curatorx.web.auth import _count_local_users

    requesting_user = None
    if _count_local_users(db) > 0:
        requesting_user = get_current_user_dep(request)

    user = register_local_user(
        username=payload.username,
        password=payload.password,
        db=db,
        requesting_user=requesting_user,
    )
    set_session_cookie(response, user.id, request)
    return {"user": user.to_dict(), "authenticated": True}


@app.post("/api/auth/local/login")
def auth_local_login(
    payload: LocalLoginPayload,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Authenticate with username/password and set session cookie."""
    user = authenticate_local_user(
        username=payload.username,
        password=payload.password,
        db=_db(),
        request=request,
    )
    set_session_cookie(response, user.id, request)
    return {"user": user.to_dict(), "authenticated": True}


@app.get("/api/auth/oidc/authorize")
def auth_oidc_authorize(request: Request) -> Dict[str, Any]:
    """Start OIDC login — returns the provider authorization URL."""
    return start_oidc_authorize(request)


@app.get("/api/auth/oidc/callback")
def auth_oidc_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Handle OIDC provider callback — exchange code, create/find user, set session."""
    user = handle_oidc_callback(code=code, state=state, db=_db(), request=request)
    set_session_cookie(response, user.id, request)
    return {"user": user.to_dict(), "authenticated": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> Dict[str, bool]:
    clear_session_cookie(response, request)
    return {"logged_out": True}


@app.get("/api/users")
def list_users(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    items = _db().list_users()
    return {"items": items, "count": len(items)}


@app.patch("/api/users/{user_id}")
def patch_user(
    user_id: str,
    payload: UserUpdatePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    if payload.role is None and payload.disabled is None:
        raise HTTPException(status_code=400, detail="Provide role and/or disabled")
    db = _db()
    target = db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    updated: Optional[Dict[str, Any]] = None
    if payload.role is not None:
        if user_id == user.id and payload.role != "owner":
            raise HTTPException(status_code=400, detail="Cannot demote your own owner account")
        if str(target["role"]) == "owner" and payload.role != "owner":
            if db.count_users_with_role("owner") <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last owner")
        try:
            updated = db.update_user_role(user_id, payload.role)
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=_safe_error_detail(error, "User not found"),
            ) from error
    if payload.disabled is not None:
        if user_id == user.id and payload.disabled:
            raise HTTPException(status_code=400, detail="Cannot disable your own account")
        if payload.disabled and str(target["role"]) == "owner":
            if db.count_users_with_role("owner") <= 1:
                raise HTTPException(status_code=400, detail="Cannot disable the last owner")
        try:
            updated = db.set_user_disabled(user_id, payload.disabled)
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail=_safe_error_detail(error, "User not found"),
            ) from error
    assert updated is not None
    return {"user": updated}


@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: str,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot remove your own account")
    db = _db()
    target = db.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target["role"]) == "owner" and db.count_users_with_role("owner") <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove the last owner")
    try:
        db.delete_user(user_id)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "User not found"),
        ) from error
    return {"deleted": True, "id": user_id}


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
def get_settings(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    return _mask_settings(_settings())


@app.put("/api/settings")
def put_settings(payload: SettingsPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    settings_path = DATA_DIR / "settings.json"
    before = Settings.load(settings_path)
    existing = _settings()
    merged = merge_secret_fields(payload.model_dump(), existing)
    settings = _normalize_mcp_image_sizes(
        normalize_path_settings(normalize_settings_llm(Settings.from_mapping(merged)))
    )
    _validate_distinct_mcp_keys(settings)
    if settings.features.multi_user_enabled and not has_usable_session_secret(DATA_DIR):
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot enable multi-user auth without a strong session secret. "
                "Set CURATORX_SESSION_SECRET to a long random value "
                "(not the development default), or remove that env var so CuratorX "
                "can generate one under DATA_DIR."
            ),
        )
    wizard_status = build_wizard_status(settings, _db())
    if not settings.onboarding_complete and wizard_status["onboarding_complete"]:
        settings = Settings.from_mapping({**asdict(settings), "onboarding_complete": True})
    invalidate_certifications_on_settings_change(_db(), before, settings, payload.model_dump())
    save_settings(DATA_DIR, settings)
    sync_settings_to_db(_db(), settings)
    return _mask_settings(settings)


def _mcp_key_field(which: str) -> str:
    return "mcp_api_key" if which == "privacy" else "mcp_full_api_key"


@app.post("/api/settings/mcp-keys/rotate")
def rotate_mcp_key(payload: McpKeyWhichPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Generate a new MCP key, persist to settings.json, return plaintext once."""
    del user
    field = _mcp_key_field(payload.which)
    settings_path = DATA_DIR / "settings.json"
    before = Settings.load(settings_path) if settings_path.exists() else Settings()
    existing = _settings()
    new_key = secrets.token_urlsafe(32)
    other_field = "mcp_full_api_key" if field == "mcp_api_key" else "mcp_api_key"
    other_value = str(getattr(existing, other_field) or "").strip()
    if other_value and new_key == other_value:
        raise HTTPException(status_code=500, detail="Generated MCP key collided; retry rotate.")
    updated = Settings.from_mapping({**asdict(existing), field: new_key})
    _validate_distinct_mcp_keys(updated)
    invalidate_certifications_on_settings_change(_db(), before, updated, {field: new_key})
    save_settings(DATA_DIR, updated)
    sync_settings_to_db(_db(), updated)
    return {
        "which": payload.which,
        "field": field,
        "key": new_key,
        "hint": _secret_hint(new_key),
        "settings": _mask_settings(updated),
    }


@app.post("/api/settings/mcp-keys/clear")
def clear_mcp_key(payload: McpKeyWhichPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Clear a file-persisted MCP key. Env/Unraid-sourced keys must be removed from the template."""
    del user
    field = _mcp_key_field(payload.which)
    sources = secret_field_sources(DATA_DIR)
    if sources.get(field) == "env":
        env_name = "CURATORX_MCP_API_KEY" if payload.which == "privacy" else "CURATORX_MCP_FULL_API_KEY"
        raise HTTPException(
            status_code=400,
            detail=(
                f"This key is set via {env_name} (container / Unraid). "
                "Remove that environment variable and restart, or rotate in Admin to "
                "persist a new key in settings.json (file overrides env)."
            ),
        )
    settings_path = DATA_DIR / "settings.json"
    before = Settings.load(settings_path) if settings_path.exists() else Settings()
    existing = _settings()
    updated = Settings.from_mapping({**asdict(existing), field: ""})
    invalidate_certifications_on_settings_change(_db(), before, updated, {field: ""})
    save_settings(DATA_DIR, updated)
    sync_settings_to_db(_db(), updated)
    return {"which": payload.which, "field": field, "settings": _mask_settings(updated)}


@app.post("/api/setup/test/plex")
def api_test_plex(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
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
def api_test_radarr(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    settings = _settings()
    resolved = _resolve_test_payload(payload)
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
def api_test_sonarr(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    settings = _settings()
    resolved = _resolve_test_payload(payload)
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
def api_test_tmdb(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
    result = test_tmdb(resolved["tmdb_api_key"])
    record_service_integration(
        _db(),
        "tmdb",
        api_token=resolved["tmdb_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/fanart")
def api_test_fanart(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
    result = test_fanart(resolved["fanart_api_key"])
    record_service_integration(
        _db(),
        "fanart",
        api_token=resolved["fanart_api_key"],
        ok=bool(result.get("ok")),
    )
    return result


@app.post("/api/setup/test/tautulli")
def api_test_tautulli(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
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
def api_test_seerr(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
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
def api_test_llm(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    resolved = _resolve_test_payload(payload)
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
def start_library_sync(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    job = get_job_manager().start_sync(_settings())
    logger.info("Library sync queued job_id=%s", job.id)
    return job.to_dict()


@app.get("/api/library/stats")
def library_stats(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    db = _db()
    items = db.all_library_items()
    movies = sum(1 for i in items if i["media_type"] == "movie")
    shows = sum(1 for i in items if i["media_type"] == "show")
    settings = _settings()
    plex_server_name = ""
    if settings.plex_url and settings.plex_token:
        plex_server_name = cached_plex_friendly_name(settings.plex_url, settings.plex_token, timeout=5)
    payload = {
        "total": len(items),
        "movies": movies,
        "shows": shows,
        "last_sync": db.get_sync_state("last_sync"),
        "plex_server_name": plex_server_name or None,
        # Phase A data surface for Admin/Explore knowledge-depth UI (Phase D).
        "knowledge_coverage": compute_knowledge_coverage(db),
    }
    return _sanitize_library_payload(payload, user)


@app.get("/api/library/knowledge-coverage")
def library_knowledge_coverage(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    """Dedicated coverage stats for Admin / Explore knowledge-depth panels."""
    return _sanitize_library_payload(compute_knowledge_coverage(_db()), user)


@app.get("/api/library/health")
def library_health(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return _sanitize_library_payload(compute_library_health(_db()), user)


@app.get("/api/library/purge-candidates")
def library_purge_candidates(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Return cached purge candidates for a fast dashboard load.

    When the cache is empty, returns an empty payload with ``stale=true``
    instead of recomputing synchronously (use POST .../refresh for that).
    """
    del limit  # limit applied at cache-build time; kept for API compatibility
    cached = read_cached_purge_candidates(_db())
    if cached is None:
        payload = {
            "count": 0,
            "items": [],
            "generated_at": None,
            "stale": True,
            "cached": False,
        }
    else:
        payload = cached
    return _sanitize_library_payload(payload, user)


@app.post("/api/library/purge-candidates/refresh")
def refresh_library_purge_candidates(
    limit: int = 25,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Force-recompute purge candidates and refresh the cache."""
    payload = recompute_purge_candidates(
        _db(),
        _settings(),
        limit=min(max(1, limit), 25),
    )
    return _sanitize_library_payload(payload, user)


def _normalize_rating_keys(payload: Dict[str, Any]) -> List[str]:
    rating_keys = payload.get("rating_keys", [])
    if not rating_keys or not isinstance(rating_keys, list):
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    keys = [str(key).strip() for key in rating_keys if str(key).strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    return keys


@app.post("/api/library/items/delete")
def delete_library_items(
    payload: Dict[str, Any],
    user=Depends(require_role("owner")),
):
    """Owner-only: remove CuratorX library index records by rating_key.

    Does not delete Plex media files. Titles still present in Plex may return
    on the next library sync.
    """
    keys = _normalize_rating_keys(payload)
    db = _db()
    deleted = db.delete_library_items_by_rating_keys(keys)
    drop_cached_purge_keys(db, keys)
    del user
    return {"deleted": deleted}


@app.post("/api/library/items/watched")
def set_library_item_watched_endpoint(
    payload: LibraryItemWatchedPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Mark an in-library title watched/unwatched locally and on Plex when configured.

    Guests are blocked when multi-user is enabled. Plex uses the caller's
    Sign-in-with-Plex token when present; otherwise the server ``plex_token``
    (admin/account watched state — household-wide).
    """
    settings = _settings()
    if settings.features.multi_user_enabled and user.role == "guest":
        raise HTTPException(status_code=403, detail="Guests cannot change watched state")

    db = _db()
    try:
        item = set_library_item_watched(
            db,
            payload.rating_key,
            watched=payload.watched,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404 if "not found" in str(error).lower() else 400,
            detail=_safe_error_detail(error, "Could not update watched state"),
        ) from error

    plex = sync_watched_to_plex(
        db,
        settings,
        payload.rating_key,
        watched=payload.watched,
        user_id=_scoped_user_id(user) or user.id,
    )
    return {**item, **plex}


@app.post("/api/library/purge-candidates/delete")
def delete_purge_candidates(
    payload: Dict[str, Any],
    user=Depends(require_role("owner")),
):
    keys = _normalize_rating_keys(payload)
    db = _db()
    deleted = db.delete_library_items_by_rating_keys(keys)
    drop_cached_purge_keys(db, keys)
    del user
    return {"deleted": deleted}


@app.post("/api/library/purge-candidates/dismiss")
def dismiss_purge_candidates_endpoint(
    payload: Dict[str, Any],
    user=Depends(require_role("owner")),
):
    rating_keys = payload.get("rating_keys", [])
    if not rating_keys or not isinstance(rating_keys, list):
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    db = _db()
    dismissed = db.dismiss_purge_candidates(rating_keys)
    drop_cached_purge_keys(db, [str(key) for key in rating_keys])
    del user
    return {"dismissed": dismissed}


@app.get("/api/admin/export/training-corpus")
def export_training_corpus(user=Depends(require_role("owner"))) -> JSONResponse:
    del user
    payload = _db().export_training_corpus()
    filename = f"curatorx-training-corpus-{int(payload['exported_at'])}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ScheduledTaskUpdatePayload(BaseModel):
    enabled: Optional[bool] = None
    run_interval_seconds: Optional[int] = Field(default=None, ge=60, le=2_592_000)
    items_per_cycle: Optional[int] = Field(default=None, ge=1, le=500)


@app.get("/api/admin/scheduled-tasks")
def list_scheduled_tasks(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        return {"items": [], "idle": False, "running": None}
    return {
        "items": scheduler.get_task_states(),
        "idle": scheduler.is_idle(),
        "running": scheduler._busy_task_name(),
    }


@app.put("/api/admin/scheduled-tasks/{name}")
def update_scheduled_task(
    name: str,
    payload: ScheduledTaskUpdatePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    updated = scheduler.update_task(
        name,
        enabled=payload.enabled,
        run_interval_seconds=payload.run_interval_seconds,
        items_per_cycle=payload.items_per_cycle,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
    return updated


@app.post("/api/admin/scheduled-tasks/{name}/run")
async def trigger_scheduled_task(
    name: str,
    wait: bool = False,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Trigger a scheduled task. Default is fire-and-forget for live monitoring.

    Pass ``wait=true`` to await completion and return the full task result.
    """
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    if wait:
        result = await scheduler.trigger_task(name)
    else:
        result = scheduler.trigger_task_background(name)
    if result.get("status") == "busy":
        raise HTTPException(status_code=409, detail=result.get("error") or "Task already running")
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/admin/scheduled-tasks/{name}/log")
def get_scheduled_task_log(
    name: str,
    after_seq: int = 0,
    limit: int = 200,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Poll buffered run events / progress lines for a scheduled task."""
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    payload = scheduler.get_task_run_log(name, after_seq=after_seq, limit=limit)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=payload["error"])
    return payload


@app.get("/api/admin/scheduled-tasks/{name}/history")
def get_scheduled_task_history(
    name: str,
    limit: int = 50,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Return durable run history for a task (survives restarts)."""
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    payload = scheduler.get_task_history(name, limit=limit)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=payload["error"])
    return payload


@app.get("/api/admin/scheduled-tasks/{name}/rate")
def get_scheduled_task_rate(
    name: str,
    lookback_hours: int = 72,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Return measured items/hour and duration percentiles from run history."""
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    payload = scheduler.get_task_rate(name, lookback_hours=lookback_hours)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=payload["error"])
    return payload


@app.get("/api/admin/scheduled-tasks-log")
def get_all_scheduled_task_logs(
    after_seq: int = 0,
    limit: int = 200,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Poll buffered run events across all scheduled tasks."""
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    return scheduler.get_task_run_log(None, after_seq=after_seq, limit=limit)


@app.post("/api/admin/scheduled-tasks/{name}/reset")
def reset_scheduled_task_quarantine(
    name: str,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Clear quarantine state for a task, allowing it to run again."""
    del user
    scheduler = _idle_scheduler()
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    result = scheduler.reset_quarantine(name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
    return result


@app.get("/api/admin/telemetry/summary")
def telemetry_summary(
    hours: int = 24,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner-only: event counts by type for the given window."""
    del user
    windows = {}
    for window in (24, 168, 720):
        windows[f"{window}h"] = _db().telemetry_summary(hours=window)
    return {"windows": windows, "requested_hours": hours, "detail": _db().telemetry_summary(hours=hours)}


@app.get("/api/admin/telemetry/events")
def telemetry_events(
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner-only: recent telemetry events with pagination."""
    del user
    events = _db().telemetry_events(event_class=type, limit=min(limit, 200), offset=offset)
    return {"items": events, "count": len(events)}


@app.get("/api/library/overview")
def library_overview_endpoint(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return _sanitize_library_payload(library_overview(_db()), user)


@app.get("/api/library/anniversaries")
def library_anniversaries_endpoint(
    limit: int = 5,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Return library titles with milestone release anniversaries (5, 10, 15, 20, 25+ years)."""
    import time as _time
    from datetime import date

    del user
    db = _db()
    today = date.today()
    current_year = today.year

    milestone_years = [current_year - n for n in (5, 10, 15, 20, 25, 30, 40, 50, 75)]
    placeholders = ",".join("?" * len(milestone_years))

    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, genres, poster_url,
                   backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                   runtime_minutes, summary
            FROM library_items
            WHERE year IN ({placeholders})
            ORDER BY year ASC
            LIMIT ?
            """,
            (*milestone_years, limit),
        ).fetchall()

    items = []
    for row in rows:
        years_ago = current_year - (row["year"] or current_year)
        context = f"Released {years_ago} year{'s' if years_ago != 1 else ''} ago"
        last_viewed = row["last_viewed_at"]
        if last_viewed:
            months_ago = max(1, int((_time.time() - last_viewed) / (30 * 86400)))
            context += f" \u00b7 Last watched {months_ago} month{'s' if months_ago != 1 else ''} ago"
        item_data = dict(row)
        item_data["anniversary_context"] = context
        items.append(item_data)

    return {"items": items, "count": len(items)}


@app.get("/api/library/feeds/recently-added")
def library_feed_recently_added(
    limit: int = 12,
    days: int = 30,
    offset: int = 0,
    media_type: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: titles added to the library within ``days``."""
    return _sanitize_library_payload(
        feed_recently_added(
            _db(),
            limit=limit,
            days=days,
            offset=offset,
            media_type=media_type,
        ),
        user,
    )


@app.get("/api/library/feeds/recent-releases")
def library_feed_recent_releases(
    limit: int = 12,
    days: int = 90,
    offset: int = 0,
    media_type: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: titles with release/first_air within ``days`` (honest empty)."""
    return _sanitize_library_payload(
        feed_recent_releases(
            _db(),
            limit=limit,
            days=days,
            offset=offset,
            media_type=media_type,
        ),
        user,
    )


@app.get("/api/library/feeds/on-this-day")
def library_feed_on_this_day(
    limit: int = 12,
    month: Optional[int] = None,
    day: Optional[int] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore On This Day — calendar dates when available, else milestone years."""
    return _sanitize_library_payload(
        feed_on_this_day(_db(), limit=limit, month=month, day=day),
        user,
    )


@app.get("/api/library/neighbors/{item_id}")
def library_neighbors_endpoint(
    item_id: int,
    mode: str = "similar",
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Cached plot neighbors by library item id (similar | surprising)."""
    return _sanitize_library_payload(
        neighbors_payload(_db(), item_id, mode=mode, limit=limit),
        user,
    )


@app.get("/api/library/motifs")
def library_motifs_endpoint(
    limit: int = 50,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Motif facet catalog for Plot Lab chips."""
    return _sanitize_library_payload(
        library_facet_catalog(_db(), "motif", limit=limit),
        user,
    )


@app.get("/api/library/quick-pick")
def library_quick_pick_endpoint(
    max_runtime: Optional[int] = None,
    genre: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Pick ONE random unwatched title, optionally constrained by runtime/genre."""
    del user
    db = _db()

    # Treat NULL view_count as unwatched (matches episode/query helpers).
    where_clauses = ["COALESCE(view_count, 0) = 0"]
    params: list = []
    if max_runtime is not None:
        where_clauses.append("runtime_minutes IS NOT NULL AND runtime_minutes <= ?")
        params.append(max_runtime)
    if genre:
        genre_parts = [g.strip() for g in genre.split(",") if g.strip()]
        if genre_parts:
            genre_or = " OR ".join("LOWER(genres) LIKE ?" for _ in genre_parts)
            where_clauses.append(f"({genre_or})")
            params.extend(f"%{g.lower()}%" for g in genre_parts)

    where_sql = " AND ".join(where_clauses)
    with db.connect() as conn:
        row = conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, genres, poster_url,
                   backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                   runtime_minutes, summary
            FROM library_items
            WHERE {where_sql}
            ORDER BY RANDOM()
            LIMIT 1
            """,
            params,
        ).fetchone()

    if not row:
        return {"item": None, "why": "No unwatched titles match the criteria."}

    genres_raw = row["genres"]
    genres_list: list = []
    if isinstance(genres_raw, list):
        genres_list = genres_raw
    elif isinstance(genres_raw, str) and genres_raw.strip():
        try:
            parsed = json.loads(genres_raw)
            genres_list = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            genres_list = []

    runtime = row["runtime_minutes"]
    reason_parts = []
    if genres_list:
        reason_parts.append(f"Matches your {str(genres_list[0]).lower()} taste")
    if runtime:
        reason_parts.append(f"{runtime} min")
    reason = " \u00b7 ".join(reason_parts) if reason_parts else "Unwatched pick for you"

    item = {key: row[key] for key in row.keys()}
    item["genres"] = genres_list
    item["view_count"] = int(item.get("view_count") or 0)
    # TitleCard expects overview + in_library (DB column is summary).
    item["overview"] = str(item.get("summary") or "")
    item["in_library"] = True

    return {"item": item, "why": reason}


@app.get("/api/library/query")
async def library_query_endpoint(
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    cast: Optional[str] = None,
    keywords: Optional[str] = None,
    motifs: Optional[str] = None,
    themes: Optional[str] = None,
    countries: Optional[str] = None,
    content_ratings: Optional[str] = None,
    collection_name: Optional[str] = None,
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
    user=Depends(get_current_user_dep),
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
            "motifs": motifs,
            "themes": themes,
            "countries": countries,
            "content_ratings": content_ratings,
            "collection_name": collection_name,
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
        result = await query_library_async(_db(), filters, _settings())
    else:
        result = query_library(_db(), filters)
    return _sanitize_library_payload(result, user)


@app.get("/api/library/aggregate")
def library_aggregate_endpoint(
    group_by: str,
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    keywords: Optional[str] = None,
    user=Depends(get_current_user_dep),
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
    return _sanitize_library_payload(
        aggregate_library(_db(), normalized, filters),  # type: ignore[arg-type]
        user,
    )


@app.get("/api/library/facets")
def library_facets_endpoint(
    facet_type: str,
    limit: int = 50,
    q: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    try:
        return _sanitize_library_payload(
            library_facet_catalog(_db(), facet_type, limit=limit, q=q),
            user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(exc, "Invalid facet query"),
        ) from exc


@app.get("/api/library/tv/episodes")
def library_tv_episodes_endpoint(
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    season: Optional[int] = None,
    unwatched_only: bool = False,
    offset: int = 0,
    limit: int = 25,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    return _sanitize_library_payload(
        query_episodes(
            _db(),
            show=show,
            show_id=show_id,
            season=season,
            unwatched_only=unwatched_only,
            offset=offset,
            limit=limit,
        ),
        user,
    )


@app.get("/api/library/tv/progress")
def library_tv_progress_endpoint(
    group_by: str = "show",
    in_progress_only: bool = False,
    limit: int = 25,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    try:
        return _sanitize_library_payload(
            summarize_tv_progress(
                _db(),
                group_by=group_by,
                in_progress_only=in_progress_only,
                limit=limit,
            ),
            user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(exc, "Invalid TV progress query"),
        ) from exc


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
def set_active_lens(payload: ActiveLensPayload, user=Depends(require_role("owner"))) -> Lens:
    del user
    try:
        _db().set_active_lens_id(payload.lens_id)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Lens not found"),
        ) from error
    row = _db().get_lens(payload.lens_id)
    assert row is not None
    return _row_to_lens(row)


@app.post("/api/lenses", response_model=Lens)
def create_lens(payload: LensCreate, user=Depends(require_role("owner"))) -> Lens:
    del user
    lens_id = re.sub(r"[^a-z0-9_-]+", "-", payload.lens_id.strip().lower()).strip("-")
    if not lens_id:
        raise HTTPException(status_code=400, detail="Invalid lens_id")
    if _db().get_lens(lens_id):
        raise HTTPException(status_code=409, detail="Lens already exists")
    return _row_to_lens(_db().create_lens(lens_id, payload.lens_name.strip(), payload.description.strip()))


@app.put("/api/lenses/{lens_id}", response_model=Lens)
def update_lens(lens_id: str, payload: LensUpdate, user=Depends(require_role("owner"))) -> Lens:
    del user
    if not _db().get_lens(lens_id):
        raise HTTPException(status_code=404, detail="Lens not found")
    try:
        row = _db().update_lens(
            lens_id,
            lens_name=payload.lens_name,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Lens not found"),
        ) from error
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
def put_persona(payload: PersonaMetricsUpdate, user=Depends(require_role("owner"))) -> PersonaMetrics:
    del user
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


# --- Persona Templates (per-conversation persona selection) ---


@app.get("/api/personas", response_model=List[PersonaTemplate])
def list_personas(user=Depends(get_current_user_dep)) -> List[PersonaTemplate]:
    """List persona templates visible to the current user.

    Returns all builtin presets, all shared templates, and the user's own
    private templates.  The persona_id on each conversation thread references
    one of these templates.
    """
    templates = _db().list_persona_templates(user_id=user.id)
    user_default = _db().get_user_default_persona_id(user.id)
    return [
        PersonaTemplate(**{**t, "is_default": t["id"] == user_default})
        for t in templates
    ]


@app.post("/api/personas", response_model=PersonaTemplate)
def create_persona(
    payload: PersonaTemplateCreate,
    user=Depends(get_current_user_dep),
) -> PersonaTemplate:
    """Create a custom persona template.

    Owner-created templates are ``shared`` (visible to everyone);
    member-created templates are ``private`` (visible only to the creator).
    """
    visibility = "shared" if user.role == "owner" else "private"
    template = _db().create_persona_template(
        template_id=uuid.uuid4().hex,
        name=payload.name.strip(),
        visibility=visibility,
        owner_user_id=user.id,
        val_bro_prof=payload.val_bro_prof,
        val_dipl_snark=payload.val_dipl_snark,
        val_pass_auto=payload.val_pass_auto,
        val_depth=payload.val_depth,
        val_obscurity=payload.val_obscurity,
        val_verbosity=payload.val_verbosity,
        val_formality=payload.val_formality,
        system_prompt_override=payload.system_prompt_override,
        accent_color=payload.accent_color,
    )
    return PersonaTemplate(**template)


@app.put("/api/personas/{persona_id}", response_model=PersonaTemplate)
def update_persona_template(
    persona_id: str,
    payload: PersonaTemplateUpdate,
    user=Depends(get_current_user_dep),
) -> PersonaTemplate:
    """Update a custom persona template (owner of that persona only; builtins immutable)."""
    db = _db()
    existing = db.get_persona_template(persona_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    if existing["visibility"] == "builtin":
        raise HTTPException(status_code=403, detail="Built-in personas are immutable")
    if existing["owner_user_id"] != user.id and user.role != "owner":
        raise HTTPException(status_code=403, detail="Only the persona owner can edit this persona")
    try:
        updated = db.update_persona_template(
            persona_id,
            name=payload.name,
            val_bro_prof=payload.val_bro_prof,
            val_dipl_snark=payload.val_dipl_snark,
            val_pass_auto=payload.val_pass_auto,
            val_depth=payload.val_depth,
            val_obscurity=payload.val_obscurity,
            val_verbosity=payload.val_verbosity,
            val_formality=payload.val_formality,
            system_prompt_override=payload.system_prompt_override,
            accent_color=payload.accent_color,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=_safe_error_detail(error, "Persona update failed")) from error
    return PersonaTemplate(**updated)


@app.delete("/api/personas/{persona_id}")
def delete_persona(
    persona_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    """Delete a custom persona template (owner only; builtins cannot be deleted)."""
    db = _db()
    existing = db.get_persona_template(persona_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    if existing["visibility"] == "builtin":
        raise HTTPException(status_code=403, detail="Built-in personas cannot be deleted")
    if existing["owner_user_id"] != user.id and user.role != "owner":
        raise HTTPException(status_code=403, detail="Only the persona owner can delete this persona")
    try:
        db.delete_persona_template(persona_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=_safe_error_detail(error, "Persona deletion failed")) from error
    return {"deleted": True}


@app.put("/api/personas/{persona_id}/default")
def set_default_persona(
    persona_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Set a persona template as the user's default for new conversations."""
    db = _db()
    template = db.get_persona_template(persona_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    db.set_user_default_persona(user.id, persona_id)
    return {"default_persona_id": persona_id, "persona": PersonaTemplate(**{**template, "is_default": True})}


@app.get("/api/system-config")
def get_system_config(user=Depends(require_role("owner"))) -> Dict[str, str]:
    del user
    return _db().get_all_config()


@app.put("/api/system-config")
def put_system_config(
    payload: SystemConfigUpdate,
    user=Depends(require_role("owner")),
) -> Dict[str, str]:
    del user
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
                raise HTTPException(
                    status_code=404,
                    detail=_safe_error_detail(error, "Lens not found"),
                ) from error
    return db.get_all_config()


@app.post("/api/chat")
async def chat(request: Request, payload: ChatRequest, user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    enforce_rate_limit(request, bucket="chat", limit=30, window_seconds=60)
    scheduler = _idle_scheduler()
    if scheduler is not None:
        scheduler.record_activity()
    session_id = payload.session_id or uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    db = _db()
    scoped = _scoped_user_id(user)
    if scoped and payload.session_id:
        existing = db.get_chat_thread(session_id, user_id=scoped)
        if existing is None and db.get_chat_thread(session_id) is not None:
            raise HTTPException(status_code=404, detail="Thread not found")
    persona_id = payload.persona_id
    db.ensure_chat_session(session_id, lens_id, user_id=scoped, persona_id=persona_id)
    if persona_id:
        db.set_thread_persona(session_id, persona_id)
    settings = _settings()
    config_error = validate_llm_settings(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)

    _telemetry().record_chat_message(
        session_id=session_id,
        lens_id=lens_id,
        message_length=len(payload.message),
        persona_id=persona_id,
        user_id=scoped,
    )

    try:
        return await CuratorAgent(
            db,
            settings,
            lens_id=lens_id,
            user_id=scoped,
            seerr_user_id=user.seerr_user_id,
            user_role=user.role,
        ).run(session_id, payload.message)
    except LLMProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Chat request failed"),
        ) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=_safe_error_detail(error, "Chat request failed"),
        ) from error


@app.get("/api/chat/threads")
def list_chat_threads(user=Depends(get_current_user_dep)) -> List[Dict[str, Any]]:
    return _db().list_chat_threads(user_id=_scoped_user_id(user))


@app.post("/api/chat/threads")
def create_chat_thread(
    payload: ThreadCreatePayload = ThreadCreatePayload(),
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    context_hash = (payload.context_hash or "general").strip() or "general"
    thread = _db().create_chat_thread(
        session_id,
        lens_id=lens_id,
        context_hash=context_hash,
        thread_title=payload.thread_title,
        user_id=_scoped_user_id(user),
        persona_id=payload.persona_id,
    )
    return {"session_id": session_id, **thread}


@app.get("/api/chat/threads/{session_id}/messages")
def get_chat_thread_messages(
    session_id: str,
    limit: int = 100,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(session_id, user_id=_scoped_user_id(user))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = db.chat_history(session_id, limit=limit)
    return {"session_id": session_id, "messages": messages, "thread": thread}


@app.patch("/api/chat/threads/{session_id}")
def update_chat_thread(
    session_id: str,
    payload: ThreadUpdatePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if _db().get_chat_thread(session_id, user_id=_scoped_user_id(user)) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    try:
        return _db().update_thread_title(session_id, payload.thread_title)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Thread not found"),
        ) from error


@app.delete("/api/chat/threads/{session_id}")
def delete_chat_thread(session_id: str, user=Depends(get_current_user_dep)) -> Dict[str, bool]:
    if not _db().delete_chat_thread(session_id, user_id=_scoped_user_id(user)):
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

    _telemetry().record_chat_feedback(
        message_id=message_id,
        feedback_type=payload.feedback,
        session_id=payload.session_id,
        user_id=user.id,
    )

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
    request: Request,
    message: str,
    session_id: Optional[str] = None,
    lens_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> EventSourceResponse:
    """SSE endpoint for token-by-token chat streaming.

    Events emitted:

    - ``event: token``       — ``{"content": "word"}``
    - ``event: tool_call``   — ``{"name": "search_library", "status": "start|complete", "args"?, "summary"?}``
    - ``event: done``        — final message payload (same shape as POST /api/chat)
    - ``event: error``       — ``{"error": "description"}``
    """
    enforce_rate_limit(request, bucket="chat", limit=30, window_seconds=60)
    scheduler = _idle_scheduler()
    if scheduler is not None:
        scheduler.record_activity()
    sid = session_id or uuid.uuid4().hex
    resolved_lens = _resolve_lens_id(lens_id)
    scoped = _scoped_user_id(user)

    async def event_generator():
        try:
            async for chunk in stream_agent(
                _db(),
                _settings(),
                sid,
                message,
                lens_id=resolved_lens,
                user_id=scoped,
                seerr_user_id=user.seerr_user_id,
                user_role=user.role,
                persona_id=persona_id,
            ):
                data = json.loads(chunk)
                event_type = data.get("type", "message")

                if event_type in ("tool_start", "tool_result"):
                    status = "start" if event_type == "tool_start" else "complete"
                    payload = {"name": data.get("name"), "status": status}
                    if event_type == "tool_start" and data.get("args") is not None:
                        payload["args"] = data.get("args")
                    if event_type == "tool_result" and data.get("summary") is not None:
                        payload["summary"] = data.get("summary")
                    yield {
                        "event": "tool_call",
                        "data": json.dumps(payload),
                    }
                else:
                    yield {"event": event_type, "data": chunk.strip()}
        except Exception as error:  # noqa: BLE001
            safe_msg = _safe_error_detail(error, "Chat stream failed")
            yield {"event": "error", "data": json.dumps({"error": safe_msg})}

    return EventSourceResponse(event_generator())


@app.get("/api/title/{media_type}/{item_id}")
def title_detail(
    media_type: str,
    item_id: str,
    id_type: str = "tmdb",
    enrich: bool = True,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    settings = _settings()
    db = _db()
    kwargs: Dict[str, Any] = {"media_type": media_type, "enrich": enrich}
    if id_type == "rating_key":
        kwargs["rating_key"] = item_id
    elif media_type == "show" and id_type == "tvdb":
        kwargs["tvdb_id"] = int(item_id)
    else:
        kwargs["tmdb_id"] = int(item_id)
    detail = get_title_detail(db, settings, **kwargs)
    return _sanitize_library_payload(detail.model_dump(), user)


def _library_titles_for_person_payload(
    db,
    *,
    person_id: Optional[int] = None,
    tmdb_person_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    rows = db.list_library_titles_for_person(
        person_id=person_id,
        tmdb_person_id=tmdb_person_id,
    )
    items: List[Dict[str, Any]] = []
    for row in rows:
        card = row_to_title_card(row)
        payload = card.model_dump()
        payload["id"] = int(row["id"]) if row["id"] is not None else None
        payload["department"] = str(row["department"] or "") if "department" in row.keys() else ""
        payload["job"] = str(row["job"] or "") if "job" in row.keys() else ""
        payload["character"] = str(row["character"] or "") if "character" in row.keys() else ""
        items.append(payload)
    return items


def _find_person_by_name(db, name: str):
    pattern = f"%{name.lower()}%"
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT id, tmdb_person_id, name, profile_url FROM people
            WHERE lower(name) LIKE ?
            ORDER BY CASE WHEN lower(name) = ? THEN 0 ELSE 1 END, name
            LIMIT 1
            """,
            (pattern, name.lower()),
        ).fetchone()


@app.get("/api/person/resolve")
def person_resolve(
    name: str = "",
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    cleaned = str(name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="name is required")
    db = _db()
    person = _find_person_by_name(db, cleaned)
    if person is not None and person["tmdb_person_id"] is not None:
        return _sanitize_library_payload(
            {
                "name": str(person["name"] or cleaned),
                "tmdb_person_id": int(person["tmdb_person_id"]),
                "person_id": int(person["id"]),
                "library_only": False,
            },
            user,
        )

    titles: List[Dict[str, Any]] = []
    person_id = int(person["id"]) if person is not None else None
    person_name = str(person["name"] or cleaned) if person is not None else cleaned
    if person_id is not None:
        titles = _library_titles_for_person_payload(db, person_id=person_id)
    if not titles:
        # Fall back to facet cast/directors query when no credit rows / no people match.
        for facet_key in ("cast", "directors"):
            result = query_library(
                db,
                filters_from_mapping({facet_key: cleaned, "limit": 50}),
            )
            items = list(result.get("items") or [])
            if items:
                titles = items
                break

    if person is None and not titles:
        raise HTTPException(status_code=404, detail="Person not found")

    return _sanitize_library_payload(
        {
            "name": person_name,
            "tmdb_person_id": None,
            "person_id": person_id,
            "library_only": True,
            "titles": titles,
            "returned": len(titles),
        },
        user,
    )


@app.get("/api/person/{tmdb_person_id}")
def person_detail(
    tmdb_person_id: int,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    settings = _settings()
    db = _db()
    tmdb_payload: Dict[str, Any] = {}
    filmography_total: Optional[int] = None
    if settings.tmdb_api_key:
        try:
            client = TMDBClient(settings.tmdb_api_key)
            raw = client.person_details(
                tmdb_person_id,
                append_to_response="combined_credits",
            )
            if isinstance(raw, dict) and raw.get("id"):
                tmdb_payload = {
                    "tmdb_person_id": int(raw.get("id") or tmdb_person_id),
                    "name": str(raw.get("name") or "").strip(),
                    "biography": str(raw.get("biography") or "").strip(),
                    "birthday": str(raw.get("birthday") or "").strip() or None,
                    "deathday": str(raw.get("deathday") or "").strip() or None,
                    "place_of_birth": str(raw.get("place_of_birth") or "").strip() or None,
                    "profile_url": client.profile_url(raw.get("profile_path"), size="w342"),
                    "known_for_department": str(raw.get("known_for_department") or "").strip(),
                }
                filmography_total = TMDBClient.filmography_total_from_combined_credits(raw)
        except RuntimeError:
            tmdb_payload = {}

    titles = _library_titles_for_person_payload(db, tmdb_person_id=tmdb_person_id)
    if not tmdb_payload and not titles:
        raise HTTPException(status_code=404, detail="Person not found")

    if not tmdb_payload:
        # Local-only person known via credits.
        with db.connect() as conn:
            local = conn.execute(
                """
                SELECT id, name, profile_url FROM people
                WHERE tmdb_person_id = ?
                LIMIT 1
                """,
                (int(tmdb_person_id),),
            ).fetchone()
        tmdb_payload = {
            "tmdb_person_id": int(tmdb_person_id),
            "name": str(local["name"] or "Unknown") if local else "Unknown",
            "biography": "",
            "birthday": None,
            "deathday": None,
            "place_of_birth": None,
            "profile_url": str(local["profile_url"] or "") if local else "",
            "known_for_department": "",
        }

    # Dedupe library titles that appear under multiple credit roles.
    unique_library = {
        (item.get("media_type"), item.get("tmdb_id") or item.get("rating_key") or item.get("title"))
        for item in titles
    }
    in_library_count = len(unique_library)
    library_owned_pct = None
    if filmography_total and filmography_total > 0:
        library_owned_pct = min(100, round((in_library_count / filmography_total) * 100))

    payload = {
        **tmdb_payload,
        "titles": titles,
        "returned": len(titles),
        "in_library_count": in_library_count,
        "filmography_total": filmography_total,
        "library_owned_pct": library_owned_pct,
    }
    return _sanitize_library_payload(payload, user)


def _resolve_library_row_for_title(
    db,
    *,
    media_type: str,
    item_id: str,
    id_type: str = "tmdb",
):
    if id_type == "rating_key":
        for item in db.all_library_items():
            if str(item["rating_key"] or "") == str(item_id):
                return item
        return None
    if media_type == "show" and id_type == "tvdb":
        return db.library_item_by_tvdb(int(item_id))
    return db.library_item_by_tmdb(int(item_id), media_type)


@app.get("/api/title/{media_type}/{item_id}/neighbors")
def title_neighbors(
    media_type: str,
    item_id: str,
    id_type: str = "tmdb",
    mode: str = "similar",
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Return cached plot neighbors for a library title, or an empty list."""
    db = _db()
    row = _resolve_library_row_for_title(
        db, media_type=media_type, item_id=item_id, id_type=id_type
    )
    if row is None:
        return _sanitize_library_payload({"items": [], "total": 0}, user)
    seed_id = int(row["id"])
    capped = min(max(1, int(limit or 12)), 24)
    neighbor_rows = db.get_neighbors(seed_id, mode=mode, limit=capped)
    items: List[Dict[str, Any]] = []
    for neighbor in neighbor_rows:
        genres_raw = neighbor["genres"] if "genres" in neighbor.keys() else "[]"
        try:
            genres = json.loads(genres_raw) if genres_raw else []
        except (TypeError, json.JSONDecodeError):
            genres = []
        if not isinstance(genres, list):
            genres = []
        score = float(neighbor["score"] or 0)
        items.append(
            {
                "media_type": str(neighbor["media_type"] or media_type),
                "title": str(neighbor["title"] or ""),
                "year": int(neighbor["year"]) if neighbor["year"] is not None else None,
                "tmdb_id": int(neighbor["tmdb_id"]) if neighbor["tmdb_id"] is not None else None,
                "tvdb_id": int(neighbor["tvdb_id"]) if neighbor["tvdb_id"] is not None else None,
                "rating_key": str(neighbor["rating_key"] or ""),
                "poster_url": str(neighbor["poster_url"] or ""),
                "overview": str(neighbor["summary"] or ""),
                "genres": [str(g) for g in genres if g],
                "in_library": True,
                "score": score,
                "match_score": score,
            }
        )
    return _sanitize_library_payload({"items": items, "total": len(items)}, user)


@app.post("/api/actions/propose")
def propose_action(payload: Dict[str, Any], user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    import uuid as uuid_mod

    scoped = _scoped_user_id(user)
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
            user_id=scoped,
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
            user_id=scoped,
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
        if settings.seerr.require_linked_user_for_requests and user.seerr_user_id is None:
            raise HTTPException(status_code=403, detail="Seerr account not linked for this user")
        if user.seerr_user_id is not None:
            pending["seerr_user_id"] = int(user.seerr_user_id)
        _db().save_pending_action(token, "request_seerr", pending, user_id=scoped)
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
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Unable to reach Seerr \u2014 check connection settings"),
        ) from error


@app.post("/api/actions/confirm")
async def confirm_action(
    payload: ActionConfirmRequest,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    scoped = _scoped_user_id(user)
    if not payload.confirmed:
        _db().pop_pending_action(payload.token, user_id=scoped)
        logger.info("Action cancelled token=%s", payload.token[:8])
        return {"cancelled": True}
    try:
        result = await execute_confirmed_action(
            _db(), _settings(), payload.token, user_id=scoped
        )
        logger.info("Action confirmed token=%s action=%s", payload.token[:8], result.get("action"))
        return {"ok": True, **result}
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Action confirmation failed"),
        ) from error


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
def list_watchlist(
    enrich: bool = False,
    user=Depends(get_current_user_dep),
) -> WatchlistListResponse:
    user_id = user.id if _settings().features.multi_user_enabled else None
    db = _db()
    items = db.list_watchlist_pins(user_id=user_id)
    if enrich and items:
        from curatorx.watchlist.curate import attach_watchlist_posters, enrich_watchlist_pins

        items = enrich_watchlist_pins(db, items)
        attach_watchlist_posters(db, items)
    return WatchlistListResponse(
        items=[WatchlistPin(**item) for item in items],
        count=len(items),
    )


def _attach_watchlist_posters(db, items: List[Dict[str, Any]]) -> None:
    """Fill poster_url + year for enriched watchlist pins from the library index."""
    from curatorx.watchlist.curate import attach_watchlist_posters

    attach_watchlist_posters(db, items)


@app.get("/api/watchlist/sync")
def get_watchlist_sync(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    from curatorx.watchlist.plex_sync import get_watchlist_sync_status

    return get_watchlist_sync_status(_db(), _settings(), user_id=user.id)


@app.put("/api/watchlist/sync")
def put_watchlist_sync(
    payload: WatchlistSyncSettingsUpdate,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    from curatorx.watchlist.plex_sync import get_watchlist_sync_status, update_watchlist_sync_settings

    if payload.enabled is None and payload.pull_on_login is None and payload.push_on_pin is None:
        raise HTTPException(status_code=400, detail="No sync settings provided")
    try:
        update_watchlist_sync_settings(
            _db(),
            user_id=user.id,
            enabled=payload.enabled,
            pull_on_login=payload.pull_on_login,
            push_on_pin=payload.push_on_pin,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Watchlist sync settings not found"),
        ) from error
    return get_watchlist_sync_status(_db(), _settings(), user_id=user.id)


@app.post("/api/watchlist/sync")
def run_watchlist_sync(
    payload: Optional[WatchlistSyncRequest] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    from curatorx.watchlist.plex_sync import sync_watchlist_with_plex

    direction = (payload.direction if payload else "both") or "both"
    if direction not in {"both", "pull", "push"}:
        raise HTTPException(status_code=400, detail="direction must be both, pull, or push")
    return sync_watchlist_with_plex(
        _db(),
        _settings(),
        user_id=user.id,
        direction=direction,
    )


@app.post("/api/watchlist", response_model=WatchlistPin)
def add_watchlist_pin(
    payload: WatchlistCreate,
    user=Depends(get_current_user_dep),
) -> WatchlistPin:
    from curatorx.watchlist.plex_sync import push_pin_to_plex

    if not payload.tmdb_id and not payload.tvdb_id:
        raise HTTPException(status_code=400, detail="tmdb_id or tvdb_id is required")
    settings = _settings()
    user_id = user.id if settings.features.multi_user_enabled else None
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
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid watchlist pin"),
        ) from error
    try:
        push_result = push_pin_to_plex(_db(), settings, pin, user_id=user.id)
        if push_result.get("plex_rating_key") and pin.get("id"):
            pin = {**pin, "plex_rating_key": push_result["plex_rating_key"]}
    except Exception:
        logger.debug("Watchlist push-on-pin failed", exc_info=True)
    return WatchlistPin(**pin)


@app.delete("/api/watchlist/{pin_id}")
def delete_watchlist_pin(
    pin_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    from curatorx.watchlist.plex_sync import remove_pin_from_plex

    settings = _settings()
    user_id = user.id if settings.features.multi_user_enabled else None
    existing = _db().get_watchlist_pin(pin_id, user_id=user_id)
    if existing is None and user_id is not None:
        # Fallback for single-scope pins created before multi-user.
        existing = _db().get_watchlist_pin(pin_id)
    removed = _db().delete_watchlist_pin(pin_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Watchlist pin not found")
    if existing is not None:
        try:
            remove_pin_from_plex(_db(), settings, existing, user_id=user.id)
        except Exception:
            logger.debug("Watchlist remove-from-plex failed", exc_info=True)
    return {"removed": True}


@app.get("/api/lists", response_model=CuratedListCollectionResponse)
def list_curated_lists(user=Depends(get_current_user_dep)) -> CuratedListCollectionResponse:
    user_id = user.id if _settings().features.multi_user_enabled else None
    items = _db().list_curated_lists(user_id=user_id)
    return CuratedListCollectionResponse(
        items=[CuratedList(**item) for item in items],
        count=len(items),
    )


@app.post("/api/lists", response_model=CuratedList)
def create_curated_list(
    payload: CuratedListCreate,
    user=Depends(get_current_user_dep),
) -> CuratedList:
    user_id = user.id if _settings().features.multi_user_enabled else None
    try:
        created = _db().create_curated_list(
            list_id=str(uuid.uuid4()),
            user_id=user_id,
            name=payload.name,
            description=payload.description or "",
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid list data"),
        ) from error
    return CuratedList(**created)


@app.get("/api/lists/{list_id}", response_model=CuratedList)
def get_curated_list(
    list_id: str,
    user=Depends(get_current_user_dep),
) -> CuratedList:
    user_id = user.id if _settings().features.multi_user_enabled else None
    found = _db().get_curated_list(list_id, user_id=user_id, include_items=True)
    if found is None:
        raise HTTPException(status_code=404, detail="List not found")
    return CuratedList(**found)


@app.patch("/api/lists/{list_id}", response_model=CuratedList)
def update_curated_list(
    list_id: str,
    payload: CuratedListUpdate,
    user=Depends(get_current_user_dep),
) -> CuratedList:
    user_id = user.id if _settings().features.multi_user_enabled else None
    if payload.name is None and payload.description is None:
        raise HTTPException(status_code=400, detail="No list fields to update")
    try:
        updated = _db().update_curated_list(
            list_id,
            user_id=user_id,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid list update"),
        ) from error
    if updated is None:
        raise HTTPException(status_code=404, detail="List not found")
    return CuratedList(**updated)


@app.delete("/api/lists/{list_id}")
def delete_curated_list(
    list_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    user_id = user.id if _settings().features.multi_user_enabled else None
    removed = _db().delete_curated_list(list_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="List not found")
    return {"removed": True}


@app.post("/api/lists/{list_id}/items", response_model=CuratedListItem)
def add_curated_list_item(
    list_id: str,
    payload: CuratedListItemCreate,
    user=Depends(get_current_user_dep),
) -> CuratedListItem:
    if not payload.tmdb_id and not payload.tvdb_id:
        raise HTTPException(status_code=400, detail="tmdb_id or tvdb_id is required")
    user_id = user.id if _settings().features.multi_user_enabled else None
    try:
        item = _db().add_curated_list_item(
            item_id=str(uuid.uuid4()),
            list_id=list_id,
            user_id=user_id,
            tmdb_id=payload.tmdb_id,
            tvdb_id=payload.tvdb_id,
            media_type=payload.media_type,
            title=payload.title.strip(),
            library_item_id=payload.library_item_id,
        )
    except ValueError as error:
        is_not_found = "not found" in str(error).lower()
        status = 404 if is_not_found else 400
        context = "List not found" if is_not_found else "Invalid list item"
        raise HTTPException(
            status_code=status,
            detail=_safe_error_detail(error, context),
        ) from error
    return CuratedListItem(**item)


@app.delete("/api/lists/{list_id}/items/{item_id}")
def delete_curated_list_item(
    list_id: str,
    item_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    user_id = user.id if _settings().features.multi_user_enabled else None
    removed = _db().delete_curated_list_item(list_id, item_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="List item not found")
    return {"removed": True}


@app.post("/api/preferences")
def add_preference(
    payload: PreferenceSignal,
    user=Depends(get_current_user_dep),
) -> Dict[str, bool]:
    remember_preference(_db(), payload, user_id=_scoped_user_id(user))
    _telemetry().record_preference_signal(
        signal_type=payload.signal_type,
        user_id=_scoped_user_id(user),
    )
    return {"saved": True}


@app.get("/api/household/peers")
def list_household_peers(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    """Sanitized household directory for recommending titles to other users."""
    if not _settings().features.multi_user_enabled:
        return {"items": [], "count": 0}
    peers = []
    for item in _db().list_users(limit=200):
        if item.get("disabled"):
            continue
        if str(item["id"]) == str(user.id):
            continue
        peers.append(
            {
                "id": item["id"],
                "display_name": item.get("preferred_name") or item.get("display_name"),
                "avatar_url": item.get("avatar_url"),
                "role": item.get("role"),
            }
        )
    return {"items": peers, "count": len(peers)}


@app.get("/api/recommendations")
def list_recommendations(
    unread_only: bool = False,
    limit: int = 20,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if not _settings().features.multi_user_enabled:
        return {"items": [], "count": 0, "unread_count": 0}
    items = _db().list_recommendations_for_user(
        user.id,
        unread_only=unread_only,
        limit=min(max(1, limit), 50),
    )
    unread_count = _db().count_unread_recommendations(user.id)
    return {"items": items, "count": len(items), "unread_count": unread_count}


@app.post("/api/recommendations")
def create_recommendations(
    payload: RecommendPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if not _settings().features.multi_user_enabled:
        raise HTTPException(status_code=400, detail="Multi-user mode is required for recommendations")
    if not payload.tmdb_id and not payload.tvdb_id and not payload.rating_key:
        raise HTTPException(status_code=400, detail="Provide tmdb_id, tvdb_id, or rating_key")
    db = _db()
    recipient_ids = []
    for raw_id in payload.to_user_ids:
        rid = str(raw_id or "").strip()
        if not rid or rid == user.id:
            continue
        target = db.get_user(rid)
        if target is None:
            raise HTTPException(status_code=404, detail=f"User not found: {rid}")
        if bool(int(target["disabled"] or 0)):
            raise HTTPException(status_code=400, detail=f"User is disabled: {rid}")
        recipient_ids.append(rid)
    if not recipient_ids:
        raise HTTPException(status_code=400, detail="Choose at least one recipient")
    created = []
    for rid in recipient_ids:
        created.append(
            db.create_recommendation(
                recommendation_id=str(uuid.uuid4()),
                from_user_id=user.id,
                to_user_id=rid,
                media_type=payload.media_type,
                title=payload.title.strip(),
                tmdb_id=payload.tmdb_id,
                tvdb_id=payload.tvdb_id,
                rating_key=(payload.rating_key or "").strip() or None,
                year=payload.year,
                poster_url=(payload.poster_url or "").strip() or None,
                message=(payload.message or "").strip() or None,
            )
        )
    return {"items": created, "count": len(created)}


@app.post("/api/recommendations/seen")
def mark_recommendations_seen(
    payload: RecommendationsSeenPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if not _settings().features.multi_user_enabled:
        return {"updated": 0}
    updated = _db().mark_recommendations_seen(
        user.id,
        recommendation_ids=payload.ids or None,
        all_unread=payload.all_unread,
    )
    return {"updated": updated}


@app.get("/api/reviews")
def list_reviews(
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
    title: Optional[str] = None,
    min_stars: Optional[int] = None,
    limit: int = 50,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    items = get_reviews(
        _db(),
        rating_key=rating_key,
        tmdb_id=tmdb_id,
        media_type=media_type,
        title=title,
        min_stars=min_stars,
        limit=limit,
        user_id=_scoped_user_id(user),
    )
    return {"items": items, "count": len(items)}


@app.post("/api/reviews")
def create_review(
    payload: UserReviewCreate,
    user=Depends(get_current_user_dep),
):
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
            user_id=_scoped_user_id(user),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid review data"),
        ) from error

    _telemetry().record_review_saved(
        rating_key=payload.rating_key,
        stars=payload.stars,
        prompted_by=payload.prompted_by,
        user_id=_scoped_user_id(user),
    )
    settings = _settings()
    saved = sync_review_rating_to_plex(
        _db(),
        settings,
        saved,
        replace_plex_rating=payload.replace_plex_rating,
    )
    if saved.get("reason") == "plex_rating_conflict":
        plex_stars = float(saved["plex_stars"])
        submitted_stars = float(saved["submitted_stars"])
        plex_label = (
            str(int(plex_stars)) if plex_stars == int(plex_stars) else str(plex_stars)
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "plex_rating_conflict",
                "plex_stars": plex_stars,
                "submitted_stars": submitted_stars,
                "message": f"Plex has {plex_label}★ — keep or replace?",
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
        user_id=_scoped_user_id(user),
    )
    return {"confirmation_token": token}


@app.post("/api/plex/collections/{collection_key}/items/propose")
def propose_plex_collection_items(
    collection_key: str,
    payload: PlexCollectionItemsProposePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
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
        user_id=_scoped_user_id(user),
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
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Prompt not found"),
        ) from error
    return RatingPrompt(**saved)
