"""Upcoming seasonal rail preview + owner veto (reuses holiday rail curation)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from projectionist.library.db import Database
from projectionist.library.feeds import preview_holiday_rail
from projectionist.library.holidays import upcoming_windows

DEFAULT_HORIZON_DAYS = 45
DEFAULT_RAIL_LIMIT = 8
MAX_RAILS = 8


def _vetoed_ids(curation: List[Dict[str, Any]]) -> List[int]:
    ids: List[int] = []
    for row in curation or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("curation") or "").strip().lower() != "exclude":
            continue
        try:
            ids.append(int(row.get("library_item_id") or row.get("id")))
        except (TypeError, ValueError):
            continue
    return ids


def preview_upcoming_rails(
    db: Database,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    limit_per_rail: int = DEFAULT_RAIL_LIMIT,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Preview the next holiday windows with titles the owner can veto."""
    horizon = max(1, min(int(horizon_days or DEFAULT_HORIZON_DAYS), 180))
    cap = max(1, min(int(limit_per_rail or DEFAULT_RAIL_LIMIT), 24))
    try:
        if today is None:
            schedule = db.list_holiday_schedule(horizon_days=horizon)
        else:
            observances = db.list_holiday_observances(include_disabled=False)
            schedule = upcoming_windows(observances, today, horizon_days=horizon)
    except Exception:  # noqa: BLE001
        schedule = []
    rails: List[Dict[str, Any]] = []
    for window in schedule or []:
        if len(rails) >= MAX_RAILS:
            break
        scope_id = str(window.get("id") or "").strip()
        if not scope_id:
            continue
        try:
            preview = preview_holiday_rail(db, scope_id, limit=cap)
        except KeyError:
            continue
        curation = list(preview.get("curation") or [])
        rails.append(
            {
                "scope_id": scope_id,
                "name": window.get("name") or preview.get("label"),
                "label": preview.get("label") or window.get("name"),
                "grounding_date": window.get("grounding_date") or preview.get("grounding_date"),
                "window_start": window.get("window_start"),
                "window_end": window.get("window_end"),
                "active_now": bool(window.get("active_now")),
                "days_until_grounding": window.get("days_until_grounding"),
                "schedule_publish": bool(window.get("schedule_publish", True)),
                "items": list(preview.get("items") or []),
                "curation": curation,
                "vetoed_ids": _vetoed_ids(curation),
                "match_count": preview.get("match_count") or 0,
                "note": preview.get("note"),
            }
        )
    return {
        "rails": rails,
        "horizon_days": horizon,
        "total": len(rails),
        "empty_reason": None if rails else "No seasonal window in the next few weeks.",
    }


def veto_rail_title(db: Database, scope_id: str, library_item_id: int) -> Dict[str, Any]:
    """Keep a title off an upcoming seasonal rail. Confirm-before-fleet: one title."""
    cleaned = str(scope_id or "").strip()
    if not cleaned:
        raise ValueError("Seasonal rail is required")
    title = db.set_holiday_rail_title(cleaned, int(library_item_id), curation="exclude")
    return {
        "ok": True,
        "scope_id": cleaned,
        "library_item_id": int(library_item_id),
        "curation": "exclude",
        "item": title,
        "vetoed_ids": _vetoed_ids(db.list_holiday_rail_titles(cleaned)),
    }


def restore_rail_title(db: Database, scope_id: str, library_item_id: int) -> Dict[str, Any]:
    """Undo a veto so the title can return to the rail."""
    cleaned = str(scope_id or "").strip()
    if not cleaned:
        raise ValueError("Seasonal rail is required")
    cleared = db.clear_holiday_rail_title(cleaned, int(library_item_id))
    return {
        "ok": bool(cleared),
        "scope_id": cleaned,
        "library_item_id": int(library_item_id),
        "vetoed_ids": _vetoed_ids(db.list_holiday_rail_titles(cleaned)),
    }
