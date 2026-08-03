"""Admin Knowledge Operations dashboard APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends

from projectionist.facets.admin_summary import registry_admin_summary
from projectionist.library.query import compute_knowledge_coverage
from projectionist.web.auth import require_role

router = APIRouter(tags=["knowledge-ops"])

_db_factory: Optional[Callable[[], Any]] = None
_data_dir: Optional[Path] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("knowledge ops routes not registered")
    return _db_factory()


def _overlay_dir() -> Path:
    if _data_dir is None:
        raise RuntimeError("knowledge ops routes not registered")
    return _data_dir


def _parse_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _serialize_event(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["payload"] = _parse_payload(row.get("payload_json"))
    return out


@router.get("/api/admin/knowledge-ops/summary")
def knowledge_ops_summary(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Summary strip: pending, signal volume, approve/reject rates, funnel."""
    del user
    db = _db()
    summary = db.closed_loop_knowledge_ops_summary()
    summary["registry"] = registry_admin_summary(data_dir=_overlay_dir())
    summary["coverage"] = compute_knowledge_coverage(db)
    return summary


@router.get("/api/admin/knowledge-ops/funnel")
def knowledge_ops_funnel(
    min_hit_count: int = 3,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Funnel: observed → threshold → staged → approved/rejected."""
    del user
    return _db().closed_loop_funnel_stats(min_hit_count=max(1, int(min_hit_count)))


@router.get("/api/admin/knowledge-ops/taxonomy-registry")
def knowledge_ops_taxonomy_registry(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Facet registry + overlay counts for the Taxonomy tab."""
    del user
    db = _db()
    registry = registry_admin_summary(data_dir=_overlay_dir())
    top_facets = db.top_closed_loop_events(
        event_type="unmapped_token",
        entity_type="facet",
        limit=25,
    )
    return {
        "registry": registry,
        "top_unresolved_facets": [
            {
                "entity_key": row.get("entity_key"),
                "hit_count": int(row.get("hit_count") or 0),
                "priority_tier": row.get("priority_tier"),
                "payload": _parse_payload(row.get("payload_json")),
                "updated_at": row.get("updated_at"),
            }
            for row in top_facets
        ],
    }


@router.get("/api/admin/knowledge-ops/telemetry/trend")
def knowledge_ops_telemetry_trend(
    days: int = 30,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Daily closed-loop signal volume by event_type."""
    del user
    window = max(1, min(int(days or 30), 90))
    rows = _db().closed_loop_telemetry_trend(days=window)
    return {"days": window, "series": rows}


@router.get("/api/admin/knowledge-ops/telemetry/top-events")
def knowledge_ops_top_events(
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 20,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Top unresolved closed-loop events by hit count."""
    del user
    items = _db().top_closed_loop_events(
        event_type=event_type,
        entity_type=entity_type,
        limit=min(max(int(limit or 20), 1), 100),
    )
    return {"items": [_serialize_event(row) for row in items], "count": len(items)}


@router.get("/api/admin/knowledge-ops/staged-aggregates")
def knowledge_ops_staged_aggregates(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Staged augmentation counts by task/tier/status."""
    del user
    return _db().staged_augmentations_aggregates()


def register_knowledge_ops_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    data_dir: Path,
) -> None:
    global _db_factory, _data_dir
    _db_factory = db_factory
    _data_dir = Path(data_dir)
    app.include_router(router)
