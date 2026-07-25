"""Async helpers to keep sync SQLite / CPU bursts off the event loop.

Chat SSE and other asyncio request handlers must not call blocking
``sqlite3`` or long pure-Python cosine scans on the loop thread. Use
``await run_db(fn, *args)`` for those hot paths only — not a thread-per-request
model for the whole app.
"""

from __future__ import annotations

import asyncio
from typing import Callable, TypeVar

T = TypeVar("T")


async def run_db(fn: Callable[..., T], /, *args, **kwargs) -> T:
    """Run ``fn(*args, **kwargs)`` in a worker thread (``asyncio.to_thread``)."""
    if kwargs:
        return await asyncio.to_thread(lambda: fn(*args, **kwargs))
    return await asyncio.to_thread(fn, *args)
