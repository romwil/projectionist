"""Unit tests for the Tunarr OpenAPI client (no live Tunarr)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from projectionist.connectors.tunarr import TunarrClient, tunarr_reachable


class TunarrClientTests(unittest.TestCase):
    def test_api_url_prefix(self) -> None:
        client = TunarrClient("http://tunarr.test:8000/")
        self.assertEqual(client._api_url("/channels"), "http://tunarr.test:8000/api/channels")
        self.assertEqual(client._api_url("version"), "http://tunarr.test:8000/api/version")

    def test_requires_base_url(self) -> None:
        with self.assertRaises(ValueError):
            TunarrClient("  ")

    def test_health_and_check(self) -> None:
        client = TunarrClient("http://tunarr.test")
        calls: list[str] = []

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del method, headers, body, timeout
            calls.append(url)
            if url.endswith("/system/health"):
                return {"ffmpeg": {"healthy": True}}
            if url.endswith("/version"):
                return {"tunarr": "1.3.2", "ffmpeg": "7.0", "nodejs": "22.0.0"}
            raise AssertionError(f"unexpected url {url}")

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            health = client.health()
            self.assertTrue(health["ffmpeg"]["healthy"])
            checked = client.check()
            self.assertTrue(checked["ok"])
            self.assertEqual(checked["tunarr_version"], "1.3.2")
        self.assertEqual(len(calls), 3)

    def test_list_and_create_channels(self) -> None:
        client = TunarrClient("http://tunarr.test")

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del headers, timeout
            if method == "GET" and url.endswith("/channels"):
                return [{"id": "ch-1", "number": 100, "name": "Chaos"}]
            if method == "POST" and url.endswith("/channels"):
                self.assertEqual(body, {"type": "new", "channel": {"name": "Motif", "number": 101}})
                return {"id": "ch-2", "number": 101, "name": "Motif"}
            raise AssertionError(f"unexpected {method} {url}")

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            listed = client.list_channels()
            self.assertEqual(listed[0]["name"], "Chaos")
            created = client.create_channel({"type": "new", "channel": {"name": "Motif", "number": 101}})
            self.assertEqual(created["id"], "ch-2")

    def test_media_sources_and_programming(self) -> None:
        client = TunarrClient("http://tunarr.test")

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del headers, timeout
            if method == "GET" and url.endswith("/media-sources"):
                return [{"id": "ms-1", "type": "plex"}]
            if method == "POST" and url.endswith("/media-sources"):
                return {"id": "ms-2", **(body or {})}
            if method == "POST" and "/programming" in url:
                return {"lineup": body or {}}
            if method == "GET" and "/programming" in url:
                return {"programs": []}
            raise AssertionError(f"unexpected {method} {url}")

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            sources = client.list_media_sources()
            self.assertEqual(sources[0]["type"], "plex")
            created = client.create_media_source({"name": "Plex", "type": "plex"})
            self.assertEqual(created["id"], "ms-2")
            programming = client.set_channel_programming("ch-1", {"type": "manual", "programs": []})
            self.assertIn("lineup", programming)
            self.assertEqual(client.get_channel_programming("ch-1")["programs"], [])

    def test_filler_lists(self) -> None:
        client = TunarrClient("http://tunarr.test")

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del headers, timeout
            if method == "GET":
                return [{"id": "f1", "name": "Trailers", "contentCount": 3}]
            return {"id": "f2"}

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            listed = client.list_filler_lists()
            self.assertEqual(listed[0]["name"], "Trailers")
            created = client.create_filler_list({"name": "Bumpers"})
            self.assertEqual(created["id"], "f2")

    def test_tunarr_reachable_empty_and_failure(self) -> None:
        empty = tunarr_reachable("")
        self.assertFalse(empty["reachable"])
        with patch(
            "projectionist.connectors.tunarr.TunarrClient.check",
            side_effect=RuntimeError("down"),
        ):
            failed = tunarr_reachable("http://tunarr.test")
        self.assertFalse(failed["reachable"])
        self.assertIn("down", failed["error"])

    def test_guide_and_now_playing(self) -> None:
        client = TunarrClient("http://tunarr.test")

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del method, headers, body, timeout
            if "/guide/channels" in url:
                self.assertIn("dateFrom=", url)
                self.assertIn("dateTo=", url)
                return {"ch-1": {"id": "ch-1", "name": "Chaos", "programs": []}}
            if url.endswith("/now_playing"):
                return {"title": "Heat", "start": 1_700_000_000_000}
            raise AssertionError(f"unexpected url {url}")

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            guide = client.get_all_channel_guides(1_700_000_000, 1_700_010_800)
            self.assertEqual(guide["ch-1"]["name"], "Chaos")
            playing = client.get_now_playing("ch-1")
            self.assertEqual(playing["title"], "Heat")

    def test_sessions_and_guide_status(self) -> None:
        client = TunarrClient("http://tunarr.test")

        def fake_request_json(url, *, method="GET", headers=None, body=None, timeout=30):
            del method, headers, body, timeout
            if url.endswith("/sessions"):
                return {
                    "ch-1": [{"type": "hls", "state": "started", "numConnections": 1}],
                    "bad": "skip",
                }
            if url.endswith("/guide/status"):
                return {"channelIds": ["ch-1"], "lastUpdate": {"ch-1": "2026-07-29T12:00:00Z"}}
            raise AssertionError(f"unexpected url {url}")

        with patch("projectionist.connectors.tunarr.request_json", side_effect=fake_request_json):
            sessions = client.list_sessions()
            self.assertEqual(sessions["ch-1"][0]["numConnections"], 1)
            self.assertNotIn("bad", sessions)
            status = client.get_guide_status()
            self.assertEqual(status["channelIds"], ["ch-1"])


if __name__ == "__main__":
    unittest.main()
