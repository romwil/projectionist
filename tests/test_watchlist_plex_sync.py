"""Tests for Plex Discover watchlist sync and pin helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import FeatureFlags, Settings
from curatorx.library.db import Database
from curatorx.watchlist.crypto import decrypt_plex_token, encrypt_plex_token
from curatorx.watchlist.curate import critique_watchlist, curate_watchlist, enrich_watchlist_pins
from curatorx.watchlist.plex_discover import discover_rating_key_from_guid
from curatorx.watchlist.plex_sync import get_watchlist_sync_status, sync_watchlist_with_plex


class WatchlistCryptoTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"DATA_DIR": tmp, "CURATORX_SESSION_SECRET": "unit-test-secret"}):
                from curatorx.web.session_tokens import clear_session_secret_cache

                clear_session_secret_cache()
                blob = encrypt_plex_token("plex-auth-token")
                self.assertNotIn("plex-auth-token", blob)
                self.assertEqual(decrypt_plex_token(blob), "plex-auth-token")
                clear_session_secret_cache()


class WatchlistDiscoverHelpersTests(unittest.TestCase):
    def test_rating_key_from_guid(self) -> None:
        self.assertEqual(
            discover_rating_key_from_guid("plex://movie/5d7768294eefaa001fabe8b3"),
            "5d7768294eefaa001fabe8b3",
        )


class WatchlistSyncUnitTests(unittest.TestCase):
    def test_missing_token_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.ensure_seed_data()
            db.ensure_bootstrap_owner()
            status = get_watchlist_sync_status(
                db,
                Settings(features=FeatureFlags(multi_user_enabled=True)),
                user_id="bootstrap-owner",
            )
            self.assertFalse(status["has_plex_token"])
            self.assertIn("Re-sign in", status["message"] or "")

    def test_pull_upserts_local_pins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.ensure_seed_data()
            user = db.upsert_plex_user(
                user_id="plex-1",
                display_name="Will",
                email=None,
                plex_user_id="1",
                role="owner",
            )
            with patch.dict("os.environ", {"DATA_DIR": tmp, "CURATORX_SESSION_SECRET": "unit-test-secret"}):
                from curatorx.web.session_tokens import clear_session_secret_cache

                clear_session_secret_cache()
                try:
                    db.set_user_plex_token_enc(user["id"], encrypt_plex_token("token"))
                    remote = [
                        {
                            "title": "Inception",
                            "media_type": "movie",
                            "tmdb_id": 27205,
                            "tvdb_id": None,
                            "plex_rating_key": "abc123",
                        }
                    ]
                    with patch(
                        "curatorx.watchlist.plex_discover.fetch_watchlist",
                        return_value=remote,
                    ):
                        result = sync_watchlist_with_plex(
                            db,
                            Settings(features=FeatureFlags(multi_user_enabled=True)),
                            user_id=user["id"],
                            direction="pull",
                        )
                finally:
                    clear_session_secret_cache()
            self.assertGreaterEqual(result["pulled"], 1)
            pins = db.list_watchlist_pins(user_id=user["id"])
            self.assertEqual(len(pins), 1)
            self.assertEqual(pins[0]["tmdb_id"], 27205)
            self.assertEqual(pins[0]["plex_rating_key"], "abc123")

    def test_curate_and_critique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.ensure_seed_data()
            pin = db.add_watchlist_pin(
                pin_id="p1",
                user_id=None,
                tmdb_id=1,
                tvdb_id=None,
                media_type="movie",
                title="Stale Pick",
            )
            curated = curate_watchlist(db, [pin])
            self.assertIn("remove_suggestions", curated)
            critique = critique_watchlist([pin], persona={"val_dipl_snark": 0.9})
            self.assertTrue(critique["critique"])
            enriched = enrich_watchlist_pins(db, [pin])
            self.assertIn("in_library", enriched[0])


class WatchlistApiTests(unittest.TestCase):
    def setUp(self) -> None:
        import importlib
        import os

        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["CURATORX_SESSION_SECRET"] = "unit-test-secret"
        from curatorx.web.session_tokens import clear_session_secret_cache
        import curatorx.web.jobs as jobs
        import curatorx.web.app as app_mod

        clear_session_secret_cache()
        jobs._manager = None
        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import os
        from curatorx.web.session_tokens import clear_session_secret_cache
        import curatorx.web.jobs as jobs

        clear_session_secret_cache()
        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        self._tmpdir.cleanup()

    def test_sync_status_endpoint(self) -> None:
        resp = self.client.get("/api/watchlist/sync")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("enabled", body)
        self.assertIn("last_synced_at", body)
        self.assertIn("limitations", body)

    def test_sync_settings_update(self) -> None:
        resp = self.client.put(
            "/api/watchlist/sync",
            json={"enabled": False, "push_on_pin": False},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["enabled"])
        self.assertFalse(resp.json()["push_on_pin"])


class PurgeCardKindTests(unittest.TestCase):
    def test_purge_cards_mark_card_kind(self) -> None:
        from curatorx.preferences.purge import suggest_purge_candidates

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.ensure_seed_data()
            db.upsert_library_item(
                {
                    "rating_key": "rk1",
                    "media_type": "movie",
                    "title": "Huge Unused",
                    "year": 2000,
                    "tmdb_id": 99,
                    "genres": ["Drama"],
                    "file_size": 2_000_000_000,
                    "view_count": 0,
                }
            )
            cards = suggest_purge_candidates(db, Settings(), limit=5, min_file_size=500_000_000)
            self.assertTrue(cards)
            self.assertEqual(cards[0].card_kind, "purge")


if __name__ == "__main__":
    unittest.main()
