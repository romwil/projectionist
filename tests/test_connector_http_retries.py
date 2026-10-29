"""Jittered GET/HEAD retries for connector HTTP helpers (architecture review M3)."""

from __future__ import annotations

import urllib.error
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from io import BytesIO
from typing import Any, Optional
from unittest.mock import patch

import unittest

from projectionist.circuit_breaker import (
    QUARANTINE_THRESHOLD,
    CircuitOpenError,
    host_circuits,
    host_key,
    reset_host_circuits,
)
from projectionist.connectors.http import (
    _IDEMPOTENT_RETRY_ATTEMPTS,
    _RETRY_AFTER_CAP_S,
    _RETRY_BASE_DELAY_S,
    _execute_request,
    _parse_retry_after,
    _retry_after_from_error,
    request_json,
)


def _http_error(
    url: str,
    code: int,
    *,
    body: bytes = b"nope",
    headers: Optional[dict[str, str]] = None,
) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url,
        code,
        "err",
        hdrs=headers or {},  # type: ignore[arg-type]
        fp=BytesIO(body),
    )


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ParseRetryAfterTests(unittest.TestCase):
    def test_integer_seconds(self) -> None:
        self.assertEqual(_parse_retry_after("3"), 3.0)

    def test_caps_large_values(self) -> None:
        self.assertEqual(_parse_retry_after("3600"), _RETRY_AFTER_CAP_S)

    def test_rejects_negative_and_garbage(self) -> None:
        self.assertIsNone(_parse_retry_after("-1"))
        self.assertIsNone(_parse_retry_after("soon"))
        self.assertIsNone(_parse_retry_after(""))
        self.assertIsNone(_parse_retry_after(None))

    def test_http_date_in_the_future(self) -> None:
        when = datetime.now(timezone.utc) + timedelta(seconds=8)
        raw = formatdate(timeval=when.timestamp(), usegmt=True)
        delay = _parse_retry_after(raw)
        self.assertIsNotNone(delay)
        assert delay is not None
        self.assertGreaterEqual(delay, 6.0)
        self.assertLessEqual(delay, 8.5)

    def test_past_http_date_is_zero(self) -> None:
        when = datetime.now(timezone.utc) - timedelta(seconds=30)
        raw = formatdate(timeval=when.timestamp(), usegmt=True)
        self.assertEqual(_parse_retry_after(raw), 0.0)

    def test_naive_http_date_assumes_utc(self) -> None:
        self.assertEqual(_parse_retry_after("Wed, 01 Jan 2020 00:00:00"), 0.0)

    def test_far_future_http_date_is_capped(self) -> None:
        when = datetime.now(timezone.utc) + timedelta(days=7)
        raw = formatdate(timeval=when.timestamp(), usegmt=True)
        self.assertEqual(_parse_retry_after(raw), _RETRY_AFTER_CAP_S)

    def test_reads_lowercase_and_list_headers(self) -> None:
        url = "http://example.test/"
        lower = _http_error(url, 429, headers={"retry-after": "2"})
        self.assertEqual(_retry_after_from_error(lower), 2.0)
        listed = _http_error(url, 429, headers={"Retry-After": ["5"]})  # type: ignore[dict-item]
        self.assertEqual(_retry_after_from_error(listed), 5.0)
        missing = urllib.error.HTTPError(url, 429, "err", None, BytesIO(b""))
        self.assertIsNone(_retry_after_from_error(missing))


class ExecuteRequestRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def _run(
        self,
        url: str,
        *,
        method: str = "GET",
        side_effect: Any,
    ) -> tuple[bytes, Any, Any]:
        with (
            patch("urllib.request.urlopen", side_effect=side_effect) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
            patch("projectionist.connectors.http.random.uniform", side_effect=lambda a, b: b),
        ):
            body = _execute_request(
                url, method=method, headers=None, data=None, timeout=5
            )
        return body, opened, slept

    def test_get_retries_503_then_succeeds_without_breaker_failure(self) -> None:
        url = "http://plex.test:32400/status/sessions"
        calls = {"n": 0}

        def flaky(req, timeout=5):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(url, 503)
            return _Resp(b"ok")

        body, opened, slept = self._run(url, side_effect=flaky)
        self.assertEqual(body, b"ok")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_count, 1)
        self.assertEqual(slept.call_args[0][0], _RETRY_BASE_DELAY_S)
        self.assertFalse(host_circuits.is_open(url))
        self.assertEqual(host_circuits._breakers[host_key(url)].consecutive_failures, 0)

    def test_get_honors_retry_after_on_429(self) -> None:
        url = "http://tmdb.test/3/movie/1"
        calls = {"n": 0}

        def flaky(req, timeout=5):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(url, 429, headers={"Retry-After": "4"})
            return _Resp(b"{}")

        body, opened, slept = self._run(url, side_effect=flaky)
        self.assertEqual(body, b"{}")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_count, 1)
        delay = slept.call_args[0][0]
        self.assertGreaterEqual(delay, 4.0)
        self.assertLessEqual(delay, 4.25)

    def test_get_exhausts_retries_then_records_one_failure(self) -> None:
        url = "http://plex.test:32400/status/sessions"

        def always_503(req, timeout=5):  # noqa: ARG001
            raise _http_error(url, 503)

        with (
            patch("urllib.request.urlopen", side_effect=always_503) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
            patch("projectionist.connectors.http.random.uniform", side_effect=lambda a, b: b),
        ):
            with self.assertRaises(RuntimeError) as raised:
                _execute_request(url, method="GET", headers=None, data=None, timeout=5)

        self.assertIn("HTTP 503", str(raised.exception))
        self.assertEqual(opened.call_count, _IDEMPOTENT_RETRY_ATTEMPTS)
        self.assertEqual(slept.call_count, _IDEMPOTENT_RETRY_ATTEMPTS - 1)
        self.assertEqual(slept.call_args_list[0][0][0], _RETRY_BASE_DELAY_S)
        self.assertEqual(slept.call_args_list[1][0][0], _RETRY_BASE_DELAY_S * 2)
        self.assertFalse(host_circuits.is_open(url))
        self.assertEqual(host_circuits._breakers[host_key(url)].consecutive_failures, 1)

    def test_single_exhausted_get_does_not_trip_breaker(self) -> None:
        url = "http://plex.test:32400/library"
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=lambda *a, **k: (_ for _ in ()).throw(_http_error(url, 500)),
            ),
            patch("projectionist.connectors.http.time.sleep"),
        ):
            with self.assertRaises(RuntimeError):
                _execute_request(url, method="GET", headers=None, data=None, timeout=5)
        self.assertFalse(host_circuits.is_open(url))

    def test_head_retries_5xx(self) -> None:
        url = "http://tunarr.test:8000/api/version"
        calls = {"n": 0}

        def flaky(req, timeout=5):  # noqa: ARG001
            calls["n"] += 1
            self.assertEqual(req.get_method(), "HEAD")
            if calls["n"] < 2:
                raise _http_error(url, 502)
            return _Resp(b"")

        body, opened, slept = self._run(url, method="HEAD", side_effect=flaky)
        self.assertEqual(body, b"")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_count, 1)

    def test_get_does_not_retry_404(self) -> None:
        url = "http://plex.test:32400/missing"
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=_http_error(url, 404),
            ) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
        ):
            with self.assertRaises(RuntimeError) as raised:
                _execute_request(url, method="GET", headers=None, data=None, timeout=5)
        self.assertIn("HTTP 404", str(raised.exception))
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()
        self.assertFalse(host_circuits.is_open(url))

    def test_post_put_delete_never_retry_429_or_5xx(self) -> None:
        url = "http://radarr.test:7878/api/v3/command"
        for method, code in (("POST", 503), ("PUT", 429), ("DELETE", 500)):
            reset_host_circuits()
            with (
                patch(
                    "urllib.request.urlopen",
                    side_effect=_http_error(url, code),
                ) as opened,
                patch("projectionist.connectors.http.time.sleep") as slept,
            ):
                with self.assertRaises(RuntimeError):
                    _execute_request(url, method=method, headers=None, data=b"{}", timeout=5)
            self.assertEqual(opened.call_count, 1, msg=method)
            slept.assert_not_called()
            self.assertEqual(host_circuits._breakers[host_key(url)].consecutive_failures, 1)

    def test_timeout_is_not_retried(self) -> None:
        url = "http://plex.test:32400/slow"
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=TimeoutError("timed out"),
            ) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
        ):
            with self.assertRaises(RuntimeError):
                _execute_request(url, method="GET", headers=None, data=None, timeout=1)
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_urlerror_is_not_retried(self) -> None:
        url = "http://tunarr.test:8000/api/channels"
        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection refused"),
            ) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
        ):
            with self.assertRaises(RuntimeError):
                _execute_request(url, method="GET", headers=None, data=None, timeout=5)
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_quiet_503_still_retries_before_breaker_failure(self) -> None:
        url = "http://plex.test:32400/livetv/dvrs"

        def always_503(req, timeout=5):  # noqa: ARG001
            raise _http_error(url, 503)

        with (
            patch("urllib.request.urlopen", side_effect=always_503) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
        ):
            with self.assertRaises(RuntimeError):
                _execute_request(
                    url,
                    method="GET",
                    headers=None,
                    data=None,
                    timeout=5,
                    quiet_statuses=(503,),
                )
        self.assertEqual(opened.call_count, _IDEMPOTENT_RETRY_ATTEMPTS)
        self.assertEqual(slept.call_count, _IDEMPOTENT_RETRY_ATTEMPTS - 1)
        self.assertEqual(host_circuits._breakers[host_key(url)].consecutive_failures, 1)


class RequestJsonRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_host_circuits()

    def tearDown(self) -> None:
        reset_host_circuits()

    def test_get_retries_then_parses_json(self) -> None:
        url = "http://tautulli.test:8181/api/v2"
        calls = {"n": 0}

        def flaky(req, timeout=30):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise _http_error(url, 503)
            return _Resp(b'{"ok": true}')

        with (
            patch("urllib.request.urlopen", side_effect=flaky),
            patch("projectionist.connectors.http.time.sleep"),
        ):
            payload = request_json(url)

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(calls["n"], 2)
        self.assertFalse(host_circuits.is_open(url))

    def test_three_exhausted_gets_trip_breaker(self) -> None:
        url = "http://plex.test:32400/status/sessions"

        def always_503(req, timeout=30):  # noqa: ARG001
            raise _http_error(url, 503)

        with (
            patch("urllib.request.urlopen", side_effect=always_503) as opened,
            patch("projectionist.connectors.http.time.sleep"),
        ):
            for _ in range(QUARANTINE_THRESHOLD):
                with self.assertRaises(RuntimeError):
                    request_json(url)
            with self.assertRaises(CircuitOpenError):
                request_json(url)

        self.assertEqual(opened.call_count, QUARANTINE_THRESHOLD * _IDEMPOTENT_RETRY_ATTEMPTS)
        self.assertTrue(host_circuits.is_open(url))

    def test_post_json_does_not_retry(self) -> None:
        url = "http://sonarr.test:8989/api/v3/command"

        def always_503(req, timeout=30):  # noqa: ARG001
            raise _http_error(url, 503)

        with (
            patch("urllib.request.urlopen", side_effect=always_503) as opened,
            patch("projectionist.connectors.http.time.sleep") as slept,
        ):
            with self.assertRaises(RuntimeError):
                request_json(url, method="POST", body={"name": "RefreshSeries"})

        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()


if __name__ == "__main__":
    unittest.main()
