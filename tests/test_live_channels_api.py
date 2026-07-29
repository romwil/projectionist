"""Focused API tests for Live Channels Phase 2 owner endpoints."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class LiveChannelsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        for key in ("CURATORX_SKIP_DOTENV", "PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _enable(self, **tunarr_extra) -> None:
        tunarr = {
            "url": "http://tunarr.test:8000",
            "docker_orchestration": False,
            "image_tag": "chrisbenincasa/tunarr:1.3.x",
            **tunarr_extra,
        }
        resp = self.client.put(
            "/api/settings",
            json={
                "features": {"live_channels_enabled": True},
                "tunarr": tunarr,
                "plex_url": "http://plex.test",
                "plex_token": "plex-token",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_setup_test_tunarr_records_certification(self) -> None:
        with patch(
            "projectionist.connectors.tunarr.TunarrClient.check",
            return_value={"ok": True, "tunarr_version": "1.3.1"},
        ), patch(
            "projectionist.connectors.tunarr.TunarrClient.list_channels",
            return_value=[],
        ):
            resp = self.client.post(
                "/api/setup/test/tunarr",
                json={"tunarr_url": "http://tunarr.test:8000"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["ok"])
        certs = self.client.get("/api/setup/certifications").json()
        self.assertTrue(certs["services"]["tunarr"]["certified"])

    def test_preflight_and_status(self) -> None:
        self._enable(plex_pass_confirmed=True)
        with patch(
            "projectionist.connectors.plex.PlexClient.server_identity",
            return_value=("mid", "Plex"),
        ), patch(
            "projectionist.live_channels.status.tunarr_reachable",
            return_value={"reachable": True, "tunarr_version": "1.3.2"},
        ), patch(
            "projectionist.live_channels.status.TunarrClient.list_channels",
            return_value=[{"id": "1", "name": "Chaos", "number": 100}],
        ):
            pre = self.client.post(
                "/api/admin/live-channels/preflight",
                json={"plex_pass_confirmed": True},
            )
            status = self.client.get("/api/admin/live-channels/status")
        self.assertEqual(pre.status_code, 200, pre.text)
        self.assertTrue(pre.json()["ready"])
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body["channel_count"], 1)
        self.assertIn("broadcast", body)

    def test_publish_requires_confirm(self) -> None:
        self._enable()
        resp = self.client.post(
            "/api/admin/live-channels/starters/publish",
            json={"recipes": [], "confirm": False},
        )
        self.assertEqual(resp.status_code, 400)

    def test_publish_starters(self) -> None:
        self._enable()
        client = MagicMock()
        client.list_media_sources.return_value = []
        client.create_media_source.return_value = {"id": "ms-1", "type": "plex"}
        client.list_channels.return_value = []
        client.create_channel.side_effect = lambda body: {
            "id": "ch-new",
            "name": body["channel"]["name"],
            "number": body["channel"]["number"],
        }
        client.set_channel_programming.return_value = {"programs": []}

        with patch(
            "projectionist.live_channels.publish.TunarrClient",
            return_value=client,
        ):
            resp = self.client.post(
                "/api/admin/live-channels/starters/publish",
                json={
                    "confirm": True,
                    "wire_plex": True,
                    "recipes": [
                        {
                            "name": "Chaos",
                            "number": 100,
                            "source": "chaos",
                            "programming_mode": "chaos",
                        }
                    ],
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["count_published"], 1)
        self.assertTrue(body["media_source"]["ok"])

    def test_lifecycle_noop_without_orchestration(self) -> None:
        self._enable(docker_orchestration=False)
        resp = self.client.post(
            "/api/admin/live-channels/lifecycle",
            json={"action": "ensure_running"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["status"], "unavailable")

    def test_plex_attach(self) -> None:
        self._enable()
        with patch(
            "projectionist.live_channels.plex_attach.probe_tuner_discovery",
            return_value={"ok": True, "message": "ok"},
        ), patch(
            "projectionist.live_channels.plex_attach.probe_existing_plex_livetv",
            return_value={
                "status": "detected",
                "ok": True,
                "device_count": 1,
                "message": "Existing Live TV setup detected — Tunarr will be added as another tuner.",
            },
        ):
            resp = self.client.get("/api/admin/live-channels/plex-attach")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("api/xmltv.xml", body["guide_url"])
        self.assertTrue(body["steps"])
        self.assertEqual(body["coexistence"]["mode"], "additional_tuner")
        self.assertEqual(body["existing_livetv"]["status"], "detected")
        self.assertIn("another tuner", body["existing_livetv"]["message"].lower())


if __name__ == "__main__":
    unittest.main()
