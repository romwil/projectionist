"""SPA HTML shell + public Vite assets.

Registered via ``register_spa_routes`` so app.py stays the composition root —
same pattern as ``live_channels_routes``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

router = APIRouter(tags=["spa"])

_frontend_dist: Path | None = None
_static_dir: Path | None = None


def _serve_index() -> HTMLResponse:
    index = (_frontend_dist or Path()) / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    fallback = (_static_dir or Path()) / "index.html"
    if fallback.exists():
        return HTMLResponse(fallback.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>CuratorX</h1><p>Build the frontend with <code>npm run build</code>.</p>")


def _frontend_public_file(*parts: str) -> Path | None:
    """Resolve a Vite public asset from dist (prod) or public/ (local pre-build).

    When both exist (common after generate-release-notes without a rebuild),
    prefer the newer file so About stays current during local development.
    """
    if _frontend_dist is None:
        return None
    candidates = [
        _frontend_dist.joinpath(*parts),
        _frontend_dist.parent.joinpath("public", *parts),
    ]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda item: item.stat().st_mtime)


@router.get("/", response_class=HTMLResponse)
@router.get("/chat", response_class=HTMLResponse)
@router.get("/search", response_class=HTMLResponse)
@router.get("/inbox", response_class=HTMLResponse)
@router.get("/my-journey", response_class=HTMLResponse)
@router.get("/setup", response_class=HTMLResponse)
@router.get("/join", response_class=HTMLResponse)
@router.get("/login", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _serve_index()


@router.get("/config", response_class=HTMLResponse)
def config_page() -> HTMLResponse:
    return _serve_index()


@router.get("/explore", response_class=HTMLResponse)
@router.get("/explore/tags", response_class=HTMLResponse)
@router.get("/explore/plot-lab", response_class=HTMLResponse)
@router.get("/explore/browse", response_class=HTMLResponse)
@router.get("/explore/engagement", response_class=HTMLResponse)
@router.get("/explore/section/{section_id}", response_class=HTMLResponse)
def explore_page(section_id: str = "") -> HTMLResponse:
    del section_id
    return _serve_index()


@router.get("/watchlist", response_class=HTMLResponse)
def watchlist_page() -> HTMLResponse:
    return _serve_index()


@router.get("/library", response_class=HTMLResponse)
@router.get("/library/saved", response_class=HTMLResponse)
@router.get("/library/saved/{page_id}", response_class=HTMLResponse)
@router.get("/library/shelves/{list_id}", response_class=HTMLResponse)
@router.get("/library/collections/{list_id}", response_class=HTMLResponse)
def library_hub_page(page_id: str = "", list_id: str = "") -> HTMLResponse:
    del page_id, list_id
    return _serve_index()


@router.get("/live", response_class=HTMLResponse)
@router.get("/live/watch", response_class=HTMLResponse)
@router.get("/live/popout", response_class=HTMLResponse)
def live_page() -> HTMLResponse:
    return _serve_index()


@router.get("/title/{media_type}/{item_id}", response_class=HTMLResponse)
def title_page(media_type: str, item_id: str) -> HTMLResponse:
    return _serve_index()


@router.get("/person/{tmdb_person_id}", response_class=HTMLResponse)
def person_page(tmdb_person_id: str) -> HTMLResponse:
    del tmdb_person_id
    return _serve_index()


@router.get("/tag/{tag_name}", response_class=HTMLResponse)
def tag_page(tag_name: str) -> HTMLResponse:
    del tag_name
    return _serve_index()


@router.get("/tour")
@router.get("/tour/")
def tour_page() -> RedirectResponse:
    """Guest tour is retired — cold hits must land on login, not JSON 404."""
    return RedirectResponse(url="/login", status_code=302)


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> HTMLResponse:
    return _serve_index()


@router.get("/about", response_class=HTMLResponse)
def about_page() -> HTMLResponse:
    return _serve_index()


@router.get("/year-in-review/{year}", response_class=HTMLResponse)
def year_in_review_page(year: str) -> HTMLResponse:
    del year
    return _serve_index()


@router.get("/help", response_class=HTMLResponse)
def help_page() -> HTMLResponse:
    return _serve_index()


@router.get("/release-notes.json")
def release_notes_json() -> FileResponse:
    """Serve release notes copied into dist (Docker) or public/ (local generate)."""
    path = _frontend_public_file("release-notes.json")
    if path is None:
        raise HTTPException(status_code=404, detail="Release notes not found")
    return FileResponse(
        path,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/favicon.svg")
def favicon_svg() -> FileResponse:
    path = _frontend_public_file("favicon.svg")
    if path is None:
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(path, media_type="image/svg+xml")


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/{section}", response_class=HTMLResponse)
def admin_page(section: str = "") -> HTMLResponse:
    del section
    return _serve_index()


@router.get("/settings", response_class=HTMLResponse)
@router.get("/settings/{section}", response_class=HTMLResponse)
def settings_page(section: str = "") -> HTMLResponse:
    del section
    return _serve_index()


def register_spa_routes(app, *, frontend_dist: Path, static_dir: Path) -> None:
    """Attach SPA HTML + public asset routes to the FastAPI app."""
    global _frontend_dist, _static_dir
    _frontend_dist = frontend_dist
    _static_dir = static_dir
    app.include_router(router)
