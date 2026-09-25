"""Setup wizard, settings, and connection-test HTTP routes.

Registered via ``register_setup_routes`` so app.py stays the composition root.
"""


def register_setup_routes(app):
    """Attach setup / settings / test routes to the FastAPI app."""
    from typing import Any, Dict, List, Optional

    from fastapi import APIRouter, Depends, HTTPException, Request, Response
    from pydantic import BaseModel, Field

    import projectionist.web.app as app_mod

    ANTHROPIC_MODEL_OPTIONS = app_mod.ANTHROPIC_MODEL_OPTIONS
    DATA_DIR = app_mod.DATA_DIR
    LLM_MODEL_DEFAULTS = app_mod.LLM_MODEL_DEFAULTS
    LLM_PROVIDER_DEFAULTS = app_mod.LLM_PROVIDER_DEFAULTS
    McpKeyWhichPayload = app_mod.McpKeyWhichPayload
    PlexClient = app_mod.PlexClient
    REVEALABLE_SECRET_FIELDS = app_mod.REVEALABLE_SECRET_FIELDS
    RevealSecretPayload = app_mod.RevealSecretPayload
    Settings = app_mod.Settings
    SettingsPayload = app_mod.SettingsPayload
    TestPayload = app_mod.TestPayload
    _db = app_mod._db
    _mask_settings = app_mod._mask_settings
    _normalize_mcp_image_sizes = app_mod._normalize_mcp_image_sizes
    _resolve_test_payload = app_mod._resolve_test_payload
    _secret_hint = app_mod._secret_hint
    _settings = app_mod._settings
    _validate_distinct_mcp_keys = app_mod._validate_distinct_mcp_keys
    asdict = app_mod.asdict
    build_certifications_status = app_mod.build_certifications_status
    build_setup_status = app_mod.build_setup_status
    build_wizard_status = app_mod.build_wizard_status
    has_usable_session_secret = app_mod.has_usable_session_secret
    invalidate_certifications_on_settings_change = app_mod.invalidate_certifications_on_settings_change
    logger = app_mod.logger
    merge_secret_fields = app_mod.merge_secret_fields
    merge_theater_settings_payload = app_mod.merge_theater_settings_payload
    normalize_path_settings = app_mod.normalize_path_settings
    normalize_plex_type = app_mod.normalize_plex_type
    normalize_settings_llm = app_mod.normalize_settings_llm
    record_service_integration = app_mod.record_service_integration
    require_role = app_mod.require_role
    resolve_radarr_root_folder = app_mod.resolve_radarr_root_folder
    resolve_sonarr_root_folder = app_mod.resolve_sonarr_root_folder
    save_settings = app_mod.save_settings
    secret_field_sources = app_mod.secret_field_sources
    secrets = app_mod.secrets
    set_session_cookie = app_mod.set_session_cookie
    sync_settings_to_db = app_mod.sync_settings_to_db
    test_fanart = app_mod.test_fanart
    test_llm = app_mod.test_llm
    test_plex = app_mod.test_plex
    test_radarr = app_mod.test_radarr
    test_seerr = app_mod.test_seerr
    test_sonarr = app_mod.test_sonarr
    test_tautulli = app_mod.test_tautulli
    test_tmdb = app_mod.test_tmdb
    test_tunarr = app_mod.test_tunarr

    router = APIRouter(tags=["setup"])

    @router.get("/api/setup/status")
    def setup_status() -> Dict[str, Any]:
        return build_setup_status(_settings(), _db())


    class SetupCommitPayload(BaseModel):
        profile: str = Field(min_length=3, max_length=16)
        username: str = Field(min_length=2, max_length=80)
        password: str = Field(min_length=8, max_length=256)
        household_domain: str = ""
        trust_proxy: bool = False
        allow_access_requests: Optional[bool] = None
        invite_only: Optional[bool] = None


    @router.get("/api/setup/handshake")
    def setup_handshake_get(request: Request) -> Dict[str, Any]:
        from projectionist.web.setup_mode import handshake_payload

        return handshake_payload(request, _db(), persist=True)


    @router.post("/api/setup/handshake")
    def setup_handshake_post(request: Request) -> Dict[str, Any]:
        from projectionist.web.setup_mode import handshake_payload

        return handshake_payload(request, _db(), persist=True)


    @router.post("/api/setup/commit")
    def setup_commit_endpoint(
        payload: SetupCommitPayload,
        request: Request,
        response: Response,
    ) -> Dict[str, Any]:
        from projectionist.web.setup_mode import commit_setup

        result = commit_setup(
            request,
            _db(),
            _settings(),
            DATA_DIR,
            profile=payload.profile,
            username=payload.username,
            password=payload.password,
            household_domain=payload.household_domain,
            trust_proxy=payload.trust_proxy,
            allow_access_requests=payload.allow_access_requests,
            invite_only=payload.invite_only,
        )
        set_session_cookie(response, str(result["user"]["id"]), request, db=_db())
        return result


    @router.get("/api/setup/wizard")
    def setup_wizard() -> Dict[str, Any]:
        return build_wizard_status(_settings(), _db())


    @router.get("/api/setup/certifications")
    def setup_certifications() -> Dict[str, Any]:
        return build_certifications_status(_db())


    @router.get("/api/setup/llm-providers")
    def llm_providers() -> Dict[str, Any]:
        from projectionist.telemetry.llm_usage import model_price_row

        return {
            "base_urls": LLM_PROVIDER_DEFAULTS,
            "models": LLM_MODEL_DEFAULTS,
            "anthropic_models": list(ANTHROPIC_MODEL_OPTIONS),
            "anthropic_model_rows": [model_price_row(m) for m in ANTHROPIC_MODEL_OPTIONS],
        }


    @router.get("/api/settings")
    def get_settings(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        return _mask_settings(_settings())


    @router.post("/api/settings/secrets/reveal")
    def reveal_settings_secret(
        payload: RevealSecretPayload, user=Depends(require_role("owner"))
    ) -> Dict[str, Any]:
        """Owner-only plaintext for one connection secret. Never logged."""
        del user
        field = str(payload.field or "").strip()
        if field not in REVEALABLE_SECRET_FIELDS:
            raise HTTPException(status_code=400, detail="Unknown or non-revealable secret field")
        settings = _settings()
        if field == "seerr.api_key":
            value = str(settings.seerr.api_key or "").strip()
        else:
            value = str(getattr(settings, field, "") or "").strip()
        if not value:
            raise HTTPException(status_code=404, detail="Secret is not configured")
        # Intentionally no logger call with *value* — trust-plane only if needed later.
        return {"field": field, "value": value}


    @router.put("/api/settings")
    def put_settings(payload: SettingsPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        settings_path = DATA_DIR / "settings.json"
        before = Settings.load(settings_path)
        existing = _settings()
        merged = merge_secret_fields(payload.model_dump(), existing)
        merge_theater_settings_payload(payload, existing, merged)
        settings = _normalize_mcp_image_sizes(
            normalize_path_settings(normalize_settings_llm(Settings.from_mapping(merged)))
        )
        _validate_distinct_mcp_keys(settings)
        if settings.features.multi_user_enabled and not has_usable_session_secret(DATA_DIR):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot enable multi-user auth without a strong session secret. "
                    "Set PROJECTIONIST_SESSION_SECRET "
                    "to a long random value (not the development default), or remove that "
                    "env var so Projectionist can generate one under DATA_DIR."
                ),
            )
        wizard_status = build_wizard_status(settings, _db())
        if not settings.onboarding_complete and wizard_status["onboarding_complete"]:
            settings = Settings.from_mapping({**asdict(settings), "onboarding_complete": True})
        invalidate_certifications_on_settings_change(_db(), before, settings, payload.model_dump())
        save_settings(DATA_DIR, settings)
        sync_settings_to_db(_db(), settings)
        try:
            from projectionist.theater.hub import get_theater_hub

            get_theater_hub().notify_settings_changed()
        except RuntimeError:
            pass
        except Exception:  # noqa: BLE001
            logger.debug("theater settings notify skipped", exc_info=True)
        # Disable→re-enable should re-nudge; clear once-ever dedupe when Live turns off.
        before_live = bool(getattr(before.features, "live_channels_enabled", False))
        after_live = bool(getattr(settings.features, "live_channels_enabled", False))
        if before_live and not after_live:
            try:
                from projectionist.live_channels.nudges import reset_live_channels_ready_nudge

                reset_live_channels_ready_nudge(_db())
            except Exception:  # noqa: BLE001
                logger.debug("Live Channels ready-nudge reset skipped", exc_info=True)
        # Seed the env-injected owner the moment multi-user is turned on, so there
        # is no window for a LAN neighbor to race the first login (H2).
        if settings.features.multi_user_enabled:
            try:
                from projectionist.web.auth import seed_env_owner

                seed_env_owner(_db())
            except Exception:  # noqa: BLE001
                logger.exception("Owner seeding after settings update failed (continuing)")
        return _mask_settings(settings)


    def _mcp_key_field(which: str) -> str:
        return "mcp_api_key" if which == "privacy" else "mcp_full_api_key"


    @router.post("/api/settings/mcp-keys/rotate")
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
        overrides: Dict[str, Any] = {field: new_key}
        # The active-curation scope is bound to full-key issuance (H3).
        if payload.which == "full" and payload.confirm_scope is not None:
            overrides["mcp_full_confirm_enabled"] = bool(payload.confirm_scope)
        updated = Settings.from_mapping({**asdict(existing), **overrides})
        _validate_distinct_mcp_keys(updated)
        invalidate_certifications_on_settings_change(_db(), before, updated, overrides)
        save_settings(DATA_DIR, updated)
        sync_settings_to_db(_db(), updated)
        return {
            "which": payload.which,
            "field": field,
            "key": new_key,
            "hint": _secret_hint(new_key),
            "settings": _mask_settings(updated),
        }


    @router.post("/api/settings/mcp-keys/clear")
    def clear_mcp_key(payload: McpKeyWhichPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
        """Clear a file-persisted MCP key. Env/Unraid-sourced keys must be removed from the template."""
        del user
        field = _mcp_key_field(payload.which)
        sources = secret_field_sources(DATA_DIR)
        if sources.get(field) == "env":
            env_name = (
                "PROJECTIONIST_MCP_API_KEY"
                if payload.which == "privacy"
                else "PROJECTIONIST_MCP_FULL_API_KEY"
            )

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
        overrides: Dict[str, Any] = {field: ""}
        # Clearing the full key also drops its active-curation scope (H3).
        if payload.which == "full":
            overrides["mcp_full_confirm_enabled"] = False
        updated = Settings.from_mapping({**asdict(existing), **overrides})
        invalidate_certifications_on_settings_change(_db(), before, updated, overrides)
        save_settings(DATA_DIR, updated)
        sync_settings_to_db(_db(), updated)
        return {"which": payload.which, "field": field, "settings": _mask_settings(updated)}


    @router.post("/api/setup/test/plex")
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


    @router.post("/api/setup/test/radarr")
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


    @router.post("/api/setup/test/sonarr")
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


    @router.post("/api/setup/test/tmdb")
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


    @router.post("/api/setup/test/fanart")
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


    @router.post("/api/setup/test/tautulli")
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


    @router.post("/api/setup/test/seerr")
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


    @router.post("/api/setup/test/tunarr")
    def api_test_tunarr(payload: TestPayload, user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        resolved = _resolve_test_payload(payload)
        result = test_tunarr(resolved.get("tunarr_url") or "")
        record_service_integration(
            _db(),
            "tunarr",
            base_url=resolved.get("tunarr_url") or "",
            api_token="",
            ok=bool(result.get("ok")),
        )
        return result


    @router.post("/api/setup/test/llm")
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


    @router.get("/api/plex/sections")
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

    app.include_router(router)
