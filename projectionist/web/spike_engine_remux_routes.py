"""Temporary owner-only fMP4 HLS remux spike (Lane A). Do not merge to main.

Serves a pre-built remux package from ``SPIKE_ENGINE_REMUX_DIR`` (default:
``tmp/spike-engine-remux`` under the repo / cwd). Owner creates a path-token
session; playlist and segment fetches use that token in the URL so Safari /
hls.js / AVPlayer do not need an Authorization header.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import secrets
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from projectionist.web.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["spike-engine-remux"])

# Unguessable path tokens → created_at monotonic unused; spike is ephemeral.
_SESSIONS: Dict[str, float] = {}

_PLAYER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Spike: engine remux</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 1.5rem; background: #111; color: #eee; }
    video { width: min(960px, 100%); background: #000; }
    code { background: #222; padding: 0.1em 0.35em; }
    #log { white-space: pre-wrap; font-size: 12px; opacity: 0.85; }
  </style>
</head>
<body>
  <h1>Spike remux player</h1>
  <p>Master: <code id="url"></code></p>
  <p>Path: <code id="path"></code></p>
  <video id="v" controls crossorigin="anonymous"></video>
  <pre id="log"></pre>
  <!-- External script: CSP default-src 'self' blocks inline JS. -->
  <script src="vendor/player.js"></script>
</body>
</html>
"""


def _package_root() -> Path:
    raw = (os.environ.get("SPIKE_ENGINE_REMUX_DIR") or "").strip()
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        root = (Path.cwd() / "tmp" / "spike-engine-remux").resolve()
    return root


def _resolve_under_package(rel: str) -> Path:
    root = _package_root()
    if not root.is_dir():
        raise HTTPException(status_code=503, detail=f"Spike package missing: {root}")
    # Normalize and reject traversal.
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid path") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


def _require_token(token: str) -> None:
    if token not in _SESSIONS:
        raise HTTPException(status_code=404, detail="Unknown or expired spike session")


def register_spike_engine_remux_routes(app) -> None:
    """Register only when ``SPIKE_ENGINE_REMUX=1`` (throwaway spike)."""
    if os.environ.get("SPIKE_ENGINE_REMUX", "").strip() not in {"1", "true", "yes", "on"}:
        return

    @router.post("/api/spike/engine-remux/session")
    def open_session(user=Depends(require_role("owner"))) -> JSONResponse:
        del user
        root = _package_root()
        if not (root / "master.m3u8").is_file():
            raise HTTPException(
                status_code=503,
                detail=f"master.m3u8 not found under {root}",
            )
        token = secrets.token_urlsafe(24)
        _SESSIONS[token] = 1.0
        base = f"/api/spike/engine-remux/{token}"
        logger.info("spike engine-remux session opened token=%s… root=%s", token[:8], root)
        return JSONResponse(
            {
                "token": token,
                "master_url": f"{base}/master.m3u8",
                "player_url": f"{base}/player",
                "package_root": str(root),
                "auth": "owner to create session; path token for media (no Authorization header)",
            }
        )

    @router.get("/api/spike/engine-remux/{token}/player", response_class=HTMLResponse)
    def player(token: str) -> HTMLResponse:
        _require_token(token)
        # Spike-only: relax CSP so the inline probe script + same-origin hls.js can run.
        return HTMLResponse(
            _PLAYER_HTML,
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline'; "
                    "media-src 'self' blob:; "
                    "connect-src 'self'; "
                    "worker-src 'self' blob:; "
                    "img-src 'self' data:; "
                    "frame-ancestors 'none'"
                )
            },
        )

    @router.get("/api/spike/engine-remux/{token}/{asset_path:path}")
    def media_asset(token: str, asset_path: str) -> Response:
        _require_token(token)
        path = _resolve_under_package(asset_path)
        media_type, _ = mimetypes.guess_type(str(path))
        if path.suffix == ".m3u8":
            media_type = "application/vnd.apple.mpegurl"
        elif path.suffix == ".m4s":
            media_type = "video/iso.segment"
        elif path.suffix == ".vtt":
            media_type = "text/vtt"
        elif path.suffix == ".mp4":
            media_type = media_type or "video/mp4"
        return FileResponse(
            path,
            media_type=media_type or "application/octet-stream",
            filename=path.name,
        )

    app.include_router(router)
    logger.warning(
        "SPIKE_ENGINE_REMUX enabled — temporary owner-only remux routes are live (%s)",
        _package_root(),
    )
