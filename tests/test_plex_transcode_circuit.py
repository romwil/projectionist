"""One title's transcode-start timeout must not open the shared Plex circuit.

Marriage Story (HEVC Main 10, 3600×2160) sat on a library transcode start.
Timeouts during that start opened the one breaker keyed by the Plex host.
The next title could not play, and its subtitle list failed because that
breaker was open.
"""

from __future__ import annotations

import threading
import unittest
import urllib.error
from unittest.mock import patch
from projectionist.circuit_breaker import QUARANTINE_THRESHOLD, host_circuits, reset_host_circuits
from projectionist.connectors.http import request_xml
from projectionist.library.playback import (
    PlaybackError,
    PlaybackSession,
    fetch_plex_bytes,
    start_plex_hls,
    universal_start_url,
)


PLEX = "http://plex.test:32400"
MARRIAGE = "40984"
ZATOICHI = "218935"


def _start_url(rating_key: str) -> str:
    return universal_start_url(
        PLEX,
        rating_key,
        session_id=f"sess-{rating_key}",
        offset_seconds=0,
    )


class _Body:
    def __init__(self, body: bytes, *, url: str) -> None:
        self._body = body
        self.url = url
        self.status = 200
        self.headers = {"Content-Type": "application/xml"}

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class TranscodeStartCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def test_a_transcode_start_timeout_does_not_open_the_next_titles_breaker(self) -> None:
        """Three start timeouts are the host threshold. Subtitles and the next
        start must still reach Plex.
        """
        marriage = _start_url(MARRIAGE)
        zatoichi = _start_url(ZATOICHI)
        subtitles = f"{PLEX}/library/metadata/{ZATOICHI}"
        calls = {"subtitles": 0, "next_start": 0}

        def fake_open(request, timeout=30):  # noqa: ARG001
            url = str(getattr(request, "full_url", request) or "")
            if "start.m3u8" in url and MARRIAGE in url:
                raise TimeoutError("timed out")
            if url.startswith(subtitles):
                calls["subtitles"] += 1
                xml = b"<MediaContainer><Video ratingKey='218935'/></MediaContainer>"
                return _Body(xml, url=url)
            if "start.m3u8" in url and ZATOICHI in url:
                calls["next_start"] += 1
                return _Body(b"#EXTM3U\n", url=url)
            raise AssertionError(f"unexpected url {url}")

        with (
            patch("urllib.request.urlopen", side_effect=fake_open),
            patch("projectionist.library.playback.urlopen", side_effect=fake_open),
        ):
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(Exception):
                    request_xml(marriage, timeout=30)
            request_xml(subtitles, timeout=20)
            fetch_plex_bytes(zatoichi, timeout=30)

        self.assertFalse(host_circuits.is_open(PLEX))
        self.assertFalse(host_circuits.is_open(subtitles))
        self.assertEqual(calls["subtitles"], 1)
        self.assertEqual(calls["next_start"], 1)

    def test_timeouts_during_one_start_do_not_block_the_next_title(self) -> None:
        """While Marriage Story's start is still waiting, other Plex calls time
        out. Those timeouts must not open the breaker Zatoichi's playback and
        subtitles use.
        """
        marriage = _start_url(MARRIAGE)
        zatoichi = _start_url(ZATOICHI)
        sessions = f"{PLEX}/status/sessions"
        subtitles = f"{PLEX}/library/metadata/{ZATOICHI}"
        started = threading.Event()
        release = threading.Event()
        calls = {"subtitles": 0, "next_start": 0}

        def fake_open(request, timeout=30):  # noqa: ARG001
            url = str(getattr(request, "full_url", request) or "")
            if "start.m3u8" in url and MARRIAGE in url:
                started.set()
                self.assertTrue(release.wait(5), "start was not released")
                raise TimeoutError("timed out")
            if sessions in url:
                raise TimeoutError("timed out")
            if url.startswith(subtitles):
                calls["subtitles"] += 1
                return _Body(
                    b"<MediaContainer><Video ratingKey='218935'><Media><Part>"
                    b"<Stream streamType='3' id='1' codec='srt' languageCode='en'/>"
                    b"</Part></Media></Video></MediaContainer>",
                    url=url,
                )
            if "start.m3u8" in url and ZATOICHI in url:
                calls["next_start"] += 1
                return _Body(b"#EXTM3U\n", url=url)
            raise AssertionError(f"unexpected url {url}")

        with (
            patch("urllib.request.urlopen", side_effect=fake_open),
            patch("projectionist.library.playback.urlopen", side_effect=fake_open),
        ):
            def _wait_for_start() -> None:
                try:
                    fetch_plex_bytes(marriage, timeout=120)
                except PlaybackError:
                    return

            worker = threading.Thread(target=_wait_for_start, daemon=True)
            worker.start()
            self.assertTrue(started.wait(2), "transcode start did not begin")
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(Exception):
                    request_xml(sessions, timeout=10)
            release.set()
            worker.join(5)
            self.assertFalse(worker.is_alive())
            request_xml(subtitles, timeout=20)
            fetch_plex_bytes(zatoichi, timeout=30)

        self.assertFalse(host_circuits.is_open(PLEX))
        self.assertFalse(host_circuits.is_open(subtitles))
        self.assertEqual(calls["subtitles"], 1)
        self.assertEqual(calls["next_start"], 1)

    def test_a_metadata_timeout_does_not_open_the_breaker_or_block_the_next_title(self) -> None:
        """Marriage Story's metadata lookups timed out while no start was held.

        Those three timeouts used to open the host breaker. The next title
        then could not ask Plex for anything. A failed /identity still opens it.
        """
        metadata = f"{PLEX}/library/metadata/{MARRIAGE}"
        identity = f"{PLEX}/identity"
        zatoichi = _start_url(ZATOICHI)
        calls = {"next": 0}

        def fake_open(request, timeout=30):  # noqa: ARG001
            url = str(getattr(request, "full_url", request) or "")
            if url.startswith(metadata):
                raise TimeoutError("timed out")
            if "/identity" in url:
                raise TimeoutError("timed out")
            if "start.m3u8" in url and ZATOICHI in url:
                calls["next"] += 1
                return _Body(b"#EXTM3U\n", url=url)
            raise AssertionError(f"unexpected url {url}")

        with (
            patch("urllib.request.urlopen", side_effect=fake_open),
            patch("projectionist.library.playback.urlopen", side_effect=fake_open),
        ):
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(Exception):
                    request_xml(metadata, timeout=8)
            self.assertFalse(host_circuits.is_open(PLEX))
            fetch_plex_bytes(zatoichi, timeout=30)
            self.assertEqual(calls["next"], 1)
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(Exception):
                    request_xml(identity, timeout=2)
            self.assertTrue(host_circuits.is_open(PLEX))

    def test_a_refused_connection_still_opens_the_shared_breaker(self) -> None:
        """A Plex that is not accepting connections is still an outage, even
        while one title's transcode start is waiting.
        """
        marriage = _start_url(MARRIAGE)
        sessions = f"{PLEX}/status/sessions"
        started = threading.Event()
        release = threading.Event()

        def fake_open(request, timeout=30):  # noqa: ARG001
            url = str(getattr(request, "full_url", request) or "")
            if "start.m3u8" in url:
                started.set()
                release.wait(5)
                raise TimeoutError("timed out")
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

        with (
            patch("urllib.request.urlopen", side_effect=fake_open),
            patch("projectionist.library.playback.urlopen", side_effect=fake_open),
        ):
            def _wait_for_start() -> None:
                try:
                    fetch_plex_bytes(marriage, timeout=120)
                except PlaybackError:
                    return

            worker = threading.Thread(target=_wait_for_start, daemon=True)
            worker.start()
            self.assertTrue(started.wait(2))
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(Exception):
                    request_xml(sessions, timeout=10)
            self.assertTrue(host_circuits.is_open(PLEX))
            with self.assertRaises(Exception):
                request_xml(f"{PLEX}/library/metadata/{ZATOICHI}", timeout=20)
            release.set()
            worker.join(5)

    def test_4k_or_hevc_10bit_start_waits_longer_than_a_normal_start(self) -> None:
        seen: dict[str, int] = {}

        def fake_fetch(url, **kwargs):
            kind = "heavy" if MARRIAGE in str(url) else "ordinary"
            seen[kind] = int(kwargs.get("timeout") or 0)
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        ordinary = PlaybackSession(
            session_id="sess-ordinary",
            user_id="owner",
            rating_key="1",
            plex_base=PLEX,
            token="t",
        )
        ordinary.video_codec = "h264"
        ordinary.video_height = 1080
        ordinary.video_width = 1920
        ordinary.video_bit_depth = 8
        marriage = PlaybackSession(
            session_id="sess-marriage",
            user_id="owner",
            rating_key=MARRIAGE,
            plex_base=PLEX,
            token="t",
        )
        marriage.video_codec = "hevc"
        marriage.video_profile = "Main 10"
        marriage.video_bit_depth = 10
        marriage.video_width = 3600
        marriage.video_height = 2160
        start_plex_hls(ordinary, offset_seconds=0, fetch=fake_fetch)
        start_plex_hls(marriage, offset_seconds=0, fetch=fake_fetch)
        self.assertLess(seen["ordinary"], 180)
        self.assertGreaterEqual(seen["heavy"], 240)
        self.assertGreater(seen["heavy"], seen["ordinary"])


if __name__ == "__main__":
    unittest.main()
