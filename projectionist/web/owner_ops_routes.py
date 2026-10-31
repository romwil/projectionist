"""Owner-only Admin ops routes: Overview rollup, checklist marks, Monday pass, security audit."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from projectionist.web.auth import require_role
from projectionist.web.owner_ops import (
    MONDAY_COMPLETE_ITEM,
    MONDAY_REOPENED_ITEM,
    MONDAY_STEP_IDS,
    SCOPE_MONDAY,
    SCOPE_SETUP,
    build_monday_pass,
    build_owner_ops_overview,
    build_secrets_health,
    build_setup_checklist,
    current_period,
    queue_warm_explore,
)

class ChecklistMarkPayload(BaseModel):
    status: Literal["pending", "skipped", "reviewed"]


def register_owner_ops_routes(app) -> None:
    import projectionist.web.app as app_mod

    router = APIRouter(tags=["owner-ops"])

    def _db():
        return app_mod._db()

    def _scheduler():
        return getattr(app.state, "idle_scheduler", None)

    @router.get("/api/admin/ops/overview")
    def owner_ops_overview(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        return build_owner_ops_overview(_db(), app_mod._settings(), app_mod.DATA_DIR, _scheduler())

    @router.put("/api/admin/ops/checklist/{scope}/{item_id}")
    def set_checklist_mark(
        scope: str,
        item_id: str,
        payload: ChecklistMarkPayload,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        db = _db()
        settings = app_mod._settings()
        if scope == SCOPE_SETUP:
            secrets = build_secrets_health(db, settings, app_mod.DATA_DIR)
            known = {item["id"] for item in build_setup_checklist(db, settings, secrets)["items"]}
            if item_id not in known:
                raise HTTPException(status_code=404, detail="Unknown checklist item")
            if payload.status == "reviewed":
                raise HTTPException(status_code=400, detail="Setup items are skipped or restored")
            if payload.status == "pending":
                db.clear_checklist_mark(SCOPE_SETUP, item_id)
            else:
                db.set_checklist_mark(SCOPE_SETUP, item_id, "skipped", user_id=str(user.id))
            return build_setup_checklist(db, settings, build_secrets_health(db, settings, app_mod.DATA_DIR))
        if scope == SCOPE_MONDAY:
            if item_id not in MONDAY_STEP_IDS:
                raise HTTPException(status_code=404, detail="Unknown Monday pass step")
            if payload.status == "skipped":
                raise HTTPException(status_code=400, detail="Monday steps are reviewed, not skipped")
            period = current_period()
            if payload.status == "pending":
                db.clear_checklist_mark(SCOPE_MONDAY, item_id, period=period)
                if db.list_checklist_marks(SCOPE_MONDAY, period=period).get(MONDAY_COMPLETE_ITEM):
                    db.set_checklist_mark(
                        SCOPE_MONDAY, MONDAY_REOPENED_ITEM, "reopened", period=period, user_id=str(user.id)
                    )
            else:
                db.set_checklist_mark(
                    SCOPE_MONDAY, item_id, "reviewed", period=period, user_id=str(user.id)
                )
            return build_monday_pass(db)
        raise HTTPException(status_code=404, detail="Unknown checklist")

    @router.post("/api/admin/ops/monday-pass/catch-up")
    async def monday_catch_up(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        queued = queue_warm_explore(scheduler)
        if not queued:
            raise HTTPException(status_code=409, detail="No Warm Explore tasks are available")
        db = _db()
        db.set_checklist_mark(
            SCOPE_MONDAY, "catchup", "done", period=current_period(), user_id=str(user.id)
        )
        return {"queued": queued, "monday": build_monday_pass(db)}

    @router.post("/api/admin/ops/monday-pass/complete")
    def monday_complete(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        db = _db()
        monday = build_monday_pass(db)
        if not monday["ready"]:
            raise HTTPException(status_code=409, detail="Finish or review every step first")
        db.set_checklist_mark(
            SCOPE_MONDAY,
            MONDAY_COMPLETE_ITEM,
            "done",
            period=monday["period"],
            user_id=str(user.id),
        )
        return build_monday_pass(db)

    @router.get("/api/admin/security-audit")
    def security_audit_log(
        event: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        db = _db()
        page = db.list_security_events(event=event, user_id=user_id, limit=limit, offset=offset)
        names: Dict[str, str] = {}
        try:
            for row in db.list_users(limit=500):
                names[str(row.get("id"))] = str(row.get("display_name") or row.get("username") or "")
        except Exception:  # noqa: BLE001
            names = {}
        return {**page, "limit": limit, "offset": offset, "user_names": names}

    app.include_router(router)
