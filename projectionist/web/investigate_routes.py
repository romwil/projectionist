"""Episode investigation HTTP routes (placeholder).

Wave 0 stub so Wave 1 can own this module without colliding on app.py.
Registered via ``register_investigate_routes`` so app.py stays the composition
root — same pattern as ``live_channels_routes``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from projectionist.web.auth import require_role

router = APIRouter(tags=["investigate"])


@router.get("/api/admin/investigate/health")
def investigate_health(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Owner-only placeholder — investigation is not implemented yet."""
    del user
    return {"status": "ok", "available": False}


def register_investigate_routes(app) -> None:
    """Attach investigation routes to the FastAPI app."""
    app.include_router(router)
