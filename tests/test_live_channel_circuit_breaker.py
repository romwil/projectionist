"""Live Channels / connector pollers share the scheduler circuit breaker."""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from projectionist.circuit_breaker import (
    QUARANTINE_THRESHOLD,
    CircuitOpenError,
    host_circuits,
    reset_host_circuits,
)
from projectionist.config_store import Settings
from projectionist.connectors.http import request_json
from projectionist.library.db import Database
from projectionist.live_channels.stream_warm import StreamWarmScheduler
from projectionist.watch_tracker.live_sessions import (
    IDLE_POLL_SECONDS,
    LiveSessionPoller,
    poll_interval_seconds,
)


class HostCircuitHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def test_unreachable_host_opens_breaker_and_skips_urlopen(self) -> None:
        calls = {"n": 0}

        def boom(*_args, **_kwargs):
            calls["n"] += 1
            raise urllib.error.URLError("connection refused")

        url = "http://tunarr.test:8000/api/channels"
        with patch("urllib.request.urlopen", side_effect=boom):
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(RuntimeError):
                    request_json(url)
            with self.assertRaises(CircuitOpenError) as raised:
                request_json(url)

        self.assertEqual(calls["n"], QUARANTINE_THRESHOLD)
        self.assertIn("tunarr.test:8000", str(raised.exception))
        self.assertTrue(host_circuits.is_open(url))

    def test_http_503_trips_breaker_but_404_does_not(self) -> None:
        def http_error(code: int):
            def _raise(req, timeout=30):  # noqa: ARG001
                raise urllib.error.HTTPError(
                    getattr(req, "full_url", "http://plex.test:32400/"),
                    code,
                    "err",
                    hdrs={},  # type: ignore[arg-type]
                    fp=BytesIO(b"nope"),
                )

            return _raise

        plex = "http://plex.test:32400/status/sessions"
        with patch("urllib.request.urlopen", side_effect=http_error(404)):
            for _ in range(QUARANTINE_THRESHOLD + 2):
                with self.assertRaises(RuntimeError):
                    request_json(plex)
        self.assertFalse(host_circuits.is_open(plex))

        reset_host_circuits()
        with patch("urllib.request.urlopen", side_effect=http_error(503)):
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(RuntimeError):
                    request_json(plex)
            with self.assertRaises(CircuitOpenError):
                request_json(plex)
        self.assertTrue(host_circuits.is_open(plex))

    def test_hosts_do_not_share_a_breaker(self) -> None:
        plex = "http://plex.test:32400/status/sessions"
        tunarr = "http://tunarr.test:8000/api/channels"
        for _ in range(QUARANTINE_THRESHOLD):
            host_circuits.record_failure(plex, "down")
        self.assertTrue(host_circuits.is_open(plex))
        self.assertFalse(host_circuits.is_open(tunarr))

    def test_bypass_still_hits_the_socket_when_open(self) -> None:
        from projectionist.circuit_breaker import bypass_host_circuits

        url = "http://tunarr.test:8000/api/version"
        for _ in range(QUARANTINE_THRESHOLD):
            host_circuits.record_failure(url, "down")
        calls = {"n": 0}

        class _Resp:
            def read(self, _n: int = -1) -> bytes:
                return b'{"tunarr":"1"}'

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def ok(*_args, **_kwargs):
            calls["n"] += 1
            return _Resp()

        with patch("urllib.request.urlopen", side_effect=ok):
            with self.assertRaises(CircuitOpenError):
                request_json(url)
            with bypass_host_circuits():
                payload = request_json(url)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(payload, {"tunarr": "1"})
        self.assertFalse(host_circuits.is_open(url))


class LiveSessionPollerCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "sessions.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        reset_host_circuits()

    def test_open_breaker_skips_plex_client_and_backs_off(self) -> None:
        url = "http://plex.test:32400"
        for _ in range(QUARANTINE_THRESHOLD):
            host_circuits.record_failure(url, "unreachable")
        settings = Settings(plex_url=url, plex_token="secret-token")
        with patch("projectionist.watch_tracker.live_sessions.PlexClient") as mocked:
            result = LiveSessionPoller.poll_once(self.db, settings)

        mocked.assert_not_called()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["reason"], "circuit_open")
        self.assertGreaterEqual(poll_interval_seconds(result), IDLE_POLL_SECONDS)
        self.assertGreaterEqual(int(result["circuit_remaining_seconds"]), IDLE_POLL_SECONDS)


class StreamWarmCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def _settings(self, url: str = "http://tunarr.test:8000") -> SimpleNamespace:
        return SimpleNamespace(
            features=SimpleNamespace(live_channels_enabled=True),
            tunarr=SimpleNamespace(url=url),
        )

    def test_open_breaker_skips_prepare_and_backs_off(self) -> None:
        url = "http://tunarr.test:8000"
        for _ in range(QUARANTINE_THRESHOLD):
            host_circuits.record_failure(url, "unreachable")
        scheduler = StreamWarmScheduler(Path("/tmp"))
        with (
            patch(
                "projectionist.live_channels.stream_warm.load_merged_settings",
                return_value=self._settings(url),
            ),
            patch(
                "projectionist.live_channels.publish.prepare_channels_for_playback"
            ) as prepare,
        ):
            delay = scheduler._tick()

        prepare.assert_not_called()
        self.assertEqual(scheduler._last_result.get("reason"), "circuit_open")
        self.assertTrue(scheduler._last_result.get("skipped"))
        self.assertGreaterEqual(delay, 60)

    def test_list_channels_failure_does_not_fall_through_to_prepare(self) -> None:
        url = "http://tunarr.test:8000"
        client = MagicMock()
        client.list_channels.side_effect = RuntimeError("connection refused")
        scheduler = StreamWarmScheduler(Path("/tmp"))
        with (
            patch(
                "projectionist.live_channels.stream_warm.load_merged_settings",
                return_value=self._settings(url),
            ),
            patch(
                "projectionist.live_channels.publish.tunarr_client_from_settings",
                return_value=client,
            ),
            patch(
                "projectionist.live_channels.publish.prepare_channels_for_playback"
            ) as prepare,
        ):
            delay = scheduler._tick()

        prepare.assert_not_called()
        self.assertEqual(scheduler._last_result.get("reason"), "tunarr_unreachable")
        self.assertGreaterEqual(delay, 60)


class WarmChannelStreamCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def test_repeated_503_opens_breaker_instead_of_polling_until_deadline(self) -> None:
        from projectionist.live_channels.publish import warm_channel_stream

        calls = {"n": 0}

        def http_503(req, timeout=8):  # noqa: ARG001
            calls["n"] += 1
            raise urllib.error.HTTPError(
                getattr(req, "full_url", "http://tunarr.test:8000/"),
                503,
                "Unavailable",
                hdrs={},  # type: ignore[arg-type]
                fp=BytesIO(b"down"),
            )

        client = MagicMock()
        client.base_url = "http://tunarr.test:8000"
        with patch("urllib.request.urlopen", side_effect=http_503):
            result = warm_channel_stream(client, "ch-1", timeout=45, pull_ts=False)

        self.assertFalse(result.get("ok"))
        # Two URLs per loop until the breaker opens (threshold=3), then fail-fast.
        self.assertLessEqual(calls["n"], QUARANTINE_THRESHOLD)
        self.assertTrue(host_circuits.is_open(client.base_url))


if __name__ == "__main__":
    unittest.main()
