"""Authenticated watch-tracker summary and diagnostics routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, FastAPI, Query

from projectionist.library.db import Database
from projectionist.watch_tracker.store import (
    list_user_show_watch_summary,
    list_user_watch_summary,
    list_watch_evidence_diagnostics,
)
from projectionist.web.auth import get_current_user_dep, require_role


def register_watch_tracker_routes(
    app: FastAPI,
    *,
    db_factory: Callable[[], Database],
) -> None:
    router = APIRouter()

    @router.get("/api/watch-tracker/summary/{rating_key}")
    def title_summary(
        rating_key: str,
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        return list_user_watch_summary(
            db_factory(),
            user_id=str(user.id),
            rating_key=rating_key,
        )

    @router.get("/api/watch-tracker/shows/{rating_key}/summary")
    def show_summary(
        rating_key: str,
        user=Depends(get_current_user_dep),
    ) -> Dict[str, Any]:
        return list_user_show_watch_summary(
            db_factory(),
            user_id=str(user.id),
            rating_key=rating_key,
        )

    @router.get("/api/admin/watch-tracker/evidence")
    def evidence_diagnostics(
        user_id: Optional[str] = None,
        rating_key: Optional[str] = None,
        limit: int = Query(default=100, ge=1, le=200),
        user=Depends(require_role("owner")),
    ) -> Dict[str, Any]:
        del user
        return list_watch_evidence_diagnostics(
            db_factory(),
            user_id=user_id,
            rating_key=rating_key,
            limit=limit,
        )

    app.include_router(router)
