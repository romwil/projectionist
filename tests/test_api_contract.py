"""Frontend-backend contract tests for lens and persona APIs."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_health_includes_version(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("version", body)

    def test_lenses_active_defaults_to_general(self) -> None:
        resp = self.client.get("/api/lenses/active")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["lens_id"], "general")
        self.assertEqual(body["lens_name"], "General")

    def test_persona_defaults(self) -> None:
        resp = self.client.get("/api/persona")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["curator_name"], "Curator")
        self.assertEqual(body["val_bro_prof"], 0.5)
        self.assertEqual(body["persona_mode"], "sliders")
        self.assertIn("assembled_prompt", body)
        self.assertIn("persona_ui", body)
        self.assertIn("preset_tagline", body["persona_ui"])

    def test_plex_collections_requires_feature_flag(self) -> None:
        resp = self.client.get("/api/plex/collections")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not enabled", resp.json()["detail"].lower())

    def test_create_lens_and_switch_active(self) -> None:
        create = self.client.post(
            "/api/lenses",
            json={
                "lens_id": "noir-study",
                "lens_name": "Neo-Noir Study",
                "description": "Director-focused noir lane",
            },
        )
        self.assertEqual(create.status_code, 200)
        self.assertEqual(create.json()["lens_id"], "noir-study")

        switch = self.client.put("/api/lenses/active", json={"lens_id": "noir-study"})
        self.assertEqual(switch.status_code, 200)
        self.assertEqual(switch.json()["lens_id"], "noir-study")

        active = self.client.get("/api/lenses/active")
        self.assertEqual(active.json()["lens_id"], "noir-study")

    def test_chat_rejects_unknown_lens(self) -> None:
        resp = self.client.post(
            "/api/chat",
            json={"message": "hello", "lens_id": "does-not-exist"},
        )
        self.assertEqual(resp.status_code, 404)
        body = resp.json()
        self.assertIn("detail", body)

    def test_chat_returns_json_error_on_llm_failure(self) -> None:
        from unittest.mock import AsyncMock, patch

        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(side_effect=RuntimeError("LLM provider unavailable"))
            agent_cls.return_value = agent

            resp = self.client.post(
                "/api/chat",
                json={"message": "hello"},
            )
            self.assertEqual(resp.status_code, 500)
            body = resp.json()
            self.assertIn("detail", body)
            self.assertNotIn("LLM provider unavailable", body["detail"])
            self.assertEqual(body["detail"], "Chat request failed")

    def test_wizard_status_shape(self) -> None:
        resp = self.client.get("/api/setup/wizard")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("current_step", body)
        self.assertIn("steps", body)
        self.assertIn("identity_seed", body["steps"])
        self.assertIn("infrastructure", body["steps"])
        self.assertIn("dropdown_mapping", body["steps"])
        self.assertNotIn("persona", body["steps"])
        self.assertFalse(body["onboarding_complete"])

    def test_llm_test_requires_api_key(self) -> None:
        resp = self.client.post(
            "/api/setup/test/llm",
            json={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("api key", body["message"].lower())

    def test_service_integration_persisted_on_plex_failure(self) -> None:
        resp = self.client.post(
            "/api/setup/test/plex",
            json={"plex_url": "http://invalid.local", "plex_token": "bad"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["ok"])

        import curatorx.web.jobs as jobs

        row = jobs.get_job_manager().db.get_service_integration("plex")
        self.assertIsNotNone(row)
        self.assertEqual(str(row["connection_status"]), "failed")
        self.assertEqual(int(row["certified"]), 0)

    def test_certifications_endpoint_shape(self) -> None:
        resp = self.client.get("/api/setup/certifications")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("services", body)
        for service in ("llm", "plex", "radarr", "sonarr", "tmdb", "fanart", "tautulli"):
            self.assertIn(service, body["services"])
            entry = body["services"][service]
            self.assertIn("certified", entry)
            self.assertIn("connection_status", entry)
            self.assertIn("last_tested_at", entry)

    def test_wizard_includes_certifications(self) -> None:
        resp = self.client.get("/api/setup/wizard")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("certifications", body)
        self.assertIn("llm", body["certifications"])

    def test_active_context_defaults_to_general(self) -> None:
        resp = self.client.get("/api/context/active")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["context_hash"], "general")
        self.assertEqual(body["inferred_label"], "General Exploration")

    def test_service_integration_certified_on_llm_success(self) -> None:
        from unittest.mock import AsyncMock, patch

        mock_chat = AsyncMock(return_value={"content": [{"type": "text", "text": "pong"}]})
        with patch("curatorx.web.setup.get_chat_provider") as get_provider:
            provider = AsyncMock()
            provider.chat = mock_chat
            get_provider.return_value = provider

            resp = self.client.post(
                "/api/setup/test/llm",
                json={
                    "llm_provider": "openai",
                    "llm_api_key": "test-key",
                    "llm_model": "gpt-4o-mini",
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["ok"])

        import curatorx.web.jobs as jobs

        row = jobs.get_job_manager().db.get_service_integration("llm")
        self.assertIsNotNone(row)
        self.assertEqual(int(row["certified"]), 1)
        self.assertEqual(str(row["connection_status"]), "verified")

    def test_certification_invalidated_when_llm_url_changes(self) -> None:
        from unittest.mock import AsyncMock, patch

        mock_chat = AsyncMock(return_value={"content": [{"type": "text", "text": "pong"}]})
        with patch("curatorx.web.setup.get_chat_provider") as get_provider:
            provider = AsyncMock()
            provider.chat = mock_chat
            get_provider.return_value = provider
            self.client.post(
                "/api/setup/test/llm",
                json={
                    "llm_provider": "openai",
                    "llm_api_key": "test-key",
                    "llm_model": "gpt-4o-mini",
                },
            )

        import curatorx.web.jobs as jobs

        row = jobs.get_job_manager().db.get_service_integration("llm")
        self.assertEqual(int(row["certified"]), 1)

        put = self.client.put(
            "/api/settings",
            json={"llm_base_url": "https://api.openai.com/v1", "llm_model": "gpt-4o-mini"},
        )
        self.assertEqual(put.status_code, 200)

        row = jobs.get_job_manager().db.get_service_integration("llm")
        self.assertEqual(int(row["certified"]), 1)

        put = self.client.put(
            "/api/settings",
            json={"llm_base_url": "https://custom.example.com/v1"},
        )
        self.assertEqual(put.status_code, 200)

        row = jobs.get_job_manager().db.get_service_integration("llm")
        self.assertEqual(int(row["certified"]), 0)
        self.assertEqual(str(row["connection_status"]), "unverified")

    def test_settings_masks_secrets_with_source(self) -> None:
        os.environ["LLM_API_KEY"] = "env-secret"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)

        resp = client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["llm_api_key"], "")
        self.assertTrue(body["llm_api_key_set"])
        self.assertEqual(body["llm_api_key_source"], "env")
        del os.environ["LLM_API_KEY"]

    def test_llm_test_uses_env_key_when_ui_empty(self) -> None:
        os.environ["LLM_API_KEY"] = "env-secret"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)

        resp = client.post(
            "/api/setup/test/llm",
            json={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertNotIn("API key is required", body["message"])
        del os.environ["LLM_API_KEY"]

    def test_llm_providers_includes_gemini(self) -> None:
        resp = self.client.get("/api/setup/llm-providers")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("gemini", body["base_urls"])
        self.assertIn("anthropic", body["base_urls"])
        self.assertIn("anthropic", body["models"])

    def test_llm_test_routes_anthropic_provider(self) -> None:
        from unittest.mock import AsyncMock, patch

        mock_chat = AsyncMock(return_value={"content": [{"type": "text", "text": "pong"}]})
        with patch("curatorx.web.setup.get_chat_provider") as get_provider:
            provider = AsyncMock()
            provider.chat = mock_chat
            get_provider.return_value = provider

            resp = self.client.post(
                "/api/setup/test/llm",
                json={
                    "llm_provider": "anthropic",
                    "llm_api_key": "test-key",
                    "llm_model": "gpt-4o-mini",
                },
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertTrue(body["ok"])
            self.assertIn("anthropic", body["message"])
            self.assertIn("claude-sonnet-4-6", body["message"])

            settings = get_provider.call_args.args[0]
            self.assertEqual(settings.llm_provider, "anthropic")
            self.assertEqual(settings.llm_model, "claude-sonnet-4-6")
            mock_chat.assert_awaited_once()

    def test_settings_sync_llm_to_db(self) -> None:
        put = self.client.put(
            "/api/settings",
            json={
                "llm_provider": "openrouter",
                "llm_base_url": "https://openrouter.ai/api/v1",
                "llm_model": "deepseek-chat",
            },
        )
        self.assertEqual(put.status_code, 200)

        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        self.assertEqual(db.get_config("llm_provider"), "openrouter")
        self.assertEqual(db.get_config("llm_base_url"), "https://openrouter.ai/api/v1")
        self.assertEqual(db.get_config("llm_model"), "deepseek-chat")

    def test_saved_llm_settings_override_env_on_get(self) -> None:
        os.environ["LLM_PROVIDER"] = "openai_compatible"
        os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
        os.environ["LLM_MODEL"] = "gpt-4o-mini"
        try:
            put = self.client.put(
                "/api/settings",
                json={
                    "llm_provider": "anthropic",
                    "llm_base_url": "https://api.anthropic.com",
                    "llm_model": "claude-sonnet-4-6",
                    "llm_api_key": "test-key",
                },
            )
            self.assertEqual(put.status_code, 200)
            self.assertEqual(put.json()["llm_provider"], "anthropic")
            self.assertEqual(put.json()["llm_model"], "claude-sonnet-4-6")

            get = self.client.get("/api/settings")
            self.assertEqual(get.status_code, 200)
            body = get.json()
            self.assertEqual(body["llm_provider"], "anthropic")
            self.assertEqual(body["llm_base_url"], "https://api.anthropic.com")
            self.assertEqual(body["llm_model"], "claude-sonnet-4-6")
            self.assertTrue(body["llm_api_key_set"])
            self.assertEqual(body["llm_api_key_source"], "file")
        finally:
            del os.environ["LLM_PROVIDER"]
            del os.environ["LLM_BASE_URL"]
            del os.environ["LLM_MODEL"]

    def test_chat_threads_crud_contract(self) -> None:
        from unittest.mock import AsyncMock, patch

        create = self.client.post("/api/chat/threads", json={"thread_title": "Neo-noir hunt"})
        self.assertEqual(create.status_code, 200)
        created = create.json()
        self.assertIn("session_id", created)
        self.assertEqual(created["thread_title"], "Neo-noir hunt")
        session_id = created["session_id"]

        listed = self.client.get("/api/chat/threads")
        self.assertEqual(listed.status_code, 200)
        threads = listed.json()
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["id"], session_id)
        self.assertEqual(threads[0]["thread_title"], "Neo-noir hunt")

        with patch("curatorx.web.app.CuratorAgent") as agent_cls:
            agent = AsyncMock()
            agent.run = AsyncMock(
                return_value={
                    "session_id": session_id,
                    "lens_id": "general",
                    "message": {
                        "id": "assistant-1",
                        "role": "assistant",
                        "blocks": [{"type": "text", "content": "Try Blade Runner."}],
                        "lens_id": "general",
                    },
                    "pending_tokens": [],
                }
            )
            agent_cls.return_value = agent

            chat = self.client.post(
                "/api/chat",
                json={"message": "Find neo-noir films", "session_id": session_id},
            )
            self.assertEqual(chat.status_code, 200)

            import curatorx.web.jobs as jobs

            db = jobs.get_job_manager().db
            db.save_chat_message(
                session_id,
                "user-1",
                "user",
                [{"type": "text", "content": "Find neo-noir films"}],
            )
            db.save_chat_message(
                session_id,
                "assistant-1",
                "assistant",
                [{"type": "text", "content": "Try Blade Runner."}],
            )

        messages = self.client.get(f"/api/chat/threads/{session_id}/messages")
        self.assertEqual(messages.status_code, 200)
        body = messages.json()
        self.assertEqual(body["session_id"], session_id)
        self.assertGreaterEqual(len(body["messages"]), 1)

        renamed = self.client.patch(
            f"/api/chat/threads/{session_id}",
            json={"thread_title": "Rainy city picks"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["thread_title"], "Rainy city picks")

        deleted = self.client.delete(f"/api/chat/threads/{session_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])

        missing = self.client.get(f"/api/chat/threads/{session_id}/messages")
        self.assertEqual(missing.status_code, 404)

    def test_library_query_and_aggregate_endpoints(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "audit-1",
                "media_type": "movie",
                "title": "French Connection",
                "year": 1971,
                "genres": ["Crime"],
            }
        )
        db.upsert_library_item(
            {
                "rating_key": "audit-2",
                "media_type": "movie",
                "title": "Blade Runner",
                "year": 1982,
                "genres": ["Sci-Fi"],
            }
        )

        query = self.client.get(
            "/api/library/query",
            params={"year_from": 1970, "year_to": 1979, "media_type": "movie"},
        )
        self.assertEqual(query.status_code, 200)
        body = query.json()
        self.assertEqual(body["total_matched"], 1)
        self.assertEqual(body["items"][0]["title"], "French Connection")

        aggregate = self.client.get(
            "/api/library/aggregate",
            params={"group_by": "decade"},
        )
        self.assertEqual(aggregate.status_code, 200)
        agg = aggregate.json()
        self.assertEqual(agg["group_by"], "decade")

        overview = self.client.get("/api/library/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertIn("total", overview.json())

        facets = self.client.get("/api/library/facets", params={"facet_type": "director", "limit": 5})
        self.assertEqual(facets.status_code, 200)
        self.assertEqual(facets.json()["facet_type"], "director")

        show_id = db.upsert_library_item(
            {
                "rating_key": "tv-show-1",
                "media_type": "show",
                "title": "Test Show",
            }
        )
        db.upsert_library_episode(
            {
                "show_item_id": show_id,
                "rating_key": "tv-ep-1",
                "season_number": 1,
                "episode_number": 1,
                "title": "Episode One",
                "view_count": 0,
            }
        )
        db.update_show_episode_rollups(show_id)

        episodes = self.client.get(
            "/api/library/tv/episodes",
            params={"show": "Test Show", "unwatched_only": True},
        )
        self.assertEqual(episodes.status_code, 200)
        self.assertEqual(episodes.json()["total_matched"], 1)

        progress = self.client.get("/api/library/tv/progress", params={"group_by": "show"})
        self.assertEqual(progress.status_code, 200)
        self.assertEqual(progress.json()["group_by"], "show")

    @patch.dict(os.environ, {}, clear=False)
    def test_settings_put_restores_empty_root_folders(self) -> None:
        for key in ("MOVIES_ROOT", "TV_ROOT", "RADARR_ROOT_FOLDER", "SONARR_ROOT_FOLDER"):
            os.environ.pop(key, None)
        self.client.put(
            "/api/settings",
            json={
                "radarr_root_folder": "",
                "movies_root": "",
                "sonarr_root_folder": "",
                "tv_root": "",
            },
        )
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["radarr_root_folder"], "/media/movies")
        self.assertEqual(body["movies_root"], "/media/movies")
        self.assertEqual(body["sonarr_root_folder"], "/media/tv")
        self.assertEqual(body["tv_root"], "/media/tv")

    def test_settings_put_preserves_plex_library_sections(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "plex_movie_section": "42",
                "plex_tv_section": "99",
            },
        )
        self.client.put(
            "/api/settings",
            json={
                "plex_movie_section": "",
                "plex_tv_section": "",
            },
        )
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["plex_movie_section"], "42")
        self.assertEqual(body["plex_tv_section"], "99")

    def test_settings_put_sets_onboarding_complete(self) -> None:
        resp = self.client.put(
            "/api/settings",
            json={"onboarding_complete": True},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["onboarding_complete"])
        status = self.client.get("/api/setup/status")
        self.assertTrue(status.json()["onboarding_complete"])

    def test_propose_and_confirm_add_radarr(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/media/movies",
            },
        )
        with patch(
            "curatorx.web.app.RadarrClient.root_folders",
            return_value=[{"path": "/media/movies"}],
        ), patch(
            "curatorx.web.app.RadarrClient.movie_by_tmdb_id",
            return_value=None,
        ):
            propose = self.client.post(
                "/api/actions/propose",
                json={"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"},
            )
        self.assertEqual(propose.status_code, 200)
        token = propose.json()["confirmation_token"]
        self.assertTrue(token)

        with patch("curatorx.agent.tools.RadarrClient.add_movie", return_value={"id": 42}) as add_movie:
            confirm = self.client.post(
                "/api/actions/confirm",
                json={"token": token, "confirmed": True},
            )
        self.assertEqual(confirm.status_code, 200)
        body = confirm.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["action"], "add_radarr")
        add_movie.assert_called_once_with(
            603,
            root_folder="/media/movies",
            quality_profile_id=1,
        )

    def test_propose_add_radarr_already_exists(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/media/movies",
            },
        )
        existing = type(
            "Movie",
            (),
            {"id": 9, "title": "The Matrix", "tmdb_id": 603},
        )()
        with patch(
            "curatorx.web.app.RadarrClient.root_folders",
            return_value=[{"path": "/media/movies"}],
        ), patch(
            "curatorx.web.app.RadarrClient.movie_by_tmdb_id",
            return_value=existing,
        ):
            propose = self.client.post(
                "/api/actions/propose",
                json={"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"},
            )
        self.assertEqual(propose.status_code, 200)
        body = propose.json()
        self.assertTrue(body["already_exists"])
        self.assertIn("already in Radarr", body["message"])
        self.assertNotIn("confirmation_token", body)

    def test_confirm_add_radarr_already_exists(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/media/movies",
            },
        )
        with patch(
            "curatorx.web.app.RadarrClient.root_folders",
            return_value=[{"path": "/media/movies"}],
        ), patch(
            "curatorx.web.app.RadarrClient.movie_by_tmdb_id",
            return_value=None,
        ):
            propose = self.client.post(
                "/api/actions/propose",
                json={"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"},
            )
        token = propose.json()["confirmation_token"]

        from curatorx.connectors.arr_errors import ArrTitleExistsError

        with patch(
            "curatorx.agent.tools.RadarrClient.add_movie",
            side_effect=ArrTitleExistsError(
                "Radarr",
                title="The Matrix",
                external_id=603,
                arr_id=9,
            ),
        ):
            confirm = self.client.post(
                "/api/actions/confirm",
                json={"token": token, "confirmed": True},
            )
        self.assertEqual(confirm.status_code, 200)
        body = confirm.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["already_exists"])
        self.assertIn("already in Radarr", body["message"])

    def test_confirm_remove_arr_returns_friendly_not_found_error(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
            },
        )
        import curatorx.web.jobs as jobs
        from curatorx.connectors.radarr import RadarrMovie

        token = "purge-token"
        db = jobs.get_job_manager().db
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
            confirm = self.client.post(
                "/api/actions/confirm",
                json={"token": token, "confirmed": True},
            )
        self.assertEqual(confirm.status_code, 400)
        detail = confirm.json()["detail"]
        self.assertEqual(detail, "Action confirmation failed")
        self.assertNotIn("NzbDrone", detail)
        self.assertNotIn("HTTP 404", detail)

    def test_propose_add_radarr_rejects_unregistered_root_folder(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/mnt/user/data/media/movies",
            },
        )
        with patch(
            "curatorx.web.app.RadarrClient.root_folders",
            return_value=[{"path": "/movies"}, {"path": "/media/movies"}],
        ):
            propose = self.client.post(
                "/api/actions/propose",
                json={"action": "add_radarr", "tmdb_id": 603, "title": "The Matrix"},
            )
        self.assertEqual(propose.status_code, 400)
        self.assertIn("Available root folders", propose.json()["detail"])

    def test_setup_test_radarr_returns_registered_root_folders(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/mnt/user/data/media/movies",
            },
        )
        with patch("curatorx.web.setup.RadarrClient.system_status", return_value={"version": "5.0"}), patch(
            "curatorx.web.setup.RadarrClient.movies", return_value=[]
        ), patch(
            "curatorx.web.setup.RadarrClient.root_folders",
            return_value=[{"path": "/movies"}],
        ):
            resp = self.client.post("/api/setup/test/radarr", json={})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["root_folders"], ["/movies"])
        self.assertEqual(body["suggested_root_folder"], "/movies")
        self.assertIn("radarr_root_folder", body["message"])

    def test_features_endpoint_defaults(self) -> None:
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["features"]["multi_user_enabled"])
        self.assertFalse(body["features"]["seerr_enabled"])
        self.assertEqual(body["auth"]["mode"], "disabled")
        self.assertTrue(body["auth"]["plex_login_enabled"])
        self.assertFalse(body["auth"]["oidc_enabled"])
        self.assertFalse(body["auth"]["local_login_enabled"])
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["role"], "owner")
        self.assertEqual(body["request_path"], "arr")

    def test_auth_me_endpoint(self) -> None:
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["authenticated"])
        self.assertEqual(body["user"]["id"], "bootstrap-owner")

    def test_bootstrap_owner_seeded(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        row = db.get_user("bootstrap-owner")
        self.assertIsNotNone(row)
        self.assertEqual(str(row["role"]), "owner")

    def test_message_feedback_helpful_records_preference(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        session_id = "feedback-session"
        message_id = "assistant-feedback-1"
        db.create_chat_thread(session_id, thread_title="Feedback test")
        db.save_chat_message(
            session_id,
            message_id,
            "assistant",
            [{"type": "text", "content": "Try Blade Runner for neo-noir vibes."}],
        )

        resp = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": "helpful"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["saved"])
        self.assertEqual(body["feedback"]["feedback"], "helpful")
        self.assertEqual(body["feedback"]["message_id"], message_id)

        facts = db.preference_facts(limit=5)
        self.assertTrue(any(f["signal_type"] == "positive" for f in facts))

        listed = self.client.get(f"/api/chat/threads/{session_id}/feedback")
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["message_id"], message_id)
        self.assertEqual(items[0]["feedback"], "helpful")

    def test_message_feedback_rejects_user_messages(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        session_id = "feedback-user-session"
        message_id = "user-feedback-1"
        db.create_chat_thread(session_id, thread_title="Feedback user test")
        db.save_chat_message(
            session_id,
            message_id,
            "user",
            [{"type": "text", "content": "Find neo-noir films"}],
        )

        resp = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": "helpful"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("assistant", resp.json()["detail"].lower())

    def test_message_feedback_not_found(self) -> None:
        resp = self.client.post(
            "/api/chat/messages/missing-message/feedback",
            json={"session_id": "missing-session", "feedback": "not_helpful"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_confirm_action_cancels_pending_token(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "radarr_url": "http://radarr",
                "radarr_api_key": "secret",
                "radarr_root_folder": "/media/movies",
            },
        )
        with patch(
            "curatorx.web.app.RadarrClient.root_folders",
            return_value=[{"path": "/media/movies"}],
        ), patch(
            "curatorx.web.app.RadarrClient.movie_by_tmdb_id",
            return_value=None,
        ):
            propose = self.client.post(
                "/api/actions/propose",
                json={
                    "action": "add_radarr",
                    "tmdb_id": 1,
                    "title": "Test",
                },
            )
        self.assertEqual(propose.status_code, 200)
        token = propose.json()["confirmation_token"]
        cancel = self.client.post(
            "/api/actions/confirm",
            json={"token": token, "confirmed": False},
        )
        self.assertEqual(cancel.status_code, 200)
        self.assertTrue(cancel.json()["cancelled"])

    def test_watchlist_crud(self) -> None:
        create = self.client.post(
            "/api/watchlist",
            json={
                "media_type": "movie",
                "tmdb_id": 27205,
                "title": "Inception",
            },
        )
        self.assertEqual(create.status_code, 200)
        pin = create.json()
        self.assertEqual(pin["title"], "Inception")
        self.assertEqual(pin["tmdb_id"], 27205)

        listing = self.client.get("/api/watchlist")
        self.assertEqual(listing.status_code, 200)
        body = listing.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["items"]), 1)

        duplicate = self.client.post(
            "/api/watchlist",
            json={
                "media_type": "movie",
                "tmdb_id": 27205,
                "title": "Inception",
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(self.client.get("/api/watchlist").json()["count"], 1)

        removed = self.client.delete(f"/api/watchlist/{pin['id']}")
        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["removed"])
        self.assertEqual(self.client.get("/api/watchlist").json()["count"], 0)

    def test_engagement_streak(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        for index in range(3):
            db.create_chat_thread(f"streak-session-{index}", thread_title=f"Streak {index}")
        resp = self.client.get("/api/engagement/streak")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["session_count_30d"], 3)
        self.assertTrue(body["streak_visible"])

    def test_message_feedback_clear_via_delete(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        session_id = "feedback-clear-session"
        message_id = "assistant-feedback-clear"
        db.create_chat_thread(session_id, thread_title="Feedback clear test")
        db.save_chat_message(
            session_id,
            message_id,
            "assistant",
            [{"type": "text", "content": "Try Blade Runner for neo-noir vibes."}],
        )

        saved = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": "helpful"},
        )
        self.assertEqual(saved.status_code, 200)

        cleared = self.client.delete(
            f"/api/chat/messages/{message_id}/feedback",
            params={"session_id": session_id},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertTrue(cleared.json()["deleted"])

        listed = self.client.get(f"/api/chat/threads/{session_id}/feedback")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"], [])

    def test_message_feedback_clear_via_post_null(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        session_id = "feedback-null-session"
        message_id = "assistant-feedback-null"
        db.create_chat_thread(session_id, thread_title="Feedback null test")
        db.save_chat_message(
            session_id,
            message_id,
            "assistant",
            [{"type": "text", "content": "Queue The Matrix tonight."}],
        )

        saved = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": "not_helpful"},
        )
        self.assertEqual(saved.status_code, 200)

        cleared = self.client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"session_id": session_id, "feedback": None},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertTrue(cleared.json()["deleted"])

        listed = self.client.get(f"/api/chat/threads/{session_id}/feedback")
        self.assertEqual(listed.json()["items"], [])

    def test_library_health_endpoint(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "health-1",
                "media_type": "movie",
                "title": "Unwatched Film",
                "view_count": 0,
                "added_at": 1,
            }
        )
        db.upsert_library_item(
            {
                "rating_key": "health-2",
                "media_type": "movie",
                "title": "Watched Film",
                "view_count": 2,
            }
        )
        resp = self.client.get("/api/library/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("unwatched_pct", body)
        self.assertIn("stale_adds", body)
        self.assertIn("rating_coverage_pct", body)
        self.assertGreaterEqual(body["total"], 2)

    def test_library_purge_candidates_endpoint(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "purge-1",
                "media_type": "movie",
                "title": "Big Unwatched",
                "file_size": 2_000_000_000,
                "view_count": 0,
                "genres": ["Horror"],
            }
        )
        resp = self.client.get("/api/library/purge-candidates?limit=5")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["count"], 1)
        self.assertTrue(body["items"][0]["title"])

    def test_training_corpus_export(self) -> None:
        import curatorx.web.jobs as jobs

        db = jobs.get_job_manager().db
        db.add_preference("explicit", "loves neo-noir")
        db.create_chat_thread("export-session", thread_title="Export test")
        db.save_chat_message(
            "export-session",
            "assistant-export",
            "assistant",
            [{"type": "text", "content": "Try Chinatown."}],
        )
        db.upsert_message_feedback(
            feedback_id="feedback-export-1",
            message_id="assistant-export",
            session_id="export-session",
            user_id=None,
            feedback_type="helpful",
            excerpt="Try Chinatown.",
        )

        resp = self.client.get("/api/admin/export/training-corpus")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("message_feedback", body)
        self.assertIn("preference_facts", body)
        self.assertIn("user_title_reviews", body)
        self.assertGreaterEqual(len(body["preference_facts"]), 1)
        self.assertGreaterEqual(len(body["message_feedback"]), 1)

    def test_persona_ui_copy_endpoint(self) -> None:
        resp = self.client.get("/api/persona/ui-copy")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("welcome_greeting", body)
        self.assertIn("composer_placeholders", body)
        self.assertIn("review_prompt_templates", body)
        self.assertIn("accent_hue", body)
        self.assertIn("preset_tagline", body)

    def test_persona_typing_phrases(self) -> None:
        resp = self.client.get("/api/persona/typing-phrases")
        self.assertEqual(resp.status_code, 200)
        phrases = resp.json()["phrases"]
        self.assertIsInstance(phrases, list)
        self.assertGreater(len(phrases), 0)


if __name__ == "__main__":
    unittest.main()
