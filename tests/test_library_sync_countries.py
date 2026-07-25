"""Tests for TMDB country extraction during library sync."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from projectionist.connectors.plex import PlexLibraryItem
from projectionist.library.sync import _apply_tmdb_enrichment, _countries_from_tmdb, _row_from_plex_item


class LibrarySyncCountryTests(unittest.TestCase):
    def test_countries_from_production_countries(self) -> None:
        details = {
            "production_countries": [
                {"iso_3166_1": "US", "name": "United States of America"},
                {"iso_3166_1": "GB", "name": "United Kingdom"},
            ]
        }
        self.assertEqual(
            _countries_from_tmdb(details),
            ["United States of America", "United Kingdom"],
        )

    def test_countries_fallback_to_origin_country(self) -> None:
        details = {
            "production_countries": [],
            "origin_country": ["JP"],
        }
        self.assertEqual(_countries_from_tmdb(details), ["JP"])

    def test_row_from_plex_item_includes_added_at(self) -> None:
        from unittest.mock import MagicMock

        item = PlexLibraryItem(
            rating_key="501",
            media_type="movie",
            title="Synced Movie",
            year=2024,
            added_at=1_700_000_000,
        )
        plex = MagicMock()
        plex.thumb_url.side_effect = lambda path: path
        row = _row_from_plex_item(item, plex=plex, tmdb=None, fanart=None, in_radarr=False, in_sonarr=False)
        self.assertEqual(row["added_at"], 1_700_000_000)

    def test_row_from_plex_item_enriches_country_language_with_tmdb(self) -> None:
        item = PlexLibraryItem(
            rating_key="218935",
            media_type="movie",
            title="The 'Burbs",
            year=1989,
            tmdb_id="11974",
        )
        plex = MagicMock()
        plex.thumb_url.side_effect = lambda path: path
        tmdb = MagicMock()
        tmdb.movie_details.return_value = {
            "original_language": "en",
            "production_countries": [{"iso_3166_1": "US", "name": "United States of America"}],
            "keywords": {"keywords": []},
            "credits": {"cast": [], "crew": []},
        }
        row = _row_from_plex_item(item, plex=plex, tmdb=tmdb, fanart=None, in_radarr=False, in_sonarr=False)
        self.assertEqual(row["tmdb_id"], 11974)
        self.assertEqual(row["original_language"], "en")
        self.assertEqual(row["countries"], ["United States of America"])
        tmdb.movie_details.assert_called_once_with(11974)

    def test_apply_tmdb_enrichment_sets_country_language(self) -> None:
        row: dict = {}
        details = {
            "original_language": "fr",
            "production_countries": [{"name": "France"}],
        }
        _apply_tmdb_enrichment(row, details, media_type="movie")
        self.assertEqual(row["original_language"], "fr")
        self.assertEqual(row["countries"], ["France"])


if __name__ == "__main__":
    unittest.main()
