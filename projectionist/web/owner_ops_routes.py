"""Owner-only Admin routes: Overview, checklists, Monday pass, security audit, logs,
scheduled tasks, telemetry, LLM usage and models, grooming undo.

New ``/api/admin/*`` routes go here (or in another ``*_routes.py`` module), not in ``app.py``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

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


class ScheduledTaskUpdatePayload(BaseModel):
    enabled: Optional[bool] = None
    run_interval_seconds: Optional[int] = Field(default=None, ge=60, le=2_592_000)
    items_per_cycle: Optional[int] = Field(default=None, ge=1, le=500)


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

    @router.get("/api/admin/grooming/actions")
    def list_grooming_actions(
        limit: int = 20,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """List recent reversible grooming actions (newest first) for the undo UI."""
        del user
        actions = _db().list_grooming_actions(limit=limit)
        return {"actions": actions, "count": len(actions)}


    @router.post("/api/admin/grooming/actions/{action_id}/undo")
    def undo_grooming_action(
        action_id: str,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Restore the index rows a destructive grooming action deleted.

        Only CuratorX index rows are restored; embeddings backfill on the next
        enrichment cycle. Plex media files were never touched by the delete.
        """
        del user
        db = _db()
        try:
            result = db.undo_grooming_action(action_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if result is None:
            raise HTTPException(status_code=404, detail="Grooming action not found")
        return {
            "undone": True,
            "restored": result.get("restored", 0),
            "action": {k: v for k, v in result.items() if k != "snapshot"},
        }


    @router.get("/api/admin/logs")
    def get_admin_logs(
        limit: int = 300,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        q: Optional[str] = None,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Return a filtered tail of the durable application log (owner only)."""
        del user
        from projectionist.web.log_viewer import read_log_tail

        try:
            return read_log_tail(limit=limit, min_level=level, logger_prefix=logger, q=q)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


    @router.get("/api/admin/logs/stream")
    async def stream_admin_logs(
        request: Request,
        after_offset: int = 0,
        level: Optional[str] = None,
        logger: Optional[str] = None,
        q: Optional[str] = None,
        user=Depends(require_role("owner")),
    ) -> EventSourceResponse:
        """SSE tail of new log lines after ``after_offset`` (owner only)."""
        del user
        from projectionist.logging_config import resolve_log_file_path
        from projectionist.web.log_viewer import (
            SENSITIVE_WARNING,
            iter_log_chunks,
            normalize_min_level,
            read_new_lines,
        )

        try:
            min_level = normalize_min_level(level)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        path = resolve_log_file_path()
        offset = max(0, int(after_offset or 0))

        async def event_generator():
            nonlocal offset
            yield {
                "event": "ready",
                "data": json.dumps(
                    {
                        "path": str(path),
                        "next_offset": offset,
                        "sensitive_warning": SENSITIVE_WARNING,
                    }
                ),
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    lines, offset = read_new_lines(
                        path,
                        after_offset=offset,
                        min_level=min_level,
                        logger_prefix=logger,
                        q=q,
                    )
                except OSError as error:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": f"Could not read log file: {error}"}),
                    }
                    break
                for chunk in iter_log_chunks(lines):
                    yield chunk
                await asyncio.sleep(1.0)

        return EventSourceResponse(event_generator())

    @router.get("/api/admin/scheduled-tasks")
    def list_scheduled_tasks(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        scheduler = _scheduler()
        if scheduler is None:
            return {"items": [], "idle": False, "running": None}
        return {
            "items": scheduler.get_task_states(),
            "idle": scheduler.is_idle(),
            "running": scheduler._busy_task_name(),
        }


    @router.post("/api/admin/scheduled-tasks/optimize-rates")
    def optimize_scheduled_task_rates(
        dry_run: bool = False,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Recompute safe batch/interval nudges for autotune-eligible tasks.

        Uses the same ``evaluate_autotune`` guards as post-run tuning: per-task
        min/max batch and interval caps, no disables, and no task starts. Pass
        ``dry_run=true`` to preview without writing.
        """
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        return scheduler.optimize_autotune_rates(dry_run=dry_run)

    @router.get("/api/admin/subtitles/backfill")
    def subtitle_backfill_status(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        """Done / remaining / last error for the subtitle backfill (from DB rows)."""
        del user
        from projectionist.scheduler.tasks import subtitle_enrichment

        scheduler = _scheduler()
        running = bool(scheduler is not None and subtitle_enrichment.backfill_running(scheduler))
        return subtitle_enrichment.backfill_status(_db(), app_mod._settings(), running=running)

    @router.post("/api/admin/subtitles/backfill")
    async def start_subtitle_backfill(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        """Start the server-side backfill as a manual run. A second confirm shows the running one."""
        from projectionist.scheduler.tasks import subtitle_enrichment

        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        return subtitle_enrichment.start_backfill(scheduler, requested_by=getattr(user, "id", None))

    @router.post("/api/admin/subtitles/backfill/stop")
    async def stop_subtitle_backfill(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        """Stop between titles. Finished titles stay cached."""
        del user
        from projectionist.scheduler.tasks import subtitle_enrichment

        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        return subtitle_enrichment.stop_backfill(scheduler)


    @router.put("/api/admin/scheduled-tasks/{name}")
    def update_scheduled_task(
        name: str,
        payload: ScheduledTaskUpdatePayload,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        updated = scheduler.update_task(
            name,
            enabled=payload.enabled,
            run_interval_seconds=payload.run_interval_seconds,
            items_per_cycle=payload.items_per_cycle,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
        return updated


    @router.post("/api/admin/scheduled-tasks/{name}/run")
    async def trigger_scheduled_task(
        name: str,
        wait: bool = False,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Trigger a scheduled task. Default is fire-and-forget for live monitoring.

        Pass ``wait=true`` to await completion and return the full task result.
        """
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        if wait:
            result = await scheduler.trigger_task(name)
        else:
            result = scheduler.trigger_task_background(name)
        if result.get("status") == "busy":
            raise HTTPException(status_code=409, detail=result.get("error") or "Task already running")
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return result


    @router.get("/api/admin/scheduled-tasks/{name}/log")
    def get_scheduled_task_log(
        name: str,
        after_seq: int = 0,
        limit: int = 200,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Poll buffered run events / progress lines for a scheduled task."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        payload = scheduler.get_task_run_log(name, after_seq=after_seq, limit=limit)
        if payload.get("error"):
            raise HTTPException(status_code=404, detail=payload["error"])
        return payload


    @router.get("/api/admin/scheduled-tasks/{name}/history")
    def get_scheduled_task_history(
        name: str,
        limit: int = 50,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Return durable run history for a task (survives restarts)."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        payload = scheduler.get_task_history(name, limit=limit)
        if payload.get("error"):
            raise HTTPException(status_code=404, detail=payload["error"])
        return payload


    @router.get("/api/admin/scheduled-tasks/{name}/rate")
    def get_scheduled_task_rate(
        name: str,
        lookback_hours: int = 72,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Return measured items/hour and duration percentiles from run history."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        payload = scheduler.get_task_rate(name, lookback_hours=lookback_hours)
        if payload.get("error"):
            raise HTTPException(status_code=404, detail=payload["error"])
        return payload


    @router.get("/api/admin/scheduled-tasks-log")
    def get_all_scheduled_task_logs(
        after_seq: int = 0,
        limit: int = 200,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Poll buffered run events across all scheduled tasks."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        return scheduler.get_task_run_log(None, after_seq=after_seq, limit=limit)


    @router.get("/api/admin/scheduled-tasks-history")
    def get_all_scheduled_task_history(
        limit: int = 100,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Return newest-first durable run history across all scheduled tasks."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        capped = max(1, min(int(limit or 100), 500))
        return scheduler.get_all_task_history(limit=capped)


    @router.post("/api/admin/scheduled-tasks/{name}/reset")
    def reset_scheduled_task_quarantine(
        name: str,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Clear quarantine state for a task, allowing it to run again."""
        del user
        scheduler = _scheduler()
        if scheduler is None:
            raise HTTPException(status_code=503, detail="Scheduler not available")
        result = scheduler.reset_quarantine(name)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Task '{name}' not found")
        return result


    @router.get("/api/admin/telemetry/summary")
    def telemetry_summary(
        hours: int = 24,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Owner-only: event counts by type for the given window."""
        del user
        windows = {}
        for window in (24, 168, 720):
            windows[f"{window}h"] = _db().telemetry_summary(hours=window)
        return {"windows": windows, "requested_hours": hours, "detail": _db().telemetry_summary(hours=hours)}


    @router.get("/api/admin/telemetry/events")
    def telemetry_events(
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Owner-only: recent telemetry events with pagination."""
        del user
        events = _db().telemetry_events(event_class=type, limit=min(limit, 200), offset=offset)
        return {"items": events, "count": len(events)}


    @router.get("/api/admin/llm/usage")
    def admin_llm_usage(
        days: int = 7,
        model: Optional[str] = None,
        purpose: Optional[str] = None,
        persona_id: Optional[str] = None,
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        """Owner-only LLM cost / usage BI aggregates for Admin → Usage."""
        del user
        return _db().llm_usage_summary(
            days=days,
            model=(model or None) or None,
            purpose=(purpose or None) or None,
            persona_id=(persona_id or None) or None,
        )


    @router.get("/api/admin/llm/models")
    async def admin_llm_models(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        """Owner-only live provider model catalog (fails soft to pinned options)."""
        del user
        from projectionist.agent.providers.catalog import fetch_provider_model_catalog

        return await fetch_provider_model_catalog(app_mod._settings())

    app.include_router(router)
