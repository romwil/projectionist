"""Fetch recent Tunarr / broadcast-engine logs for the owner Live Channels panel."""

from __future__ import annotations

from typing import Any, Dict

from projectionist.connectors.tunarr import TunarrClient
from projectionist.live_channels.docker import (
    DEFAULT_CONTAINER_NAME,
    lifecycle_from_settings,
)


def fetch_tunarr_logs(
    settings: Any,
    *,
    lines: int = 200,
) -> Dict[str, Any]:
    """Return recent log text from Tunarr API, falling back to Docker logs.

    Soft-fails with ``ok=False`` and an owner-facing message when neither path
    works (no URL, Tunarr down, no docker.sock).
    """
    limit = max(1, min(int(lines or 200), 2000))
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""

    errors: list[str] = []

    if url:
        try:
            text = TunarrClient(url, timeout=20).fetch_debug_logs(line_limit=limit)
            return {
                "ok": True,
                "source": "tunarr_api",
                "lines": limit,
                "text": text,
                "message": "Recent Tunarr API logs.",
            }
        except Exception as error:  # noqa: BLE001
            errors.append(f"Tunarr API: {error}")

    try:
        lifecycle = lifecycle_from_settings(settings)
        if not lifecycle.available():
            errors.append(
                "Docker socket unavailable — mount the socket or set a reachable Tunarr URL."
            )
        else:
            text = lifecycle.container_logs(tail=limit)
            if text.strip():
                return {
                    "ok": True,
                    "source": "docker",
                    "lines": limit,
                    "text": text,
                    "message": f"Recent Docker logs from {lifecycle.container_name}.",
                }
            errors.append(
                f"Docker container {lifecycle.container_name} returned empty logs "
                "(is the broadcast engine running?)."
            )
    except Exception as error:  # noqa: BLE001
        errors.append(f"Docker: {error}")

    return {
        "ok": False,
        "source": "",
        "lines": limit,
        "text": "",
        "message": (
            "Could not load broadcast engine logs. "
            + ("; ".join(errors) if errors else "No Tunarr URL or Docker access.")
        )[:480],
        "errors": errors,
        "container_name": DEFAULT_CONTAINER_NAME,
    }
