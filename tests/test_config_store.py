"""Tests for config store."""

import os
import tempfile
import unittest
from pathlib import Path

from curatorx.config_store import (
    Settings,
    load_dotenv_file,
    load_merged_settings,
    model_looks_openai,
    normalize_path_settings,
    radarr_add_configuration_error,
    reconcile_llm_provider,
    resolve_llm_base_url,
    resolve_llm_model,
    resolve_radarr_root_folder,
    pick_arr_root_folder,
    validate_arr_root_folder,
    save_settings,
    secret_field_sources,
    validate_llm_settings,
)


class ConfigStoreTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(plex_url="http://plex", tmdb_api_key="secret")
            save_settings(data_dir, settings)
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.plex_url, "http://plex")
            self.assertEqual(loaded.tmdb_api_key, "secret")

    def test_from_mapping_ignores_unknown(self) -> None:
        settings = Settings.from_mapping({"plex_url": "x", "unknown": "y"})
        self.assertEqual(settings.plex_url, "x")

    def test_env_overrides_file_when_field_not_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(llm_api_key="from-file"))
            os.environ["LLM_API_KEY"] = "from-env"
            try:
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.llm_api_key, "from-file")
            finally:
                del os.environ["LLM_API_KEY"]

    def test_env_fills_missing_file_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            os.environ["LLM_PROVIDER"] = "openai_compatible"
            os.environ["LLM_MODEL"] = "gpt-4o-mini"
            try:
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.llm_provider, "openai_compatible")
                self.assertEqual(loaded.llm_model, "gpt-4o-mini")
            finally:
                del os.environ["LLM_PROVIDER"]
                del os.environ["LLM_MODEL"]

    def test_file_overrides_env_for_llm_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(
                data_dir,
                Settings(
                    llm_provider="anthropic",
                    llm_base_url="https://api.anthropic.com",
                    llm_model="claude-sonnet-4-6",
                    llm_api_key="file-key",
                ),
            )
            os.environ["LLM_PROVIDER"] = "openai_compatible"
            os.environ["LLM_BASE_URL"] = "https://api.openai.com/v1"
            os.environ["LLM_MODEL"] = "gpt-4o-mini"
            os.environ["LLM_API_KEY"] = "env-key"
            try:
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.llm_provider, "anthropic")
                self.assertEqual(loaded.llm_base_url, "https://api.anthropic.com")
                self.assertEqual(loaded.llm_model, "claude-sonnet-4-6")
                self.assertEqual(loaded.llm_api_key, "file-key")
            finally:
                del os.environ["LLM_PROVIDER"]
                del os.environ["LLM_BASE_URL"]
                del os.environ["LLM_MODEL"]
                del os.environ["LLM_API_KEY"]

    def test_empty_env_does_not_clear_file_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(llm_api_key="from-file"))
            os.environ["LLM_API_KEY"] = ""
            try:
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.llm_api_key, "from-file")
            finally:
                del os.environ["LLM_API_KEY"]

    def test_secret_field_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(tmdb_api_key="file-key"))
            saved_plex = os.environ.pop("PLEX_TOKEN", None)
            os.environ["LLM_API_KEY"] = "env-key"
            try:
                sources = secret_field_sources(data_dir)
                self.assertEqual(sources["tmdb_api_key"], "file")
                self.assertEqual(sources["llm_api_key"], "env")
                self.assertEqual(sources["plex_token"], "")
            finally:
                del os.environ["LLM_API_KEY"]
                if saved_plex is not None:
                    os.environ["PLEX_TOKEN"] = saved_plex

    def test_secret_field_sources_prefers_file_over_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(data_dir, Settings(llm_api_key="file-key"))
            os.environ["LLM_API_KEY"] = "env-key"
            try:
                sources = secret_field_sources(data_dir)
                self.assertEqual(sources["llm_api_key"], "file")
            finally:
                del os.environ["LLM_API_KEY"]

    def test_resolve_llm_model_switches_openai_model_for_anthropic(self) -> None:
        self.assertEqual(
            resolve_llm_model("anthropic", "gpt-4o-mini"),
            "claude-sonnet-4-6",
        )
        self.assertEqual(resolve_llm_model("anthropic", ""), "claude-sonnet-4-6")
        self.assertEqual(
            resolve_llm_model("anthropic", "claude-3-5-sonnet-20241022"),
            "claude-sonnet-4-6",
        )

    def test_resolve_llm_model_normalizes_anthropic_aliases(self) -> None:
        self.assertEqual(
            resolve_llm_model("anthropic", "claude-sonnet-4"),
            "claude-sonnet-4-6",
        )
        self.assertEqual(
            resolve_llm_model("anthropic", "claude-3-5-sonnet-latest"),
            "claude-sonnet-4-6",
        )
        self.assertEqual(
            resolve_llm_model("anthropic", "claude-sonnet-4-6"),
            "claude-sonnet-4-6",
        )
        self.assertEqual(
            resolve_llm_model("anthropic", "claude-sonnet-4-20250514"),
            "claude-sonnet-4-20250514",
        )

    def test_load_merged_settings_normalizes_stale_anthropic_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(
                data_dir,
                Settings(llm_provider="anthropic", llm_model="claude-sonnet-4"),
            )
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.llm_model, "claude-sonnet-4-6")
            self.assertEqual(loaded.llm_base_url, "https://api.anthropic.com")

    def test_reconcile_llm_provider_from_anthropic_api_key(self) -> None:
        settings = Settings(
            llm_provider="openai",
            llm_base_url="https://api.openai.com/v1",
            llm_model="gpt-4o-mini",
            llm_api_key="sk-ant-test-key",
        )
        reconciled = reconcile_llm_provider(settings)
        self.assertEqual(reconciled.llm_provider, "anthropic")

    def test_load_merged_settings_reconciles_anthropic_key_with_openai_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(
                data_dir,
                Settings(
                    llm_provider="openai",
                    llm_base_url="https://api.openai.com/v1",
                    llm_model="gpt-4o-mini",
                    llm_api_key="sk-ant-test-key",
                ),
            )
            loaded = load_merged_settings(data_dir)
            self.assertEqual(loaded.llm_provider, "anthropic")
            self.assertEqual(loaded.llm_model, "claude-sonnet-4-6")
            self.assertEqual(loaded.llm_base_url, "https://api.anthropic.com")

    def test_validate_llm_settings_flags_openai_provider_with_anthropic_key(self) -> None:
        settings = Settings(
            llm_provider="openai",
            llm_api_key="sk-ant-test-key",
        )
        message = validate_llm_settings(settings)
        self.assertIsNotNone(message)
        self.assertIn("Anthropic", message or "")

    def test_validate_llm_settings_requires_api_key(self) -> None:
        message = validate_llm_settings(Settings(llm_provider="openai"))
        self.assertIsNotNone(message)
        self.assertIn("API key", message or "")

    def test_resolve_llm_base_url_anthropic_without_chat_completions(self) -> None:
        self.assertEqual(resolve_llm_base_url("anthropic", ""), "https://api.anthropic.com")
        self.assertEqual(
            resolve_llm_base_url("anthropic", "https://api.anthropic.com/v1"),
            "https://api.anthropic.com",
        )
        self.assertEqual(resolve_llm_base_url("openai", ""), "https://api.openai.com/v1")

    def test_model_looks_openai(self) -> None:
        self.assertTrue(model_looks_openai("gpt-4o-mini"))
        self.assertFalse(model_looks_openai("claude-sonnet-4-20250514"))

    def test_load_dotenv_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("LLM_API_KEY=dotenv-key\n# comment\nEMPTY=\n", encoding="utf-8")
            original = os.environ.pop("LLM_API_KEY", None)
            try:
                load_dotenv_file(env_path)
                self.assertEqual(os.environ["LLM_API_KEY"], "dotenv-key")
            finally:
                if original is None:
                    os.environ.pop("LLM_API_KEY", None)
                else:
                    os.environ["LLM_API_KEY"] = original

    def test_load_dotenv_file_skips_empty_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_env = Path(tmp) / "empty.env"
            empty_env.write_text("# only comments\n\n", encoding="utf-8")
            fallback_env = Path(tmp) / "fallback.env"
            fallback_env.write_text("LLM_API_KEY=fallback-key\n", encoding="utf-8")
            original = os.environ.pop("LLM_API_KEY", None)
            try:
                load_dotenv_file(empty_env)
                self.assertNotIn("LLM_API_KEY", os.environ)
                load_dotenv_file(fallback_env)
                self.assertEqual(os.environ["LLM_API_KEY"], "fallback-key")
            finally:
                if original is None:
                    os.environ.pop("LLM_API_KEY", None)
                else:
                    os.environ["LLM_API_KEY"] = original

    def test_resolve_radarr_root_folder_prefers_radarr_then_movies(self) -> None:
        settings = Settings(radarr_root_folder="/radarr/movies", movies_root="/plex/movies")
        self.assertEqual(resolve_radarr_root_folder(settings), "/radarr/movies")
        settings = Settings(radarr_root_folder="", movies_root="/plex/movies")
        self.assertEqual(resolve_radarr_root_folder(settings), "/plex/movies")

    def test_normalize_path_settings_restores_defaults(self) -> None:
        settings = Settings(
            movies_root="",
            tv_root="",
            radarr_root_folder="",
            sonarr_root_folder="",
        )
        normalized = normalize_path_settings(settings)
        self.assertEqual(normalized.radarr_root_folder, "/media/movies")
        self.assertEqual(normalized.movies_root, "/media/movies")

    def test_normalize_path_settings_uses_movies_root_for_radarr(self) -> None:
        settings = Settings(movies_root="/plex/movies", radarr_root_folder="")
        normalized = normalize_path_settings(settings)
        self.assertEqual(normalized.radarr_root_folder, "/plex/movies")

    def test_radarr_add_configuration_error_when_root_missing(self) -> None:
        settings = Settings(
            radarr_url="http://radarr",
            radarr_api_key="secret",
            radarr_root_folder="",
            movies_root="",
        )
        error = radarr_add_configuration_error(settings)
        self.assertIn("root folder", error or "")

    def test_pick_arr_root_folder_exact_match(self) -> None:
        resolved = pick_arr_root_folder("/movies", ["/movies"], service="Radarr")
        self.assertEqual(resolved, "/movies")

    def test_validate_arr_root_folder_returns_none_for_match(self) -> None:
        error = validate_arr_root_folder("Radarr", "/movies", [{"path": "/movies"}])
        self.assertIsNone(error)

    def test_validate_arr_root_folder_returns_error_for_mismatch(self) -> None:
        error = validate_arr_root_folder(
            "Radarr",
            "/mnt/user/data/media/movies",
            [{"path": "/movies"}, {"path": "/media/movies"}],
        )
        self.assertIn("Available root folders", error or "")

    def test_feature_flags_defaults(self) -> None:
        settings = Settings()
        self.assertFalse(settings.features.multi_user_enabled)
        self.assertFalse(settings.features.seerr_enabled)
        self.assertEqual(settings.auth.mode, "disabled")
        self.assertTrue(settings.auth.plex_login_enabled)
        self.assertFalse(settings.auth.oidc_enabled)
        self.assertFalse(settings.auth.local_login_enabled)
        self.assertEqual(settings.seerr.url, "")
        self.assertTrue(settings.seerr.link_on_login)
        self.assertFalse(settings.seerr.require_linked_user_for_requests)

    def test_feature_flags_round_trip(self) -> None:
        from curatorx.config_store import AuthSettings, FeatureFlags, SeerrSettings

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(
                features=FeatureFlags(multi_user_enabled=True, seerr_enabled=True),
                auth=AuthSettings(mode="plex", oidc_enabled=True),
                seerr=SeerrSettings(url="http://seerr.local", api_key="secret"),
            )
            save_settings(data_dir, settings)
            loaded = load_merged_settings(data_dir)
            self.assertTrue(loaded.features.multi_user_enabled)
            self.assertTrue(loaded.features.seerr_enabled)
            self.assertEqual(loaded.auth.mode, "plex")
            self.assertTrue(loaded.auth.oidc_enabled)
            self.assertEqual(loaded.seerr.url, "http://seerr.local")
            self.assertEqual(loaded.seerr.api_key, "secret")

    def test_load_merged_settings_normalizes_empty_path_fields(self) -> None:
        env_keys = ("MOVIES_ROOT", "TV_ROOT", "RADARR_ROOT_FOLDER", "SONARR_ROOT_FOLDER")
        saved = {k: os.environ.pop(k, None) for k in env_keys}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                save_settings(
                    data_dir,
                    Settings(radarr_root_folder="", movies_root="", radarr_url="http://radarr"),
                )
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.radarr_root_folder, "/media/movies")
                self.assertEqual(loaded.movies_root, "/media/movies")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
