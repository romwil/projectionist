"""Telemetry ingestion for CuratorX interaction events.

Captures lightweight metadata (never raw message text) for taste analysis
and system observability.  All writes are non-blocking fire-and-forget so
they never slow down the request path.
"""

from projectionist.telemetry.ingestion import TelemetryIngester
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
    "PURPOSE_CHAT",
    "PURPOSE_CHAT_TOOL",
    "PURPOSE_WRAP_UP",
    "PURPOSE_LIBRARY_SUMMARY",
    "PURPOSE_LOGLINE",
    "PURPOSE_EMBED",
    "PURPOSE_PERSONA_CONSULT",
]
