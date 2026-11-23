"""One background ffmpeg or ffprobe at a time, at low priority.

Caption extraction, the playability confirmation, and an audio-only transcode
share this slot. A second background caller waits. A Play probe does not take
the slot. A play that needs ffmpeg does not wait out a background probe: on
this household the disk, the probe, and the first segment were all under a
second, and the 30 second miss was the wait for this slot. The command is
prefixed with ``nice`` and, when it is installed, ``ionice``.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import types
from typing import Any, Callable, Optional

_SLOT = threading.Lock()
_PLAY = threading.Event()
_HOLDER = threading.Lock()
_HOLDER_PROC: dict[str, Optional[subprocess.Popen]] = {"proc": None}


def media_command(argv: list[str]) -> list[str]:
    """Return ``argv`` behind idle scheduling, when those tools exist."""
    prefix: list[str] = []
    if shutil.which("nice"):
        prefix.extend(["nice", "-n", "19"])
    if shutil.which("ionice"):
        prefix.extend(["ionice", "-c", "3"])
    return prefix + list(argv)


def _remember(process: subprocess.Popen) -> None:
    with _HOLDER:
        _HOLDER_PROC["proc"] = process


def _forget(process: subprocess.Popen) -> None:
    with _HOLDER:
        if _HOLDER_PROC.get("proc") is process:
            _HOLDER_PROC["proc"] = None


def _stop_holder() -> None:
    with _HOLDER:
        process = _HOLDER_PROC.get("proc")
    if process is not None:
        _stop_quiet(process)


def _failed(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 1, "", "")


def _real_subprocess_run(runner: Any) -> bool:
    """True for the real ``subprocess.run``. A test double is not that function."""
    if not isinstance(runner, (types.FunctionType, types.BuiltinFunctionType)):
        return False
    return getattr(runner, "__module__", "") == "subprocess" and getattr(runner, "__name__", "") == "run"


def _run_subprocess(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run ``command`` until it exits, or until a play asks for the slot."""
    if _PLAY.is_set():
        return _failed(command)
    timeout = kwargs.pop("timeout", None)
    check = bool(kwargs.pop("check", False))
    text = bool(kwargs.pop("text", False))
    capture = bool(kwargs.pop("capture_output", False))
    out_pipe = subprocess.PIPE if capture else kwargs.pop("stdout", None)
    err_pipe = subprocess.PIPE if capture else kwargs.pop("stderr", None)
    cwd = kwargs.pop("cwd", None)
    kwargs.pop("input", None)
    proc = subprocess.Popen(command, stdout=out_pipe, stderr=err_pipe, cwd=cwd)
    _remember(proc)
    started = time.monotonic()
    try:
        while proc.poll() is None:
            if _PLAY.is_set():
                _stop_quiet(proc)
                return _failed(command)
            if timeout is not None and time.monotonic() - started > float(timeout):
                _stop_quiet(proc)
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.05)
        raw_out, raw_err = proc.communicate()
        if text:
            body: str | bytes = (
                raw_out.decode("utf-8", errors="replace") if isinstance(raw_out, bytes) else (raw_out or "")
            )
            errors: str | bytes = (
                raw_err.decode("utf-8", errors="replace") if isinstance(raw_err, bytes) else (raw_err or "")
            )
        else:
            body = raw_out if raw_out is not None else b""
            errors = raw_err if raw_err is not None else b""
        result = subprocess.CompletedProcess(command, int(proc.returncode or 0), body, errors)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, command, body, errors)
        return result
    finally:
        _forget(proc)


def run_media_tool(argv: list[str], runner: Callable[..., Any], **kwargs: Any) -> Any:
    """Run one media tool. A play does not wait for this process to finish."""
    command = media_command(argv)
    real = _real_subprocess_run(runner)
    with _SLOT:
        if _PLAY.is_set() and real:
            return _failed(command)
        if real:
            return _run_subprocess(command, **kwargs)
        return runner(command, **kwargs)


def run_prepared_command(command: list[str], runner: Callable[..., Any], **kwargs: Any) -> Any:
    """Run a command that is already prefixed. One heavy process at a time."""
    real = _real_subprocess_run(runner)
    with _SLOT:
        if _PLAY.is_set() and real:
            return _failed(list(command))
        if real:
            return _run_subprocess(list(command), **kwargs)
        return runner(list(command), **kwargs)


def spawn_heavy(
    argv: list[str],
    *,
    cwd: str,
    still_wanted: Callable[[], bool],
    attach: Callable[[subprocess.Popen], bool],
) -> None:
    """Start one heavy ffmpeg on the shared slot and hold the slot until it exits.

    The caller returns immediately. A background probe already in the slot is
    stopped so this play can start. The process starts only if ``still_wanted``
    is still true. ``attach`` receives the process and returns false when the
    session was cancelled, in which case the process is stopped. A Play probe
    never calls this.
    """
    command = media_command(argv)

    def work() -> None:
        _PLAY.set()
        _stop_holder()
        with _SLOT:
            try:
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
            finally:
                _PLAY.clear()

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
