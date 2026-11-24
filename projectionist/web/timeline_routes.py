"""Timeline file fingerprint and dialogue import."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from projectionist.timeline.dialogue import import_dialogue
from projectionist.timeline.files import (
    TimelineError,
    list_timeline_files,
    record_timeline_file,
)
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["timeline"])


class TimelineFilePayload(BaseModel):
    rating_key: str = ""
    size: int = 0
    mtime_ns: int = 0
    duration_ms: int = 0


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _raise(error: TimelineError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _known_title(rating_key: str) -> None:
    row = _db().library_item_by_rating_key(rating_key)
    if row is None:
        raise HTTPException(status_code=404, detail="That title is not available.")


@router.post("/api/library/timeline/files")
def create_timeline_file(payload: TimelineFilePayload, user=Depends(get_current_user_dep)) -> dict:
    """Record size, modification time, and duration for one media file."""
    del user
    _known_title(payload.rating_key)
    try:
        return record_timeline_file(
            _db(),
            rating_key=payload.rating_key,
            size=payload.size,
            mtime_ns=payload.mtime_ns,
            duration_ms=payload.duration_ms,
        )
    except TimelineError as error:
        _raise(error)


@router.get("/api/library/timeline/files/{rating_key}")
def read_timeline_files(rating_key: str, user=Depends(get_current_user_dep)) -> dict:
    del user
    _known_title(rating_key)
    try:
        return list_timeline_files(_db(), rating_key)
    except TimelineError as error:
        _raise(error)


@router.post("/api/library/timeline/files/{file_id}/dialogue")
def import_timeline_dialogue(
    file_id: int,
    language: str = "en",
    user=Depends(get_current_user_dep),
) -> dict:
    """Copy the household subtitle cache onto the file. Returns a count."""
    del user
    from projectionist.library.subtitle_cache import cache_path, iso2
    from projectionist.sessions.captions import parse_cues

    with _db().connect() as conn:
        row = conn.execute(
            "SELECT rating_key FROM timeline_files WHERE id = ?",
            (file_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="That file is not available.")
    lang = iso2(language)
    if not lang or not lang.isalpha() or len(lang) > 8:
        raise HTTPException(status_code=400, detail="That language is not available.")
    path = cache_path(str(row["rating_key"]), lang)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="No captions are saved for that language.")
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise HTTPException(status_code=404, detail="No captions are saved for that language.") from error
    try:
        imported = import_dialogue(_db(), file_id=file_id, cues=parse_cues(raw[:2_000_000]))
    except TimelineError as error:
        _raise(error)
    return {"imported": imported, "language": lang, "file_id": file_id}


def register_timeline_routes(app) -> None:
    app.include_router(router)
