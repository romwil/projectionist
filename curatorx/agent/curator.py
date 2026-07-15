"""Curator agent orchestration."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional

from curatorx.agent.providers import get_chat_provider
from curatorx.agent.tools import build_tool_definitions, ToolRegistry, build_system_prompt
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.models.schemas import TitleCard

logger = logging.getLogger(__name__)


def _displayable_cards(cards: List[TitleCard]) -> List[TitleCard]:
    """Skip empty placeholder cards that have no title or external ids."""
    displayable: List[TitleCard] = []
    for card in cards:
        if card.title or card.tmdb_id or card.tvdb_id or card.rating_key:
            displayable.append(card)
    return displayable


def _cards_for_response(registry: ToolRegistry) -> List[TitleCard]:
    """Cards shown in title_cards blocks — drop owned/queued titles during add/recommend flows."""
    cards = registry.cards
    if registry.recommendation_context:
        cards = [
            card
            for card in cards
            if not card.in_library and not card.in_radarr and not card.in_sonarr
        ]
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


MAX_TOOL_ROUNDS = 8


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
    ) -> None:
        self.db = db
        self.settings = settings
        self.lens_id = lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
        self.user_id = user_id
        self.seerr_user_id = seerr_user_id
        self.user_role = user_role
        self.provider = get_chat_provider(settings) if settings.llm_api_key or settings.llm_provider == "ollama" else None

    async def _fallback_run(self, registry: ToolRegistry, user_message: str) -> str:
        lowered = user_message.lower()
        if any(word in lowered for word in ("purge", "remove", "clunker", "space", "delete")):
            await registry.execute("suggest_purge_candidates", {"limit": 10})
            return "Here are titles that may not be worth the drive space based on play history and taste fit."
        if any(word in lowered for word in ("add", "missing", "gap", "recommend", "gem", "70s", "80s", "genre")):
            await registry.execute(
                "find_collection_gaps",
                {"media_type": "movie", "year_from": 1970, "year_to": 1979} if "70s" in lowered else {"media_type": "movie"},
            )
            return "I searched for missing titles that fit what you described. Review the cards below."
        if "watch" in lowered or "tonight" in lowered:
            await registry.execute("search_library", {"query": user_message, "media_type": "movie"})
            return "Based on your library, here are some options worth revisiting tonight."
        await registry.execute("search_library", {"query": user_message})
        return "Here's what I found in your library. Configure an LLM provider for richer conversation."

    def _registry(self) -> ToolRegistry:
        return ToolRegistry(
            self.db,
            self.settings,
            self.lens_id,
            user_id=self.user_id,
            seerr_user_id=self.seerr_user_id,
            user_role=self.user_role,
        )

    async def run(self, session_id: str, user_message: str) -> Dict[str, Any]:
        self.db.ensure_chat_session(session_id, self.lens_id, user_id=self.user_id)
        registry = self._registry()

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
            _append_review_prompt_blocks(blocks, registry)
            _append_review_conflict_blocks(blocks, registry)
            user_id = uuid.uuid4().hex
            assistant_id = uuid.uuid4().hex
            self.db.save_chat_message(
                session_id, user_id, "user", [{"type": "text", "content": user_message}], lens_id=self.lens_id
            )
            self.db.maybe_auto_title_thread(session_id, user_message)
            self.db.save_chat_message(session_id, assistant_id, "assistant", blocks, lens_id=self.lens_id)
            return {
                "session_id": session_id,
                "lens_id": self.lens_id,
                "message": {"id": assistant_id, "role": "assistant", "blocks": blocks, "lens_id": self.lens_id},
                "pending_tokens": registry.pending_tokens,
            }

        history = self.db.chat_history(session_id, limit=20, lens_id=self.lens_id)
        thread_persona_id = self.db.get_thread_persona_id(session_id)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(self.db, self.lens_id, persona_id=thread_persona_id)}
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

        registry = self._registry()
        use_tools = bool(self.settings.llm_api_key or self.settings.llm_provider == "ollama")
        tool_defs = build_tool_definitions(self.settings) if use_tools else None
        response = await self.provider.chat(messages, tools=tool_defs)

        for _ in range(MAX_TOOL_ROUNDS):
            tool_calls = _extract_tool_calls(response)
            if not tool_calls:
                break
            messages.append(_assistant_message_from_response(response))
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                args = json.loads(fn.get("arguments") or "{}")
                logger.debug("Agent tool call name=%s args=%s", name, args)
                result = await registry.execute(str(name), args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": result,
                    }
                )
            response = await self.provider.chat(messages, tools=tool_defs)

        text = _extract_text(response)
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
                        "The curator used tools but did not finish with a summary. "
                        "Try asking again or check your LLM model configuration."
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
        _append_review_prompt_blocks(blocks, registry)
        _append_review_conflict_blocks(blocks, registry)

        user_id = uuid.uuid4().hex
        assistant_id = uuid.uuid4().hex
        self.db.save_chat_message(
            session_id, user_id, "user", [{"type": "text", "content": user_message}], lens_id=self.lens_id
        )
        self.db.maybe_auto_title_thread(session_id, user_message)
        self.db.save_chat_message(session_id, assistant_id, "assistant", blocks, lens_id=self.lens_id)

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
) -> AsyncIterator[str]:
    result = await CuratorAgent(
        db,
        settings,
        lens_id=lens_id,
        user_id=user_id,
        seerr_user_id=seerr_user_id,
        user_role=user_role,
    ).run(session_id, user_message)
    text_blocks = [b for b in result["message"]["blocks"] if b.get("type") == "text"]
    content = text_blocks[0]["content"] if text_blocks else ""
    chunk_size = 40
    for index in range(0, len(content), chunk_size):
        yield json.dumps({"type": "text_delta", "content": content[index : index + chunk_size]}) + "\n"
    yield json.dumps(
        {
            "type": "complete",
            "message": result["message"],
            "pending_tokens": result["pending_tokens"],
            "lens_id": result.get("lens_id"),
        }
    ) + "\n"
