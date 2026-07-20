"""Tests for safe, provenance-aware title research."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from curatorx.config_store import Settings


class TitleResearchTests(unittest.TestCase):
    @patch("curatorx.research.title_research.TMDBClient")
    def test_person_research_and_filmography_comparison(self, tmdb_cls) -> None:
        from curatorx.research.title_research import compare_filmographies, research_person

        tmdb_cls.return_value.person_details.side_effect = [
            {
                "id": 1, "name": "One", "combined_credits": {
                    "cast": [{"id": 10, "media_type": "movie", "title": "Shared"}],
                    "crew": [{"id": 11, "media_type": "tv", "name": "Only One", "job": "Director"}],
                },
            },
            {
                "id": 2, "name": "Two", "combined_credits": {
                    "cast": [{"id": 10, "media_type": "movie", "title": "Shared"}],
                },
            },
        ]
        left = research_person(Settings(tmdb_api_key="configured"), name="One", tmdb_id=1)
        right = research_person(Settings(tmdb_api_key="configured"), name="Two", tmdb_id=2)
        comparison = compare_filmographies(left, right)
        self.assertEqual(len(left["filmography"]), 2)
        self.assertEqual(comparison["shared_credits"], 1)
        self.assertEqual(comparison["left_only"], 1)

    @patch("curatorx.research.title_research.TMDBClient")
    def test_company_research_requires_an_exact_provider_id(self, tmdb_cls) -> None:
        from curatorx.research.title_research import research_company

        no_id = research_company(Settings(tmdb_api_key="configured"), name="Ambiguous")
        self.assertEqual(no_id["sources_checked"]["tmdb"]["status"], "id_required")
        tmdb_cls.return_value.company_details.return_value = {
            "id": 42, "name": "Studio", "description": "Public facts",
        }
        result = research_company(Settings(tmdb_api_key="configured"), name="Studio", tmdb_id=42)
        self.assertEqual(result["identity"]["tmdb_id"], 42)
        self.assertEqual(result["sources_checked"]["tmdb"]["status"], "ok")

    @patch("curatorx.research.title_research.fetch_extract", return_value="Wikipedia context.")
    @patch("curatorx.research.title_research.TMDBClient")
    def test_research_combines_tmdb_and_wikipedia_with_provenance(self, tmdb_cls, wiki) -> None:
        from curatorx.research.title_research import research_title

        tmdb_cls.return_value.movie_details.return_value = {
            "id": 1725116,
            "title": "Simpsley",
            "release_date": "2026-07-03",
            "overview": "TMDB plot.",
            "tagline": "A Simpsons noir?",
            "credits": {
                "cast": [{"name": "Dan Castellaneta", "character": "Homer Simpsley"}],
                "crew": [{"name": "Debbie Bruce Mahan", "job": "Director"}],
            },
            "keywords": {"keywords": []},
            "external_ids": {"imdb_id": "tt43140642"},
        }

        result = research_title(
            Settings(tmdb_api_key="configured"),
            title="Simpsley",
            year=2026,
            media_type="movie",
            tmdb_id=1725116,
        )

        self.assertEqual(result["identity"]["title"], "Simpsley")
        self.assertEqual(result["plot"]["tmdb_overview"], "TMDB plot.")
        self.assertEqual(result["plot"]["wikipedia_extract"], "Wikipedia context.")
        self.assertEqual(result["credits"]["cast"][0]["name"], "Dan Castellaneta")
        self.assertEqual(result["sources_checked"]["tmdb"]["status"], "ok")
        self.assertEqual(result["sources_checked"]["wikipedia"]["status"], "ok")
        self.assertNotIn("api_key", str(result))
        wiki.assert_called_once_with("Simpsley", year=2026, media_type="movie")

    def test_research_reports_unconfigured_optional_sources(self) -> None:
        from curatorx.research.title_research import research_title

        result = research_title(Settings(), title="Unknown", media_type="movie")

        self.assertEqual(result["sources_checked"]["tmdb"]["status"], "not_configured")
        self.assertEqual(result["sources_checked"]["omdb"]["status"], "not_configured")
        self.assertEqual(result["sources_checked"]["tvdb"]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
