"""Tests for Radarr/Sonarr error helpers."""

from __future__ import annotations

import json
import unittest

from projectionist.connectors.arr_errors import (
    ArrPathConflictError,
    ArrTitleExistsError,
    ArrTitleNotFoundError,
    arr_exists_error_code,
    classify_radarr_add_error,
    classify_radarr_catalog,
    folder_path_from_arr_error,
    format_arr_http_error,
    is_arr_not_found_error,
    is_arr_path_conflict_error,
)
from projectionist.connectors.radarr import RadarrMovie


PATH_VALIDATOR_HTTP = (
    "HTTP 400 from http://10.10.1.210/api/v3/movie: "
    + json.dumps(
        [
            {
                "propertyName": "Path",
                "errorMessage": (
                    "Path '/movies/Presence (2025)' is already configured "
                    "for an existing movie"
                ),
                "attemptedValue": "/movies/Presence (2025)",
                "severity": "error",
                "errorCode": "MoviePathValidator",
                "formattedMessageArguments": [],
                "formattedMessagePlaceholderValues": {
                    "path": "/movies/Presence (2025)"
                },
            }
        ]
    )
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

    def test_movie_path_validator_is_not_same_tmdb_exists(self) -> None:
        self.assertFalse(arr_exists_error_code(PATH_VALIDATOR_HTTP, movie=True))
        self.assertTrue(is_arr_path_conflict_error(RuntimeError(PATH_VALIDATOR_HTTP)))

    def test_folder_path_from_movie_path_validator(self) -> None:
        self.assertEqual(
            folder_path_from_arr_error(RuntimeError(PATH_VALIDATOR_HTTP)),
            "/movies/Presence (2025)",
        )

    def test_format_path_validator_never_dumps_radarr_placeholders(self) -> None:
        formatted = format_arr_http_error(RuntimeError(PATH_VALIDATOR_HTTP))
        self.assertNotIn("formattedMessagePlaceholderValues", formatted)
        self.assertNotIn("errorCode", formatted)
        self.assertNotIn("HTTP 400", formatted)

    def test_catalog_same_tmdb_is_already(self) -> None:
        occupant = RadarrMovie(
            id=9,
            title="Presence",
            year=2025,
            tmdb_id=1388150,
            monitored=True,
            has_file=True,
            folder_path="/movies/Presence (2025)",
        )
        classified = classify_radarr_catalog(
            intended_tmdb_id=1388150,
            intended_title="Presence",
            intended_path="/movies/Presence (2025)",
            by_tmdb=occupant,
        )
        self.assertIsNotNone(classified)
        assert classified is not None
        self.assertEqual(classified.kind, "already")
        self.assertIn("Already in Radarr", classified.message)
        self.assertNotIn("formattedMessagePlaceholderValues", classified.message)

    def test_catalog_path_taken_by_different_tmdb_is_conflict(self) -> None:
        occupant = RadarrMovie(
            id=9,
            title="Presence",
            year=2025,
            tmdb_id=111,
            monitored=True,
            has_file=True,
            folder_path="/movies/Presence (2025)",
        )
        classified = classify_radarr_catalog(
            intended_tmdb_id=1388150,
            intended_title="Presence",
            intended_path="/movies/Presence (2025)",
            by_path=occupant,
        )
        self.assertIsNotNone(classified)
        assert classified is not None
        self.assertEqual(classified.kind, "path_conflict")
        self.assertIn("Path conflict", classified.message)
        self.assertIn("1388150", classified.message)
        self.assertIn("111", classified.message)
        self.assertNotIn("formattedMessagePlaceholderValues", classified.message)

    def test_catalog_miss_means_proceed(self) -> None:
        self.assertIsNone(
            classify_radarr_catalog(
                intended_tmdb_id=1388150,
                intended_title="Presence",
                intended_path="/movies/Presence (2025)",
            )
        )

    def test_http_path_validator_same_occupant_tmdb_is_already(self) -> None:
        occupant = RadarrMovie(
            id=9,
            title="Presence",
            year=2025,
            tmdb_id=1388150,
            monitored=True,
            has_file=True,
            folder_path="/movies/Presence (2025)",
        )
        classified = classify_radarr_add_error(
            RuntimeError(PATH_VALIDATOR_HTTP),
            intended_tmdb_id=1388150,
            intended_title="Presence",
            occupant=occupant,
        )
        self.assertEqual(classified.kind, "already")

    def test_http_path_validator_different_occupant_is_conflict(self) -> None:
        occupant = RadarrMovie(
            id=9,
            title="Presence",
            year=2025,
            tmdb_id=111,
            monitored=True,
            has_file=True,
            folder_path="/movies/Presence (2025)",
        )
        classified = classify_radarr_add_error(
            RuntimeError(PATH_VALIDATOR_HTTP),
            intended_tmdb_id=1388150,
            intended_title="Presence",
            occupant=occupant,
        )
        self.assertEqual(classified.kind, "path_conflict")
        self.assertNotIn("{", classified.message)

    def test_http_path_validator_without_occupant_is_still_conflict(self) -> None:
        classified = classify_radarr_add_error(
            RuntimeError(PATH_VALIDATOR_HTTP),
            intended_tmdb_id=1388150,
            intended_title="Presence",
        )
        self.assertEqual(classified.kind, "path_conflict")
        self.assertIn("/movies/Presence (2025)", classified.message)

    def test_movie_exists_validator_is_already(self) -> None:
        raw = (
            "HTTP 400 from http://radarr/api/v3/movie: "
            '[{"errorCode":"MovieExistsValidator","errorMessage":"This movie has already been added"}]'
        )
        classified = classify_radarr_add_error(
            RuntimeError(raw),
            intended_tmdb_id=35669,
            intended_title="Existing Movie",
        )
        self.assertEqual(classified.kind, "already")
        self.assertIn("Already in Radarr", classified.message)

    def test_title_exists_error_is_already(self) -> None:
        classified = classify_radarr_add_error(
            ArrTitleExistsError("Radarr", title="Moon", external_id=17431, arr_id=3)
        )
        self.assertEqual(classified.kind, "already")

    def test_path_conflict_error_is_conflict(self) -> None:
        classified = classify_radarr_add_error(
            ArrPathConflictError(
                path="/movies/Presence (2025)",
                intended_title="Presence",
                intended_tmdb_id=1388150,
                occupant_title="Presence",
                occupant_tmdb_id=111,
            )
        )
        self.assertEqual(classified.kind, "path_conflict")

    def test_unrelated_http_error_stays_error_without_json_dump(self) -> None:
        raw = (
            "HTTP 401 from http://10.10.1.210/api/v3/movie: "
            '{"error":"Unauthorized"}'
        )
        classified = classify_radarr_add_error(RuntimeError(raw))
        self.assertEqual(classified.kind, "error")
        self.assertNotIn("formattedMessagePlaceholderValues", classified.message)
        self.assertNotIn("{", classified.message)


if __name__ == "__main__":
    unittest.main()
