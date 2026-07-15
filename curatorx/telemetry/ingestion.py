"""Non-blocking telemetry event ingestion.

Events are written to ``system_telemetry_stream`` in a daemon thread so
the calling request never blocks on the DB write.  The ingester respects a
``telemetry_enabled`` feature flag read from the system config table —
when disabled, events are silently dropped.

Privacy contract: callers MUST NOT pass raw message text.  Only metadata
(lengths, IDs, counts, durations) should appear in the payload.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Dict, Optional

from curatorx.library.db import Database

logger = logging.getLogger(__name__)

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
        self._emit(
            EVENT_CHAT_MESSAGE,
            {
                "session_id": session_id,
                "lens_id": lens_id,
                "message_length": message_length,
                "persona_id": persona_id,
                "user_id": user_id,
            },
            context_hash=lens_id,
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
