"""LLM token/cost accounting helpers.

Persists call metadata (never prompt/completion text) for the owner Usage BI
explorer. Pricing is a small built-in table — unknown models keep token totals
without inventing a USD figure.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, Dict, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

PURPOSE_CHAT = "chat"
PURPOSE_CHAT_TOOL = "chat_tool"
PURPOSE_WRAP_UP = "wrap_up"
PURPOSE_LIBRARY_SUMMARY = "library_summary"
PURPOSE_LOGLINE = "logline"
PURPOSE_EMBED = "embed"
PURPOSE_PERSONA_CONSULT = "persona_consult"

VALID_PURPOSES = frozenset(
    {
        PURPOSE_CHAT,
        PURPOSE_CHAT_TOOL,
        PURPOSE_WRAP_UP,
        PURPOSE_LIBRARY_SUMMARY,
        PURPOSE_LOGLINE,
        PURPOSE_EMBED,
        PURPOSE_PERSONA_CONSULT,
    }
)

# Approximate USD per 1M tokens (input, output). Homelab / local models → None.
# Keep deliberately small; heuristics below fill common cheaper-tier nicknames.
_PRICE_PER_MTOK: Dict[str, Tuple[float, float]] = {
    # OpenAI chat
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    # OpenAI embeddings
    "text-embedding-3-small": (0.02, 0.02),
    "text-embedding-3-large": (0.13, 0.13),
    "text-embedding-ada-002": (0.10, 0.10),
    # Anthropic
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
    # Google / Groq / Mistral / DeepSeek (ballpark)
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "mistral-small-latest": (0.20, 0.60),
    "deepseek-chat": (0.14, 0.28),
}

_CHEAPER_HINTS = (
    (re.compile(r"haiku|mini|nano|flash|small|lite", re.I), "cheaper-tier"),
    (re.compile(r"sonnet|gpt-4o$|gpt-4\.1$|opus|o3$|o4$", re.I), "standard-tier"),
)

# Short TTL for identical deterministic owner jobs (logline stubs).
_JOB_CACHE_TTL_SECONDS = 6 * 3600


def parse_token_usage(payload: Any) -> Dict[str, Optional[int]]:
    """Normalize OpenAI / Anthropic usage blobs into prompt/completion/total."""
    usage: Any = payload
    if isinstance(payload, Mapping):
        usage = payload.get("usage") if "usage" in payload else payload
    if not isinstance(usage, Mapping):
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}

    prompt = _coalesce_int(usage.get("prompt_tokens"), usage.get("input_tokens"))
    completion = _coalesce_int(usage.get("completion_tokens"), usage.get("output_tokens"))
    total = _coalesce_int(usage.get("total_tokens"))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    elif total is None and prompt is not None and completion is None:
        total = prompt
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _coalesce_int(*values: Any) -> Optional[int]:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _lookup_price(model: str) -> Optional[Tuple[float, float]]:
    cleaned = str(model or "").strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in _PRICE_PER_MTOK:
        return _PRICE_PER_MTOK[lowered]
    # OpenRouter-style "vendor/model"
    if "/" in lowered:
        suffix = lowered.rsplit("/", 1)[-1]
        if suffix in _PRICE_PER_MTOK:
            return _PRICE_PER_MTOK[suffix]
    # Prefix match for dated snapshots (claude-3-5-haiku-…)
    for key, price in _PRICE_PER_MTOK.items():
        if lowered.startswith(key) or key.startswith(lowered):
            return price
    return None


def estimate_usd(
    model: str,
    *,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> Optional[float]:
    """Estimate USD cost from the built-in price table. Unknown model → None."""
    price = _lookup_price(model)
    if price is None:
        return None
    in_rate, out_rate = price
    prompt = int(prompt_tokens or 0)
    completion = int(completion_tokens or 0)
    if prompt == 0 and completion == 0 and total_tokens:
        # Embeddings / incomplete splits: charge total at the input rate.
        return round((int(total_tokens) / 1_000_000.0) * in_rate, 6)
    return round((prompt / 1_000_000.0) * in_rate + (completion / 1_000_000.0) * out_rate, 6)


def cheaper_tier_hint(model_id: str) -> Optional[str]:
    """Return a short hint label for model pickers (cheaper vs standard)."""
    cleaned = str(model_id or "").strip()
    if not cleaned:
        return None
    for pattern, label in _CHEAPER_HINTS:
        if pattern.search(cleaned):
            return label
    price = _lookup_price(cleaned)
    if price is None:
        return None
    # Cheap if blended input+output under ~$2 / 1M.
    if price[0] + price[1] <= 2.0:
        return "cheaper-tier"
    return "standard-tier"


def model_price_row(model_id: str) -> Dict[str, Any]:
    """Shape used by the Admin model catalog / picker."""
    price = _lookup_price(model_id)
    return {
        "id": model_id,
        "hint": cheaper_tier_hint(model_id),
        "usd_per_mtok_in": price[0] if price else None,
        "usd_per_mtok_out": price[1] if price else None,
    }


def content_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def job_cache_get(db: Any, *, kind: str, key_hash: str) -> Optional[str]:
    """Return cached job output when still within TTL, else None."""
    try:
        raw = db.get_sync_state(f"llm_cache:{kind}:{key_hash}")
    except Exception:
        return None
    if not raw:
        return None
    try:
        stored_at_s, _, value = raw.partition("|")
        stored_at = float(stored_at_s)
    except (TypeError, ValueError):
        return None
    if not value or (time.time() - stored_at) > _JOB_CACHE_TTL_SECONDS:
        return None
    return value


def job_cache_set(db: Any, *, kind: str, key_hash: str, value: str) -> None:
    try:
        db.set_sync_state(f"llm_cache:{kind}:{key_hash}", f"{time.time():.3f}|{value}")
    except Exception:
        logger.debug("LLM job cache write failed", exc_info=True)


def merge_stream_usage(
    acc: Dict[str, Optional[int]],
    chunk: Mapping[str, Any],
) -> Dict[str, Optional[int]]:
    """Fold usage from a stream chunk into an accumulator."""
    parsed = parse_token_usage(chunk)
    if all(v is None for v in parsed.values()):
        # Anthropic message_delta nests usage under the event, already handled
        # by parse when chunk itself is the usage mapping.
        nested = chunk.get("usage") if isinstance(chunk.get("usage"), Mapping) else None
        if nested is None:
            return acc
        parsed = parse_token_usage(nested)
    out = dict(acc)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        incoming = parsed.get(key)
        if incoming is None:
            continue
        prior = out.get(key)
        # Prefer the latest non-null; for Anthropic, input arrives early and
        # output later — take max so partials accumulate correctly.
        if prior is None:
            out[key] = incoming
        else:
            out[key] = max(int(prior), int(incoming)) if key != "total_tokens" else int(incoming)
    if out.get("total_tokens") is None:
        p, c = out.get("prompt_tokens"), out.get("completion_tokens")
        if p is not None and c is not None:
            out["total_tokens"] = int(p) + int(c)
    return out
