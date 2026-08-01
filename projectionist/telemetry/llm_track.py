"""Helpers to record LLM provider calls with purpose + latency."""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

from projectionist.telemetry.ingestion import TelemetryIngester
from projectionist.telemetry.llm_usage import merge_stream_usage, parse_token_usage

logger = logging.getLogger(__name__)


def _provider_meta(provider: Any) -> Dict[str, str]:
    return {
        "model": str(getattr(provider, "model", "") or ""),
        "provider": type(provider).__name__.replace("Provider", "").lower(),
    }


def record_from_response(
    db: Any,
    *,
    purpose: str,
    provider: Any,
    response: Any = None,
    latency_ms: Optional[int] = None,
    persona_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    usage: Optional[Mapping[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort usage persist from a chat/embed response or raw usage blob."""
    try:
        tokens = parse_token_usage(usage or response or getattr(provider, "last_usage", None))
        info = _provider_meta(provider)
        model = ""
        if isinstance(response, Mapping) and response.get("model"):
            model = str(response.get("model") or "")
        TelemetryIngester(db).record_llm_usage(
            purpose=purpose,
            model=model or info["model"],
            provider=info["provider"],
            prompt_tokens=tokens.get("prompt_tokens"),
            completion_tokens=tokens.get("completion_tokens"),
            total_tokens=tokens.get("total_tokens"),
            latency_ms=latency_ms,
            persona_id=persona_id,
            session_id=session_id,
            user_id=user_id,
            meta=meta,
        )
    except Exception:
        logger.debug("Failed to record LLM usage (%s)", purpose, exc_info=True)


async def tracked_chat(
    db: Any,
    provider: Any,
    messages: List[Mapping[str, Any]],
    tools: Optional[List[Mapping[str, Any]]] = None,
    *,
    purpose: str,
    persona_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Mapping[str, Any]:
    """Call ``provider.chat`` and persist token usage."""
    t0 = time.time()
    response = await provider.chat(messages, tools=tools)
    latency_ms = int((time.time() - t0) * 1000)
    record_from_response(
        db,
        purpose=purpose,
        provider=provider,
        response=response,
        latency_ms=latency_ms,
        persona_id=persona_id,
        session_id=session_id,
        user_id=user_id,
        meta=meta,
    )
    return response


async def tracked_stream(
    db: Any,
    provider: Any,
    messages: List[Mapping[str, Any]],
    tools: Optional[List[Mapping[str, Any]]] = None,
    *,
    purpose: str,
    persona_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[Mapping[str, Any]]:
    """Yield stream chunks, then persist accumulated usage once the stream ends."""
    t0 = time.time()
    usage_acc: Dict[str, Optional[int]] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    saw_chunk = False
    failed = False
    try:
        async for chunk in provider.stream(messages, tools=tools):
            saw_chunk = True
            if isinstance(chunk, Mapping):
                usage_acc = merge_stream_usage(usage_acc, chunk)
            yield chunk
    except Exception:
        failed = True
        raise
    finally:
        # Skip empty failed streams so a buffered fallback is not double-counted
        # as a zero-token sibling row. Do not `return` here — that would swallow
        # the active exception from the `except` above.
        if not (failed and not saw_chunk):
            latency_ms = int((time.time() - t0) * 1000)
            last = getattr(provider, "last_usage", None)
            if isinstance(last, Mapping):
                usage_acc = merge_stream_usage(usage_acc, {"usage": last})
            record_from_response(
                db,
                purpose=purpose,
                provider=provider,
                latency_ms=latency_ms,
                persona_id=persona_id,
                session_id=session_id,
                user_id=user_id,
                usage=usage_acc,
                meta=meta,
            )
