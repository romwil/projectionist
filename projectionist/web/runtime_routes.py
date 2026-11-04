"""Owner-only runtime and pulse routes, plus the request-timing middleware.

``GET /api/admin/runtime`` (PERF-001) and ``GET /api/admin/pulse`` (GRO-018)
read on-box state only. Members get 403 in household mode.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends

from projectionist.telemetry.ingestion import TelemetryIngester
from projectionist.web import runtime_metrics
from projectionist.web.auth import require_role
from projectionist.web.household_pulse import build_household_pulse


class RequestTimingMiddleware:
    """Plain ASGI timer (not ``BaseHTTPMiddleware``, which serializes concurrent requests)."""

    def __init__(self, app: Any, db_factory: Callable[[], Any]) -> None:
        self.app = app
        self.db_factory = db_factory

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        group = runtime_metrics.request_group(scope.get("path", "")) if scope.get("type") == "http" else None
        if group is None:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            runtime_metrics.RESERVOIR.record(group, (time.perf_counter() - started) * 1000.0)
            runtime_metrics.maybe_log_runtime(self.db_factory)


def register_runtime_routes(app) -> None:
    import projectionist.web.app as app_mod

    router = APIRouter(tags=["owner-ops"])

    app.add_middleware(RequestTimingMiddleware, db_factory=app_mod._db)

    @router.get("/api/admin/runtime")
    def admin_runtime(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        del user
        return runtime_metrics.runtime_snapshot(app_mod._db())

    @router.get("/api/admin/pulse")
    def admin_pulse(user=Depends(require_role("owner"))) -> Dict[str, Any]:
        db = app_mod._db()
        pulse = build_household_pulse(db)
        TelemetryIngester(db).record_owner_pulse_view(user_id=getattr(user, "id", None))
        return pulse

    app.include_router(router)
