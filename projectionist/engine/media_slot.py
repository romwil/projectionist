"""One background ffmpeg or ffprobe at a time, at low priority.

Caption extraction, the playability confirmation, and an audio-only transcode
share this slot. A second background caller waits. A Play probe does not take
the slot, so a transcode cannot hold up the probe that decides the plan. The
command is prefixed with ``nice`` and, when it is installed, ``ionice``.
"""

from __future__ import annotations

import shutil
import subprocess
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


def run_prepared_command(command: list[str], runner: Callable[..., Any], **kwargs: Any) -> Any:
    """Run a command that is already prefixed. One heavy process at a time."""
    with _SLOT:
        return runner(list(command), **kwargs)


def spawn_heavy(
    argv: list[str],
    *,
    cwd: str,
    still_wanted: Callable[[], bool],
    attach: Callable[[subprocess.Popen], bool],
) -> None:
    """Start one heavy ffmpeg on the shared slot and hold the slot until it exits.

    The caller returns immediately. The process starts only after the slot is
    free, and only if ``still_wanted`` is still true. ``attach`` receives the
    process and returns false when the session was cancelled, in which case
    the process is stopped. A Play probe never calls this.
    """
    command = media_command(argv)

    def work() -> None:
        with _SLOT:
            if not still_wanted():
                return
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if not attach(process):
                _stop_quiet(process)
                return
            try:
                process.wait()
            except OSError:
                return

    threading.Thread(target=work, name="projectionist-heavy-ffmpeg", daemon=True).start()


def _stop_quiet(process: subprocess.Popen) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            return
