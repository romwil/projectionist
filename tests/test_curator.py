"""Tests for CuratorAgent response parsing and tool loops."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from projectionist.agent.curator import (
    CuratorAgent,
    _cards_for_response,
    _displayable_cards,
    _extract_text,
    _extract_tool_calls,
    _suggested_reply_block,
)
from projectionist.agent.tools import ToolRegistry
from projectionist.agent.providers import _normalize_anthropic_response
from projectionist.config_store import Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.models.schemas import TitleCard


class CuratorResponseParsingTests(unittest.TestCase):
    def test_extract_text_from_anthropic_json(self) -> None:
        response = {
            "content": [{"type": "text", "text": "Try these picks."}],
            "role": "assistant",
            "stop_reason": "end_turn",
        }
        self.assertEqual(_extract_text(response), "Try these picks.")

    def test_extract_text_from_normalized_anthropic_json(self) -> None:
        response = _normalize_anthropic_response(
            {
                "content": [{"type": "text", "text": "Normalized text."}],
                "stop_reason": "end_turn",
            }
        )
        self.assertEqual(_extract_text(response), "Normalized text.")

    def test_extract_tool_calls_from_anthropic_tool_use(self) -> None:
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "search_library",
                    "input": {"query": "noir"},
                }
            ],
            "stop_reason": "tool_use",
        }
        calls = _extract_tool_calls(response)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "search_library")


class CuratorAgentToolLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_anthropic_tool_use_runs_tools_not_empty_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="test-key",
                llm_model="claude-sonnet-4-6",
            )
            agent = CuratorAgent(db, settings)

            tool_response = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search_library",
                            "input": {"query": "noir"},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            )
            text_response = _normalize_anthropic_response(
                {
                    "content": [{"type": "text", "text": "Here are some noir picks."}],
                    "stop_reason": "end_turn",
                }
            )

            call_count = {"n": 0}

            async def mock_chat(messages, tools=None):
                call_count["n"] += 1
                return tool_response if call_count["n"] == 1 else text_response

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)

            result = await agent.run("session-1", "find noir movies")
            blocks = result["message"]["blocks"]
            text_blocks = [block for block in blocks if block.get("type") == "text"]

            self.assertGreaterEqual(call_count["n"], 2)
            self.assertTrue(text_blocks)
            self.assertIn("noir", text_blocks[0]["content"].lower())

    async def test_multi_round_tool_use_continues_until_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="test-key",
                llm_model="claude-sonnet-4-6",
            )
            agent = CuratorAgent(db, settings)

            tool_response = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search_library",
                            "input": {"query": "noir"},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            )
            text_response = _normalize_anthropic_response(
                {
                    "content": [{"type": "text", "text": "Done after two tool rounds."}],
                    "stop_reason": "end_turn",
                }
            )

            call_count = {"n": 0}

            async def mock_chat(messages, tools=None):
                call_count["n"] += 1
                if call_count["n"] < 3:
                    return tool_response
                return text_response

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)

            result = await agent.run("session-2", "find noir movies")
            text_blocks = [block for block in result["message"]["blocks"] if block.get("type") == "text"]

            self.assertEqual(call_count["n"], 3)
            self.assertEqual(text_blocks[0]["content"], "Done after two tool rounds.")

    async def test_round1_prose_preserved_when_final_round_has_no_text(self) -> None:
        """run() analog: prose narrated alongside a round-1 tool call must be
        preserved even when the final response returns no narration."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="test-key",
                llm_model="claude-sonnet-4-6",
            )
            agent = CuratorAgent(db, settings)

            # Round 1: narrate prose AND call a tool in the same response.
            prose_plus_tool_response = _normalize_anthropic_response(
                {
                    "content": [
                        {"type": "text", "text": "Let me search your noir collection for something moody."},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "search_library",
                            "input": {"query": "noir"},
                        },
                    ],
                    "stop_reason": "tool_use",
                }
            )
            # Round 2: only results, no narration at all.
            empty_text_response = _normalize_anthropic_response(
                {
                    "content": [{"type": "text", "text": ""}],
                    "stop_reason": "end_turn",
                }
            )

            call_count = {"n": 0}

            async def mock_chat(messages, tools=None):
                call_count["n"] += 1
                return prose_plus_tool_response if call_count["n"] == 1 else empty_text_response

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)

            result = await agent.run("session-prose", "find noir movies")
            text_blocks = [block for block in result["message"]["blocks"] if block.get("type") == "text"]

            self.assertGreaterEqual(call_count["n"], 2)
            self.assertTrue(text_blocks)
            self.assertIn("noir collection", text_blocks[0]["content"])
            self.assertNotEqual(text_blocks[0]["content"], "Here are the results I found.")

    async def test_stop_retrying_forces_tool_free_wrap_up(self) -> None:
        """Fail-closed gap payloads must end the tool loop with a prose-only turn."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="test-key",
                llm_model="claude-sonnet-4-6",
                tmdb_api_key="test-key",
            )
            agent = CuratorAgent(db, settings)

            tool_response = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_gaps",
                            "name": "find_collection_gaps",
                            "input": {"media_type": "movie", "genres": "NotAGenre"},
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            )
            text_response = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "I could not find confident matches for that theme.",
                        }
                    ],
                    "stop_reason": "end_turn",
                }
            )
            seen_tools: list[object] = []

            async def mock_chat(messages, tools=None):
                seen_tools.append(tools)
                if len(seen_tools) == 1:
                    return tool_response
                return text_response

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)

            with patch("projectionist.agent.tools.TMDBClient") as mock_tmdb_cls:
                mock_tmdb = mock_tmdb_cls.return_value
                mock_tmdb.genre_list_movies.return_value = [{"id": 99, "name": "Documentary"}]
                result = await agent.run("session-stop", "missing BBC science documentaries")
            text_blocks = [block for block in result["message"]["blocks"] if block.get("type") == "text"]

            self.assertEqual(len(seen_tools), 2)
            self.assertIsNotNone(seen_tools[0])
            self.assertIsNone(seen_tools[1])
            self.assertIn("could not find confident matches", text_blocks[0]["content"].lower())

    async def test_empty_gaps_fallback_keeps_tools_for_one_round(self) -> None:
        """First empty themed gaps keep tools; only stop_retrying strips them."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                llm_provider="anthropic",
                llm_api_key="test-key",
                llm_model="claude-sonnet-4-6",
                tmdb_api_key="test-key",
            )
            agent = CuratorAgent(db, settings)

            first_tool = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_gaps1",
                            "name": "find_collection_gaps",
                            "input": {
                                "media_type": "show",
                                "genres": "History",
                                "tv_type": "miniseries",
                            },
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            )
            second_tool = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_gaps2",
                            "name": "find_collection_gaps",
                            "input": {
                                "media_type": "show",
                                "genres": "History",
                                "tv_type": "miniseries",
                                "is_fallback_attempt": True,
                            },
                        }
                    ],
                    "stop_reason": "tool_use",
                }
            )
            text_response = _normalize_anthropic_response(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "Nothing confident matched after the broader History miniseries pass.",
                        }
                    ],
                    "stop_reason": "end_turn",
                }
            )
            seen_tools: list[object] = []

            async def mock_chat(messages, tools=None):
                seen_tools.append(tools)
                if len(seen_tools) == 1:
                    return first_tool
                if len(seen_tools) == 2:
                    return second_tool
                return text_response

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)

            with patch("projectionist.agent.tools.TMDBClient") as mock_tmdb_cls:
                mock_tmdb = mock_tmdb_cls.return_value
                mock_tmdb.genre_list_tv.return_value = [{"id": 36, "name": "History"}]
                mock_tmdb.discover_tv.return_value = []
                mock_tmdb.poster_url.return_value = ""
                mock_tmdb.backdrop_url.return_value = ""
                result = await agent.run("session-fallback", "recent history miniseries")
            text_blocks = [block for block in result["message"]["blocks"] if block.get("type") == "text"]

            self.assertEqual(len(seen_tools), 3)
            self.assertIsNotNone(seen_tools[0])
            self.assertIsNotNone(seen_tools[1])  # fallback round still has tools
            self.assertIsNone(seen_tools[2])  # stop_retrying wrap-up
            self.assertIn("nothing confident matched", text_blocks[0]["content"].lower())


class DisplayableCardsTests(unittest.TestCase):
    def test_filters_empty_placeholder_cards(self) -> None:
        cards = [
            TitleCard(media_type="movie", title="Blade Runner", tmdb_id=78),
            TitleCard(media_type="movie", title=""),
            TitleCard(media_type="movie", title="", tmdb_id=829),
        ]
        filtered = _displayable_cards(cards)
        self.assertEqual([card.title for card in filtered], ["Blade Runner", ""])
        self.assertEqual(filtered[1].tmdb_id, 829)

    def test_cards_for_response_drops_owned_in_recommendation_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            registry._recommendation_context = True
            registry._cards = [
                TitleCard(media_type="movie", title="Owned", tmdb_id=1, in_library=True),
                TitleCard(media_type="movie", title="Missing", tmdb_id=2, in_library=False),
            ]
            filtered = _cards_for_response(registry)
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].title, "Missing")

    def test_cards_for_response_drops_shows_without_tvdb_on_arr_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            registry._recommendation_context = True
            registry._cards = [
                TitleCard(media_type="show", title="Ready", tmdb_id=10, tvdb_id=20),
                TitleCard(media_type="show", title="No TVDB", tmdb_id=11),
                TitleCard(media_type="movie", title="Film", tmdb_id=12),
            ]
            filtered = _cards_for_response(registry)
            self.assertEqual([card.title for card in filtered], ["Ready", "Film"])

    def test_cards_for_response_keeps_discussed_show_without_tvdb_with_reason(self) -> None:
        """Gap rails must explain why a TMDB-only show cannot be added to Sonarr."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            registry._recommendation_context = True
            registry._discussed_cards = [
                TitleCard(media_type="show", title="Ready", tmdb_id=10, tvdb_id=20, year=2020),
                TitleCard(media_type="show", title="No TVDB", tmdb_id=11, year=2023),
            ]
            filtered = _cards_for_response(registry)
            self.assertEqual([card.title for card in filtered], ["Ready", "No TVDB"])
            blocked = next(card for card in filtered if card.title == "No TVDB")
            self.assertIn("TVDB", blocked.add_blocked_reason)

    def test_cards_for_response_prefers_discussed_missing_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            registry._recommendation_context = True
            registry._cards = [TitleCard(media_type="movie", title="Owned context", tmdb_id=1, in_library=True)]
            registry._discussed_cards = [
                TitleCard(media_type="movie", title="Missing discussion", tmdb_id=2, in_library=False),
                TitleCard(media_type="movie", title="Queued discussion", tmdb_id=3, in_radarr=True),
            ]
            filtered = _cards_for_response(registry)
            self.assertEqual([card.title for card in filtered], ["Missing discussion"])


class SuggestedRepliesTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_suggestions_are_sanitized_and_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            await registry.execute(
                "suggest_follow_ups",
                {
                    "replies": [
                        "Dive deeper into the gaps",
                        "Dive deeper into the gaps",
                        "/private/library/path",
                        "Show me where to watch these",
                        "Add these to a list",
                        "Compare the top two first",
                        "One more reply that should be capped",
                    ]
                },
            )
            self.assertEqual(
                registry.suggested_replies,
                [
                    "Dive deeper into the gaps",
                    "Show me where to watch these",
                    "Add these to a list",
                    "Compare the top two first",
                ],
            )

    async def test_gap_fallback_suggestions_are_emitted_when_agent_omits_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            registry._recommendation_context = True
            registry._discussed_cards = [TitleCard(media_type="movie", title="Missing", tmdb_id=2)]
            block = _suggested_reply_block(registry)
            self.assertEqual(block["type"], "suggested_replies")
            self.assertIn("Dive deeper into the gaps", block["payload"]["replies"])


if __name__ == "__main__":
    unittest.main()
