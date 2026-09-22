"""Poll helpers for Sonarr-style admin execution snapshots."""

from __future__ import annotations

import time
from typing import Any, Dict

from projectionist.library.admin_execution import reset_admin_execution_for_tests


def reset_admin_jobs() -> None:
    reset_admin_execution_for_tests()


def wait_admin_job(client, status_path: str, *, timeout: float = 4.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    payload: Dict[str, Any] = {}
    while time.time() < deadline:
        resp = client.get(status_path)
        if resp.status_code != 200:
            time.sleep(0.02)
            continue
        payload = resp.json()
        if not payload.get("busy"):
            return payload
        time.sleep(0.02)
    raise AssertionError(f"{status_path} still busy: {payload}")
