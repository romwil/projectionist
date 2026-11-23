"""A play must not sit behind a background probe.

Measured on the household file for the Dick Van Dyke episode, with the disks
already spinning: opening the file took 0.008s, ffprobe took 0.135s, and the
first fragmented output was on the pipe in 0.396s. The session that was not
ready within 30 seconds was waiting for this slot, not for a longer timeout.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from projectionist.engine.media_slot import run_media_tool, spawn_heavy
from projectionist.engine.session import _PLAYLIST_WAIT_S


def test_a_play_starts_while_a_background_probe_would_still_be_running(tmp_path: Path) -> None:
    assert _PLAYLIST_WAIT_S == 30.0
    release = threading.Event()

    def background() -> None:
        run_media_tool(["sleep", "30"], subprocess.run, timeout=30)
        release.set()

    worker = threading.Thread(target=background)
    worker.start()
    deadline = time.monotonic() + 2
    from projectionist.engine import media_slot

    while time.monotonic() < deadline and not media_slot._SLOT.locked():
        time.sleep(0.02)
    assert media_slot._SLOT.locked()

    marker = tmp_path / "play-started"
    started = time.monotonic()
    spawn_heavy(
        [sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ok')"],
        cwd=str(tmp_path),
        still_wanted=lambda: True,
        attach=lambda _process: True,
    )
    while time.monotonic() - started < 2 and not marker.is_file():
        time.sleep(0.02)
    elapsed = time.monotonic() - started
    assert marker.is_file(), "the play did not start while the background sleep held the slot"
    assert elapsed < 2, elapsed
    assert release.wait(2), "the background probe was not stopped for the play"
    worker.join(2)
    assert _PLAYLIST_WAIT_S == 30.0
