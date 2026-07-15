"""BYOP LLM provider implementations."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Protocol, Sequence

import httpx

from curatorx.config_store import Settings, resolve_llm_base_url, resolve_llm_model


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider returns a structured API error."""


def _anthropic_message_content(content: Any) -> Any:
    """Use plain string content for simple messages (Anthropic API default)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return content
    return str(content or "")


def _parse_tool_call_input(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _convert_messages_for_anthropic(
    messages: List[Mapping[str, Any]],
) -> tuple[str, List[Dict[str, Any]]]:
    """Convert OpenAI-style chat messages to Anthropic Messages API format.

    - ``system`` messages are extracted to the top-level ``system`` parameter.
    - OpenAI ``tool`` role messages become ``user`` messages with ``tool_result`` blocks.
    - OpenAI assistant ``tool_calls`` become ``tool_use`` content blocks.
    """
    system_parts: List[str] = []
    converted: List[Dict[str, Any]] = []
    pending_tool_results: List[Dict[str, Any]] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            converted.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for message in messages:
        role = str(message.get("role") or "")
        if role == "system":
            flush_tool_results()
            text = str(message.get("content") or "")
            if text:
                system_parts.append(text)
            continue

        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(message.get("tool_call_id") or message.get("tool_use_id") or ""),
                    "content": str(message.get("content") or ""),
                }
            )
            continue

        flush_tool_results()

        if role == "assistant":
            tool_calls = message.get("tool_calls")
            if tool_calls:
                blocks: List[Dict[str, Any]] = []
                content = message.get("content")
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for call in tool_calls:
                    fn = call.get("function") or {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": str(call.get("id") or ""),
                            "name": str(fn.get("name") or ""),
                            "input": _parse_tool_call_input(fn.get("arguments")),
                        }
                    )
                converted.append({"role": "assistant", "content": blocks})
                continue

        if role in {"user", "assistant"}:
            converted.append(
                {
                    "role": role,
                    "content": _anthropic_message_content(message.get("content")),
                }
            )

    flush_tool_results()
    return "\n\n".join(system_parts), converted


def _normalize_anthropic_response(response: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert Anthropic Messages API payload to OpenAI chat completion shape."""
    if "choices" in response:
        return dict(response)

    content_blocks = response.get("content") or []
    if not isinstance(content_blocks, list):
        content_blocks = []

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )

    message: Dict[str, Any] = {"role": "assistant", "content": "".join(text_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls

    stop_reason = str(response.get("stop_reason") or "")
    finish_reason = "tool_calls" if tool_calls else stop_reason or "stop"

    return {
        "id": response.get("id"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "model": response.get("model"),
        "usage": response.get("usage"),
    }


def _format_openai_compatible_error(response: httpx.Response, base_url: str) -> str:
    host = base_url.rstrip("/") or "the configured LLM endpoint"
    if response.status_code == 401:
        return (
            f"Authentication failed (401) calling {host}. "
            "Check LLM provider and API key in Configuration."
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return f"LLM API error ({response.status_code}) calling {host}: {message}"
    detail = response.text.strip()
    if detail:
        return f"LLM API error ({response.status_code}) calling {host}: {detail}"
    return f"LLM API error ({response.status_code}) calling {host}"


def _format_anthropic_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        error_type = str(error.get("type") or "").strip()
        message = str(error.get("message") or "").strip()
        if response.status_code == 404 and error_type == "not_found_error":
            if message.lower().startswith("model:"):
                model_id = message.split(":", 1)[-1].strip()
                return (
                    f"Anthropic model not found: {model_id}. "
                    "Use a pinned model ID such as claude-sonnet-4-6 or claude-sonnet-4-20250514."
                )
            return (
                "Anthropic API endpoint or model not found. "
                "Check LLM_BASE_URL (use https://api.anthropic.com) and LLM_MODEL."
            )
        if message:
            return f"Anthropic API error ({response.status_code}): {message}"
    return f"Anthropic API error ({response.status_code}): {response.text.strip() or 'request failed'}"


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> List[float]: ...

    async def embed_many(self, texts: Sequence[str]) -> List[List[float]]: ...


class ChatProvider(Protocol):
    async def chat(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> Mapping[str, Any]: ...

    async def stream(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> AsyncIterator[Mapping[str, Any]]: ...


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> Mapping[str, Any]:
        body: Dict[str, Any] = {"model": self.model, "messages": list(messages)}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            if response.is_error:
                raise LLMProviderError(_format_openai_compatible_error(response, self.base_url))
            return response.json()

    async def stream(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> AsyncIterator[Mapping[str, Any]]:
        body: Dict[str, Any] = {"model": self.model, "messages": list(messages), "stream": True}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    yield json.loads(payload)


class OpenAIEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def embed(self, text: str) -> List[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": list(texts)},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data") or []
            ordered = sorted(rows, key=lambda row: int(row.get("index", 0)))
            if len(ordered) != len(texts):
                raise LLMProviderError(
                    f"Embedding API returned {len(ordered)} vectors for {len(texts)} inputs"
                )
            return [list(row["embedding"]) for row in ordered]


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.anthropic.com") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/").removesuffix("/v1")

    def _anthropic_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _anthropic_tools(self, tools: Optional[List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
        if not tools:
            return []
        return [
            {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "input_schema": tool["function"].get("parameters", {"type": "object", "properties": {}}),
            }
            for tool in tools
        ]

    def _anthropic_body(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
        *,
        stream: bool = False,
    ) -> Dict[str, Any]:
        system, converted = _convert_messages_for_anthropic(messages)
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": converted,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = self._anthropic_tools(tools)
        if stream:
            body["stream"] = True
        return body

    async def chat(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> Mapping[str, Any]:
        body = self._anthropic_body(messages, tools)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._anthropic_headers(),
                json=body,
            )
            if response.is_error:
                raise LLMProviderError(_format_anthropic_error(response))
            return _normalize_anthropic_response(response.json())

    async def stream(
        self,
        messages: List[Mapping[str, Any]],
        tools: Optional[List[Mapping[str, Any]]] = None,
    ) -> AsyncIterator[Mapping[str, Any]]:
        """Stream Anthropic Messages API, yielding OpenAI-format delta chunks.

        Each yielded dict matches the shape from ``OpenAICompatibleProvider.stream``
        so ``stream_agent`` can process both providers identically.  Tool-use blocks
        are emitted as ``tool_calls`` deltas (index-keyed) and text blocks as
        ``content`` deltas, with a final chunk carrying ``finish_reason``.
        """
        body = self._anthropic_body(messages, tools, stream=True)
        tool_call_index = -1

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._anthropic_headers(),
                json=body,
            ) as response:
                if response.is_error:
                    await response.aread()
                    raise LLMProviderError(_format_anthropic_error(response))

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")

                    if event_type == "content_block_start":
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            tool_call_index += 1
                            yield {
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "tool_calls": [{
                                            "index": tool_call_index,
                                            "id": block.get("id", ""),
                                            "type": "function",
                                            "function": {
                                                "name": block.get("name", ""),
                                                "arguments": "",
                                            },
                                        }],
                                    },
                                    "finish_reason": None,
                                }],
                            }

                    elif event_type == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield {
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": text},
                                        "finish_reason": None,
                                    }],
                                }
                        elif delta.get("type") == "input_json_delta":
                            partial = delta.get("partial_json", "")
                            if partial:
                                yield {
                                    "choices": [{
                                        "index": 0,
                                        "delta": {
                                            "tool_calls": [{
                                                "index": tool_call_index,
                                                "function": {"arguments": partial},
                                            }],
                                        },
                                        "finish_reason": None,
                                    }],
                                }

                    elif event_type == "message_delta":
                        stop = (event.get("delta") or {}).get("stop_reason")
                        finish = "tool_calls" if stop == "tool_use" else "stop"
                        yield {
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": finish,
                            }],
                        }

                    elif event_type == "error":
                        err = event.get("error") or {}
                        raise LLMProviderError(
                            f"Anthropic streaming error: {err.get('message', 'unknown')}"
                        )


def get_chat_provider(settings: Settings) -> ChatProvider:
    provider = settings.llm_provider.lower()
    model = resolve_llm_model(provider, settings.llm_model)
    if provider == "anthropic":
        base_url = resolve_llm_base_url(provider, settings.llm_base_url)
        return AnthropicProvider(settings.llm_api_key, model, base_url)
    base_url = resolve_llm_base_url(provider, settings.llm_base_url)
    return OpenAICompatibleProvider(base_url, settings.llm_api_key, model)


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    base_url = settings.llm_embedding_base_url or settings.llm_base_url or "https://api.openai.com/v1"
    return OpenAIEmbeddingProvider(base_url, settings.llm_api_key, settings.llm_embedding_model)
