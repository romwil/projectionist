"""Delight 1.37.66 fleet briefs: FL-02, NW-01, LP-01, LIB-01, RA-01."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.programme_candidates import (
    GAP_REFUSE_NOTE,
    owned_programme_candidates,
)
from projectionist.mcp.mode import set_mcp_mode
from projectionist.notifications.newsletters import build_member_newsletter

try:
    from projectionist.mcp import server as mcp_server

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False
    mcp_server = None  # type: ignore[assignment]


def _radarr_ready_settings() -> MagicMock:
    mock_settings = MagicMock()
    mock_settings.radarr_url = "http://radarr"
    mock_settings.radarr_api_key = "key"
    mock_settings.radarr_root_folder = "/movies"
    mock_settings.movies_root = "/movies"
    mock_settings.radarr_quality_profile_id = 1
    return mock_settings


@skipUnless(HAS_MCP, "mcp package not installed")
class FleetProposeGapTests(unittest.TestCase):
    """FL-02: pending *arr add is a real gap; FL-01 confirm-gate stays."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_pending_add_tmdb_id_absent_from_library_items(self) -> None:
        with (
            patch.object(mcp_server, "_database", return_value=self.db),
            patch.object(mcp_server, "_settings", return_value=_radarr_ready_settings()),
            patch("projectionist.config_store.radarr_add_configuration_error", return_value=None),
            patch("projectionist.config_store.validate_arr_root_folder", return_value=None),
            patch("projectionist.config_store.resolve_radarr_root_folder", return_value="/movies"),
            patch("projectionist.connectors.radarr.RadarrClient") as client_cls,
            patch("projectionist.agent.tools.check_radarr_already_exists", return_value=None),
        ):
            client_cls.return_value.root_folders.return_value = [{"path": "/movies"}]
            raw = mcp_server.propose_add_radarr(
                tmdb_id=603,
                title="The Matrix",
                source="discover_missing_titles",
            )
        payload = json.loads(raw)
        token = payload["pending_token"]
        pending = self.db.pop_pending_action(token, user_id="plex-owner")
        self.assertIsNotNone(pending)
        tmdb_id = int(pending["tmdb_id"])
        self.assertEqual(tmdb_id, 603)
        self.assertIsNone(self.db.library_item_by_tmdb(tmdb_id, "movie"))
        self.assertEqual(pending.get("source"), "discover_missing_titles")
        self.assertEqual(payload.get("source"), "discover_missing_titles")

    def test_owned_library_title_does_not_mint_token(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-jaws",
                "media_type": "movie",
                "title": "Jaws",
                "year": 1975,
                "tmdb_id": 578,
            }
        )
        with (
            patch.object(mcp_server, "_database", return_value=self.db),
            patch.object(mcp_server, "_settings", return_value=_radarr_ready_settings()),
            patch("projectionist.config_store.radarr_add_configuration_error", return_value=None),
            patch("projectionist.connectors.radarr.RadarrClient") as client_cls,
            patch("projectionist.agent.tools.check_radarr_already_exists") as exists,
        ):
            raw = mcp_server.propose_add_radarr(tmdb_id=578, title="Jaws")
        payload = json.loads(raw)
        self.assertTrue(payload.get("already_in_library"))
        self.assertNotIn("pending_token", payload)
        client_cls.assert_not_called()
        exists.assert_not_called()

    def test_already_in_radarr_returns_existing_short_circuit(self) -> None:
        short = {
            "already_exists": True,
            "message": '"The Matrix" is already in Radarr',
            "result": {"id": 9, "title": "The Matrix"},
        }
        with (
            patch.object(mcp_server, "_database", return_value=self.db),
            patch.object(mcp_server, "_settings", return_value=_radarr_ready_settings()),
            patch("projectionist.config_store.radarr_add_configuration_error", return_value=None),
            patch("projectionist.config_store.validate_arr_root_folder", return_value=None),
            patch("projectionist.config_store.resolve_radarr_root_folder", return_value="/movies"),
            patch("projectionist.connectors.radarr.RadarrClient") as client_cls,
            patch("projectionist.agent.tools.check_radarr_already_exists", return_value=short),
            patch("projectionist.agent.tools.mark_in_radarr") as mark,
        ):
            client_cls.return_value.root_folders.return_value = [{"path": "/movies"}]
            raw = mcp_server.propose_add_radarr(tmdb_id=603, title="The Matrix")
        payload = json.loads(raw)
        self.assertTrue(payload.get("already_exists"))
        self.assertIn("already in Radarr", payload["message"])
        self.assertNotIn("pending_token", payload)
        mark.assert_called_once()

    def test_cosine_or_tmdb_search_source_is_refused(self) -> None:
        with patch.object(mcp_server, "_database", return_value=self.db):
            for source in ("search_tmdb_proxy", "cosine", "find_similar_titles"):
                payload = json.loads(
                    mcp_server.propose_add_radarr(tmdb_id=603, title="The Matrix", source=source)
                )
                self.assertIn("error", payload)
                self.assertNotIn("pending_token", payload)
                self.assertIn("discover_missing_titles", payload["error"])

    def test_confirm_without_scope_keeps_token(self) -> None:
        token = "tok-fl01"
        self.db.save_pending_action(
            token,
            "add_radarr",
            {"action": "add_radarr", "tmdb_id": 603, "source": "owner_named"},
            user_id=None,
        )
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("PROJECTIONIST_MCP_FULL_CONFIRM", None)
            with patch.object(mcp_server, "_database", return_value=self.db):
                payload = json.loads(mcp_server.confirm_pending_action(token, confirmed=True))
        self.assertTrue(payload.get("requires_human_confirmation"))
        surviving = self.db.pop_pending_action(token, user_id="plex-owner")
        self.assertIsNotNone(surviving)


@skipUnless(HAS_MCP, "mcp package not installed")
class NewsletterPreviewTests(unittest.TestCase):
    """NW-01: preview wraps build_member_newsletter and does not send mail."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        self.user = self.db.create_local_user(
            user_id="local-preview",
            display_name="PreviewMember",
            password_hash="x",
            role="member",
            email="preview@example.com",
        )
        self.settings = Settings.load(Path(self._tmpdir.name) / "settings.json")

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_preview_body_matches_admin_builder_and_does_not_send(self) -> None:
        expected = build_member_newsletter(
            self.db, self.settings, user=self.db._row_to_user(self.db.get_user(self.user["id"]))
        )
        with (
            patch.object(mcp_server, "_database", return_value=self.db),
            patch.object(mcp_server, "_settings", return_value=self.settings),
            patch("projectionist.notifications.service.deliver_notification") as deliver,
            patch("projectionist.notifications.newsletters.deliver_weekly_newsletters") as fanout,
        ):
            raw = mcp_server.weekly_newsletter_preview(user_id=self.user["id"])
        payload = json.loads(raw)
        self.assertTrue(payload.get("preview"))
        self.assertFalse(payload.get("sent"))
        self.assertEqual(payload.get("body"), expected["body"])
        self.assertEqual(payload.get("subject"), expected["subject"])
        self.assertEqual(payload.get("picks"), expected.get("picks") or [])
        self.assertIn("Nothing new this week", payload["body"])
        deliver.assert_not_called()
        fanout.assert_not_called()


class ProgrammeCandidateTests(unittest.TestCase):
    """LP-01: Chaos Night lists are owned library_query hits; gaps are refused."""

    def test_owned_library_query_hits_are_accepted(self) -> None:
        owned = [
            {
                "title": "The Thing",
                "year": 1982,
                "media_type": "movie",
                "rating_key": "rk-thing",
                "playable": True,
            },
            {
                "title": "Halloween",
                "year": 1978,
                "media_type": "movie",
                "rating_key": "rk-halloween",
            },
        ]
        payload = owned_programme_candidates(owned)
        keys = {item["rating_key"] for item in payload["items"]}
        self.assertEqual(keys, {"rk-thing", "rk-halloween"})
        self.assertTrue(all(item.get("playable") and item.get("in_library") for item in payload["items"]))
        self.assertFalse(payload.get("published"))
        self.assertEqual(payload["refused"], [])

    def test_discover_missing_titles_hit_is_refused(self) -> None:
        gap = {
            "title": "Missing Doc",
            "year": 2020,
            "media_type": "movie",
            "tmdb_id": 501,
            "poster_url": "https://image.tmdb.org/t/p/w500/x.jpg",
            "in_library": False,
        }
        payload = owned_programme_candidates([gap])
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["error"], GAP_REFUSE_NOTE)
        self.assertEqual(payload["refused"][0]["title"], "Missing Doc")
        self.assertFalse(payload.get("published"))

    def test_mixed_list_keeps_only_owned_playable_subset(self) -> None:
        payload = owned_programme_candidates(
            [
                {
                    "title": "The Thing",
                    "rating_key": "rk-thing",
                    "media_type": "movie",
                    "playable": True,
                },
                {
                    "title": "Missing Doc",
                    "tmdb_id": 501,
                    "in_library": False,
                },
            ]
        )
        self.assertEqual([item["title"] for item in payload["items"]], ["The Thing"])
        self.assertEqual(payload["refused"][0]["title"], "Missing Doc")


@skipUnless(HAS_MCP, "mcp package not installed")
class LibraryOwnedVsGapsTests(unittest.TestCase):
    """LIB-01 / LP-01 MCP: sample is a library row; gaps stay in_library false; no publish."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("privacy")
        self.db = Database(Path(self._tmpdir.name) / "test.db")
        self.db.upsert_library_item(
            {
                "rating_key": "rk-thing",
                "media_type": "movie",
                "title": "The Thing",
                "year": 1982,
                "genres": ["Horror"],
                "tmdb_id": 1090,
            }
        )

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_sample_owned_item_is_library_row(self) -> None:
        with patch.object(mcp_server, "_database", return_value=self.db):
            sample = json.loads(mcp_server.sample_owned_library(genres="Horror", limit=5))
        item = sample["sample_owned"]["items"][0]
        self.assertEqual(item["title"], "The Thing")
        self.assertTrue(item.get("in_library"))
        self.assertIsNotNone(self.db.library_item_by_tmdb(1090, "movie"))

    def test_discover_missing_items_are_not_in_library(self) -> None:
        settings = Settings(tmdb_api_key="test-key")
        with patch.object(mcp_server, "_database", return_value=self.db):
            with patch.object(mcp_server, "_settings", return_value=settings):
                with patch("projectionist.agent.tools.TMDBClient") as mock_tmdb_cls:
                    mock_tmdb = mock_tmdb_cls.return_value
                    mock_tmdb.genre_list_movies.return_value = [{"id": 27, "name": "Horror"}]
                    mock_tmdb.discover_movies.return_value = [
                        {
                            "id": 501,
                            "title": "Missing Doc",
                            "release_date": "2020-01-01",
                            "vote_average": 7.5,
                            "poster_path": "/x.jpg",
                        }
                    ]
                    mock_tmdb.poster_url.return_value = "https://image.tmdb.org/t/p/w500/x.jpg"
                    mock_tmdb.backdrop_url.return_value = ""
                    raw = mcp_server.discover_missing_titles(
                        media_type="movie", genres="Horror", limit=5
                    )
        payload = json.loads(raw)
        self.assertTrue(payload["items"])
        self.assertTrue(all(item.get("in_library") is False for item in payload["items"]))
        refused = owned_programme_candidates(payload["items"])
        self.assertEqual(refused["items"], [])
        self.assertEqual(refused["error"], GAP_REFUSE_NOTE)

    def test_library_query_candidates_are_owned_programmes(self) -> None:
        set_mcp_mode("full")
        with patch.object(mcp_server, "_database", return_value=self.db):
            queried = json.loads(mcp_server.library_query(genres="Horror", limit=5))
        payload = owned_programme_candidates(queried["items"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["rating_key"], "rk-thing")
        self.assertTrue(payload["items"][0]["playable"])

    def test_no_mcp_live_publish_tool(self) -> None:
        for name in (
            "publish_live_channel",
            "publish_channel_recipe",
            "publish_lineup",
            "go_on_air",
        ):
            self.assertFalse(hasattr(mcp_server, name))


class ProductTruthDocsTests(unittest.TestCase):
    """RA-01: PRODUCT/MCP tell agents VIP is not version truth; no Tunarr resurrection."""

    def test_product_and_mcp_name_lan_truth_and_not_vip(self) -> None:
        root = Path(__file__).resolve().parents[1]
        product = (root / "docs" / "PRODUCT.md").read_text(encoding="utf-8")
        mcp = (root / "docs" / "MCP.md").read_text(encoding="utf-8")
        self.assertIn("10.10.1.202:8788", product)
        self.assertIn("projectionist.automat.vip", product)
        self.assertIn("**not** version truth", product)
        self.assertIn("not version truth", mcp)
        self.assertIn("8792", product)
        self.assertNotIn("chrisbenincasa/tunarr", product)
        self.assertNotIn("gift_queue", product)
        self.assertIn("sample_owned_library", mcp)
        self.assertIn("**Not** gap discovery", mcp)
        self.assertIn("**no** MCP publish", mcp)


if __name__ == "__main__":
    unittest.main()
