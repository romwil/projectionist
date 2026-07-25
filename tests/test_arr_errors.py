"""Tests for Radarr/Sonarr error helpers."""

from __future__ import annotations

import unittest

from projectionist.connectors.arr_errors import (
    ArrTitleNotFoundError,
    format_arr_http_error,
    is_arr_not_found_error,
)


class ArrErrorHelperTests(unittest.TestCase):
    def test_format_arr_http_error_extracts_json_message(self) -> None:
        raw = (
            'HTTP 404 from http://radarr/api/v3/movie/76478: '
            '{"message":"Movie with ID 76478 does not exist","description":null}'
        )
        self.assertEqual(
            format_arr_http_error(RuntimeError(raw)),
            "Movie with ID 76478 does not exist",
        )

    def test_format_arr_http_error_strips_stack_trace(self) -> None:
        raw = (
            'HTTP 404 from http://radarr/api/v3/movie/9: {"message":"Movie with ID 9 does not exist"}\n'
            "   at NzbDrone.Core.Datastore.BasicRepository`1.Get(IDbConnection, Int32 id)"
        )
        self.assertEqual(
            format_arr_http_error(RuntimeError(raw)),
            "Movie with ID 9 does not exist",
        )

    def test_is_arr_not_found_error_detects_404_payload(self) -> None:
        error = RuntimeError('HTTP 404 from http://radarr: {"message":"Movie with ID 1 does not exist"}')
        self.assertTrue(is_arr_not_found_error(error))

    def test_arr_title_not_found_error_message(self) -> None:
        error = ArrTitleNotFoundError("Radarr", title="Rust", external_id=123)
        self.assertIn("Rust", str(error))
        self.assertIn("not in Radarr", str(error))


if __name__ == "__main__":
    unittest.main()
