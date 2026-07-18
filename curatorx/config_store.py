"""Persistent settings for CuratorX."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Type

NESTED_SETTINGS_TYPES: Dict[str, Type[Any]] = {}

ENV_TO_FIELD = {
    "PLEX_URL": "plex_url",
    "PLEX_TOKEN": "plex_token",
    "PLEX_MOVIE_SECTION": "plex_movie_section",
    "PLEX_TV_SECTION": "plex_tv_section",
    "RADARR_URL": "radarr_url",
    "RADARR_API_KEY": "radarr_api_key",
    "SONARR_URL": "sonarr_url",
    "SONARR_API_KEY": "sonarr_api_key",
    "MOVIES_ROOT": "movies_root",
    "TV_ROOT": "tv_root",
    "RADARR_ROOT_FOLDER": "radarr_root_folder",
    "SONARR_ROOT_FOLDER": "sonarr_root_folder",
    "RADARR_QUALITY_PROFILE_ID": "radarr_quality_profile_id",
    "SONARR_QUALITY_PROFILE_ID": "sonarr_quality_profile_id",
    "TMDB_API_KEY": "tmdb_api_key",
    "TVDB_API_KEY": "tvdb_api_key",
    "FANART_API_KEY": "fanart_api_key",
    "OMDB_API_KEY": "omdb_api_key",
    "CURATORX_LONG_SYNOPSIS_SOURCE": "long_synopsis_source",
    "TAUTULLI_URL": "tautulli_url",
    "TAUTULLI_API_KEY": "tautulli_api_key",
    "LLM_PROVIDER": "llm_provider",
    "LLM_BASE_URL": "llm_base_url",
    "LLM_API_KEY": "llm_api_key",
    "LLM_MODEL": "llm_model",
    "LLM_EMBEDDING_MODEL": "llm_embedding_model",
    "LLM_EMBEDDING_BASE_URL": "llm_embedding_base_url",
    "CURATORX_WEBHOOK_SECRET": "webhook_secret",
    "CURATORX_MCP_API_KEY": "mcp_api_key",
    "CURATORX_MCP_FULL_API_KEY": "mcp_full_api_key",
}

FIELD_TO_ENV = {value: key for key, value in ENV_TO_FIELD.items()}

LLM_PROVIDER_DEFAULTS: Dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "custom_openai_compatible": "",
    "openai_compatible": "https://api.openai.com/v1",
}

ANTHROPIC_MODEL_OPTIONS: tuple[str, ...] = (
    "claude-sonnet-4-6",
    "claude-sonnet-4-20250514",
    "claude-sonnet-4-5-20250929",
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
    "claude-haiku-4-5",
)

ANTHROPIC_MODEL_ALIASES: Dict[str, str] = {
    "claude-sonnet-4": "claude-sonnet-4-6",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-0": "claude-sonnet-4-6",
    "claude-3-5-sonnet": "claude-sonnet-4-6",
    "claude-3-5-sonnet-latest": "claude-sonnet-4-6",
    "claude-3-sonnet": "claude-sonnet-4-6",
    "claude-3-5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-5-haiku-latest": "claude-3-5-haiku-20241022",
    "claude-3-haiku": "claude-3-haiku-20240307",
    "claude-3-haiku-latest": "claude-3-haiku-20240307",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
}

_DEPRECATED_ANTHROPIC_MODELS: Dict[str, str] = {
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    "claude-3-5-sonnet-20240620": "claude-sonnet-4-6",
    "claude-3-opus-20240229": "claude-sonnet-4-6",
}

_ANTHROPIC_DATED_MODEL = re.compile(r"^claude-[a-z0-9.-]+-\d{8}$", re.IGNORECASE)

LLM_MODEL_DEFAULTS: Dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "mistral": "mistral-small-latest",
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "deepseek": "deepseek-chat",
    "ollama": "llama3",
    "openrouter": "openai/gpt-4o-mini",
    "custom_openai_compatible": "gpt-4o-mini",
    "openai_compatible": "gpt-4o-mini",
}

_OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4", "text-embedding", "chatgpt-")
_OPENAI_COMPAT_PROVIDERS = frozenset({"openai", "openai_compatible", "custom_openai_compatible"})

PATH_FIELDS = (
    "movies_root",
    "tv_root",
    "radarr_root_folder",
    "sonarr_root_folder",
)

logger = logging.getLogger(__name__)


def model_looks_openai(model: str) -> bool:
    cleaned = str(model or "").lower().strip()
    return any(cleaned.startswith(prefix) for prefix in _OPENAI_MODEL_PREFIXES)


def model_looks_anthropic(model: str) -> bool:
    return str(model or "").lower().strip().startswith("claude")


def normalize_anthropic_model(model: str) -> str:
    """Map stale or alias Anthropic model IDs to pinned, API-valid snapshots."""
    default = LLM_MODEL_DEFAULTS["anthropic"]
    cleaned = str(model or "").strip()
    if not cleaned:
        return default
    if model_looks_openai(cleaned):
        return default

    lowered = cleaned.lower()
    if lowered in ANTHROPIC_MODEL_ALIASES:
        return ANTHROPIC_MODEL_ALIASES[lowered]
    if lowered in _DEPRECATED_ANTHROPIC_MODELS:
        return _DEPRECATED_ANTHROPIC_MODELS[lowered]
    if lowered.endswith("-latest"):
        return default
    if lowered in {option.lower() for option in ANTHROPIC_MODEL_OPTIONS}:
        for option in ANTHROPIC_MODEL_OPTIONS:
            if option.lower() == lowered:
                return option
    if _ANTHROPIC_DATED_MODEL.match(lowered):
        return lowered
    if model_looks_anthropic(lowered):
        return default
    return default


def resolve_llm_model(provider: str, model: str = "") -> str:
    normalized = (provider or "openai").lower().strip()
    cleaned = str(model or "").strip()
    default = LLM_MODEL_DEFAULTS.get(normalized, LLM_MODEL_DEFAULTS["openai"])
    if not cleaned:
        return default
    if normalized == "anthropic":
        return normalize_anthropic_model(cleaned)
    if normalized in {"openai", "openai_compatible", "custom_openai_compatible"} and model_looks_anthropic(cleaned):
        return LLM_MODEL_DEFAULTS["openai"]
    return cleaned


def api_key_implies_provider(api_key: str) -> str | None:
    """Infer LLM vendor from common API key prefixes when unambiguous."""
    cleaned = str(api_key or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("sk-ant-"):
        return "anthropic"
    return None


def reconcile_llm_provider(settings: Settings) -> Settings:
    """Align provider with API key prefix when the mismatch is unambiguous."""
    implied = api_key_implies_provider(settings.llm_api_key)
    if not implied:
        return settings
    provider = (settings.llm_provider or "openai").lower().strip()
    if implied == "anthropic" and provider in _OPENAI_COMPAT_PROVIDERS:
        return Settings.from_mapping({**asdict(settings), "llm_provider": "anthropic"})
    return settings


def resolve_radarr_root_folder(settings: Settings) -> str:
    for value in (settings.radarr_root_folder, settings.movies_root):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return "/media/movies"


def resolve_sonarr_root_folder(settings: Settings) -> str:
    for value in (settings.sonarr_root_folder, settings.tv_root):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return "/media/tv"


def normalize_root_path(path: str) -> str:
    return str(path or "").strip().rstrip("/")


def root_folder_paths_from_api(entries: List[Mapping[str, Any]]) -> List[str]:
    paths: List[str] = []
    for entry in entries:
        path = str(entry.get("path") or "").strip()
        if path:
            paths.append(path)
    return paths


def format_arr_root_folder_mismatch_error(
    service: str,
    configured: str,
    available: List[str],
) -> str:
    service_label = service.strip() or "Arr"
    setting_key = "radarr_root_folder" if service_label.lower() == "radarr" else "sonarr_root_folder"
    if not available:
        return (
            f"{service_label} has no root folders configured. "
            f"Add one in {service_label} Settings → Media Management → Root Folders, "
            f"then set {setting_key} in Configuration → Advanced settings."
        )
    listed = ", ".join(available)
    return (
        f"Configured {service_label.lower()} root folder '{configured}' is not registered in {service_label}. "
        f"Available root folders: {listed}. "
        f"Set {setting_key} in Configuration → Advanced settings to one of these paths."
    )


def pick_arr_root_folder(configured: str, available: List[str], *, service: str = "Arr") -> str:
    configured_clean = normalize_root_path(configured)
    if not configured_clean:
        raise RuntimeError(
            f"{service} root folder path is not configured. "
            f"Set radarr_root_folder or sonarr_root_folder in Configuration → Advanced settings."
        )
    if not available:
        raise RuntimeError(format_arr_root_folder_mismatch_error(service, configured_clean, available))

    for path in available:
        if normalize_root_path(path) == configured_clean:
            return path

    if len(available) == 1:
        return available[0]

    raise RuntimeError(format_arr_root_folder_mismatch_error(service, configured_clean, available))


def configured_arr_root_folder_mismatch(
    service: str,
    configured: str,
    root_folders: List[Mapping[str, Any]],
) -> str | None:
    configured_clean = normalize_root_path(configured)
    if not configured_clean:
        return None
    available = root_folder_paths_from_api(root_folders)
    if any(normalize_root_path(path) == configured_clean for path in available):
        return None
    return format_arr_root_folder_mismatch_error(service, configured_clean, available)


def validate_arr_root_folder(
    service: str,
    configured: str,
    root_folders: List[Mapping[str, Any]],
) -> str | None:
    try:
        pick_arr_root_folder(
            configured,
            root_folder_paths_from_api(root_folders),
            service=service,
        )
    except RuntimeError as error:
        return str(error)
    return None


def radarr_root_folder_configured(settings: Settings) -> bool:
    return bool(
        str(settings.radarr_root_folder or "").strip()
        or str(settings.movies_root or "").strip()
    )


def sonarr_root_folder_configured(settings: Settings) -> bool:
    return bool(
        str(settings.sonarr_root_folder or "").strip()
        or str(settings.tv_root or "").strip()
    )


def radarr_add_configuration_error(settings: Settings) -> str | None:
    if not str(settings.radarr_url or "").strip() or not str(settings.radarr_api_key or "").strip():
        return "Radarr is not configured. Add Radarr URL and API key in Configuration."
    if not radarr_root_folder_configured(settings):
        return (
            "Radarr root folder path is not configured. "
            "Open Configuration → Advanced settings and set radarr_root_folder or movies_root."
        )
    return None


def sonarr_add_configuration_error(settings: Settings) -> str | None:
    if not str(settings.sonarr_url or "").strip() or not str(settings.sonarr_api_key or "").strip():
        return "Sonarr is not configured. Add Sonarr URL and API key in Configuration."
    if not sonarr_root_folder_configured(settings):
        return (
            "Sonarr root folder path is not configured. "
            "Open Configuration → Advanced settings and set sonarr_root_folder or tv_root."
        )
    return None


def plex_configuration_error(settings: Settings) -> str | None:
    if not str(settings.plex_url or "").strip() or not str(settings.plex_token or "").strip():
        return "Plex is not configured. Add Plex URL and token in Configuration."
    return None


def seerr_configuration_error(settings: Settings) -> str | None:
    if not settings.features.seerr_enabled:
        return "Seerr is not enabled. Turn on features.seerr_enabled in Configuration."
    if not str(settings.seerr.url or "").strip() or not str(settings.seerr.api_key or "").strip():
        return "Seerr is not configured. Add Seerr URL and API key in Configuration."
    return None


def uses_seerr_request_path(settings: Settings, *, role: str) -> bool:
    return bool(settings.features.seerr_enabled and str(role or "").lower() != "owner")


def plex_collections_configuration_error(settings: Settings) -> str | None:
    if not settings.features.plex_collections_enabled:
        return (
            "Plex collection management is not enabled. "
            "Turn on features.plex_collections_enabled in Configuration."
        )
    return plex_configuration_error(settings)


def resolve_plex_section(settings: Settings, media_type: str) -> str:
    if media_type == "movie":
        return str(settings.plex_movie_section or "").strip()
    return str(settings.plex_tv_section or "").strip()


def normalize_path_settings(settings: Settings) -> Settings:
    fresh = Settings()
    merged = asdict(settings)
    updates: Dict[str, Any] = {}

    if not str(merged.get("movies_root") or "").strip():
        updates["movies_root"] = fresh.movies_root
    if not str(merged.get("tv_root") or "").strip():
        updates["tv_root"] = fresh.tv_root

    movies_root = str(updates.get("movies_root") or merged.get("movies_root") or "").strip()
    tv_root = str(updates.get("tv_root") or merged.get("tv_root") or "").strip()

    if not str(merged.get("radarr_root_folder") or "").strip():
        updates["radarr_root_folder"] = movies_root or fresh.radarr_root_folder
    if not str(merged.get("sonarr_root_folder") or "").strip():
        updates["sonarr_root_folder"] = tv_root or fresh.sonarr_root_folder

    if not updates:
        return settings
    return Settings.from_mapping({**merged, **updates})


def validate_llm_settings(settings: Settings) -> str | None:
    """Return a user-facing error when LLM settings cannot authenticate."""
    provider = (settings.llm_provider or "openai").lower().strip()
    api_key = str(settings.llm_api_key or "").strip()
    if provider == "ollama":
        return None
    if not api_key:
        return (
            "LLM API key is not configured. "
            "Open Configuration → LLM, enter your API key, verify, and save."
        )
    implied = api_key_implies_provider(api_key)
    if implied == "anthropic" and provider in _OPENAI_COMPAT_PROVIDERS:
        return (
            "Your API key is for Anthropic, but LLM provider is set to OpenAI. "
            "Open Configuration → LLM, select Anthropic, verify, and save."
        )
    if provider == "anthropic" and api_key.startswith("sk-") and not api_key.startswith("sk-ant-"):
        return (
            "Your API key looks like an OpenAI key, but LLM provider is set to Anthropic. "
            "Open Configuration → LLM, select OpenAI, verify, and save."
        )
    return None


def normalize_settings_llm(settings: Settings) -> Settings:
    settings = reconcile_llm_provider(settings)
    provider = (settings.llm_provider or "openai").lower().strip()
    resolved_model = resolve_llm_model(provider, settings.llm_model)
    resolved_base = resolve_llm_base_url(provider, settings.llm_base_url)
    updates: Dict[str, Any] = {}
    if (settings.llm_provider or "openai").lower().strip() != provider:
        updates["llm_provider"] = provider
    if resolved_model != settings.llm_model:
        updates["llm_model"] = resolved_model
    if resolved_base != settings.llm_base_url:
        updates["llm_base_url"] = resolved_base
    if not updates:
        return settings
    return Settings.from_mapping({**asdict(settings), **updates})


def load_dotenv_file(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (existing vars win)."""
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.append(Path.cwd() / ".env")
        candidates.append(Path(__file__).resolve().parents[1] / ".env")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        loaded_any = False
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
                loaded_any = True
        if loaded_any:
            logger.debug("Loaded environment from %s", candidate)
            return


def resolve_llm_base_url(provider: str, base_url: str = "") -> str:
    normalized = (provider or "openai").lower().strip()
    if normalized == "anthropic":
        cleaned = base_url.strip().rstrip("/")
        default = LLM_PROVIDER_DEFAULTS["anthropic"]
        if not cleaned:
            return default
        stripped = cleaned.removesuffix("/v1")
        openai_hosts = {
            LLM_PROVIDER_DEFAULTS["openai"].removesuffix("/v1"),
            LLM_PROVIDER_DEFAULTS["openai_compatible"].removesuffix("/v1"),
        }
        if stripped in openai_hosts:
            return default
        return stripped
    if normalized == "custom_openai_compatible":
        return base_url.strip().rstrip("/")
    if base_url.strip():
        return base_url.strip().rstrip("/")
    return LLM_PROVIDER_DEFAULTS.get(normalized, LLM_PROVIDER_DEFAULTS["openai"])


@dataclass
class FeatureFlags:
    multi_user_enabled: bool = False
    seerr_enabled: bool = False
    plex_collections_enabled: bool = False


@dataclass
class AuthSettings:
    mode: str = "disabled"
    plex_login_enabled: bool = True
    oidc_enabled: bool = False
    local_login_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_provider_name: str = "SSO"


@dataclass
class SeerrSettings:
    url: str = ""
    api_key: str = ""
    link_on_login: bool = True
    require_linked_user_for_requests: bool = False


NESTED_SETTINGS_TYPES.update(
    {
        "features": FeatureFlags,
        "auth": AuthSettings,
        "seerr": SeerrSettings,
    }
)


@dataclass
class Settings:
    plex_url: str = ""
    plex_token: str = ""
    plex_movie_section: str = ""
    plex_tv_section: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    movies_root: str = "/media/movies"
    tv_root: str = "/media/tv"
    radarr_root_folder: str = "/media/movies"
    sonarr_root_folder: str = "/media/tv"
    radarr_quality_profile_id: int = 1
    sonarr_quality_profile_id: int = 1
    tmdb_api_key: str = ""
    tvdb_api_key: str = ""
    fanart_api_key: str = ""
    omdb_api_key: str = ""
    # Long-synopsis idle source: "wikipedia" (default), "omdb", "auto", or "off".
    # Missing/unset → wikipedia. Explicit empty / off / none / disabled → trickle off.
    long_synopsis_source: str = "wikipedia"
    tautulli_url: str = ""
    tautulli_api_key: str = ""
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_embedding_model: str = "text-embedding-3-small"
    llm_embedding_base_url: str = ""
    onboarding_complete: bool = False
    setup_wizard_pending: bool = False
    library_sync_interval_hours: int = 24
    # Preferred local hour (0–23) for daily sync; None = interval-only scheduling.
    library_sync_hour: Optional[int] = None
    tv_page_size: int = 500
    library_enrich_workers: int = 6
    sync_reviews_to_plex: bool = True
    webhook_secret: str = ""
    # Dual-mode MCP HTTP keys (also CURATORX_MCP_* env / Unraid).
    mcp_api_key: str = ""
    mcp_full_api_key: str = ""
    # MCP / privacy image CDN sizes (image.tmdb.org/t/p/{size}/…).
    mcp_tmdb_poster_size: str = "w500"
    mcp_tmdb_backdrop_size: str = "w1280"
    features: FeatureFlags = field(default_factory=FeatureFlags)
    auth: AuthSettings = field(default_factory=AuthSettings)
    seerr: SeerrSettings = field(default_factory=SeerrSettings)

    def apply_to_environ(self) -> None:
        for env_name, field_name in ENV_TO_FIELD.items():
            value = getattr(self, field_name)
            if value is not None and value != "":
                os.environ[env_name] = str(value)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Settings":
        known = {field.name for field in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered: Dict[str, Any] = {}
        for key in known:
            if key not in data:
                continue
            value = data[key]
            nested_cls = NESTED_SETTINGS_TYPES.get(key)
            if nested_cls and isinstance(value, Mapping):
                nested_known = {field.name for field in nested_cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
                nested_filtered = {k: v for k, v in value.items() if k in nested_known}
                filtered[key] = nested_cls(**nested_filtered)
            elif key.endswith("_id") and value is not None:
                filtered[key] = int(value)
            elif key == "library_sync_hour":
                if value is None or value == "":
                    filtered[key] = None
                else:
                    hour = int(value)
                    filtered[key] = hour if 0 <= hour <= 23 else None
            elif key.endswith("_hours") or key in {"tv_page_size", "library_enrich_workers"}:
                filtered[key] = int(value) if value is not None else value
            else:
                filtered[key] = value
        return cls(**filtered)

    @classmethod
    def from_env(cls) -> "Settings":
        values: Dict[str, Any] = {}
        for env_name, field_name in ENV_TO_FIELD.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        for int_field in (
            "radarr_quality_profile_id",
            "sonarr_quality_profile_id",
            "library_sync_interval_hours",
            "tv_page_size",
            "library_enrich_workers",
        ):
            env_key = FIELD_TO_ENV.get(int_field, "")
            if env_key in os.environ:
                values[int_field] = int(os.environ[env_key])
        return cls.from_mapping(values)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_mapping(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_settings_file_data(data_dir: Path) -> Dict[str, Any]:
    settings_path = data_dir / "settings.json"
    if not settings_path.exists():
        logger.debug("No settings.json at %s; using defaults and env", data_dir)
        return {}
    try:
        return json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        logger.warning("Invalid settings.json at %s: %s", settings_path, error)
        return {}


def _file_field_explicitly_set(file_data: Mapping[str, Any], field_name: str) -> bool:
    if field_name not in file_data:
        return False
    value = file_data[field_name]
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def load_merged_settings(data_dir: Path) -> Settings:
    """Merge settings.json with environment variables.

    Values explicitly saved in settings.json take precedence. Environment
    variables fill gaps when a field is missing or empty in the file.
    """
    file_data = _load_settings_file_data(data_dir)
    settings = Settings.from_mapping(file_data) if file_data else Settings()
    merged = asdict(settings)
    for env_name, field_name in ENV_TO_FIELD.items():
        if env_name not in os.environ:
            continue
        env_value = os.environ[env_name]
        if env_value is None or str(env_value).strip() == "":
            continue
        if _file_field_explicitly_set(file_data, field_name):
            continue
        merged[field_name] = env_value
        logger.debug("Settings field %s filled from env %s", field_name, env_name)
    for int_field in (
        "radarr_quality_profile_id",
        "sonarr_quality_profile_id",
        "library_sync_interval_hours",
        "tv_page_size",
        "library_enrich_workers",
    ):
        env_key = FIELD_TO_ENV.get(int_field, "")
        if env_key not in os.environ or str(os.environ[env_key]).strip() == "":
            continue
        if _file_field_explicitly_set(file_data, int_field):
            continue
        merged[int_field] = int(os.environ[env_key])
    return normalize_path_settings(normalize_settings_llm(Settings.from_mapping(merged)))


def secret_field_sources(data_dir: Path) -> Dict[str, str]:
    """Return per-secret source: 'env', 'file', or '' (unset)."""
    file_data = _load_settings_file_data(data_dir)
    sources: Dict[str, str] = {}
    secret_fields = (
        "plex_token",
        "radarr_api_key",
        "sonarr_api_key",
        "tmdb_api_key",
        "tvdb_api_key",
        "fanart_api_key",
        "omdb_api_key",
        "tautulli_api_key",
        "llm_api_key",
        "webhook_secret",
        "mcp_api_key",
        "mcp_full_api_key",
    )
    for field in secret_fields:
        if _file_field_explicitly_set(file_data, field):
            sources[field] = "file"
            continue
        env_key = FIELD_TO_ENV.get(field, "")
        if env_key in os.environ and str(os.environ[env_key]).strip():
            sources[field] = "env"
        else:
            sources[field] = ""
    return sources


def save_settings(data_dir: Path, settings: Settings) -> Path:
    path = data_dir / "settings.json"
    settings.save(path)
    return path
