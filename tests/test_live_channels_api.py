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
        from projectionist.live_channels.lifecycle_progress import reset_progress_for_tests

        reset_progress_for_tests()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs
        from projectionist.live_channels.lifecycle_progress import reset_progress_for_tests

        jobs._manager = None
        reset_progress_for_tests()
        for key in ("CURATORX_SKIP_DOTENV", "PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _enable(self, **tunarr_extra) -> None:
        tunarr = {
            "url": "http://tunarr.test:8000",
            "docker_orchestration": False,
            "image_tag": "chrisbenincasa/tunarr:1.3.9",
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

    def test_tunarr_logs_endpoint(self) -> None:
        self._enable()
        with patch(
            "projectionist.live_channels.logs.fetch_tunarr_logs",
            return_value={
                "ok": True,
                "source": "tunarr_api",
                "lines": 200,
                "text": "log-line",
                "message": "Recent Tunarr API logs.",
            },
        ):
            resp = self.client.get("/api/admin/live-channels/tunarr-logs?lines=50")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["text"], "log-line")
        self.assertEqual(body["source"], "tunarr_api")

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
        client.default_transcode_config_id.return_value = "tc-default"
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
        create_body = client.create_media_source.call_args.args[0]
        self.assertEqual(create_body["type"], "plex")
        self.assertIn("userId", create_body)
        self.assertIn("username", create_body)
        self.assertEqual(create_body["pathReplacements"], [])

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

    def test_lifecycle_status_ready_via_http(self) -> None:
        self._enable(docker_orchestration=True, url="http://tunarr.test:18765")
        with patch(
            "projectionist.live_channels.docker.docker_socket_available",
            return_value=True,
        ), patch(
            "projectionist.live_channels.lifecycle_progress.probe_tunarr_http_ready",
            return_value=True,
        ), patch(
            "projectionist.live_channels.lifecycle_progress.probe_ready_from_docker",
            return_value={
                "container_running": True,
                "container_id": "abc123def456",
                "logs_ready": False,
                "log_snippet": "",
            },
        ):
            resp = self.client.get("/api/admin/live-channels/lifecycle-status")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["ready"])
        self.assertEqual(body["phase"], "ready")
        self.assertEqual(body["percent"], 100)
        self.assertTrue(body["http_ready"])
        self.assertEqual(body["container_id"], "abc123def456")

    def test_lifecycle_status_ready_via_logs_marker(self) -> None:
        self._enable(docker_orchestration=True, url="")
        with patch(
            "projectionist.live_channels.docker.docker_socket_available",
            return_value=True,
        ), patch(
            "projectionist.live_channels.lifecycle_progress.probe_tunarr_http_ready",
            return_value=False,
        ), patch(
            "projectionist.live_channels.lifecycle_progress.probe_ready_from_docker",
            return_value={
                "container_running": True,
                "container_id": "deadbeef0001",
                "logs_ready": True,
                "log_snippet": "Tunarr is ready!",
            },
        ):
            resp = self.client.get("/api/admin/live-channels/lifecycle-status")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["ready"])
        self.assertTrue(body["logs_ready"])
        self.assertEqual(body["phase"], "ready")

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


    def test_plex_attach_guide(self) -> None:
        self._enable(public_url="http://10.10.1.202:18765")
        with patch(
            "projectionist.live_channels.plex_attach.attach_tunarr_xmltv_to_plex",
            return_value={
                "ok": True,
                "dvr_key": "12",
                "mapped": 3,
                "message": "Tunarr guide attached on Plex DVR 12 (3 channel(s) mapped).",
                "steps": ["reused_xmltv_dvr"],
            },
        ):
            resp = self.client.post("/api/admin/live-channels/plex-attach-guide")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["dvr_key"], "12")

    def test_plex_attach_uses_public_url_not_docker_internal(self) -> None:
        self._enable(
            url="http://host.docker.internal:8000",
            public_url="http://10.10.1.202:8000",
        )
        with patch(
            "projectionist.live_channels.plex_attach.probe_tuner_discovery",
            return_value={"ok": True, "message": "ok"},
        ), patch(
            "projectionist.live_channels.plex_attach.probe_existing_plex_livetv",
            return_value={
                "status": "none",
                "ok": True,
                "device_count": 0,
                "message": "No existing tuners.",
            },
        ):
            resp = self.client.get("/api/admin/live-channels/plex-attach")
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["tuner_url"], "http://10.10.1.202:8000/")
        self.assertEqual(body["guide_url"], "http://10.10.1.202:8000/api/xmltv.xml")
        self.assertNotIn("host.docker.internal", body["tuner_url"])
        self.assertFalse(body.get("docker_only_url"))


if __name__ == "__main__":
    unittest.main()
