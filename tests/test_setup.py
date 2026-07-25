"""Tests for setup wizard helpers."""

import unittest

from projectionist.config_store import Settings
from projectionist.web.setup import merge_secret_fields, resolve_test_payload


class SetupTests(unittest.TestCase):
    def test_resolve_test_payload_backfills_llm_model(self) -> None:
        existing = Settings(llm_provider="anthropic", llm_model="claude-sonnet-4-6")
        merged = resolve_test_payload({"llm_provider": "anthropic"}, existing)
        self.assertEqual(merged["llm_model"], "claude-sonnet-4-6")

    def test_resolve_test_payload_preserves_incoming_llm_model(self) -> None:
        existing = Settings(llm_provider="anthropic", llm_model="claude-sonnet-4-6")
        merged = resolve_test_payload(
            {"llm_provider": "anthropic", "llm_model": "claude-sonnet-4-20250514"},
            existing,
        )
        self.assertEqual(merged["llm_model"], "claude-sonnet-4-20250514")

    def test_merge_secret_fields_preserves_plex_sections(self) -> None:
        existing = Settings(plex_movie_section="1", plex_tv_section="2")
        merged = merge_secret_fields(
            {"plex_movie_section": "", "plex_tv_section": ""},
            existing,
        )
        self.assertEqual(merged["plex_movie_section"], "1")
        self.assertEqual(merged["plex_tv_section"], "2")

    def test_merge_secret_fields_preserves_onboarding_complete(self) -> None:
        existing = Settings(onboarding_complete=True)
        merged = merge_secret_fields({"onboarding_complete": False}, existing)
        self.assertTrue(merged["onboarding_complete"])

    def test_merge_secret_fields_allows_onboarding_complete(self) -> None:
        existing = Settings(onboarding_complete=False)
        merged = merge_secret_fields({"onboarding_complete": True}, existing)
        self.assertTrue(merged["onboarding_complete"])


if __name__ == "__main__":
    unittest.main()
