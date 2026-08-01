"""Live provider model catalog for Admin Connections LLM picker.

OpenAI-compatible ``GET /models`` (and Ollama ``/api/tags`` when the base URL
looks local). Anthropic has no public list endpoint we rely on — fail soft to
pinned ``ANTHROPIC_MODEL_OPTIONS``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from projectionist.config_store import (
    ANTHROPIC_MODEL_OPTIONS,
    LLM_MODEL_DEFAULTS,
    Settings,
    resolve_llm_base_url,
)
from projectionist.telemetry.llm_usage import model_price_row

logger = logging.getLogger(__name__)

_CATALOG_TIMEOUT = 8.0


def _looks_like_ollama(base_url: str) -> bool:
    cleaned = (base_url or "").strip().lower()
    if not cleaned:
        return False
    if "11434" in cleaned:
        return True
    host = urlparse(cleaned if "://" in cleaned else f"http://{cleaned}").hostname or ""
    return host in {"localhost", "127.0.0.1", "ollama", "host.docker.internal"}


def _ollama_tags_url(base_url: str) -> str:
    """Map OpenAI-compat base (…/v1) to Ollama native /api/tags."""
    cleaned = base_url.rstrip("/")
    if cleaned.endswith("/v1"):
        cleaned = cleaned[: -len("/v1")]
    return f"{cleaned}/api/tags"


def _annotate(models: List[str]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    rows: List[Dict[str, Any]] = []
    for model_id in models:
        mid = str(model_id or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        rows.append(model_price_row(mid))
    # Prefer cheaper-tier first within the picker.
    rows.sort(key=lambda row: (0 if row.get("hint") == "cheaper-tier" else 1, row["id"]))
    return rows


async def _fetch_openai_models(base_url: str, api_key: str) -> List[str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=_CATALOG_TIMEOUT) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    ids: List[str] = []
    for row in data:
        if isinstance(row, dict) and row.get("id"):
            ids.append(str(row["id"]))
        elif isinstance(row, str):
            ids.append(row)
    return ids


async def _fetch_ollama_tags(base_url: str) -> List[str]:
    url = _ollama_tags_url(base_url)
    async with httpx.AsyncClient(timeout=_CATALOG_TIMEOUT) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    ids: List[str] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "").strip()
        if name:
            ids.append(name)
    return ids


async def fetch_provider_model_catalog(settings: Settings) -> Dict[str, Any]:
    """Return live (or pinned) models for the configured chat provider."""
    provider = str(settings.llm_provider or "openai").lower().strip()
    base_url = resolve_llm_base_url(provider, settings.llm_base_url)
    default_model = LLM_MODEL_DEFAULTS.get(provider, LLM_MODEL_DEFAULTS["openai"])
    result: Dict[str, Any] = {
        "provider": provider,
        "base_url": base_url,
        "source": "pinned",
        "models": [],
        "error": None,
        "default_model": default_model,
    }

    if provider == "anthropic":
        result["models"] = _annotate(list(ANTHROPIC_MODEL_OPTIONS))
        result["source"] = "pinned"
        result["note"] = "Anthropic does not expose a public /models list; showing pinned options."
        return result

    ids: List[str] = []
    source = "pinned"
    error: Optional[str] = None

    try:
        if provider == "ollama" or _looks_like_ollama(base_url):
            try:
                ids = await _fetch_ollama_tags(base_url)
                if ids:
                    source = "ollama_tags"
            except Exception as exc:  # noqa: BLE001
                logger.debug("Ollama tags fetch failed: %s", exc)
                error = f"Ollama tags unavailable: {exc}"
        if not ids:
            ids = await _fetch_openai_models(base_url, settings.llm_api_key or "")
            source = "openai_models"
            error = None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Provider model catalog fetch failed: %s", exc)
        error = str(exc)
        ids = []
        source = "pinned"

    if not ids:
        fallback = [default_model] if default_model else []
        result["models"] = _annotate(fallback)
        result["source"] = "pinned"
        result["error"] = error or "Model list unavailable; showing the configured default."
        return result

    result["models"] = _annotate(ids)
    result["source"] = source
    result["error"] = None
    return result
