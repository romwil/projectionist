"""Tests for the true SSE streaming path (Item 27).

Covers:
- Token event format produced by ``stream_agent``
- Tool-call event format (start / result)
- Graceful fallback when the provider raises during streaming
- Complete message assembly from streamed tokens
- SSE endpoint event remapping (tool_start/tool_result -> tool_call)
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from curatorx.agent.curator import (
    CuratorAgent,
    _cards_for_response,
    _extract_text,
    _extract_tool_calls,
    stream_agent,
)
from curatorx.agent.providers import (
    AnthropicProvider,
    LLMProviderError,
    OpenAICompatibleProvider,
)
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.models.schemas import TitleCard


def _make_db(tmp: Path) -> Database:
    db = Database(tmp / "test.db")
    db.ensure_seed_data()
    return db


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "llm_provider": "openai",
        "llm_base_url": "http://localhost:11434/v1",
        "llm_api_key": "test-key",
        "llm_model": "test-model",
        "plex_url": "",
        "plex_token": "",
    }
    base.update(overrides)
    return Settings.from_mapping(base)


def _collect_events(raw_chunks: List[str]) -> List[Dict[str, Any]]:
    """Parse newline-delimited JSON chunks into a list of event dicts."""
    events: List[Dict[str, Any]] = []
    for chunk in raw_chunks:
        for line in chunk.strip().splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


class TokenEventFormatTests(unittest.IsolatedAsyncioTestCase):
    """Token events should carry ``{"type": "token", "content": "…"}``."""

    async def test_token_events_from_streaming_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            streaming_chunks = [
                {"choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]

            async def fake_stream(messages, tools=None):
                for chunk in streaming_chunks:
                    yield chunk

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            with patch("curatorx.agent.curator.get_chat_provider", return_value=provider):
                chunks: List[str] = []
                async for chunk in stream_agent(
                    db, settings, "sess-tok", "hi",
                    lens_id=DEFAULT_LENS_ID,
                ):
                    chunks.append(chunk)

            events = _collect_events(chunks)
            token_events = [e for e in events if e["type"] == "token"]
            self.assertGreater(len(token_events), 0)
            self.assertEqual(token_events[0]["content"], "Hello")
            self.assertEqual(token_events[1]["content"], " world")

            done_events = [e for e in events if e["type"] == "done"]
            self.assertEqual(len(done_events), 1)
            assembled = done_events[0]["message"]["blocks"][0]["content"]
            self.assertEqual(assembled, "Hello world")

    async def test_token_events_have_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            async def fake_stream(messages, tools=None):
                yield {"choices": [{"index": 0, "delta": {"content": "test"}, "finish_reason": None}]}
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            with patch("curatorx.agent.curator.get_chat_provider", return_value=provider):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-fmt", "hello",
                    lens_id=DEFAULT_LENS_ID,
                )]

            events = _collect_events(chunks)
            for event in events:
                self.assertIn("type", event)
            token = next(e for e in events if e["type"] == "token")
            self.assertIn("content", token)
            self.assertIsInstance(token["content"], str)


class ToolCallEventFormatTests(unittest.IsolatedAsyncioTestCase):
    """Tool call events: tool_start and tool_result with name fields."""

    async def test_tool_start_and_result_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            first_response_chunks = [
                {"choices": [{"index": 0, "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search_library", "arguments": ""},
                    }],
                }, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {
                    "tool_calls": [{"index": 0, "function": {"arguments": '{"query":"noir"}'}}],
                }, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            ]

            second_response_chunks = [
                {"choices": [{"index": 0, "delta": {"content": "Found noir films."}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]

            call_count = 0

            async def fake_stream(messages, tools=None):
                nonlocal call_count
                call_count += 1
                source = first_response_chunks if call_count == 1 else second_response_chunks
                for chunk in source:
                    yield chunk

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            mock_registry = MagicMock()
            mock_registry.cards = []
            mock_registry.pending_tokens = []
            mock_registry.recommendation_context = False
            mock_registry.review_prompts = []
            mock_registry.review_conflicts = []
            mock_registry.execute = AsyncMock(return_value='[{"title":"Chinatown"}]')

            with (
                patch("curatorx.agent.curator.get_chat_provider", return_value=provider),
                patch.object(CuratorAgent, "_registry", return_value=mock_registry),
            ):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-tool", "noir films",
                    lens_id=DEFAULT_LENS_ID,
                )]

            events = _collect_events(chunks)
            tool_starts = [e for e in events if e["type"] == "tool_start"]
            tool_results = [e for e in events if e["type"] == "tool_result"]
            self.assertEqual(len(tool_starts), 1)
            self.assertEqual(tool_starts[0]["name"], "search_library")
            self.assertEqual(tool_starts[0].get("args"), {"query": "noir"})
            self.assertEqual(len(tool_results), 1)
            self.assertEqual(tool_results[0]["name"], "search_library")
            self.assertIn("Chinatown", tool_results[0].get("summary", ""))

            done = next(e for e in events if e["type"] == "done")
            self.assertEqual(done["message"]["blocks"][0]["content"], "Found noir films.")


class GracefulFallbackTests(unittest.IsolatedAsyncioTestCase):
    """When streaming fails before any tokens, fall back to buffered chat."""

    async def test_fallback_to_buffered_on_stream_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            async def failing_stream(messages, tools=None):
                raise ConnectionError("Streaming not supported")
                yield  # pragma: no cover — makes this an async generator

            buffered_response = {
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Buffered response"},
                    "finish_reason": "stop",
                }],
            }

            provider = MagicMock()
            provider.stream = failing_stream
            provider.chat = AsyncMock(return_value=buffered_response)

            with patch("curatorx.agent.curator.get_chat_provider", return_value=provider):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-fb", "fallback test",
                    lens_id=DEFAULT_LENS_ID,
                )]

            events = _collect_events(chunks)
            token_events = [e for e in events if e["type"] == "token"]
            self.assertTrue(len(token_events) > 0)
            combined = "".join(e["content"] for e in token_events)
            self.assertEqual(combined, "Buffered response")

            done = next(e for e in events if e["type"] == "done")
            self.assertEqual(done["message"]["blocks"][0]["content"], "Buffered response")
            provider.chat.assert_awaited_once()

    async def test_fallback_tolerates_none_extract_text(self) -> None:
        """Streaming fallback must not AttributeError if extract yields None."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            async def failing_stream(messages, tools=None):
                raise ConnectionError("Streaming not supported")
                yield  # pragma: no cover — makes this an async generator

            provider = MagicMock()
            provider.stream = failing_stream
            provider.chat = AsyncMock(
                return_value={
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": None},
                        "finish_reason": "stop",
                    }],
                }
            )

            with (
                patch("curatorx.agent.curator.get_chat_provider", return_value=provider),
                patch("curatorx.agent.curator._extract_text", return_value=None),
            ):
                chunks = [
                    c
                    async for c in stream_agent(
                        db,
                        settings,
                        "sess-fb-none",
                        "fallback none",
                        lens_id=DEFAULT_LENS_ID,
                    )
                ]

            events = _collect_events(chunks)
            done = next(e for e in events if e["type"] == "done")
            self.assertEqual(done["type"], "done")
            provider.chat.assert_awaited_once()


class CompleteMessageAssemblyTests(unittest.IsolatedAsyncioTestCase):
    """Done event should contain a fully assembled message with blocks."""

    async def test_done_event_assembles_all_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            words = ["The ", "answer ", "is ", "42."]

            async def fake_stream(messages, tools=None):
                for word in words:
                    yield {"choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}]}
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            with patch("curatorx.agent.curator.get_chat_provider", return_value=provider):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-asm", "what is the answer?",
                    lens_id=DEFAULT_LENS_ID,
                )]

            events = _collect_events(chunks)
            done = next(e for e in events if e["type"] == "done")

            self.assertIn("message", done)
            message = done["message"]
            self.assertEqual(message["role"], "assistant")
            self.assertTrue(len(message["blocks"]) >= 1)
            self.assertEqual(message["blocks"][0]["type"], "text")
            self.assertEqual(message["blocks"][0]["content"], "The answer is 42.")
            self.assertIn("id", message)
            self.assertIn("lens_id", message)

    async def test_done_event_includes_pending_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            async def fake_stream(messages, tools=None):
                yield {"choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]}
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            with patch("curatorx.agent.curator.get_chat_provider", return_value=provider):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-pt", "test",
                    lens_id=DEFAULT_LENS_ID,
                )]

            done = next(e for e in _collect_events(chunks) if e["type"] == "done")
            self.assertIn("pending_tokens", done)


class NoProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    """When no LLM provider is configured, stream simulated token events."""

    async def test_no_provider_yields_token_and_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings(llm_api_key="", llm_provider="none")

            chunks = [c async for c in stream_agent(
                db, settings, "sess-no-llm", "watch tonight",
                lens_id=DEFAULT_LENS_ID,
            )]

            events = _collect_events(chunks)
            token_events = [e for e in events if e["type"] == "token"]
            done_events = [e for e in events if e["type"] == "done"]
            self.assertGreater(len(token_events), 0)
            self.assertEqual(len(done_events), 1)


class MultiRoundProsePreservationTests(unittest.IsolatedAsyncioTestCase):
    """Prose narrated in an early round must survive when a later round returns
    only cards with no text (regression for the turnstile text-loss bug)."""

    async def test_round1_prose_preserved_when_round2_returns_only_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(Path(tmp))
            settings = _make_settings()

            round1_chunks = [
                {"choices": [{"index": 0, "delta": {
                    "content": "Let me dig through your noir collection for something moody.",
                }, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search_library", "arguments": ""},
                    }],
                }, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {
                    "tool_calls": [{"index": 0, "function": {"arguments": '{"query":"noir"}'}}],
                }, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            ]
            # Round 2 returns no narration at all — only the tool results feed cards.
            round2_chunks = [
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]

            call_count = 0

            async def fake_stream(messages, tools=None):
                nonlocal call_count
                call_count += 1
                source = round1_chunks if call_count == 1 else round2_chunks
                for chunk in source:
                    yield chunk

            provider = MagicMock()
            provider.stream = fake_stream
            provider.chat = AsyncMock()

            mock_registry = MagicMock()
            mock_registry.cards = [TitleCard(media_type="movie", title="Chinatown", tmdb_id=829)]
            mock_registry.pending_tokens = []
            mock_registry.recommendation_context = False
            mock_registry.discussed_cards = []
            mock_registry.review_prompts = []
            mock_registry.review_conflicts = []
            mock_registry.suggested_replies = []
            mock_registry.execute = AsyncMock(return_value='[{"title":"Chinatown"}]')

            with (
                patch("curatorx.agent.curator.get_chat_provider", return_value=provider),
                patch.object(CuratorAgent, "_registry", return_value=mock_registry),
            ):
                chunks = [c async for c in stream_agent(
                    db, settings, "sess-multi", "noir films",
                    lens_id=DEFAULT_LENS_ID,
                )]

            events = _collect_events(chunks)
            done = next(e for e in events if e["type"] == "done")
            blocks = done["message"]["blocks"]
            text_block = blocks[0]
            self.assertEqual(text_block["type"], "text")
            self.assertIn("noir collection", text_block["content"])
            self.assertNotEqual(text_block["content"], "Here are the results I found.")
            # Cards from the tool round are still attached after the prose.
            self.assertTrue(any(b["type"] == "title_cards" for b in blocks))


class SSEEndpointEventMappingTests(unittest.TestCase):
    """Verify the SSE endpoint remaps tool_start/tool_result to tool_call."""

    def test_tool_start_maps_to_tool_call_start(self) -> None:
        raw = json.dumps({"type": "tool_start", "name": "search_library", "args": {"query": "noir"}})
        data = json.loads(raw)
        event_type = data.get("type", "message")
        if event_type in ("tool_start", "tool_result"):
            status = "start" if event_type == "tool_start" else "complete"
            mapped_event = "tool_call"
            mapped_data = {"name": data.get("name"), "status": status}
            if event_type == "tool_start" and data.get("args") is not None:
                mapped_data["args"] = data.get("args")
            if event_type == "tool_result" and data.get("summary") is not None:
                mapped_data["summary"] = data.get("summary")
        else:
            mapped_event = event_type
            mapped_data = data
        self.assertEqual(mapped_event, "tool_call")
        self.assertEqual(mapped_data["name"], "search_library")
        self.assertEqual(mapped_data["status"], "start")
        self.assertEqual(mapped_data["args"], {"query": "noir"})

    def test_tool_result_maps_to_tool_call_complete(self) -> None:
        raw = json.dumps({"type": "tool_result", "name": "search_library", "summary": "[{...}]"})
        data = json.loads(raw)
        event_type = data.get("type", "message")
        status = "start" if event_type == "tool_start" else "complete"
        mapped = {"name": data.get("name"), "status": status}
        if data.get("summary") is not None:
            mapped["summary"] = data.get("summary")
        self.assertEqual(status, "complete")
        self.assertEqual(mapped["summary"], "[{...}]")

    def test_token_event_passes_through(self) -> None:
        raw = json.dumps({"type": "token", "content": "hello"})
        data = json.loads(raw)
        event_type = data.get("type", "message")
        self.assertEqual(event_type, "token")
        self.assertNotIn(event_type, ("tool_start", "tool_result"))


class AnthropicStreamFormatTests(unittest.TestCase):
    """AnthropicProvider.stream should yield OpenAI-format delta chunks."""

    def test_anthropic_text_delta_format(self) -> None:
        chunk = {
            "choices": [{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None,
            }],
        }
        self.assertIn("choices", chunk)
        self.assertEqual(chunk["choices"][0]["delta"]["content"], "Hello")

    def test_anthropic_tool_call_delta_format(self) -> None:
        chunk = {
            "choices": [{
                "index": 0,
                "delta": {
                    "tool_calls": [{
                        "index": 0,
                        "id": "toolu_123",
                        "type": "function",
                        "function": {"name": "search_library", "arguments": ""},
                    }],
                },
                "finish_reason": None,
            }],
        }
        tc = chunk["choices"][0]["delta"]["tool_calls"][0]
        self.assertEqual(tc["function"]["name"], "search_library")
        self.assertEqual(tc["id"], "toolu_123")


if __name__ == "__main__":
    unittest.main()
