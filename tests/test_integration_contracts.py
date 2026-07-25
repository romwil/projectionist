"""Opt-in contract snapshot tests for Radarr / Sonarr / TMDB response shapes.

Default CI runs these against **recorded fixtures** under
``tests/fixtures/contracts/`` — no live upstreams required.

To re-record from a live host (optional):

.. code-block:: bash

    CURATORX_CONTRACT_RECORD=1 \\
      RADARR_URL=... RADARR_API_KEY=... \\
      SONARR_URL=... SONARR_API_KEY=... \\
      TMDB_API_KEY=... \\
      .venv/bin/python -m pytest tests/test_integration_contracts.py -k record -v

Live ping coverage (including TMDB) stays in ``tests/test_live_integrations.py``
behind ``CURATORX_LIVE_INTEGRATION=1``.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, Mapping
from unittest import mock

from curatorx.connectors.arr_errors import arr_exists_error_code
from curatorx.connectors.radarr import RadarrClient
from curatorx.connectors.sonarr import SonarrClient
from curatorx.connectors.tmdb import TMDBClient

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contracts"
_RECORD = os.environ.get("CURATORX_CONTRACT_RECORD", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _load(name: str) -> Dict[str, Any]:
    path = FIXTURES / name
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise AssertionError(f"Fixture {name} must be a JSON object")
    return data


def _assert_keys(payload: Mapping[str, Any], required: set[str], *, label: str) -> None:
    missing = required - set(payload.keys())
    self_msg = f"{label} missing keys: {sorted(missing)}"
    if missing:
        raise AssertionError(self_msg)


class RadarrContractTests(unittest.TestCase):
    def test_lookup_response_shape(self) -> None:
        fixture = _load("radarr_lookup.json")
        items = fixture["response"]
        self.assertIsInstance(items, list)
        self.assertGreaterEqual(len(items), 1)
        movie = items[0]
        _assert_keys(movie, {"title", "tmdbId", "year"}, label="radarr lookup item")
        self.assertIsInstance(movie["title"], str)
        self.assertIsInstance(movie["tmdbId"], int)

        with mock.patch(
            "curatorx.connectors.radarr.request_json",
            return_value=items,
        ):
            client = RadarrClient("http://radarr.test", "key")
            results = client.lookup("matrix")
        self.assertEqual(len(results), 1)
        self.assertEqual(int(results[0]["tmdbId"]), 603)

    def test_add_exists_error_code(self) -> None:
        fixture = _load("radarr_add_error_exists.json")
        body = str(fixture["response_body"])
        self.assertTrue(arr_exists_error_code(body, movie=True))
        self.assertFalse(arr_exists_error_code(body, movie=False))


class SonarrContractTests(unittest.TestCase):
    def test_lookup_response_shape(self) -> None:
        fixture = _load("sonarr_lookup.json")
        items = fixture["response"]
        self.assertIsInstance(items, list)
        series = items[0]
        _assert_keys(series, {"title", "tvdbId", "year"}, label="sonarr lookup item")

        with mock.patch(
            "curatorx.connectors.sonarr.request_json",
            return_value=items,
        ):
            client = SonarrClient("http://sonarr.test", "key")
            results = client.lookup("breaking bad")
        self.assertEqual(int(results[0]["tvdbId"]), 81189)

    def test_add_exists_error_code(self) -> None:
        fixture = _load("sonarr_add_error_exists.json")
        body = str(fixture["response_body"])
        self.assertTrue(arr_exists_error_code(body, movie=False))
        self.assertFalse(arr_exists_error_code(body, movie=True))


class TmdbContractTests(unittest.TestCase):
    def test_search_movie_page_shape(self) -> None:
        fixture = _load("tmdb_search_movie.json")
        page = fixture["response"]
        _assert_keys(
            page,
            {"page", "results", "total_results"},
            label="tmdb search page",
        )
        self.assertIsInstance(page["results"], list)
        hit = page["results"][0]
        _assert_keys(hit, {"id", "title", "overview"}, label="tmdb search result")

        with mock.patch(
            "curatorx.connectors.tmdb.request_json",
            return_value=page,
        ):
            client = TMDBClient("fake-key")
            results = client.search_movie("matrix")
        self.assertEqual(int(results[0]["id"]), 603)

    def test_movie_details_shape(self) -> None:
        fixture = _load("tmdb_movie_details.json")
        details = fixture["response"]
        _assert_keys(
            details,
            {"id", "title", "overview", "release_date", "credits", "keywords"},
            label="tmdb movie details",
        )
        with mock.patch(
            "curatorx.connectors.tmdb.request_json",
            return_value=details,
        ):
            client = TMDBClient("fake-key")
            payload = client.movie_details(603)
        self.assertEqual(int(payload["id"]), 603)
        self.assertIn("cast", payload["credits"])


class ContractFixtureHygieneTests(unittest.TestCase):
    """Always runs — fixtures must exist for CI."""

    def test_all_expected_fixtures_present(self) -> None:
        expected = {
            "radarr_lookup.json",
            "radarr_add_error_exists.json",
            "sonarr_lookup.json",
            "sonarr_add_error_exists.json",
            "tmdb_search_movie.json",
            "tmdb_movie_details.json",
        }
        present = {path.name for path in FIXTURES.glob("*.json")}
        self.assertTrue(expected.issubset(present), f"missing {expected - present}")


@unittest.skipUnless(
    _RECORD,
    "Set CURATORX_CONTRACT_RECORD=1 plus service credentials to re-record fixtures",
)
class ContractRecordTests(unittest.TestCase):
    """Optional live re-record path — skipped in default CI."""

    def test_record_placeholder(self) -> None:
        self.skipTest(
            "Recording is operator-driven; update fixtures manually from live JSON "
            "or extend this class when automating capture."
        )


if __name__ == "__main__":
    unittest.main()
