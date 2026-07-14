"""Tests for Seerr connector, setup, API routes, and agent tools."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.agent.tools import ToolRegistry
from curatorx.config_store import (
    FeatureFlags,
    SeerrSettings,
    Settings,
    seerr_configuration_error,
    uses_seerr_request_path,
)
from curatorx.connectors.seerr import SeerrClient
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.web import setup as setup_mod


class SeerrClientTests(unittest.TestCase):
    def test_create_request_posts_expected_body(self) -> None:
        client = SeerrClient("http://seerr.test", "secret-key")
        captured: dict[str, object] = {}

        def fake_request_json(url: str, *, method: str = "GET", headers=None, body=None, timeout: int = 30):
            captured["url"] = url
            captured["method"] = method
            captured["headers"] = headers
            captured["body"] = body
            return {"id": 42, "status": 2}

        with patch("curatorx.connectors.seerr.request_json", side_effect=fake_request_json):
            result = client.create_request("show", 123, tvdb_id=456, seasons=[1, 2])

        self.assertEqual(captured["method"], "POST")
        self.assertIn("/api/v1/request", str(captured["url"]))
        self.assertEqual(captured["headers"], {"X-Api-Key": "secret-key"})
        self.assertEqual(
            captured["body"],
            {"mediaType": "tv", "mediaId": 123, "is4k": False, "tvdbId": 456, "seasons": [1, 2]},
        )
        self.assertEqual(result["id"], 42)

    def test_list_requests_builds_query_params(self) -> None:
        client = SeerrClient("http://seerr.test", "secret-key")
        captured: dict[str, str] = {}

        def fake_request_json(url: str, *, method: str = "GET", headers=None, body=None, timeout: int = 30):
            captured["url"] = url
            captured["method"] = method
            return {"results": [], "pageInfo": {"results": 0, "pages": 0, "page": 1, "pageSize": 5}}

        with patch("curatorx.connectors.seerr.request_json", side_effect=fake_request_json):
            client.list_requests(take=5, skip=10, filter="pending", media_type="show")

        self.assertEqual(captured["method"], "GET")
        self.assertIn("take=5", captured["url"])
        self.assertIn("skip=10", captured["url"])
        self.assertIn("filter=pending", captured["url"])
        self.assertIn("mediaType=tv", captured["url"])

    def test_get_user_requires_dict_response(self) -> None:
        client = SeerrClient("http://seerr.test", "secret-key")
        with patch("curatorx.connectors.seerr.request_json", return_value=[]):
            with self.assertRaises(RuntimeError):
                client.get_user()


class SeerrConfigTests(unittest.TestCase):
    def test_configuration_error_when_disabled(self) -> None:
        settings = Settings(features=FeatureFlags(seerr_enabled=False))
        self.assertEqual(
            seerr_configuration_error(settings),
            "Seerr is not enabled. Turn on features.seerr_enabled in Configuration.",
        )

    def test_configuration_error_when_missing_credentials(self) -> None:
        settings = Settings(features=FeatureFlags(seerr_enabled=True))
        self.assertEqual(
            seerr_configuration_error(settings),
            "Seerr is not configured. Add Seerr URL and API key in Configuration.",
        )

    def test_configuration_ok_when_enabled_and_configured(self) -> None:
        settings = Settings(
            features=FeatureFlags(seerr_enabled=True),
            seerr=SeerrSettings(url="http://seerr.test", api_key="secret"),
        )
        self.assertIsNone(seerr_configuration_error(settings))

    def test_uses_seerr_request_path_for_members_only(self) -> None:
        settings = Settings(features=FeatureFlags(seerr_enabled=True))
        self.assertFalse(uses_seerr_request_path(settings, role="owner"))
        self.assertTrue(uses_seerr_request_path(settings, role="member"))


class SeerrSetupTests(unittest.TestCase):
    def test_test_seerr_requires_url_and_key(self) -> None:
        result = setup_mod.test_seerr("", "")
        self.assertFalse(result["ok"])
        self.assertIn("required", result["message"])

    def test_test_seerr_success_message(self) -> None:
        with patch("curatorx.web.setup.SeerrClient.get_user", return_value={"displayName": "Admin", "id": 1}), patch(
            "curatorx.web.setup.SeerrClient.list_requests",
            return_value={"pageInfo": {"results": 3}},
        ):
            result = setup_mod.test_seerr("http://seerr.test", "secret")
        self.assertTrue(result["ok"])
        self.assertIn("Admin", result["message"])
        self.assertEqual(result["pending_requests"], 3)


class SeerrApiTests(unittest.TestCase):
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

    def _enable_seerr(self) -> None:
        self.client.put(
            "/api/settings",
            json={
                "features": {"seerr_enabled": True},
                "seerr": {"url": "http://seerr.test", "api_key": "secret"},
            },
        )

    def test_setup_test_seerr_records_certification(self) -> None:
        with patch("curatorx.web.setup.SeerrClient.get_user", return_value={"email": "owner@example.com", "id": 9}), patch(
            "curatorx.web.setup.SeerrClient.list_requests",
            return_value={"pageInfo": {"results": 0}},
        ):
            resp = self.client.post(
                "/api/setup/test/seerr",
                json={"seerr_url": "http://seerr.test", "seerr_api_key": "secret"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])

        certs = self.client.get("/api/setup/certifications").json()
        self.assertTrue(certs["services"]["seerr"]["certified"])

    def test_list_requests_requires_enabled_seerr(self) -> None:
        resp = self.client.get("/api/requests")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not enabled", resp.json()["detail"].lower())

    def test_list_requests_proxies_seerr(self) -> None:
        self._enable_seerr()
        payload = {
            "results": [{"id": 1, "status": 2}],
            "pageInfo": {"results": 1, "pages": 1, "page": 1, "pageSize": 20},
        }
        with patch("curatorx.web.app.SeerrClient.list_requests", return_value=payload) as mock_list:
            resp = self.client.get("/api/requests?take=10&filter=pending")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), payload)
        mock_list.assert_called_once_with(take=10, skip=0, filter="pending", requested_by=None)

    def test_propose_request_seerr_returns_token(self) -> None:
        self._enable_seerr()
        resp = self.client.post(
            "/api/actions/propose",
            json={
                "action": "request_seerr",
                "media_type": "movie",
                "tmdb_id": 603,
                "title": "The Matrix",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("confirmation_token", body)

    def test_features_request_path_for_owner_defaults_to_arr(self) -> None:
        self._enable_seerr()
        resp = self.client.get("/api/features")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["features"]["seerr_enabled"])
        self.assertEqual(body["request_path"], "arr")


class SeerrAgentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_via_seerr_returns_confirmation_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                features=FeatureFlags(seerr_enabled=True),
                seerr=SeerrSettings(url="http://seerr.test", api_key="secret"),
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID)
            result = await registry.execute(
                "request_via_seerr",
                {"media_type": "movie", "tmdb_id": 603, "title": "The Matrix"},
            )
            payload = json.loads(result)
            self.assertIn("confirmation_token", payload)
            self.assertEqual(len(registry.pending_tokens), 1)

    async def test_request_via_seerr_always_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                features=FeatureFlags(seerr_enabled=True),
                seerr=SeerrSettings(url="http://seerr.test", api_key="secret"),
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID)
            with patch(
                "curatorx.agent.tools.SeerrClient.create_request",
            ) as create_request:
                result = await registry.execute(
                    "request_via_seerr",
                    {
                        "media_type": "movie",
                        "tmdb_id": 603,
                        "title": "The Matrix",
                        "require_confirmation": False,
                    },
                )
            payload = json.loads(result)
            self.assertIn("confirmation_token", payload)
            create_request.assert_not_called()

    async def test_request_via_seerr_errors_when_not_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute(
                "request_via_seerr",
                {"media_type": "movie", "tmdb_id": 603, "title": "The Matrix"},
            )
            payload = json.loads(result)
            self.assertIn("error", payload)

    async def test_search_seerr_movie_returns_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(
                features=FeatureFlags(seerr_enabled=True),
                seerr=SeerrSettings(url="http://seerr.test", api_key="secret"),
            )
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID)
            fake_results = [
                {
                    "mediaType": "movie",
                    "title": "The Matrix",
                    "tmdbId": 603,
                    "releaseDate": "1999-03-31",
                    "overview": "A hacker learns the truth.",
                }
            ]
            with patch.object(SeerrClient, "search_movie", return_value=fake_results):
                result = await registry.execute("search_seerr_movie", {"query": "Matrix"})
            payload = json.loads(result)
            self.assertEqual(payload["returned"], 1)
            self.assertEqual(payload["items"][0]["tmdb_id"], 603)

    async def test_search_seerr_tv_errors_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            result = await registry.execute("search_seerr_tv", {"query": "Severance"})
            payload = json.loads(result)
            self.assertIn("error", payload)
            self.assertIn("not enabled", payload["error"].lower())
