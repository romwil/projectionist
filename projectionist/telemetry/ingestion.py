"""Non-blocking telemetry event ingestion.

Two surfaces share this module:

1. **Interaction stream** — ``TelemetryIngester`` writes ``system_telemetry_stream``
   on a daemon thread (chat/playback/LLM BI). Respects ``telemetry_enabled``.
2. **Closed-loop augmentation** — ``schedule_closed_loop_event`` /
   ``upsert_closed_loop_event`` write the unified ``telemetry_events`` table
   via ``asyncio.to_thread`` (daemon-thread fallback). Never blocks the request
   path. Independent of the interaction-stream feature flag.

Privacy contract: callers MUST NOT pass raw message text or secrets. Only
metadata (lengths, IDs, counts, durations, scrubbed context) should appear
in payloads. Credential-like keys are stripped before persistence; logs never
print secrets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from typing import Any, Dict, Mapping, Optional

from projectionist.library.db import Database

logger = logging.getLogger(__name__)

# Keys that must never land in closed-loop payloads or logs.
_SECRET_PAYLOAD_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "api_token",
        "authorization",
        "plex_token",
        "credential",
        "credentials",
        "private_key",
        "client_secret",
    }
)
_MAX_ENTITY_KEY_LEN = 512
_MAX_PAYLOAD_CHARS = 8_192

# Canonical event classes — keep in sync with the telemetry API docs.
EVENT_CHAT_MESSAGE = "chat_message"
EVENT_CHAT_FEEDBACK = "chat_feedback"
EVENT_PREFERENCE_SIGNAL = "preference_signal"
EVENT_REVIEW_SAVED = "review_saved"
EVENT_PLAYBACK_EVENT = "playback_event"
EVENT_TOOL_INVOCATION = "tool_invocation"


class TelemetryIngester:
    """Fire-and-forget writer for the ``system_telemetry_stream`` table.

    All public ``record_*`` methods return immediately; the actual DB insert
    happens on a background daemon thread.  If the write fails it is logged
    and silently dropped — telemetry must never crash the request path.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def _is_enabled(self) -> bool:
        """Check the ``telemetry_enabled`` system config flag (default: true)."""
        try:
            value = self._db.get_config("telemetry_enabled")
            if value is None:
                return True
            return str(value).strip().lower() not in ("0", "false", "no", "off")
        except Exception:
            return True

    def _emit(
        self,
        event_class: str,
        payload: Dict[str, Any],
        *,
        media_node_id: Optional[str] = None,
        context_hash: Optional[str] = None,
    ) -> None:
        """Schedule a background write.  Returns immediately."""
        if not self._is_enabled():
            return

        event_id = uuid.uuid4().hex
        payload_json = json.dumps(payload, default=str, separators=(",", ":"))

        def _write() -> None:
            try:
                self._db.insert_telemetry_event(
                    event_id=event_id,
                    event_class=event_class,
                    payload_json=payload_json,
                    media_node_id=media_node_id,
                    associated_context_hash=context_hash,
                )
            except Exception:
                logger.debug("Telemetry write failed for %s", event_class, exc_info=True)

        thread = threading.Thread(target=_write, daemon=True, name=f"telemetry-{event_class}")
        thread.start()

    # --- Public recording helpers ---

    def record_chat_message(
        self,
        *,
        session_id: str,
        lens_id: Optional[str] = None,
        message_length: int,
        persona_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        # Do not pass lens_id as associated_context_hash — that column FKs
        # derived_contexts.context_hash (default seed is "general"), and FK
        # enforcement rejects lens ids like "default".
        self._emit(
            EVENT_CHAT_MESSAGE,
            {
                "session_id": session_id,
                "lens_id": lens_id,
                "message_length": message_length,
                "persona_id": persona_id,
                "user_id": user_id,
            },
        )

    def record_chat_feedback(
        self,
        *,
        message_id: str,
        feedback_type: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        self._emit(
            EVENT_CHAT_FEEDBACK,
            {
                "message_id": message_id,
                "feedback_type": feedback_type,
                "session_id": session_id,
                "user_id": user_id,
            },
        )

    def record_preference_signal(
        self,
        *,
        signal_type: str,
        media_references: Optional[list] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self._emit(
            EVENT_PREFERENCE_SIGNAL,
            {
                "signal_type": signal_type,
                "media_reference_count": len(media_references or []),
                "user_id": user_id,
            },
        )

    def record_review_saved(
        self,
        *,
        rating_key: Optional[str] = None,
        stars: int,
        prompted_by: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self._emit(
            EVENT_REVIEW_SAVED,
            {
                "rating_key": rating_key,
                "stars": stars,
                "prompted_by": prompted_by,
                "user_id": user_id,
            },
            media_node_id=rating_key,
        )

    def record_playback_event(
        self,
        *,
        event: str,
        rating_key: str,
        completion_pct: Optional[float] = None,
        media_type: Optional[str] = None,
    ) -> None:
        self._emit(
            EVENT_PLAYBACK_EVENT,
            {
                "event": event,
                "rating_key": rating_key,
                "completion_pct": completion_pct,
                "media_type": media_type,
            },
            media_node_id=rating_key,
        )

    def record_tool_invocation(
        self,
        *,
        tool_name: str,
        duration_ms: Optional[int] = None,
        result_count: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._emit(
            EVENT_TOOL_INVOCATION,
            {
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "result_count": result_count,
                "session_id": session_id,
            },
        )

    def record_llm_usage(
        self,
        *,
        purpose: str,
        model: str = "",
        provider: str = "",
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        latency_ms: Optional[int] = None,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist one LLM call into ``llm_usage`` (fire-and-forget).

        Also mirrors a lightweight ``llm_usage`` event into the telemetry stream
        so existing summary APIs can see call volume without reading the BI table.
        """
        from projectionist.telemetry.llm_usage import (
            VALID_PURPOSES,
            estimate_usd,
            parse_token_usage,
        )

        cleaned_purpose = str(purpose or "").strip() or "chat"
        if cleaned_purpose not in VALID_PURPOSES:
            cleaned_purpose = "chat"

        # Allow callers to pass a raw provider usage blob via meta["usage"].
        if prompt_tokens is None and completion_tokens is None and isinstance(meta, dict):
            parsed = parse_token_usage(meta.get("usage") or meta)
            prompt_tokens = parsed.get("prompt_tokens")
            completion_tokens = parsed.get("completion_tokens")
            total_tokens = total_tokens if total_tokens is not None else parsed.get("total_tokens")

        estimated = estimate_usd(
            model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        event_id = uuid.uuid4().hex
        safe_meta = {
            key: value
            for key, value in (meta or {}).items()
            if key not in {"prompt", "messages", "content", "text", "usage"}
        }

        def _write() -> None:
            try:
                self._db.insert_llm_usage(
                    usage_id=event_id,
                    purpose=cleaned_purpose,
                    model=str(model or ""),
                    provider=str(provider or ""),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    estimated_usd=estimated,
                    persona_id=persona_id,
                    session_id=session_id,
                    user_id=user_id,
                    meta_json=json.dumps(safe_meta, default=str, separators=(",", ":")),
                )
            except Exception:
                logger.debug("LLM usage write failed for %s", cleaned_purpose, exc_info=True)

        if self._is_enabled():
            thread = threading.Thread(target=_write, daemon=True, name="telemetry-llm_usage")
            thread.start()
            self._emit(
                "llm_usage",
                {
                    "purpose": cleaned_purpose,
                    "model": str(model or ""),
                    "provider": str(provider or ""),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "latency_ms": latency_ms,
                    "estimated_usd": estimated,
                    "persona_id": persona_id,
                    "session_id": session_id,
                    "user_id": user_id,
                },
            )
        else:
            # Usage BI is owner ops data — still persist even when interaction
            # telemetry is muted, so cost visibility is not silently lost.
            thread = threading.Thread(target=_write, daemon=True, name="telemetry-llm_usage")
            thread.start()


# ---------------------------------------------------------------------------
# Closed-loop augmentation telemetry (table: telemetry_events)
# ---------------------------------------------------------------------------


def scrub_closed_loop_payload(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a JSON-safe payload with credential-like keys removed."""
    if not payload:
        return {}
    cleaned: Dict[str, Any] = {}
    for key, value in dict(payload).items():
        key_l = str(key).strip().lower()
        if key_l in _SECRET_PAYLOAD_KEYS or key_l.endswith("_token") or key_l.endswith("_secret"):
            continue
        if key_l in {"prompt", "messages", "content", "text", "body"}:
            continue
        cleaned[str(key)] = value
    return cleaned


def _normalize_entity_key(entity_key: str) -> str:
    key = str(entity_key or "").strip()
    if len(key) > _MAX_ENTITY_KEY_LEN:
        key = key[:_MAX_ENTITY_KEY_LEN]
    return key


def upsert_closed_loop_event_sync(
    db: Database,
    *,
    event_type: str,
    priority_tier: str,
    entity_type: str,
    entity_key: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> None:
    """Synchronous upsert into ``telemetry_events`` (safe for ``asyncio.to_thread``)."""
    key = _normalize_entity_key(entity_key)
    if not key:
        return
    scrubbed = scrub_closed_loop_payload(payload)
    payload_json = json.dumps(scrubbed, default=str, separators=(",", ":"))
    if len(payload_json) > _MAX_PAYLOAD_CHARS:
        payload_json = json.dumps(
            {"_truncated": True, "keys": sorted(scrubbed.keys())[:40]},
            separators=(",", ":"),
        )
    db.upsert_closed_loop_event(
        event_type=str(event_type or "").strip() or "unknown",
        priority_tier=str(priority_tier or "P3").strip().upper() or "P3",
        entity_type=str(entity_type or "").strip() or "unknown",
        entity_key=key,
        payload_json=payload_json,
    )


async def upsert_closed_loop_event(
    db: Database,
    *,
    event_type: str,
    priority_tier: str,
    entity_type: str,
    entity_key: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> None:
    """Awaitable upsert that never blocks the event loop on SQLite I/O."""
    await asyncio.to_thread(
        upsert_closed_loop_event_sync,
        db,
        event_type=event_type,
        priority_tier=priority_tier,
        entity_type=entity_type,
        entity_key=entity_key,
        payload=payload,
    )


def schedule_closed_loop_event(
    db: Database,
    *,
    event_type: str,
    priority_tier: str,
    entity_type: str,
    entity_key: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> None:
    """Fire-and-forget closed-loop upsert; returns immediately.

    Prefer ``asyncio.to_thread`` when a running loop exists; fall back to a
    daemon thread so sync call sites (and tests without a loop) stay non-blocking.
    Write failures are logged without payload contents and never raised.
    """

    def _safe_write() -> None:
        try:
            upsert_closed_loop_event_sync(
                db,
                event_type=event_type,
                priority_tier=priority_tier,
                entity_type=entity_type,
                entity_key=entity_key,
                payload=payload,
            )
        except Exception:
            logger.debug(
                "Closed-loop telemetry write failed for type=%s entity=%s",
                event_type,
                entity_type,
                exc_info=True,
            )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        thread = threading.Thread(
            target=_safe_write,
            daemon=True,
            name=f"closed-loop-{event_type}",
        )
        thread.start()
        return

    async def _runner() -> None:
        try:
            await asyncio.to_thread(_safe_write)
        except Exception:
            logger.debug(
                "Closed-loop telemetry schedule failed for type=%s entity=%s",
                event_type,
                entity_type,
                exc_info=True,
            )

    try:
        loop.create_task(_runner(), name=f"closed-loop-{event_type}")
    except TypeError:
        # Python <3.11: create_task has no name=
        loop.create_task(_runner())
