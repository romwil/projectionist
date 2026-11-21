"""One ffmpeg or ffprobe at a time, at low priority.

Caption extraction and the playability confirmation share this slot. A second
caller waits. The command is prefixed with ``nice`` and, when it is installed,
``ionice`` so a library walk does not compete with playback.
"""

from __future__ import annotations

import shutil
import threading
from typing import Any, Callable

_SLOT = threading.Lock()


def media_command(argv: list[str]) -> list[str]:
    """Return ``argv`` behind idle scheduling, when those tools exist."""
    prefix: list[str] = []
    if shutil.which("nice"):
        prefix.extend(["nice", "-n", "19"])
    if shutil.which("ionice"):
        prefix.extend(["ionice", "-c", "3"])
    return prefix + list(argv)


def run_media_tool(argv: list[str], runner: Callable[..., Any], **kwargs: Any) -> Any:
    """Run one media tool. The next caller waits until this process returns."""
    command = media_command(argv)
    with _SLOT:
        return runner(command, **kwargs)
