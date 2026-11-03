"""Which model a Youth chat may use. Never the household model.

The owner picks ``youth.chat_route``:

- ``none`` (default): no model call. The member sees ``notice`` instead.
- ``local``: an OpenAI-compatible server on the home network (Ollama, LM Studio,
  llama.cpp, vLLM). Anything that is not clearly local fails closed to a notice.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, replace
from typing import Any, Optional
from urllib.parse import urlparse

from projectionist.config_store import Settings

CHAT_ROUTE_NONE = "none"
CHAT_ROUTE_LOCAL = "local"
CHAT_ROUTES = (CHAT_ROUTE_NONE, CHAT_ROUTE_LOCAL)

_LOCAL_HOST_SUFFIXES = (
    ".local",
    ".lan",
    ".home",
    ".home.arpa",
    ".internal",
    ".localdomain",
    ".localhost",
)

YOUTH_CHAT_OFF_NOTICE = (
    "Chat with the curator is turned off for Youth accounts in this household, so "
    "nothing you type here is sent to an AI model. You can still browse, search, and "
    "play anything in your library. If you'd like to chat, ask the person who runs "
    "this server. They can connect a model that runs at home."
)

YOUTH_CHAT_LOCAL_NOT_READY_NOTICE = (
    "Chat for Youth accounts is set to use a model that runs at home, but it isn't "
    "connected yet. Nothing you typed was sent anywhere. Ask the person who runs this "
    "server to finish setting it up."
)

YOUTH_CHAT_LOCAL_NOT_LOCAL_NOTICE = (
    "Chat for Youth accounts is set to use a model at home, but the address it points "
    "to isn't on your home network, so your message wasn't sent. Ask the person who "
    "runs this server to check the Youth chat settings."
)


def normalize_chat_route(value: Any) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned if cleaned in CHAT_ROUTES else CHAT_ROUTE_NONE


def is_local_base_url(url: str) -> bool:
    """True only for loopback, private, link-local, or single-label / LAN hostnames."""
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return bool(address.is_loopback or address.is_private or address.is_link_local)
    if "." not in host:
        # Docker / Compose service names such as ``ollama``.
        return True
    return host.endswith(_LOCAL_HOST_SUFFIXES)


@dataclass(frozen=True)
class YouthChatRoute:
    """``settings`` is the model config to use, or None with a member-facing ``notice``."""

    route: str
    settings: Optional[Settings]
    notice: Optional[str]


def resolve_youth_chat_route(settings: Settings) -> YouthChatRoute:
    youth = getattr(settings, "youth", None)
    route = normalize_chat_route(getattr(youth, "chat_route", CHAT_ROUTE_NONE))
    if route != CHAT_ROUTE_LOCAL:
        return YouthChatRoute(CHAT_ROUTE_NONE, None, YOUTH_CHAT_OFF_NOTICE)
    base_url = str(getattr(youth, "local_base_url", "") or "").strip().rstrip("/")
    model = str(getattr(youth, "local_model", "") or "").strip()
    if not base_url or not model:
        return YouthChatRoute(route, None, YOUTH_CHAT_LOCAL_NOT_READY_NOTICE)
    if not is_local_base_url(base_url):
        return YouthChatRoute(route, None, YOUTH_CHAT_LOCAL_NOT_LOCAL_NOTICE)
    # "ollama" is the keyless OpenAI-compatible path. An empty key also keeps
    # semantic search on local hash embeddings instead of a cloud endpoint.
    routed = replace(
        settings,
        llm_provider="ollama",
        llm_base_url=base_url,
        llm_model=model,
        llm_api_key="",
        llm_embedding_base_url="",
    )
    return YouthChatRoute(route, routed, None)
