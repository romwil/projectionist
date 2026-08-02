"""Admin closed-loop staged augmentation review (Phase B facet promote)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.facets.overlay import promote_facet_alias_to_overlay
from projectionist.web.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["augmentations"])

_db_factory: Optional[Callable[[], Any]] = None
_data_dir: Optional[Path] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("augmentation routes not registered")
    return _db_factory()


def _overlay_dir() -> Path:
    if _data_dir is None:
        raise RuntimeError("augmentation routes not registered")
    return _data_dir


class ApproveStagedPayload(BaseModel):
    """Owner mapping overrides for facet alias promote."""

    concept_id: Optional[str] = Field(default=None, max_length=120)
    canonical_name: Optional[str] = Field(default=None, max_length=120)


def _parse_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("candidate_data_json")
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _serialize_staged(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["candidate"] = _parse_candidate(row)
    return out


@router.get("/api/admin/staged-augmentations")
def list_staged_augmentations_endpoint(
    status: Optional[str] = "pending",
    task_name: Optional[str] = None,
    limit: int = 100,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner-only: list staged closed-loop candidates (facet taxonomy first)."""
    del user
    cleaned_status = status
    if status is not None and str(status).strip().lower() in {"", "all", "*"}:
        cleaned_status = None
    items = _db().list_staged_augmentations(
        status=cleaned_status,
        task_name=task_name,
        limit=min(max(int(limit or 100), 1), 200),
    )
    return {"items": [_serialize_staged(row) for row in items], "count": len(items)}


@router.post("/api/admin/staged-augmentations/{row_id}/approve")
def approve_staged_augmentation(
    row_id: int,
    payload: Optional[ApproveStagedPayload] = None,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Approve a staged facet alias → write DATA_DIR taxonomy overlay (not seed)."""
    del user
    body = payload or ApproveStagedPayload()
    db = _db()
    row = db.get_staged_augmentation(int(row_id))
    if not row:
        raise HTTPException(status_code=404, detail="Staged augmentation not found")
    if str(row.get("status") or "") != "pending":
        raise HTTPException(status_code=409, detail=f"Already {row.get('status')}")

    if str(row.get("target_entity_type") or "") != "facet":
        raise HTTPException(
            status_code=400,
            detail="Only facet staged augmentations can be promoted in Phase B",
        )

    candidate = _parse_candidate(row)
    alias = str(candidate.get("alias") or row.get("target_entity_id") or "").strip()
    # Prefer explicit body overrides, then audit suggestions.
    concept_id = str(body.concept_id or candidate.get("suggested_concept_id") or "").strip()
    canonical_name = str(
        body.canonical_name or candidate.get("suggested_canonical_name") or ""
    ).strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Staged row is missing an alias token")
    if not concept_id and not canonical_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide concept_id or canonical_name to map this facet alias "
                "(audit did not suggest a unique concept)."
            ),
        )

    try:
        promote_result = promote_facet_alias_to_overlay(
            alias=alias,
            concept_id=concept_id or None,
            canonical_name=canonical_name or None,
            data_dir=_overlay_dir(),
            reload=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to write taxonomy overlay")
        raise HTTPException(status_code=500, detail="Could not write taxonomy overlay") from exc

    # Persist the mapping used at approve time for audit trail.
    candidate["promoted_concept_id"] = concept_id or None
    candidate["promoted_canonical_name"] = canonical_name or None
    candidate["overlay_path"] = promote_result.get("path")
    updated = db.update_staged_augmentation_status(
        int(row_id),
        status="approved",
        candidate_data_json=json.dumps(candidate, default=str, separators=(",", ":")),
    )
    return {
        "item": _serialize_staged(updated or row),
        "overlay_path": promote_result.get("path"),
        "promoted": {
            "alias": alias.casefold(),
            "concept_id": concept_id or None,
            "canonical_name": canonical_name or None,
        },
    }


@router.post("/api/admin/staged-augmentations/{row_id}/reject")
def reject_staged_augmentation(
    row_id: int,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Reject a staged candidate without writing an overlay."""
    del user
    db = _db()
    row = db.get_staged_augmentation(int(row_id))
    if not row:
        raise HTTPException(status_code=404, detail="Staged augmentation not found")
    if str(row.get("status") or "") != "pending":
        raise HTTPException(status_code=409, detail=f"Already {row.get('status')}")
    updated = db.update_staged_augmentation_status(int(row_id), status="rejected")
    return {"item": _serialize_staged(updated or row)}


def register_augmentation_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    data_dir: Path,
) -> None:
    global _db_factory, _data_dir
    _db_factory = db_factory
    _data_dir = Path(data_dir)
    app.include_router(router)
