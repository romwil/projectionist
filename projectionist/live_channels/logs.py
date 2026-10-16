"""Live has no broadcast-engine log stream."""

from __future__ import annotations

from typing import Any, Dict


def fetch_tunarr_logs(
    settings: Any,
    *,
    lines: int = 200,
) -> Dict[str, Any]:
    del settings
    limit = max(1, min(int(lines or 200), 2000))
    return {
        "ok": False,
        "source": "",
        "lines": limit,
        "text": "",
        "message": "Live channels do not keep a separate broadcast log.",
        "errors": [],
    }
