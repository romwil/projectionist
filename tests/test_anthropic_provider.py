"""Tests for Anthropic provider error handling."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from projectionist.agent.providers import (
    AnthropicProvider,
    LLMProviderError,
    _convert_messages_for_anthropic,
    _format_anthropic_error,
    _normalize_anthropic_response,
)


class AnthropicProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_format_anthropic_model_not_found_error(self) -> None:
        response = httpx.Response(
            404,
            json={
                "type": "error",
                "error": {
                    "type": "not_found_error",
                    "message": "model: claude-sonnet-4",
                },
            },
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        )
        message = _format_anthropic_error(response)
        self.assertIn("model not found", message.lower())
        self.assertIn("claude-sonnet-4", message)

    async def test_chat_sends_plain_string_content(self) -> None:
        provider = AnthropicProvider("test-key", "claude-sonnet-4-6")
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "pong"}],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("projectionist.agent.providers.httpx.AsyncClient", return_value=mock_client):
            await provider.chat([{"role": "user", "content": "ping"}])

        body = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(body["model"], "claude-sonnet-4-6")
        self.assertEqual(body["messages"], [{"role": "user", "content": "ping"}])

    async def test_chat_raises_provider_error_on_model_not_found(self) -> None:
        provider = AnthropicProvider("test-key", "claude-sonnet-4")
        mock_response = MagicMock()
        mock_response.is_error = True
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "type": "error",
            "error": {
                "type": "not_found_error",
                "message": "model: claude-sonnet-4",
            },
        }
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("projectionist.agent.providers.httpx.AsyncClient", return_value=mock_client):
            with self.assertRaises(LLMProviderError) as ctx:
                await provider.chat([{"role": "user", "content": "ping"}])

        self.assertIn("model not found", str(ctx.exception).lower())

    def test_convert_messages_strips_system_and_tool_roles(self) -> None:
        system, converted = _convert_messages_for_anthropic(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Find movies"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "function": {
                                "name": "search_library",
                                "arguments": '{"query": "noir"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_abc",
                    "content": "Found 3 titles",
                },
            ]
        )

        self.assertEqual(system, "You are helpful.")
        self.assertEqual(len(converted), 3)
        self.assertEqual(converted[0], {"role": "user", "content": "Find movies"})
        self.assertEqual(converted[1]["role"], "assistant")
        assistant_blocks = converted[1]["content"]
        self.assertEqual(assistant_blocks[0]["type"], "tool_use")
        self.assertEqual(assistant_blocks[0]["id"], "call_abc")
        self.assertEqual(assistant_blocks[0]["name"], "search_library")
        self.assertEqual(assistant_blocks[0]["input"], {"query": "noir"})
        self.assertEqual(converted[2]["role"], "user")
        self.assertEqual(converted[2]["content"][0]["type"], "tool_result")
        self.assertEqual(converted[2]["content"][0]["tool_use_id"], "call_abc")
        self.assertEqual(converted[2]["content"][0]["content"], "Found 3 titles")

    def test_convert_messages_batches_multiple_tool_results(self) -> None:
        _, converted = _convert_messages_for_anthropic(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "a", "arguments": "{}"}},
                        {"id": "call_2", "function": {"name": "b", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "result-a"},
                {"role": "tool", "tool_call_id": "call_2", "content": "result-b"},
            ]
        )

        self.assertEqual(len(converted), 2)
        tool_results = converted[1]["content"]
        self.assertEqual(len(tool_results), 2)
        self.assertEqual(tool_results[0]["tool_use_id"], "call_1")
        self.assertEqual(tool_results[1]["tool_use_id"], "call_2")

    async def test_chat_converts_tool_messages_without_400(self) -> None:
        provider = AnthropicProvider("test-key", "claude-sonnet-4-6")
        mock_response = MagicMock()
        mock_response.is_error = False
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Here are some noir picks."}],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)

        messages = [
            {"role": "system", "content": "Curator"},
            {"role": "user", "content": "Find noir"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_xyz",
                        "function": {
                            "name": "search_library",
                            "arguments": '{"query": "noir"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_xyz", "content": "3 results"},
        ]

        with patch("projectionist.agent.providers.httpx.AsyncClient", return_value=mock_client):
            result = await provider.chat(messages)

        body = mock_client.post.await_args.kwargs["json"]
        self.assertEqual(body["system"], "Curator")
        roles = [message["role"] for message in body["messages"]]
        self.assertNotIn("tool", roles)
        self.assertNotIn("system", roles)
        self.assertEqual(roles, ["user", "assistant", "user"])
        message = result["choices"][0]["message"]
        self.assertEqual(message["content"], "Here are some noir picks.")

    def test_normalize_anthropic_text_response(self) -> None:
        normalized = _normalize_anthropic_response(
            {
                "id": "msg_01",
                "content": [{"type": "text", "text": "Hello from Claude."}],
                "stop_reason": "end_turn",
            }
        )
        self.assertIn("choices", normalized)
        self.assertEqual(normalized["choices"][0]["message"]["content"], "Hello from Claude.")

    def test_normalize_anthropic_tool_use_response(self) -> None:
        normalized = _normalize_anthropic_response(
            {
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "search_library", "input": {"query": "noir"}},
                ],
                "stop_reason": "tool_use",
            }
        )
        message = normalized["choices"][0]["message"]
        self.assertEqual(message["content"], "")
        self.assertEqual(len(message["tool_calls"]), 1)
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "search_library")


if __name__ == "__main__":
    unittest.main()
