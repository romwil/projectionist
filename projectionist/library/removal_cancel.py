"""In-process cancel flags for a library removal stream.

Stop remaining titles that have not started. A title whose delete already
began is not rolled back.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}


def arm_removal_cancel(run_id: str) -> threading.Event:
    key = str(run_id or "").strip()
    if not key:
        raise ValueError("run_id is required")
    with _lock:
        event = _events.get(key)
        if event is None:
            event = threading.Event()
            _events[key] = event
        return event


def request_removal_cancel(run_id: str) -> bool:
    key = str(run_id or "").strip()
    if not key:
        return False
    arm_removal_cancel(key).set()
    return True


def clear_removal_cancel(run_id: str) -> None:
    key = str(run_id or "").strip()
    if not key:
        return
    with _lock:
        _events.pop(key, None)
