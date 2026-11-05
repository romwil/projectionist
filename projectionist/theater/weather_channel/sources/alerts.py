"""NWS active alerts for a point (US only)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, fetch_json

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"

_SEVERITY_RANK = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3, "unknown": 4}


def alerts_url(latitude: float, longitude: float) -> str:
    return f"{NWS_ALERTS_URL}?point={latitude:.4f},{longitude:.4f}"


def is_warning(event: str) -> bool:
    return str(event or "").strip().lower().endswith("warning")


def _clean(text: Any, limit: int = 1800) -> str:
    value = " ".join(str(text or "").split())
    return value[:limit]


def format_alert_time(iso: str) -> str:
    """``2026-11-05T21:00:00-06:00`` → ``9 PM Thursday`` (in the alert's own offset)."""
    try:
        when = datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    hour = when.hour % 12 or 12
    minute = f":{when.minute:02d}" if when.minute else ""
    suffix = "AM" if when.hour < 12 else "PM"
    return f"{hour}{minute} {suffix} {when.strftime('%A')}"


def parse_alerts(body: Any) -> List[Dict[str, Any]]:
    features = body.get("features") if isinstance(body, dict) else None
    if not isinstance(features, list):
        return []
    out: List[Dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(props, dict):
            continue
        event = _clean(props.get("event"), 120)
        if not event:
            continue
        if str(props.get("status") or "Actual").lower() not in {"actual", ""}:
            continue
        ends = str(props.get("ends") or props.get("expires") or "")
        onset = str(props.get("onset") or props.get("effective") or "")
        area = _clean(props.get("areaDesc"), 400)
        out.append(
            {
                "id": str(props.get("id") or feature.get("id") or ""),
                "event": event,
                "severity": _clean(props.get("severity"), 20) or "Unknown",
                "urgency": _clean(props.get("urgency"), 20),
                "certainty": _clean(props.get("certainty"), 20),
                "area": area,
                "area_short": area.split(";")[0].strip(),
                "onset": onset,
                "ends": ends,
                "onset_label": format_alert_time(onset),
                "ends_label": format_alert_time(ends),
                "headline": _clean(props.get("headline"), 300),
                "description": _clean(props.get("description")),
                "instruction": _clean(props.get("instruction")),
                "sender": _clean(props.get("senderName"), 120),
                "is_warning": is_warning(event),
            }
        )
    return sort_alerts(out)


def sort_alerts(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Warnings first, then by severity."""
    return sorted(
        alerts,
        key=lambda a: (
            0 if a.get("is_warning") else 1,
            _SEVERITY_RANK.get(str(a.get("severity") or "").lower(), 4),
            str(a.get("onset") or ""),
        ),
    )


def alerts_fingerprint(alerts: List[Dict[str, Any]]) -> str:
    parts = [(a.get("id"), a.get("event"), a.get("ends"), a.get("severity")) for a in alerts]
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def fetch_alerts(latitude: float, longitude: float, *, fetch: Optional[Fetcher] = None) -> List[Dict[str, Any]]:
    body = fetch_json(fetch, alerts_url(latitude, longitude), headers={"Accept": "application/geo+json"})
    return parse_alerts(body)
