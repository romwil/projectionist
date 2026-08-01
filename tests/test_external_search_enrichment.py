"""Tests for TVDB enrichment and Sonarr fallback on gap/show cards."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from projectionist.config_store import Settings
from projectionist.library.external_search import (
    _enrich_show_external_ids,
    _sonarr_resolve_tvdb_id,
    _tmdb_card,
)


class ExternalShowEnrichmentTests(unittest.TestCase):
    def test_tmdb_card_blocks_show_without_tvdb(self) -> None:
        tmdb = MagicMock()
        tmdb.poster_url.return_value = ""
        tmdb.backdrop_url.return_value = ""
        card = _tmdb_card(
            {"id": 221508, "name": "Back in Time for the Corner Shop", "first_air_date": "2023-03-07"},
            "show",
            tmdb,
        )
        self.assertIsNone(card.tvdb_id)
        self.assertIn("TVDB", card.add_blocked_reason)

    def test_tmdb_card_clears_block_when_tvdb_present(self) -> None:
        tmdb = MagicMock()
        tmdb.poster_url.return_value = ""
        tmdb.backdrop_url.return_value = ""
        card = _tmdb_card(
            {
                "id": 99646,
                "name": "Back in Time for the Corner Shop",
                "first_air_date": "2020-02-25",
                "external_ids": {"tvdb_id": 377033},
            },
            "show",
            tmdb,
        )
        self.assertEqual(card.tvdb_id, 377033)
        self.assertEqual(card.add_blocked_reason, "")

    def test_enrich_uses_sonarr_lookup_when_tmdb_lacks_tvdb(self) -> None:
        tmdb = MagicMock()
        tmdb.tv_details.return_value = {
            "id": 221508,
            "name": "Back in Time for the Corner Shop",
            "first_air_date": "2023-03-07",
            "external_ids": {"tvdb_id": None},
        }
        settings = Settings(sonarr_url="http://sonarr.test", sonarr_api_key="key")
        with patch("projectionist.connectors.sonarr.SonarrClient") as mock_cls:
            mock_cls.return_value.lookup.return_value = [
                {"title": "Back in Time for the Corner Shop", "year": 2023, "tvdbId": 999001, "tmdbId": 221508},
            ]
            enriched = _enrich_show_external_ids(
                {"id": 221508, "name": "Back in Time for the Corner Shop", "first_air_date": "2023-03-07"},
                tmdb,
                settings=settings,
            )
        self.assertEqual(enriched["external_ids"]["tvdb_id"], 999001)

    def test_sonarr_resolve_prefers_tmdb_id_match(self) -> None:
        settings = Settings(sonarr_url="http://sonarr.test", sonarr_api_key="key")
        with patch("projectionist.connectors.sonarr.SonarrClient") as mock_cls:
            mock_cls.return_value.lookup.return_value = [
                {"title": "Back in Time for the Corner Shop", "year": 2020, "tvdbId": 377033, "tmdbId": 99646},
                {"title": "Back in Time for the Corner Shop", "year": 2023, "tvdbId": 999001, "tmdbId": 221508},
            ]
            found = _sonarr_resolve_tvdb_id(
                settings,
                title="Back in Time for the Corner Shop",
                year=2023,
                tmdb_id=221508,
            )
        self.assertEqual(found, 999001)


if __name__ == "__main__":
    unittest.main()
