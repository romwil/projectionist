"""Tests for agent tools."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.agent.tools import (
    PLEX_COLLECTION_TOOL_NAMES,
    SEERR_TOOL_NAMES,
    TOOL_DEFINITIONS,
    ToolRegistry,
    _append_recommendation_cards,
    _card_to_tool_item,
    _rank_tmdb_search_results,
    build_system_prompt,
    build_tool_definitions,
)
from curatorx.config_store import FeatureFlags, Settings
from curatorx.connectors.arr_errors import ArrTitleNotFoundError
from curatorx.connectors.radarr import RadarrMovie
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.models.schemas import TitleCard


class ToolRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_remember_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("remember_preference", {"text": "loves 70s sci-fi"})
            self.assertIn("saved", result)
            self.assertIn("70s", build_system_prompt(db, lens_id=DEFAULT_LENS_ID))

    async def test_remember_preference_uses_agent_lens_not_active_lens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_lens("noir", "Noir Studies", "Hardboiled crime cinema")
            db.set_active_lens_id(DEFAULT_LENS_ID)

            registry = ToolRegistry(db, Settings(), "noir")
            result = await registry.execute("remember_preference", {"text": "loves neo-noir"})
            self.assertIn("saved", result)

            noir_taste = db.get_lens_taste_profile("noir")
            general_taste = db.get_lens_taste_profile(DEFAULT_LENS_ID)
            self.assertEqual(len(noir_taste), 1)
            self.assertIn("neo-noir", noir_taste[0]["cluster_tag"])
            self.assertEqual(len(general_taste), 0)
            self.assertIn("neo-noir", build_system_prompt(db, lens_id="noir"))

    async def test_analyze_watch_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Test Movie",
                    "genres": ["Sci-Fi"],
                    "view_count": 0,
                }
            )
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("analyze_watch_patterns", {})
            payload = json.loads(result)
            self.assertEqual(payload["unwatched_count"], 1)

    def test_tool_definitions_include_library_query_tools(self) -> None:
        names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
        for expected in (
            "query_library",
            "summarize_library",
            "get_library_overview",
            "get_facet_catalog",
            "find_similar_titles",
            "query_tv_episodes",
            "summarize_tv_progress",
            "search_tmdb",
            "set_recommendation_reasons",
            "get_title_detail",
            "explore_genre",
            "what_to_watch_tonight",
            "analyze_watch_patterns",
            "list_plex_collections",
            "create_plex_collection",
            "add_to_plex_collection",
            "get_user_reviews",
            "save_user_review",
            "suggest_titles_to_rate",
            "start_review_dialogue",
            "query_watchlist",
            "add_to_watchlist",
            "remove_from_watchlist",
            "curate_watchlist",
            "critique_watchlist",
            "upcoming_premieres",
        ):
            self.assertIn(expected, names)

    def test_build_tool_definitions_omits_disabled_features(self) -> None:
        disabled = Settings(
            features=FeatureFlags(
                seerr_enabled=False,
                plex_collections_enabled=False,
            )
        )
        names = {tool["function"]["name"] for tool in build_tool_definitions(disabled)}
        for omitted in PLEX_COLLECTION_TOOL_NAMES | SEERR_TOOL_NAMES:
            self.assertNotIn(omitted, names)
        self.assertIn("save_user_review", names)

    def test_build_tool_definitions_includes_enabled_features(self) -> None:
        enabled = Settings(
            features=FeatureFlags(
                seerr_enabled=True,
                plex_collections_enabled=True,
            )
        )
        names = {tool["function"]["name"] for tool in build_tool_definitions(enabled)}
        for expected in PLEX_COLLECTION_TOOL_NAMES | SEERR_TOOL_NAMES:
            self.assertIn(expected, names)

    async def test_save_user_review_returns_conflict_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(plex_url="http://plex.test", plex_token="token", sync_reviews_to_plex=True),
                DEFAULT_LENS_ID,
            )
            with patch(
                "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
                return_value=5,
            ), patch("curatorx.connectors.plex.PlexClient.set_user_rating"):
                result = await registry.execute(
                    "save_user_review",
                    {
                        "title": "Blade Runner",
                        "media_type": "movie",
                        "stars": 3,
                        "rating_key": "555",
                    },
                )
            payload = json.loads(result)
            self.assertTrue(payload["saved"])
            self.assertTrue(payload["plex_rating_conflict"])
            self.assertEqual(payload["code"], "plex_rating_conflict")
            self.assertEqual(payload["plex_stars"], 5)
            self.assertEqual(payload["submitted_stars"], 3)
            self.assertIn("replace_plex_rating=true", payload["message"])

    async def test_save_user_review_force_replace_overwrites_plex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(plex_url="http://plex.test", plex_token="token", sync_reviews_to_plex=True),
                DEFAULT_LENS_ID,
            )
            with patch(
                "curatorx.reviews.plex_sync.lookup_plex_user_rating_stars",
                return_value=5,
            ), patch("curatorx.connectors.plex.PlexClient.set_user_rating") as mock_rate:
                result = await registry.execute(
                    "save_user_review",
                    {
                        "title": "Blade Runner",
                        "media_type": "movie",
                        "stars": 3,
                        "rating_key": "555",
                        "force_replace": True,
                    },
                )
            payload = json.loads(result)
            self.assertTrue(payload["review"]["plex_rating_synced"])
            self.assertNotIn("plex_rating_conflict", payload)
            mock_rate.assert_called_once_with("555", 3)

    async def test_query_watchlist_returns_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.add_watchlist_pin(
                pin_id="pin-1",
                user_id=None,
                tmdb_id=27205,
                tvdb_id=None,
                media_type="movie",
                title="Inception",
            )
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("query_watchlist", {"limit": 10})
            payload = json.loads(result)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["title"], "Inception")
            self.assertIn("in_library", payload["items"][0])

    async def test_add_and_critique_watchlist_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.ensure_seed_data()
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            added = json.loads(
                await registry.execute(
                    "add_to_watchlist",
                    {
                        "title": "Heat",
                        "media_type": "movie",
                        "tmdb_id": 949,
                    },
                )
            )
            self.assertIn("pin", added)
            critique = json.loads(await registry.execute("critique_watchlist", {}))
            self.assertIn("critique", critique)
            curated = json.loads(await registry.execute("curate_watchlist", {}))
            self.assertIn("remove_suggestions", curated)

    async def test_upcoming_premieres_without_tmdb_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("upcoming_premieres", {})
            payload = json.loads(result)
            self.assertIn("error", payload)

    async def test_query_library_attaches_facet_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "genres": ["Sci-Fi"],
                    "directors": ["Ridley Scott"],
                    "view_count": 0,
                }
            )
            from curatorx.library.facets import rebuild_library_facets

            rebuild_library_facets(db)
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            await registry.execute(
                "query_library",
                {"genres": "Sci-Fi", "directors": "Ridley Scott", "unwatched_only": True},
            )
            self.assertEqual(len(registry.cards), 1)
            card = registry.cards[0]
            self.assertIn("Sci-Fi", card.recommendation_reason)
            self.assertTrue(any("Genre" in match for match in card.facet_matches))

    async def test_get_facet_catalog_directors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Dunkirk",
                    "directors": ["Christopher Nolan"],
                }
            )
            from curatorx.library.facets import rebuild_library_facets

            rebuild_library_facets(db)
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("get_facet_catalog", {"facet_type": "director"})
            payload = json.loads(result)
            self.assertEqual(payload["facet_type"], "director")
            self.assertEqual(payload["facets"][0]["value"], "Christopher Nolan")

    async def test_query_tv_episodes_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-1",
                    "media_type": "show",
                    "title": "The Wire",
                }
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "ep-1",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Pilot",
                    "view_count": 0,
                }
            )
            db.update_show_episode_rollups(show_id)
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute(
                "query_tv_episodes",
                {"show": "Wire", "unwatched_only": True},
            )
            payload = json.loads(result)
            self.assertEqual(payload["total_matched"], 1)

    async def test_query_library_returns_total_matched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            for year in (1974, 1977, 1982):
                db.upsert_library_item(
                    {
                        "rating_key": f"k{year}",
                        "media_type": "movie",
                        "title": f"Film {year}",
                        "year": year,
                        "genres": ["Drama"],
                    }
                )
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute(
                "query_library",
                {"year_from": 1970, "year_to": 1979, "limit": 10},
            )
            payload = json.loads(result)
            self.assertEqual(payload["total_matched"], 2)
            self.assertEqual(len(payload["items"]), 2)

    async def test_summarize_library_by_decade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Chinatown",
                    "year": 1974,
                    "genres": ["Crime"],
                }
            )
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("summarize_library", {"group_by": "decade"})
            payload = json.loads(result)
            self.assertEqual(payload["group_by"], "decade")
            self.assertEqual(payload["buckets"][0]["count"], 1)

    def test_system_prompt_includes_library_overview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Test",
                    "year": 1970,
                    "genres": ["Drama"],
                }
            )
            prompt = build_system_prompt(db, lens_id=DEFAULT_LENS_ID)
            self.assertIn("Library inventory", prompt)
            self.assertIn("query_library", prompt)
            self.assertIn("search_tmdb", prompt)
            self.assertIn("Query cookbook", prompt)

    def test_system_prompt_includes_persona_and_lens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_persona(curator_name="Atlas", val_bro_prof=0.9)
            db.create_lens("noir", "Noir Studies", "Hardboiled crime cinema")
            prompt = build_system_prompt(db, lens_id="noir")
            self.assertIn("Atlas", prompt)
            self.assertIn("Noir Studies", prompt)
            self.assertIn("Hardboiled", prompt)
            self.assertIn(DEFAULT_LENS_ID, build_system_prompt(db, lens_id=DEFAULT_LENS_ID) or "")

    def test_card_to_tool_item_includes_external_ids(self) -> None:
        movie = TitleCard(media_type="movie", title="Blade Runner", year=1982, tmdb_id=78, in_library=False)
        show = TitleCard(media_type="show", title="The Wire", year=2002, tmdb_id=1438, tvdb_id=79126, in_library=False)
        owned = TitleCard(
            media_type="movie",
            title="Chinatown",
            year=1974,
            rating_key="rk-1",
            in_library=True,
        )

        movie_item = _card_to_tool_item(movie)
        show_item = _card_to_tool_item(show)
        owned_item = _card_to_tool_item(owned)

        self.assertEqual(movie_item["tmdb_id"], 78)
        self.assertNotIn("tvdb_id", movie_item)
        self.assertEqual(show_item["tmdb_id"], 1438)
        self.assertEqual(show_item["tvdb_id"], 79126)
        self.assertEqual(owned_item["rating_key"], "rk-1")
        self.assertNotIn("tmdb_id", owned_item)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_find_collection_gaps_items_include_tmdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "vote_average": 8.2,
            }
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("find_collection_gaps", {"media_type": "movie"})
            payload = json.loads(result)
            self.assertEqual(payload["items"][0]["tmdb_id"], 603)
            self.assertEqual(payload["items"][0]["title"], "The Matrix")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_find_collection_gaps_excludes_owned_tmdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "vote_average": 8.2,
            },
            {
                "id": 604,
                "title": "The Matrix Reloaded",
                "release_date": "2003-05-15",
                "vote_average": 7.0,
            },
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "owned-matrix",
                    "media_type": "movie",
                    "title": "The Matrix",
                    "tmdb_id": 603,
                }
            )
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("find_collection_gaps", {"media_type": "movie"})
            payload = json.loads(result)
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 604)
            self.assertFalse(payload["items"][0]["in_library"])
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 604)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_find_collection_gaps_excludes_queued_tmdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = []
        mock_tmdb.discover_movies.return_value = [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "vote_average": 8.2,
            },
            {
                "id": 604,
                "title": "The Matrix Reloaded",
                "release_date": "2003-05-15",
                "vote_average": 7.0,
            },
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.record_arr_queue(
                media_type="movie",
                source="radarr",
                tmdb_id=603,
                title="The Matrix",
            )
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("find_collection_gaps", {"media_type": "movie"})
            payload = json.loads(result)
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 604)
            prompt = build_system_prompt(db, lens_id=DEFAULT_LENS_ID)
            self.assertIn("Already queued", prompt)
            self.assertIn("The Matrix", prompt)

    async def test_save_user_review_accepts_half_stars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(sync_reviews_to_plex=False),
                DEFAULT_LENS_ID,
            )
            result = await registry.execute(
                "save_user_review",
                {
                    "title": "Ghost in the Shell 2.0",
                    "media_type": "movie",
                    "stars": 4.5,
                    "rating_key": "gits-2",
                },
            )
            payload = json.loads(result)
            self.assertTrue(payload["saved"])
            self.assertEqual(payload["review"]["stars"], 4.5)

    async def test_suggest_titles_to_rate_attaches_review_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "viewed-1",
                    "media_type": "movie",
                    "title": "Heat",
                    "view_count": 1,
                    "last_viewed_at": 1_700_000_000,
                    "poster_url": "http://example/heat.jpg",
                }
            )
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("suggest_titles_to_rate", {"limit": 5})
            payload = json.loads(result)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(len(registry.review_prompts), 1)
            self.assertEqual(registry.review_prompts[0]["title"], "Heat")

    def test_append_recommendation_cards_skips_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.record_arr_queue(media_type="movie", source="radarr", tmdb_id=99, title="Queued")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            queued = TitleCard(media_type="movie", title="Queued", tmdb_id=99, in_library=False)
            missing = TitleCard(media_type="movie", title="Missing", tmdb_id=2, in_library=False)
            _append_recommendation_cards(registry, [queued, missing])
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 2)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_recommend_hidden_gems_excludes_owned_tmdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.discover_movies.return_value = [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "vote_average": 8.2,
            },
            {
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-16",
                "vote_average": 8.8,
            },
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "owned-matrix",
                    "media_type": "movie",
                    "title": "The Matrix",
                    "tmdb_id": 603,
                }
            )
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("recommend_hidden_gems", {"media_type": "movie"})
            payload = json.loads(result)
            self.assertEqual(len(payload["items"]), 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 27205)
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 27205)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_omits_owned_from_cards_but_reports_in_library(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 2,
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "Owned already.",
                    "vote_average": 8.2,
                },
                {
                    "id": 604,
                    "title": "The Matrix Reloaded",
                    "release_date": "2003-05-15",
                    "overview": "Not owned.",
                    "vote_average": 7.0,
                },
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "owned-matrix",
                    "media_type": "movie",
                    "title": "The Matrix",
                    "tmdb_id": 603,
                }
            )
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"title": "The Matrix", "media_type": "movie"},
            )
            payload = json.loads(result)
            self.assertEqual(payload["returned"], 2)
            self.assertTrue(payload["items"][0]["in_library"])
            self.assertFalse(payload["items"][1]["in_library"])
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 604)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_explore_genre_include_missing_only_attaches_gap_cards(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.genre_list_movies.return_value = [{"id": 878, "name": "Science Fiction"}]
        mock_tmdb.discover_movies.return_value = [
            {
                "id": 603,
                "title": "The Matrix",
                "release_date": "1999-03-31",
                "vote_average": 8.2,
            },
        ]
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_library_item(
                {
                    "rating_key": "owned-blade",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "genres": ["Science Fiction"],
                }
            )
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "explore_genre",
                {"genre": "Science Fiction", "media_type": "movie", "include_missing": True},
            )
            payload = json.loads(result)
            self.assertEqual(payload["returned_in_library"], 1)
            self.assertEqual(payload["returned_missing"], 1)
            self.assertEqual(len(payload["items"]), 2)
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 603)
            self.assertFalse(registry.cards[0].in_library)

    def test_system_prompt_discourages_owned_as_add_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            prompt = build_system_prompt(db, lens_id=DEFAULT_LENS_ID)
            self.assertIn("Never present in_library=true or already_queued", prompt)
            self.assertIn("find_collection_gaps", prompt)
            self.assertIn("half-stars", prompt)

    def test_append_recommendation_cards_skips_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            owned = TitleCard(media_type="movie", title="Owned", tmdb_id=1, in_library=True)
            missing = TitleCard(media_type="movie", title="Missing", tmdb_id=2, in_library=False)
            _append_recommendation_cards(registry, [owned, missing])
            self.assertTrue(registry.recommendation_context)
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 2)

    def test_rank_tmdb_search_results_year_filters_out_other_years(self) -> None:
        results = [
            {"id": 460885, "title": "Mandy", "release_date": "2018-09-14"},
            {"id": 111, "title": "Mandy", "release_date": "1952-01-01"},
            {"id": 222, "title": "Mandy", "release_date": "2016-06-01"},
        ]
        ranked = _rank_tmdb_search_results(results, year=2018)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["id"], 460885)

    def test_rank_tmdb_search_results_without_year_keeps_all(self) -> None:
        results = [
            {"id": 1, "title": "Mandy", "release_date": "2018-09-14"},
            {"id": 2, "title": "Mandy", "release_date": "1952-01-01"},
        ]
        ranked = _rank_tmdb_search_results(results, year=None)
        self.assertEqual(len(ranked), 2)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_movie_returns_structured_matches(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 42,
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "A hacker discovers reality is a simulation.",
                    "vote_average": 8.2,
                },
                {
                    "id": 604,
                    "title": "The Matrix Reloaded",
                    "release_date": "2003-05-15",
                    "overview": "Neo continues the fight.",
                    "vote_average": 7.0,
                },
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"title": "The Matrix", "media_type": "movie", "year": 1999},
            )
            payload = json.loads(result)
            # Year pin filters Reloaded (2003) out of cards and items.
            self.assertEqual(payload["total_matched"], 1)
            self.assertEqual(payload["returned"], 1)
            self.assertFalse(payload["has_more"])
            self.assertEqual(payload["items"][0]["tmdb_id"], 603)
            self.assertEqual(payload["items"][0]["title"], "The Matrix")
            self.assertEqual(payload["items"][0]["year"], 1999)
            self.assertIn("simulation", payload["items"][0]["overview"])
            self.assertNotIn("tvdb_id", payload["items"][0])
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 603)
            self.assertEqual(registry.cards[0].recommendation_reason, "")
            self.assertNotIn("recommendation_reason", payload["items"][0])

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_year_does_not_expand_ambiguous_title(self, mock_tmdb_cls) -> None:
        """Mandy + year=2018 must pin Cosmatos 2018, not every same-name hit."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 5,
            "results": [
                {
                    "id": 111,
                    "title": "Mandy",
                    "release_date": "1952-07-29",
                    "overview": "British drama.",
                    "vote_average": 6.8,
                },
                {
                    "id": 460885,
                    "title": "Mandy",
                    "release_date": "2018-09-14",
                    "overview": "A psychedelic revenge nightmare.",
                    "vote_average": 6.5,
                },
                {
                    "id": 222,
                    "title": "Mandy",
                    "release_date": "2016-01-01",
                    "overview": "Unrelated Mandy.",
                    "vote_average": 5.0,
                },
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {
                    "title": "Mandy",
                    "media_type": "movie",
                    "year": 2018,
                    "reason": "Cosmic neon revenge for your B-movie streak",
                },
            )
            payload = json.loads(result)
            self.assertEqual(payload["returned"], 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 460885)
            self.assertEqual(payload["items"][0]["year"], 2018)
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 460885)
            self.assertEqual(registry.cards[0].year, 2018)
            self.assertIn("Cosmic neon", registry.cards[0].recommendation_reason)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_by_tmdb_id_pins_exact_work(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.return_value = {
            "id": 460885,
            "title": "Mandy",
            "release_date": "2018-09-14",
            "overview": "A psychedelic revenge nightmare.",
            "vote_average": 6.5,
            "poster_path": "/mandy.jpg",
        }
        mock_tmdb.poster_url.return_value = "https://image.tmdb.org/t/p/w500/mandy.jpg"
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"tmdb_id": 460885, "media_type": "movie", "reason": "Panos Cosmatos fever dream"},
            )
            payload = json.loads(result)
            mock_tmdb.search_movie_page.assert_not_called()
            mock_tmdb.movie_details.assert_called_once_with(460885)
            self.assertEqual(payload["total_matched"], 1)
            self.assertEqual(payload["returned"], 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 460885)
            self.assertEqual(payload["items"][0]["title"], "Mandy")
            self.assertEqual(len(registry.cards), 1)
            self.assertEqual(registry.cards[0].tmdb_id, 460885)
            self.assertEqual(registry.cards[0].title, "Mandy")
            self.assertEqual(registry.cards[0].year, 2018)

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_title_only_may_return_multiple_same_name(self, mock_tmdb_cls) -> None:
        """Without year/tmdb_id, disambiguation candidates are still allowed."""
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 3,
            "results": [
                {"id": 460885, "title": "Mandy", "release_date": "2018-09-14", "vote_average": 6.5},
                {"id": 111, "title": "Mandy", "release_date": "1952-07-29", "vote_average": 6.8},
                {"id": 222, "title": "Mandy", "release_date": "2016-01-01", "vote_average": 5.0},
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"title": "Mandy", "media_type": "movie"},
            )
            payload = json.loads(result)
            self.assertEqual(payload["returned"], 3)
            self.assertEqual(len(registry.cards), 3)
            self.assertEqual({c.tmdb_id for c in registry.cards}, {460885, 111, 222})

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_accepts_curator_reason(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 1,
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "A hacker discovers reality is a simulation.",
                    "vote_average": 8.2,
                }
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {
                    "title": "The Matrix",
                    "media_type": "movie",
                    "reason": "Mind-bending sci-fi that fits your unwatched cyberpunk streak",
                },
            )
            payload = json.loads(result)
            self.assertEqual(
                payload["items"][0]["recommendation_reason"],
                "Mind-bending sci-fi that fits your unwatched cyberpunk streak",
            )
            self.assertEqual(
                registry.cards[0].recommendation_reason,
                "Mind-bending sci-fi that fits your unwatched cyberpunk streak",
            )

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_set_recommendation_reasons_updates_cards(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_movie_page.return_value = {
            "total_results": 1,
            "results": [
                {
                    "id": 603,
                    "title": "The Matrix",
                    "release_date": "1999-03-31",
                    "overview": "A hacker discovers reality is a simulation.",
                    "vote_average": 8.2,
                }
            ],
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            await registry.execute("search_tmdb", {"title": "The Matrix", "media_type": "movie"})
            self.assertEqual(registry.cards[0].recommendation_reason, "")
            result = await registry.execute(
                "set_recommendation_reasons",
                {
                    "reasons": [
                        {"tmdb_id": 603, "reason": "British Quatermass energy"},
                        {"tmdb_id": 603, "reason": "TMDB title match"},
                    ]
                },
            )
            payload = json.loads(result)
            self.assertEqual(payload["updated"], 1)
            self.assertEqual(registry.cards[0].recommendation_reason, "British Quatermass energy")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_show_enriches_tvdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.search_tv_page.return_value = {
            "total_results": 1,
            "results": [
                {
                    "id": 1438,
                    "name": "The Wire",
                    "first_air_date": "2002-06-02",
                    "overview": "Baltimore drug scene.",
                    "vote_average": 8.7,
                }
            ],
        }
        mock_tmdb.tv_details.return_value = {"external_ids": {"tvdb_id": 79126}}
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"title": "The Wire", "media_type": "show"},
            )
            payload = json.loads(result)
            self.assertEqual(payload["total_matched"], 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 1438)
            self.assertEqual(payload["items"][0]["tvdb_id"], 79126)
            self.assertEqual(payload["items"][0]["title"], "The Wire")

    @patch("curatorx.agent.tools.TMDBClient")
    async def test_search_tmdb_requires_api_key(self, mock_tmdb_cls) -> None:
        del mock_tmdb_cls
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute(
                "search_tmdb",
                {"title": "Obscure Film", "media_type": "movie"},
            )
            payload = json.loads(result)
            self.assertIn("error", payload)

    @patch("curatorx.library.titles.TMDBClient")
    async def test_get_title_detail_tool_returns_tmdb_id(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.return_value = {
            "title": "The Matrix",
            "overview": "A hacker discovers reality is a simulation.",
            "vote_average": 8.2,
        }
        mock_tmdb.poster_url.return_value = ""
        mock_tmdb.backdrop_url.return_value = ""

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("get_title_detail", {"media_type": "movie", "tmdb_id": 603})
            payload = json.loads(result)
            self.assertEqual(payload["tmdb_id"], 603)
            self.assertEqual(payload["title"], "The Matrix")
            self.assertNotIn("error", payload)

    @patch("curatorx.library.titles.TMDBClient")
    async def test_get_title_detail_tool_reports_missing_metadata(self, mock_tmdb_cls) -> None:
        mock_tmdb = mock_tmdb_cls.return_value
        mock_tmdb.movie_details.side_effect = RuntimeError("HTTP 404")

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(tmdb_api_key="test-key"), DEFAULT_LENS_ID)
            result = await registry.execute("get_title_detail", {"media_type": "movie", "tmdb_id": 999999})
            payload = json.loads(result)
            self.assertEqual(payload["tmdb_id"], 999999)
            self.assertIn("error", payload)

    async def test_add_to_radarr_requires_root_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(
                    radarr_url="http://radarr",
                    radarr_api_key="secret",
                    radarr_root_folder="",
                    movies_root="",
                ),
                DEFAULT_LENS_ID,
            )
            result = await registry.execute("add_to_radarr", {"tmdb_id": 603, "title": "The Matrix"})
            payload = json.loads(result)
            self.assertIn("error", payload)
            self.assertIn("root folder", payload["error"])
            self.assertEqual(registry.pending_tokens, [])

    async def test_remove_from_arr_resolves_tmdb_id_and_registers_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(radarr_url="http://radarr", radarr_api_key="secret"),
                DEFAULT_LENS_ID,
            )
            movie = RadarrMovie(
                id=42,
                title="The Producers",
                year=1968,
                tmdb_id=5156,
                monitored=True,
                has_file=True,
            )
            with patch(
                "curatorx.agent.tools.RadarrClient.movie_by_tmdb_id",
                return_value=movie,
            ):
                result = await registry.execute(
                    "remove_from_arr",
                    {
                        "media_type": "movie",
                        "tmdb_id": 5156,
                        "title": "The Producers",
                        "delete_files": True,
                    },
                )
            payload = json.loads(result)
            self.assertIn("confirmation_token", payload)
            self.assertEqual(payload["arr_id"], 42)
            self.assertEqual(
                registry.pending_tokens,
                [{"token": payload["confirmation_token"], "action": "remove_arr"}],
            )

    async def test_remove_from_arr_returns_error_when_not_in_radarr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db,
                Settings(radarr_url="http://radarr", radarr_api_key="secret"),
                DEFAULT_LENS_ID,
            )
            with patch(
                "curatorx.agent.tools.RadarrClient.movie_by_tmdb_id",
                return_value=None,
            ):
                result = await registry.execute(
                    "remove_from_arr",
                    {"media_type": "movie", "tmdb_id": 999, "title": "Missing Movie"},
                )
            payload = json.loads(result)
            self.assertIn("error", payload)
            self.assertIn("not in Radarr", payload["error"])
            self.assertEqual(registry.pending_tokens, [])

    async def test_execute_confirmed_remove_arr_uses_friendly_not_found_error(self) -> None:
        from curatorx.agent.tools import execute_confirmed_action

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(radarr_url="http://radarr", radarr_api_key="secret")
            token = "remove-token"
            db.save_pending_action(
                token,
                "remove_arr",
                {
                    "action": "remove_arr",
                    "media_type": "movie",
                    "arr_id": 76478,
                    "tmdb_id": 5156,
                    "title": "Rust",
                    "delete_files": True,
                },
            )
            movie = RadarrMovie(
                id=99,
                title="Rust",
                year=2024,
                tmdb_id=5156,
                monitored=True,
                has_file=True,
            )
            with patch(
                "curatorx.agent.tools.RadarrClient.movie_by_tmdb_id",
                return_value=movie,
            ), patch(
                "curatorx.agent.tools.RadarrClient.delete_movie",
                side_effect=RuntimeError(
                    'HTTP 404 from http://radarr/api/v3/movie/99: '
                    '{"message":"Movie with ID 99 does not exist"}'
                ),
            ):
                with self.assertRaises(ArrTitleNotFoundError):
                    await execute_confirmed_action(db, settings, token)


if __name__ == "__main__":
    unittest.main()
