"""Telemetry ingestion for CuratorX interaction events.

Captures lightweight metadata (never raw message text) for taste analysis
and system observability.  All writes are non-blocking fire-and-forget so
they never slow down the request path.
"""

from curatorx.telemetry.ingestion import TelemetryIngester

__all__ = ["TelemetryIngester"]
