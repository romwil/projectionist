"""Telemetry ingestion for CuratorX interaction events.

Captures lightweight metadata (never raw message text) for taste analysis
and system observability.  All writes are non-blocking fire-and-forget so
they never slow down the request path.

Closed-loop augmentation helpers (``schedule_closed_loop_event`` /
``upsert_closed_loop_event``) write the unified ``telemetry_events`` table
used by ``BaseAugmentationTask`` — separate from the interaction stream.
"""

from projectionist.telemetry.demand import (
    EVENT_METADATA_DEMAND,
    schedule_metadata_demand,
)
from projectionist.telemetry.ingestion import (
    TelemetryIngester,
    schedule_closed_loop_event,
    scrub_closed_loop_payload,
    upsert_closed_loop_event,
    upsert_closed_loop_event_sync,
)
from projectionist.telemetry.llm_usage import (
    PURPOSE_CHAT,
    PURPOSE_CHAT_TOOL,
    PURPOSE_EMBED,
    PURPOSE_LIBRARY_SUMMARY,
    PURPOSE_LOGLINE,
    PURPOSE_PERSONA_CONSULT,
    PURPOSE_WRAP_UP,
)

__all__ = [
    "TelemetryIngester",
    "EVENT_METADATA_DEMAND",
    "schedule_closed_loop_event",
    "schedule_metadata_demand",
    "scrub_closed_loop_payload",
    "upsert_closed_loop_event",
    "upsert_closed_loop_event_sync",
    "PURPOSE_CHAT",
    "PURPOSE_CHAT_TOOL",
    "PURPOSE_WRAP_UP",
    "PURPOSE_LIBRARY_SUMMARY",
    "PURPOSE_LOGLINE",
    "PURPOSE_EMBED",
    "PURPOSE_PERSONA_CONSULT",
]
