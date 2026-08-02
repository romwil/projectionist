"""Curator agent orchestration."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

from projectionist.agent.providers import get_chat_provider
from projectionist.agent.tools import (
    UNTRUSTED_MEMORY_TOOLS,
    ToolRegistry,
    build_system_prompt,
    build_tool_definitions,
    wrap_untrusted_data,
)
from projectionist.config_store import Settings, uses_seerr_request_path
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.db_io import run_db
from projectionist.library.query import resolve_thread_ambient_context_label
from projectionist.models.schemas import TitleCard
from projectionist.privacy.schema import sanitize
from projectionist.telemetry import (
    PURPOSE_CHAT,
    PURPOSE_CHAT_TOOL,
    PURPOSE_WRAP_UP,
)
from projectionist.telemetry.llm_track import tracked_chat, tracked_stream

logger = logging.getLogger(__name__)

# Separates multi-round streamed narration so "…once!Let me…" never glues.
_STREAM_SEGMENT_SEP = "\n\n"


def join_assistant_text_segments(segments: List[str]) -> str:
    """Join multi-round assistant prose with blank lines (never concatenate bare)."""
    parts = [str(part or "").strip() for part in segments if str(part or "").strip()]
    return _STREAM_SEGMENT_SEP.join(parts)


def household_tool_summary(raw: Any, *, limit: int = 160) -> str:
    """Short, household-safe tool activity blurb — no raw JSON dumps or self-talk."""
    text = str(raw or "").strip()
    if not text:
        return ""
    lowered = text.casefold()
    if any(
        needle in lowered
        for needle in (
            "useless junk",
            "inventing ids",
            "wrong id",
            "tracebacks",
            "stack trace",
        )
    ):
        return "Checked results"
    if text.startswith("{") or text.startswith("["):
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if isinstance(payload, list):
            n = len(payload)
            return f"Found {n} title{'s' if n != 1 else ''}"
        if isinstance(payload, dict):
            if payload.get("quote_ok") and payload.get("persona"):
                name = str(payload.get("persona") or "sibling").strip() or "sibling"
                return f"Asked {name}"
            if payload.get("code") == "consult_timeout" or payload.get("busy"):
                return "Sibling busy"
            if str(payload.get("code") or "").startswith("consult_"):
                return "Consult skipped"
            if payload.get("error"):
                return "No confident match"
            count = payload.get("returned")
            if count is None and isinstance(payload.get("items"), list):
                count = len(payload["items"])
            if count is not None:
                try:
                    n = int(count)
                except (TypeError, ValueError):
                    n = None
                if n is not None:
                    return f"Found {n} title{'s' if n != 1 else ''}"
            if payload.get("ok") is True or payload.get("status") == "ok":
                return "Done"
        return "Updated results"
    cleaned = " ".join(text.split())
    if len(cleaned) > limit:
        return cleaned[: max(0, limit - 3)] + "..."
    return cleaned


def _displayable_cards(cards: List[TitleCard]) -> List[TitleCard]:
    """Skip placeholders and collapse duplicate cards by stable media identity."""
    displayable: List[TitleCard] = []
    positions: Dict[str, int] = {}
    for card in cards:
        if not (card.title or card.tmdb_id or card.tvdb_id or card.rating_key):
            continue
        identity = (
            f"{card.media_type}:tmdb:{card.tmdb_id}"
            if card.tmdb_id
            else f"{card.media_type}:tvdb:{card.tvdb_id}"
            if card.tvdb_id
            else f"{card.media_type}:rating:{card.rating_key}"
            if card.rating_key
            else f"{card.media_type}:title:{card.title.strip().casefold()}:{card.year or ''}"
        )
        existing_index = positions.get(identity)
        if existing_index is None:
            positions[identity] = len(displayable)
            displayable.append(card)
        elif card.recommendation_reason and not displayable[existing_index].recommendation_reason:
            displayable[existing_index] = card
    return displayable


def _actionable_recommendation_card(card: TitleCard, registry: ToolRegistry) -> bool:
    """Keep only titles that can actually be added/requested (matches UI add gates)."""
    if card.in_library or card.in_radarr or card.in_sonarr:
        return False
    seerr_path = uses_seerr_request_path(registry.settings, role=registry.user_role or "owner")
    if seerr_path:
        return bool(card.tmdb_id) and card.media_type in {"movie", "show"}
    if card.media_type == "movie":
        return bool(card.tmdb_id)
    if card.media_type == "show":
        # Sonarr add requires tvdb_id — drop TMDB-only shows so Confirm/Expand counts match.
        return bool(card.tvdb_id)
    return False


def _cards_for_response(registry: ToolRegistry) -> List[TitleCard]:
    """Cards shown in title_cards blocks — drop owned/queued titles during add/recommend flows."""
    cards = registry.cards
    if registry.recommendation_context:
        discussed = registry.discussed_cards
        if discussed:
            # Gap/recommendation tools explicitly identify the titles under discussion.
            # Keep actionable adds, plus shows that are true gaps but cannot be added
            # yet (missing TVDB) so the UI can explain instead of silently omitting Add.
            kept: List[TitleCard] = []
            for card in discussed:
                if card.in_library or card.in_radarr or card.in_sonarr:
                    continue
                if _actionable_recommendation_card(card, registry):
                    kept.append(card)
                    continue
                if (
                    card.media_type == "show"
                    and card.tmdb_id
                    and not card.tvdb_id
                    and not uses_seerr_request_path(registry.settings, role=registry.user_role or "owner")
                ):
                    if not str(getattr(card, "add_blocked_reason", "") or "").strip():
                        card.add_blocked_reason = "Can't add — no TVDB id yet"
                    kept.append(card)
            cards = kept
        else:
            # Compatibility for recommendation tools that have not yet been migrated
            # to the discussed-card channel.
            cards = [card for card in cards if _actionable_recommendation_card(card, registry)]
    return _displayable_cards(cards)


def _extract_tool_calls(response: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    if "choices" in response:
        message = response["choices"][0]["message"]
        return list(message.get("tool_calls") or [])
    if "content" in response:
        tool_uses = []
        for block in response.get("content") or []:
            if block.get("type") == "tool_use":
                tool_uses.append(
                    {
                        "id": block.get("id"),
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    }
                )
        return tool_uses
    return []


def _assistant_message_from_response(response: Mapping[str, Any]) -> Dict[str, Any]:
    if "choices" in response:
        return dict(response["choices"][0]["message"])
    return {"role": "assistant", "content": response.get("content") or []}


def _extract_text(response: Mapping[str, Any]) -> str:
    if "choices" in response:
        message = response["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "".join(parts)
        return str(content or "")
    if "content" in response:
        parts = []
        for block in response.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


# Cap tool↔LLM loops so a bad gap/discover retry spiral cannot leave the UI on
# "Jefferson is thinking" for many minutes (each provider call can take ≤120s).
MAX_TOOL_ROUNDS = 6


def _tool_result_requests_stop(result: str) -> bool:
    """True when a tool JSON payload asks the agent to stop retrying tools."""
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(parsed, dict) and bool(parsed.get("stop_retrying"))


def _append_review_prompt_blocks(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> None:
    prompts = registry.review_prompts
    if not prompts:
        return
    if len(prompts) == 1:
        blocks.append({"type": "review_prompt", "content": "", "payload": {"prompt": prompts[0]}})
        return
    blocks.append({"type": "review_batch", "content": "", "payload": {"prompts": prompts}})


def _append_review_conflict_blocks(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> None:
    for conflict in registry.review_conflicts:
        blocks.append({"type": "plex_rating_conflict", "payload": conflict})


def _suggested_reply_block(registry: ToolRegistry) -> Optional[Dict[str, Any]]:
    replies = registry.suggested_replies
    if not isinstance(replies, list):
        replies = []
    replies = [reply for reply in replies if isinstance(reply, str) and reply][:4]
    if not replies and registry.recommendation_context and registry.discussed_cards:
        replies = [
            "Dive deeper into the gaps",
            "Show me where to watch these",
            "Add these to a list",
        ]
    if not replies:
        return None
    return {"type": "suggested_replies", "payload": {"replies": replies}}


def _append_suggested_reply_block(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> None:
    block = _suggested_reply_block(registry)
    if block:
        blocks.append(block)


def _append_persona_consult_blocks(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> None:
    """Surface quoted village handoffs as structured chat blocks."""
    from projectionist.agent.village import quote_block_from_consult

    for payload in getattr(registry, "persona_consults", ()) or ():
        block = quote_block_from_consult(payload)
        if block:
            blocks.append(block)


def _sanitize_chat_blocks(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> List[Dict[str, Any]]:
    """Persist and return member-safe message blocks without local media metadata."""
    return sanitize(blocks, audience="member", settings=registry.settings)


def _finalize_chat_blocks(blocks: List[Dict[str, Any]], registry: ToolRegistry) -> List[Dict[str, Any]]:
    """Youth scrub (cards + known blocked titles) then privacy sanitize."""
    # Require an explicit True — MagicMock attributes are truthy and must not
    # trip the Youth scrub in unit tests that stub the registry.
    if getattr(registry, "is_youth", False) is True:
        from projectionist.youth.scrub import scrub_youth_chat_blocks

        blocks = scrub_youth_chat_blocks(
            blocks,
            settings=registry.settings,
            blocked_titles=getattr(registry, "youth_blocked_titles", ()) or (),
        )
    return _sanitize_chat_blocks(blocks, registry)


class CuratorAgent:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        lens_id: Optional[str] = None,
        *,
        user_id: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        user_role: Optional[str] = None,
        is_youth: bool = False,
    ) -> None:
        self.db = db
        self.settings = settings
        self.lens_id = lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
        self.user_id = user_id
        self.seerr_user_id = seerr_user_id
        self.user_role = user_role
        self.is_youth = bool(is_youth)
        self.provider = get_chat_provider(settings) if settings.llm_api_key or settings.llm_provider == "ollama" else None

    async def _fallback_run(self, registry: ToolRegistry, user_message: str) -> str:
        lowered = user_message.lower()
        if any(word in lowered for word in ("purge", "remove", "clunker", "space", "delete")):
            await registry.execute("suggest_purge_candidates", {"limit": 10})
            return "Here are titles that may not be worth the drive space based on play history and taste fit."
        if any(word in lowered for word in ("add", "missing", "gap", "recommend", "gem", "70s", "80s", "genre")):
            # Pass the NL ask as query so find_collection_gaps can structure
            # History/miniseries/negations via facets.augment_gaps_args_from_query.
            # Bare media_type=movie dumps popular theatrical discover junk.
            gaps_args: Dict[str, Any] = {"query": user_message}
            if "70s" in lowered:
                gaps_args.update(
                    {"media_type": "movie", "year_from": 1970, "year_to": 1979}
                )
            await registry.execute("find_collection_gaps", gaps_args)
            if registry.cards or registry.discussed_cards:
                return (
                    "I searched for missing titles that fit what you described. "
                    "Review the cards below."
                )
            return (
                "I could not find confident missing titles that match that ask. "
                "Try a more specific genre or brand, or configure an LLM provider "
                "for richer conversation."
            )
        if "watch" in lowered or "tonight" in lowered:
            await registry.execute("search_library", {"query": user_message, "media_type": "movie"})
            return "Based on your library, here are some options worth revisiting tonight."
        await registry.execute("search_library", {"query": user_message})
        return "Here's what I found in your library. Configure an LLM provider for richer conversation."

    def _registry(
        self,
        *,
        persona_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> ToolRegistry:
        return ToolRegistry(
            self.db,
            self.settings,
            self.lens_id,
            user_id=self.user_id,
            seerr_user_id=self.seerr_user_id,
            user_role=self.user_role,
            is_youth=self.is_youth,
            persona_id=persona_id,
            session_id=session_id,
        )

    async def run(self, session_id: str, user_message: str) -> Dict[str, Any]:
        self.db.ensure_chat_session(session_id, self.lens_id, user_id=self.user_id)
        thread_persona_id = self.db.get_thread_persona_id(session_id)
        registry = self._registry(persona_id=thread_persona_id, session_id=session_id)

        if not self.provider:
            text = await self._fallback_run(registry, user_message)
            blocks: List[Dict[str, Any]] = [{"type": "text", "content": text}]
            if registry.cards:
                cards = _cards_for_response(registry)
                if cards:
                    blocks.append({"type": "title_cards", "items": [card.model_dump() for card in cards]})
                    blocks.append(
                        {
                            "type": "action_prompt",
                            "action": "open_viewport",
                            "payload": {"title": "Results", "items": [c.model_dump() for c in cards]},
                        }
                    )
            _append_persona_consult_blocks(blocks, registry)
            _append_review_prompt_blocks(blocks, registry)
            _append_review_conflict_blocks(blocks, registry)
            _append_suggested_reply_block(blocks, registry)
            blocks = _finalize_chat_blocks(blocks, registry)
            user_id = uuid.uuid4().hex
            assistant_id = uuid.uuid4().hex
            self.db.save_chat_message(
                session_id, user_id, "user", [{"type": "text", "content": user_message}], lens_id=self.lens_id
            )
            self.db.maybe_auto_title_thread(session_id, user_message)
            self.db.save_chat_message(session_id, assistant_id, "assistant", blocks, lens_id=self.lens_id)
            context_label = _sync_thread_context_label(self.db, session_id, registry.turn_audit_label)
            return {
                "session_id": session_id,
                "lens_id": self.lens_id,
                "message": {"id": assistant_id, "role": "assistant", "blocks": blocks, "lens_id": self.lens_id},
                "pending_tokens": registry.pending_tokens,
                "context_label": context_label,
            }

        history = self.db.chat_history(session_id, limit=20, lens_id=self.lens_id)
        thread_persona_id = self.db.get_thread_persona_id(session_id)
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": build_system_prompt(
                    self.db,
                    self.lens_id,
                    persona_id=thread_persona_id,
                    user_id=self.user_id,
                    user_role=self.user_role,
                    is_youth=self.is_youth,
                ),
            }
        ]
        for entry in history:
            text = " ".join(
                block.get("content", "")
                for block in entry.get("blocks", [])
                if block.get("type") == "text"
            )
            if text:
                messages.append({"role": entry["role"], "content": text})
        messages.append({"role": "user", "content": user_message})

        registry = self._registry(persona_id=thread_persona_id, session_id=session_id)
        use_tools = bool(self.settings.llm_api_key or self.settings.llm_provider == "ollama")
        tool_defs = build_tool_definitions(self.settings) if use_tools else None
        response = await tracked_chat(
            self.db,
            self.provider,
            messages,
            tools=tool_defs,
            purpose=PURPOSE_CHAT,
            persona_id=thread_persona_id,
            session_id=session_id,
            user_id=self.user_id,
        )

        # Accumulate prose from the initial response and every tool round so
        # the final text block preserves earlier-round narration instead of
        # keeping only the last response (which is often cards with no text).
        text_segments: List[str] = []

        def _accumulate_response_text(resp: Any) -> None:
            seg = (_extract_text(resp) or "").strip()
            if seg and (not text_segments or text_segments[-1] != seg):
                text_segments.append(seg)

        _accumulate_response_text(response)

        for _ in range(MAX_TOOL_ROUNDS):
            tool_calls = _extract_tool_calls(response)
            if not tool_calls:
                break
            messages.append(_assistant_message_from_response(response))
            stop_retrying = False
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                args = json.loads(fn.get("arguments") or "{}")
                logger.debug("Agent tool call name=%s args=%s", name, args)
                _t0 = __import__("time").time()
                result = await registry.execute(str(name), args)
                _duration_ms = int((__import__("time").time() - _t0) * 1000)
                if _tool_result_requests_stop(result):
                    stop_retrying = True
                try:
                    from projectionist.telemetry import TelemetryIngester

                    result_count = None
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "count" in parsed:
                            result_count = int(parsed["count"])
                        elif isinstance(parsed, list):
                            result_count = len(parsed)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                    TelemetryIngester(self.db).record_tool_invocation(
                        tool_name=str(name),
                        duration_ms=_duration_ms,
                        result_count=result_count,
                        session_id=session_id,
                    )
                except Exception:
                    logger.debug("Failed to record tool-invocation telemetry", exc_info=True)
                tool_content = (
                    wrap_untrusted_data(result)
                    if str(name) in UNTRUSTED_MEMORY_TOOLS
                    else result
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": tool_content,
                    }
                )
            # Force a prose wrap-up without tools after fail-closed gap/discover.
            next_tools = None if stop_retrying else tool_defs
            response = await tracked_chat(
                self.db,
                self.provider,
                messages,
                tools=next_tools,
                purpose=PURPOSE_WRAP_UP if stop_retrying else PURPOSE_CHAT_TOOL,
                persona_id=thread_persona_id,
                session_id=session_id,
                user_id=self.user_id,
            )
            _accumulate_response_text(response)
            if stop_retrying:
                break

        text = join_assistant_text_segments(text_segments)
        blocks: List[Dict[str, Any]] = []
        if text:
            blocks.append({"type": "text", "content": text})
        elif registry.cards:
            blocks.append({"type": "text", "content": "Here are the results I found."})
        elif _extract_tool_calls(response):
            blocks.append(
                {
                    "type": "text",
                    "content": (
                        "I looked for matches but could not finish a confident answer. "
                        "Try a more specific title, genre, or brand (for example BBC + Documentary)."
                    ),
                }
            )
        else:
            blocks.append(
                {
                    "type": "text",
                    "content": (
                        "The curator returned an empty response. "
                        "Check your LLM provider, API key, and model ID in Settings."
                    ),
                }
            )
        if registry.cards:
            cards = _cards_for_response(registry)
            if cards:
                viewport_title = "Recommendations" if registry.recommendation_context else "Results"
                blocks.append({"type": "title_cards", "items": [card.model_dump() for card in cards]})
                blocks.append(
                    {
                        "type": "action_prompt",
                        "action": "open_viewport",
                        "payload": {"title": viewport_title, "items": [c.model_dump() for c in cards]},
                    }
                )
        _append_persona_consult_blocks(blocks, registry)
        _append_review_prompt_blocks(blocks, registry)
        _append_review_conflict_blocks(blocks, registry)
        _append_suggested_reply_block(blocks, registry)
        blocks = _finalize_chat_blocks(blocks, registry)

        user_id = uuid.uuid4().hex
        assistant_id = uuid.uuid4().hex
        self.db.save_chat_message(
            session_id, user_id, "user", [{"type": "text", "content": user_message}], lens_id=self.lens_id
        )
        self.db.maybe_auto_title_thread(session_id, user_message)
        self.db.save_chat_message(session_id, assistant_id, "assistant", blocks, lens_id=self.lens_id)
        context_label = _sync_thread_context_label(self.db, session_id, registry.turn_audit_label)

        return {
            "session_id": session_id,
            "lens_id": self.lens_id,
            "message": {
                "id": assistant_id,
                "role": "assistant",
                "blocks": blocks,
                "lens_id": self.lens_id,
            },
            "pending_tokens": registry.pending_tokens,
            "context_label": context_label,
        }


async def stream_agent(
    db: Database,
    settings: Settings,
    session_id: str,
    user_message: str,
    lens_id: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
    seerr_user_id: Optional[int] = None,
    user_role: Optional[str] = None,
    persona_id: Optional[str] = None,
    is_youth: bool = False,
) -> AsyncIterator[str]:
    """Stream agent responses with true token-by-token LLM streaming.

    Yields newline-delimited JSON events:

    - ``{"type": "token", "content": "…"}`` — incremental text token from the LLM
    - ``{"type": "tool_start", "name": "…", "args": {…}}`` — tool execution begins
    - ``{"type": "tool_result", "name": "…", "summary": "…"}`` — tool execution completed
    - ``{"type": "done", "message": {…}, …}`` — final assembled message

    Tool calls are fully buffered (the agent needs complete results before
    the next LLM turn).  Text responses stream token-by-token.  If the
    provider does not support streaming, the function falls back to the
    buffered ``CuratorAgent.run`` path and simulates token events.
    """
    agent = CuratorAgent(
        db,
        settings,
        lens_id=lens_id,
        user_id=user_id,
        seerr_user_id=seerr_user_id,
        user_role=user_role,
        is_youth=is_youth,
    )
    resolved_lens = agent.lens_id

    def _prepare_session() -> None:
        db.ensure_chat_session(session_id, resolved_lens, user_id=user_id, persona_id=persona_id)
        if persona_id:
            db.set_thread_persona(session_id, persona_id)

    await run_db(_prepare_session)

    # --- Build conversation history (sync sqlite off the event loop) ---
    def _load_history() -> tuple:
        return (
            db.chat_history(session_id, limit=20, lens_id=resolved_lens),
            db.get_thread_persona_id(session_id),
        )

    history, thread_persona_id = await run_db(_load_history)
    registry = agent._registry(persona_id=thread_persona_id, session_id=session_id)

    # --- No LLM configured: keyword fallback with simulated streaming ---
    if not agent.provider:
        text = await agent._fallback_run(registry, user_message)
        async for event in _emit_buffered(
            db, registry, agent, session_id, user_message, text, resolved_lens,
        ):
            yield event
        return
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                db,
                resolved_lens,
                persona_id=thread_persona_id,
                user_id=user_id,
                user_role=user_role,
                is_youth=is_youth,
            ),
        },
    ]
    for entry in history:
        text = " ".join(
            block.get("content", "")
            for block in entry.get("blocks", [])
            if block.get("type") == "text"
        )
        if text:
            messages.append({"role": entry["role"], "content": text})
    messages.append({"role": "user", "content": user_message})

    tool_defs = build_tool_definitions(settings) if (settings.llm_api_key or settings.llm_provider == "ollama") else None
    text_segments: List[str] = []
    pending_segment_sep = False
    stream_round = 0

    for _ in range(MAX_TOOL_ROUNDS):
        round_text = ""
        current_tool_calls: Dict[int, Dict[str, Any]] = {}
        streamed_any_token = False
        purpose = PURPOSE_CHAT if stream_round == 0 else PURPOSE_CHAT_TOOL
        stream_round += 1

        try:
            async for chunk in tracked_stream(
                db,
                agent.provider,
                messages,
                tools=tool_defs,
                purpose=purpose,
                persona_id=thread_persona_id,
                session_id=session_id,
                user_id=user_id,
            ):
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}

                content = delta.get("content")
                if content:
                    if pending_segment_sep and text_segments:
                        # Live UI concatenates tokens; insert the same separator
                        # final assembly uses so rounds never glue ("once!Let").
                        yield json.dumps({"type": "token", "content": _STREAM_SEGMENT_SEP}) + "\n"
                        pending_segment_sep = False
                    round_text += content
                    streamed_any_token = True
                    yield json.dumps({"type": "token", "content": content}) + "\n"

                for tc_delta in delta.get("tool_calls") or []:
                    idx = tc_delta.get("index", 0)
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": tc_delta.get("id", ""),
                            "name": (tc_delta.get("function") or {}).get("name", ""),
                            "arguments": "",
                        }
                    else:
                        if tc_delta.get("id"):
                            current_tool_calls[idx]["id"] = tc_delta["id"]
                        fn = tc_delta.get("function") or {}
                        if fn.get("name"):
                            current_tool_calls[idx]["name"] = fn["name"]
                    args_frag = (tc_delta.get("function") or {}).get("arguments", "")
                    if args_frag:
                        current_tool_calls[idx]["arguments"] += args_frag
        except Exception as exc:
            if streamed_any_token:
                raise
            logger.warning("Streaming failed, falling back to buffered: %s", exc)
            response = await tracked_chat(
                db,
                agent.provider,
                messages,
                tools=tool_defs,
                purpose=purpose,
                persona_id=thread_persona_id,
                session_id=session_id,
                user_id=user_id,
                meta={"fallback": "buffered"},
            )
            round_text = _extract_text(response)
            if round_text:
                if pending_segment_sep and text_segments:
                    yield json.dumps({"type": "token", "content": _STREAM_SEGMENT_SEP}) + "\n"
                    pending_segment_sep = False
                yield json.dumps({"type": "token", "content": round_text}) + "\n"
            for tc in _extract_tool_calls(response):
                fn = tc.get("function") or {}
                idx = len(current_tool_calls)
                current_tool_calls[idx] = {
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                }

        # Accumulate prose across every tool round so the persisted/returned
        # text matches what the user actually watched stream. Earlier rounds
        # often narrate ("Let me look…") before a tool call, and a later round
        # may return only cards; keeping just the last round would drop that
        # prose and fall back to the generic placeholder.
        # Guard like _accumulate_response_text: buffered fallback / odd payloads
        # must not AttributeError if round_text is unexpectedly None.
        stripped = (round_text or "").strip()
        if stripped and (not text_segments or text_segments[-1] != stripped):
            text_segments.append(stripped)

        if current_tool_calls:
            tool_calls_list = []
            for idx in sorted(current_tool_calls):
                tc = current_tool_calls[idx]
                tool_calls_list.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })

            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": round_text or None}
            assistant_msg["tool_calls"] = tool_calls_list
            messages.append(assistant_msg)

            stop_retrying = False
            for call in tool_calls_list:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                args = json.loads(fn.get("arguments") or "{}")
                logger.debug("Stream agent tool call name=%s args=%s", name, args)

                brief_args = args if isinstance(args, dict) else {"value": args}
                yield json.dumps({"type": "tool_start", "name": name, "args": brief_args}) + "\n"
                _t0 = __import__("time").time()
                # Tool handlers that hit sqlite/cosine already offload via run_db.
                result = await registry.execute(str(name), args)
                _duration_ms = int((__import__("time").time() - _t0) * 1000)
                if _tool_result_requests_stop(result):
                    stop_retrying = True
                try:
                    from projectionist.telemetry import TelemetryIngester

                    result_count = None
                    try:
                        parsed = json.loads(result)
                        if isinstance(parsed, dict) and "count" in parsed:
                            result_count = int(parsed["count"])
                        elif isinstance(parsed, list):
                            result_count = len(parsed)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                    TelemetryIngester(db).record_tool_invocation(
                        tool_name=str(name),
                        duration_ms=_duration_ms,
                        result_count=result_count,
                        session_id=session_id,
                    )
                except Exception:
                    logger.debug("Failed to record stream tool-invocation telemetry", exc_info=True)
                tool_content = (
                    wrap_untrusted_data(result) if str(name) in UNTRUSTED_MEMORY_TOOLS else result
                )
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": tool_content})
                summary = household_tool_summary(result)
                yield json.dumps({"type": "tool_result", "name": name, "summary": summary}) + "\n"
            # Next LLM round's tokens need a separator after tool work.
            if text_segments:
                pending_segment_sep = True
            if stop_retrying:
                # One final prose turn without tools, then end the stream loop.
                # Skip a second paid call when the wrap-up stream already produced
                # a final completion (partial stream + buffered chat was double-pay).
                round_text = ""
                wrap_streamed = False
                try:
                    async for chunk in tracked_stream(
                        db,
                        agent.provider,
                        messages,
                        tools=None,
                        purpose=PURPOSE_WRAP_UP,
                        persona_id=thread_persona_id,
                        session_id=session_id,
                        user_id=user_id,
                    ):
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content:
                            if pending_segment_sep and text_segments:
                                yield json.dumps({"type": "token", "content": _STREAM_SEGMENT_SEP}) + "\n"
                                pending_segment_sep = False
                            round_text += content
                            wrap_streamed = True
                            yield json.dumps({"type": "token", "content": content}) + "\n"
                except Exception as exc:
                    if (round_text or "").strip() or wrap_streamed:
                        logger.warning(
                            "Streaming wrap-up interrupted after tokens; skipping buffered fallback: %s",
                            exc,
                        )
                    else:
                        logger.warning("Streaming wrap-up failed, falling back to buffered: %s", exc)
                        response = await tracked_chat(
                            db,
                            agent.provider,
                            messages,
                            tools=None,
                            purpose=PURPOSE_WRAP_UP,
                            persona_id=thread_persona_id,
                            session_id=session_id,
                            user_id=user_id,
                            meta={"fallback": "buffered_wrap_up"},
                        )
                        round_text = _extract_text(response) or ""
                        if round_text:
                            if pending_segment_sep and text_segments:
                                yield json.dumps({"type": "token", "content": _STREAM_SEGMENT_SEP}) + "\n"
                                pending_segment_sep = False
                            yield json.dumps({"type": "token", "content": round_text}) + "\n"
                stripped = (round_text or "").strip()
                if stripped and (not text_segments or text_segments[-1] != stripped):
                    text_segments.append(stripped)
                break
        else:
            break

    # --- Assemble final message ---
    final_text = join_assistant_text_segments(text_segments)
    blocks: List[Dict[str, Any]] = []
    if final_text:
        blocks.append({"type": "text", "content": final_text})
    elif registry.cards:
        blocks.append({"type": "text", "content": "Here are the results I found."})
    else:
        blocks.append(
            {
                "type": "text",
                "content": (
                    "I looked for matches but could not finish a confident answer. "
                    "Try a more specific title, genre, or brand (for example BBC + Documentary)."
                ),
            }
        )

    if registry.cards:
        cards = _cards_for_response(registry)
        if cards:
            viewport_title = "Recommendations" if registry.recommendation_context else "Results"
            blocks.append({"type": "title_cards", "items": [card.model_dump() for card in cards]})
            blocks.append({
                "type": "action_prompt",
                "action": "open_viewport",
                "payload": {"title": viewport_title, "items": [c.model_dump() for c in cards]},
            })

    _append_persona_consult_blocks(blocks, registry)
    _append_review_prompt_blocks(blocks, registry)
    _append_review_conflict_blocks(blocks, registry)
    _append_suggested_reply_block(blocks, registry)
    blocks = _finalize_chat_blocks(blocks, registry)

    user_msg_id = uuid.uuid4().hex
    assistant_id = uuid.uuid4().hex
    context_label = await run_db(
        _persist_stream_turn,
        db,
        session_id,
        user_message,
        user_msg_id,
        assistant_id,
        blocks,
        resolved_lens,
        registry.turn_audit_label,
    )

    yield json.dumps({
        "type": "done",
        "message": {
            "id": assistant_id,
            "role": "assistant",
            "blocks": blocks,
            "lens_id": resolved_lens,
        },
        "pending_tokens": registry.pending_tokens,
        "lens_id": resolved_lens,
        "context_label": context_label,
    }) + "\n"


def _sync_thread_context_label(
    db: Database,
    session_id: str,
    turn_audit_label: Optional[str] = None,
) -> str:
    """Best-effort ambient label sync; never fail the chat turn."""
    try:
        return resolve_thread_ambient_context_label(
            db,
            session_id,
            turn_audit_label=turn_audit_label,
        )
    except Exception:
        logger.debug("Failed to update thread derived-context label", exc_info=True)
        return "General Exploration"


def _persist_stream_turn(
    db: Database,
    session_id: str,
    user_message: str,
    user_msg_id: str,
    assistant_id: str,
    blocks: List[Dict[str, Any]],
    lens_id: str,
    turn_audit_label: Optional[str] = None,
) -> str:
    """Persist a streamed chat turn (runs in a worker thread via ``run_db``)."""
    db.save_chat_message(
        session_id,
        user_msg_id,
        "user",
        [{"type": "text", "content": user_message}],
        lens_id=lens_id,
    )
    db.maybe_auto_title_thread(session_id, user_message)
    db.save_chat_message(session_id, assistant_id, "assistant", blocks, lens_id=lens_id)
    return _sync_thread_context_label(db, session_id, turn_audit_label)


async def _emit_buffered(
    db: Database,
    registry: "ToolRegistry",
    agent: CuratorAgent,
    session_id: str,
    user_message: str,
    text: str,
    lens_id: str,
) -> AsyncIterator[str]:
    """Simulate token events from a fully-buffered text response."""
    chunk_size = 40
    for i in range(0, len(text), chunk_size):
        yield json.dumps({"type": "token", "content": text[i : i + chunk_size]}) + "\n"

    blocks: List[Dict[str, Any]] = [{"type": "text", "content": text}]
    if registry.cards:
        cards = _cards_for_response(registry)
        if cards:
            blocks.append({"type": "title_cards", "items": [card.model_dump() for card in cards]})
            blocks.append({
                "type": "action_prompt",
                "action": "open_viewport",
                "payload": {"title": "Results", "items": [c.model_dump() for c in cards]},
            })
    _append_persona_consult_blocks(blocks, registry)
    _append_review_prompt_blocks(blocks, registry)
    _append_review_conflict_blocks(blocks, registry)
    _append_suggested_reply_block(blocks, registry)
    blocks = _finalize_chat_blocks(blocks, registry)

    user_msg_id = uuid.uuid4().hex
    assistant_id = uuid.uuid4().hex
    context_label = await run_db(
        _persist_stream_turn,
        db,
        session_id,
        user_message,
        user_msg_id,
        assistant_id,
        blocks,
        lens_id,
        registry.turn_audit_label,
    )

    yield json.dumps({
        "type": "done",
        "message": {
            "id": assistant_id,
            "role": "assistant",
            "blocks": blocks,
            "lens_id": lens_id,
        },
        "pending_tokens": registry.pending_tokens,
        "lens_id": lens_id,
        "context_label": context_label,
    }) + "\n"
