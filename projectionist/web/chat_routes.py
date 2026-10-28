"""Chat HTTP routes: threads, messages, feedback, SSE stream."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from projectionist.agent.curator import CuratorAgent, stream_agent
from projectionist.agent.providers import LLMProviderError
from projectionist.config_store import Settings, validate_llm_settings
from projectionist.library.db import DEFAULT_LENS_ID
from projectionist.models.schemas import ChatRequest, MessageFeedbackRequest, PreferenceSignal
from projectionist.preferences.store import remember_preference
from projectionist.web.auth import get_current_user_dep
from projectionist.web.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

_db_factory: Optional[Callable[[], Any]] = None
_settings_factory: Optional[Callable[[], Settings]] = None
_safe_error_detail_fn: Optional[Callable[..., str]] = None
_fastapi_app = None


def _db():
    if _db_factory is None:
        raise RuntimeError("chat routes not registered")
    return _db_factory()


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("chat routes not registered")
    return _settings_factory()


def _safe_error_detail(error: Exception, context: str = "") -> str:
    if _safe_error_detail_fn is None:
        raise RuntimeError("chat routes not registered")
    return _safe_error_detail_fn(error, context)


def _telemetry():
    from projectionist.telemetry import TelemetryIngester

    return TelemetryIngester(_db())


def _idle_scheduler():
    if _fastapi_app is None:
        return None
    return getattr(_fastapi_app.state, "idle_scheduler", None)


def _scoped_user_id(user) -> Optional[str]:
    """Return user.id when multi-user partitioning is active, else None."""
    if _settings().features.multi_user_enabled:
        return user.id
    return None


def _include_orphan_threads(user) -> bool:
    """Only owners may see/act on legacy NULL-owner (orphan) chat threads."""
    return _settings().features.multi_user_enabled and getattr(user, "role", None) == "owner"


def _resolve_lens_id(lens_id: Optional[str]) -> str:
    db = _db()
    resolved = (lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID).strip() or DEFAULT_LENS_ID
    if not db.get_lens(resolved):
        raise HTTPException(status_code=404, detail=f"Unknown lens_id: {resolved}")
    return resolved

class ThreadCreatePayload(BaseModel):
    thread_title: Optional[str] = None
    lens_id: Optional[str] = None
    context_hash: Optional[str] = None
    persona_id: Optional[str] = None


class ThreadUpdatePayload(BaseModel):
    thread_title: str = Field(min_length=1, max_length=200)


def _message_text_excerpt(blocks: List[Mapping[str, Any]], *, limit: int = 500) -> str:
    parts: List[str] = []
    for block in blocks:
        if str(block.get("type") or "") == "text":
            content = str(block.get("content") or "").strip()
            if content:
                parts.append(content)
    text = " ".join(parts).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


@router.post("/api/chat")
async def chat(request: Request, payload: ChatRequest, user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    enforce_rate_limit(request, bucket="chat", limit=30, window_seconds=60)
    scheduler = _idle_scheduler()
    if scheduler is not None:
        scheduler.record_activity()
    session_id = payload.session_id or uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    db = _db()
    scoped = _scoped_user_id(user)
    if scoped and payload.session_id:
        existing = db.get_chat_thread(
            session_id, user_id=scoped, include_orphans=_include_orphan_threads(user)
        )
        if existing is None and db.get_chat_thread(session_id) is not None:
            raise HTTPException(status_code=404, detail="Thread not found")
    persona_id = payload.persona_id
    db.ensure_chat_session(session_id, lens_id, user_id=scoped, persona_id=persona_id)
    if persona_id:
        db.set_thread_persona(session_id, persona_id)
    settings = _settings()
    config_error = validate_llm_settings(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)

    _telemetry().record_chat_message(
        session_id=session_id,
        lens_id=lens_id,
        message_length=len(payload.message),
        persona_id=persona_id,
        user_id=scoped,
    )

    try:
        return await CuratorAgent(
            db,
            settings,
            lens_id=lens_id,
            user_id=scoped,
            seerr_user_id=user.seerr_user_id,
            user_role=user.role,
            is_youth=bool(getattr(user, "is_youth", False)),
        ).run(session_id, payload.message)
    except LLMProviderError as error:
        raise HTTPException(
            status_code=502,
            detail=_safe_error_detail(error, "Chat request failed"),
        ) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=_safe_error_detail(error, "Chat request failed"),
        ) from error


@router.get("/api/chat/threads")
def list_chat_threads(user=Depends(get_current_user_dep)) -> List[Dict[str, Any]]:
    return _db().list_chat_threads(
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    )


@router.post("/api/chat/threads")
def create_chat_thread(
    payload: ThreadCreatePayload = ThreadCreatePayload(),
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    session_id = uuid.uuid4().hex
    lens_id = _resolve_lens_id(payload.lens_id)
    context_hash = (payload.context_hash or "general").strip() or "general"
    thread = _db().create_chat_thread(
        session_id,
        lens_id=lens_id,
        context_hash=context_hash,
        thread_title=payload.thread_title,
        user_id=_scoped_user_id(user),
        persona_id=payload.persona_id,
    )
    return {"session_id": session_id, **thread}


@router.get("/api/chat/threads/{session_id}/messages")
def get_chat_thread_messages(
    session_id: str,
    limit: int = 100,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(
        session_id,
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = db.chat_history(session_id, limit=limit)
    # Re-gate persisted title_cards for Youth (pre-fix threads often lack
    # content_rating and would otherwise leak over-ceiling posters on reopen).
    from projectionist.youth.scrub import scrub_youth_history_messages

    messages = scrub_youth_history_messages(messages, user=user, settings=_settings())
    return {"session_id": session_id, "messages": messages, "thread": thread}


@router.patch("/api/chat/threads/{session_id}")
def update_chat_thread(
    session_id: str,
    payload: ThreadUpdatePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if _db().get_chat_thread(
        session_id,
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    ) is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    try:
        return _db().update_thread_title(session_id, payload.thread_title)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=_safe_error_detail(error, "Thread not found"),
        ) from error


@router.delete("/api/chat/threads/{session_id}")
def delete_chat_thread(session_id: str, user=Depends(get_current_user_dep)) -> Dict[str, bool]:
    if not _db().delete_chat_thread(
        session_id,
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    ):
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": True}


@router.post("/api/chat/messages/{message_id}/feedback")
def submit_message_feedback(
    message_id: str,
    payload: MessageFeedbackRequest,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(
        payload.session_id,
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    row = db.get_chat_message(message_id)
    if not row or str(row["session_id"]) != payload.session_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if str(row["role"]) != "assistant":
        raise HTTPException(status_code=400, detail="Feedback is only supported on assistant messages")

    if payload.feedback is None:
        deleted = db.delete_message_feedback(message_id, user_id=user.id)
        return {"saved": False, "deleted": deleted, "feedback": None}

    _telemetry().record_chat_feedback(
        message_id=message_id,
        feedback_type=payload.feedback,
        session_id=payload.session_id,
        user_id=user.id,
    )

    blocks = json.loads(str(row["blocks_json"]))
    excerpt = _message_text_excerpt(blocks)
    signal_type = "positive" if payload.feedback == "helpful" else "negative"
    remember_preference(
        db,
        PreferenceSignal(
            signal_type=signal_type,
            text=excerpt or f"Curator response marked {payload.feedback}",
            lens_id=str(row["lens_id"]) if row["lens_id"] is not None else None,
        ),
    )
    saved = db.upsert_message_feedback(
        feedback_id=uuid.uuid4().hex,
        message_id=message_id,
        session_id=payload.session_id,
        user_id=user.id,
        feedback_type=payload.feedback,
        excerpt=excerpt,
    )
    return {"saved": True, "deleted": False, "feedback": saved}


@router.delete("/api/chat/messages/{message_id}/feedback")
def delete_message_feedback(
    message_id: str,
    session_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(
        session_id,
        user_id=_scoped_user_id(user),
        include_orphans=_include_orphan_threads(user),
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    row = db.get_chat_message(message_id)
    if not row or str(row["session_id"]) != session_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if str(row["role"]) != "assistant":
        raise HTTPException(status_code=400, detail="Feedback is only supported on assistant messages")
    deleted = db.delete_message_feedback(message_id, user_id=user.id)
    return {"saved": False, "deleted": deleted, "feedback": None}


@router.get("/api/chat/threads/{session_id}/feedback")
def list_thread_feedback(
    session_id: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    thread = db.get_chat_thread(session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    items = db.list_message_feedback(session_id, user_id=user.id)
    return {"session_id": session_id, "items": items}


@router.get("/api/chat/stream")
async def chat_stream_get_gone() -> None:
    """GET query-string stream is gone. Stub stays for one release, then delete."""
    raise HTTPException(
        status_code=410,
        detail="GET /api/chat/stream is gone. POST a JSON body to /api/chat/stream.",
    )


@router.post("/api/chat/stream")
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    user=Depends(get_current_user_dep),
) -> EventSourceResponse:
    """SSE endpoint for token-by-token chat streaming.

    Native EventSource cannot POST. Clients must use fetch + a stream reader
    and must not reconstruct EventSource after a dropped socket.

    Events emitted:

    - ``event: token``       — ``{"content": "word"}``
    - ``event: tool_call``   — ``{"name": "search_library", "status": "start|complete", "args"?, "summary"?}``
    - ``event: done``        — final message payload (same shape as POST /api/chat)
    - ``event: error``       — ``{"error": "description"}``
    """
    enforce_rate_limit(request, bucket="chat", limit=30, window_seconds=60)
    scheduler = _idle_scheduler()
    if scheduler is not None:
        scheduler.record_activity()
    sid = payload.session_id or uuid.uuid4().hex
    resolved_lens = _resolve_lens_id(payload.lens_id)
    scoped = _scoped_user_id(user)

    async def event_generator():
        completed = False
        try:
            async for chunk in stream_agent(
                _db(),
                _settings(),
                sid,
                payload.message,
                lens_id=resolved_lens,
                user_id=scoped,
                seerr_user_id=user.seerr_user_id,
                user_role=user.role,
                persona_id=payload.persona_id,
                is_youth=bool(getattr(user, "is_youth", False)),
            ):
                data = json.loads(chunk)
                event_type = data.get("type", "message")

                if event_type in ("tool_start", "tool_result"):
                    status = "start" if event_type == "tool_start" else "complete"
                    event_payload = {"name": data.get("name"), "status": status}
                    if event_type == "tool_start" and data.get("args") is not None:
                        event_payload["args"] = data.get("args")
                    if event_type == "tool_result" and data.get("summary") is not None:
                        event_payload["summary"] = data.get("summary")
                    yield {
                        "event": "tool_call",
                        "data": json.dumps(event_payload),
                    }
                else:
                    if event_type == "done":
                        completed = True
                    yield {"event": event_type, "data": chunk.strip()}
        except Exception as error:  # noqa: BLE001
            safe_msg = _safe_error_detail(error, "Chat stream failed")
            yield {"event": "error", "data": json.dumps({"error": safe_msg})}
        finally:
            if not completed:
                from projectionist.agent.village import (
                    cancel_unpromised_persona_consults,
                )

                cancel_unpromised_persona_consults(sid)

    return EventSourceResponse(event_generator())



def register_chat_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    settings_factory: Callable[[], Settings],
    safe_error_detail: Callable[..., str],
) -> None:
    """Attach chat routes to the FastAPI app. Lifespan stays in app.py."""
    global _db_factory, _settings_factory, _safe_error_detail_fn, _fastapi_app
    _db_factory = db_factory
    _settings_factory = settings_factory
    _safe_error_detail_fn = safe_error_detail
    _fastapi_app = app
    app.include_router(router)
