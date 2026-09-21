"""Sonarr Find-all-missing: aired+monitored+no-file scan, Wanted compare, EpisodeSearch."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.connectors.sonarr import SonarrClient, SonarrSeries
from projectionist.library.sonarr_missing import (
    EPISODE_SEARCH_CHUNK,
    compare_to_wanted,
    filter_aired_missing_episodes,
    is_aired_missing_episode,
    normalize_command_status,
    queue_episode_searches,
    refresh_execution,
    reset_sonarr_missing_for_tests,
    scan_monitored_series,
    summarize_episode_search_commands,
)
from projectionist.web.auth import SESSION_COOKIE_NAME
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache, create_session_token


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _ep(
    *,
    episode_id: int = 101,
    series_id: int = 1,
    season: int = 1,
    episode: int = 1,
    title: str = "Pilot",
    air: Optional[str] = "2020-01-01T00:00:00Z",
    has_file: bool = False,
    monitored: bool = True,
) -> Dict[str, Any]:
    return {
        "id": episode_id,
        "seriesId": series_id,
        "seasonNumber": season,
        "episodeNumber": episode,
        "title": title,
        "airDateUtc": air,
        "hasFile": has_file,
        "monitored": monitored,
    }


class AiredMissingFilterTests(unittest.TestCase):
    def test_keeps_aired_monitored_episode_without_file(self) -> None:
        episode = _ep()
        self.assertTrue(
            is_aired_missing_episode(
                episode,
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )
        rows = filter_aired_missing_episodes(
            [episode],
            series_id=1,
            series_title="Lost",
            series_monitored=True,
            seasons=[{"seasonNumber": 1, "monitored": True}],
            include_specials=False,
            now=NOW,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            {
                "seriesId": 1,
                "seriesTitle": "Lost",
                "episodeId": 101,
                "season": 1,
                "episode": 1,
                "airDate": "2020-01-01T00:00:00Z",
                "title": "Pilot",
            },
        )

    def test_excludes_has_file(self) -> None:
        self.assertFalse(
            is_aired_missing_episode(
                _ep(has_file=True),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )

    def test_excludes_unmonitored_episode(self) -> None:
        self.assertFalse(
            is_aired_missing_episode(
                _ep(monitored=False),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )

    def test_excludes_future_and_missing_air_date(self) -> None:
        self.assertFalse(
            is_aired_missing_episode(
                _ep(air="2026-12-01T00:00:00Z"),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )
        self.assertFalse(
            is_aired_missing_episode(
                _ep(air=None),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )
        self.assertFalse(
            is_aired_missing_episode(
                _ep(air=""),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )

    def test_specials_default_off_and_opt_in(self) -> None:
        special = _ep(season=0, episode=1, title="Behind the Scenes")
        self.assertFalse(
            is_aired_missing_episode(
                special,
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=True,
            )
        )
        self.assertTrue(
            is_aired_missing_episode(
                special,
                now=NOW,
                include_specials=True,
                series_monitored=True,
                season_monitored=True,
            )
        )

    def test_unmonitored_series_excluded(self) -> None:
        self.assertFalse(
            is_aired_missing_episode(
                _ep(),
                now=NOW,
                include_specials=False,
                series_monitored=False,
                season_monitored=True,
            )
        )

    def test_unmonitored_season_excluded_even_if_episode_monitored(self) -> None:
        self.assertFalse(
            is_aired_missing_episode(
                _ep(season=2),
                now=NOW,
                include_specials=False,
                series_monitored=True,
                season_monitored=False,
            )
        )

    def test_missing_season_map_falls_back_to_series_monitored(self) -> None:
        rows = filter_aired_missing_episodes(
            [_ep()],
            series_id=1,
            series_title="Lost",
            series_monitored=True,
            seasons=None,
            include_specials=False,
            now=NOW,
        )
        self.assertEqual(len(rows), 1)

    def test_include_specials_keeps_s00_when_series_monitored_even_if_season_is_not(self) -> None:
        rows = filter_aired_missing_episodes(
            [_ep(season=0, episode=1, title="Special")],
            series_id=1,
            series_title="Lost",
            series_monitored=True,
            seasons=[{"seasonNumber": 0, "monitored": False}],
            include_specials=True,
            now=NOW,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["episodeId"], 101)


class WantedCompareTests(unittest.TestCase):
    def test_reports_scan_vs_wanted_counts_and_id_delta(self) -> None:
        comparison = compare_to_wanted([101, 102, 103], [102, 104])
        self.assertEqual(comparison["scan_count"], 3)
        self.assertEqual(comparison["wanted_count"], 2)
        self.assertEqual(sorted(comparison["only_in_scan"]), [101, 103])
        self.assertEqual(comparison["only_in_wanted"], [104])
        self.assertEqual(
            comparison["summary"],
            "Library scan found 3; Sonarr Wanted lists 2",
        )


class FakeSonarr:
    def __init__(self) -> None:
        self.series = [
            SonarrSeries(id=1, title="Lost", year=2004, tvdb_id=73739, tmdb_id=None, monitored=True),
            SonarrSeries(id=2, title="Skip Me", year=1999, tvdb_id=1, tmdb_id=None, monitored=False),
            SonarrSeries(id=3, title="The Wire", year=2002, tvdb_id=79126, tmdb_id=None, monitored=True),
        ]
        self.raw_series = [
            {
                "id": 1,
                "title": "Lost",
                "monitored": True,
                "seasons": [
                    {"seasonNumber": 0, "monitored": False},
                    {"seasonNumber": 1, "monitored": True},
                ],
            },
            {
                "id": 2,
                "title": "Skip Me",
                "monitored": False,
                "seasons": [{"seasonNumber": 1, "monitored": True}],
            },
            {
                "id": 3,
                "title": "The Wire",
                "monitored": True,
                "seasons": [{"seasonNumber": 1, "monitored": True}],
            },
        ]
        self.episode_map = {
            1: [
                _ep(episode_id=11, series_id=1, season=1, episode=1, title="Pilot"),
                _ep(episode_id=12, series_id=1, season=1, episode=2, title="Tabula Rasa", has_file=True),
                _ep(
                    episode_id=10,
                    series_id=1,
                    season=0,
                    episode=1,
                    title="Special",
                ),
            ],
            2: [_ep(episode_id=21, series_id=2, season=1, episode=1, title="Nope")],
            3: [
                _ep(episode_id=31, series_id=3, season=1, episode=1, title="The Target"),
                _ep(
                    episode_id=32,
                    series_id=3,
                    season=1,
                    episode=2,
                    title="Unaired",
                    air="2026-12-01T00:00:00Z",
                ),
            ],
        }
        self.wanted_pages = [
            {
                "page": 1,
                "pageSize": 100,
                "totalRecords": 2,
                "records": [{"id": 11}, {"id": 99}],
            }
        ]
        self.search_calls: List[List[int]] = []
        self.commands: List[Dict[str, Any]] = []
        self.cancelled_ids: List[int] = []
        self._next_command_id = 500

    def series_list(self) -> List[SonarrSeries]:
        return list(self.series)

    def series_items(self) -> List[Mapping[str, Any]]:
        return list(self.raw_series)

    def episodes(self, series_id: int) -> List[Mapping[str, Any]]:
        return list(self.episode_map.get(int(series_id), []))

    def wanted_missing(self, page: int = 1, page_size: int = 100) -> Mapping[str, Any]:
        del page_size
        if page < 1 or page > len(self.wanted_pages):
            return {"page": page, "pageSize": 100, "totalRecords": 0, "records": []}
        return self.wanted_pages[page - 1]

    def search_episodes(self, episode_ids: List[int]) -> Mapping[str, Any]:
        ids = [int(value) for value in episode_ids]
        self.search_calls.append(ids)
        command_id = self._next_command_id
        self._next_command_id += 1
        record = {
            "id": command_id,
            "name": "EpisodeSearch",
            "status": "queued",
            "message": "",
            "exception": None,
            "queued": "2026-09-21T17:00:00Z",
            "started": None,
            "ended": None,
            "body": {"episodeIds": ids, "name": "EpisodeSearch"},
            "episodeIds": ids,
        }
        self.commands.append(record)
        return dict(record)

    def list_commands(self) -> List[Mapping[str, Any]]:
        return [dict(item) for item in self.commands]

    def cancel_command(self, command_id: int) -> None:
        self.cancelled_ids.append(int(command_id))
        for item in self.commands:
            if int(item.get("id") or 0) == int(command_id) and str(item.get("status")) == "queued":
                item["status"] = "cancelled"
                item["ended"] = "2026-09-21T17:01:00Z"
                return

    def complete_commands(self, *, failed_ids: Optional[Sequence[int]] = None) -> None:
        failed = {int(value) for value in (failed_ids or [])}
        for item in self.commands:
            command_id = int(item.get("id") or 0)
            if str(item.get("status")) in {"completed", "failed", "aborted", "cancelled"}:
                continue
            if command_id in failed:
                item["status"] = "failed"
                item["exception"] = "Download client is unavailable"
                item["ended"] = "2026-09-21T17:02:00Z"
            else:
                item["status"] = "completed"
                item["ended"] = "2026-09-21T17:02:00Z"

    def search_series(self, series_id: int) -> Mapping[str, Any]:
        raise AssertionError(f"SeriesSearch must not be the missing path ({series_id})")


class ScanAndSearchTests(unittest.TestCase):
    def test_scan_aggregates_monitored_aired_gaps_and_skips_specials(self) -> None:
        fake = FakeSonarr()
        result = scan_monitored_series(fake, include_specials=False, now=NOW)
        ids = [row["episodeId"] for row in result["episodes"]]
        self.assertEqual(ids, [11, 31])
        self.assertEqual(result["scan_count"], 2)
        self.assertEqual(result["wanted_count"], 2)
        self.assertEqual(result["summary"], "Library scan found 2; Sonarr Wanted lists 2")
        self.assertEqual(result["only_in_scan"], [31])
        self.assertEqual(result["only_in_wanted"], [99])
        titles = {row["seriesTitle"] for row in result["episodes"]}
        self.assertEqual(titles, {"Lost", "The Wire"})

    def test_scan_includes_specials_when_toggled(self) -> None:
        fake = FakeSonarr()
        result = scan_monitored_series(fake, include_specials=True, now=NOW)
        ids = [row["episodeId"] for row in result["episodes"]]
        self.assertEqual(ids, [11, 10, 31])

    def test_episode_search_batches_and_never_uses_wanted_command(self) -> None:
        fake = FakeSonarr()
        ids = list(range(1, 92))
        queued = queue_episode_searches(fake, ids, chunk_size=50)
        self.assertEqual(queued["searches_queued"], 2)
        self.assertEqual(len(fake.search_calls), 2)
        self.assertEqual(len(fake.search_calls[0]), 50)
        self.assertEqual(len(fake.search_calls[1]), 41)
        self.assertEqual(queued["command"], "EpisodeSearch")
        self.assertEqual([row["id"] for row in queued["commands"]], [500, 501])

    def test_explicit_episode_ids_search_does_not_require_last_scan(self) -> None:
        fake = FakeSonarr()
        queued = queue_episode_searches(fake, [501, 502], chunk_size=50)
        self.assertEqual(fake.search_calls, [[501, 502]])
        self.assertEqual(queued["searches_queued"], 1)

    def test_queue_stops_when_cancel_requested_between_chunks(self) -> None:
        fake = FakeSonarr()
        ids = list(range(1, 92))
        calls = {"n": 0}

        def should_continue() -> bool:
            calls["n"] += 1
            return calls["n"] <= 1

        queued = queue_episode_searches(
            fake, ids, chunk_size=50, should_continue=should_continue
        )
        self.assertEqual(queued["searches_queued"], 1)
        self.assertEqual(len(fake.search_calls), 1)
        self.assertTrue(queued["stopped_early"])
        self.assertEqual(queued["pending_submit"], 1)


class SonarrClientHttpTests(unittest.TestCase):
    def test_wanted_missing_hits_paged_endpoint(self) -> None:
        payload = {"page": 2, "pageSize": 50, "totalRecords": 51, "records": [{"id": 7}]}

        def fake_request(url: str, **kwargs: Any) -> Any:
            self.assertIn("/api/v3/wanted/missing", url)
            self.assertIn("page=2", url)
            self.assertIn("pageSize=50", url)
            self.assertEqual(kwargs.get("method", "GET"), "GET")
            return payload

        with patch("projectionist.connectors.sonarr.request_json", side_effect=fake_request):
            client = SonarrClient("http://sonarr.test", "key")
            result = client.wanted_missing(page=2, page_size=50)
        self.assertEqual(result["totalRecords"], 51)
        self.assertEqual(result["records"][0]["id"], 7)

    def test_list_aired_missing_episodes_uses_episode_endpoint(self) -> None:
        series = {
            "id": 4,
            "title": "Fringe",
            "monitored": True,
            "seasons": [{"seasonNumber": 1, "monitored": True}],
        }
        episodes = [
            _ep(episode_id=41, series_id=4, title="Pilot"),
            _ep(episode_id=42, series_id=4, has_file=True, title="The Same Old Story"),
        ]
        calls: List[str] = []

        def fake_request(url: str, **kwargs: Any) -> Any:
            del kwargs
            calls.append(url)
            if "/api/v3/episode?" in url:
                self.assertIn("seriesId=4", url)
                return episodes
            if url.endswith("/api/v3/series/4"):
                return series
            raise AssertionError(url)

        with patch("projectionist.connectors.sonarr.request_json", side_effect=fake_request):
            client = SonarrClient("http://sonarr.test", "key")
            rows = client.list_aired_missing_episodes(4, include_specials=False, now=NOW)
        self.assertEqual([row["episodeId"] for row in rows], [41])
        self.assertTrue(any("/api/v3/episode?" in url for url in calls))

    def test_search_episodes_posts_episode_search_not_missing_episode_search(self) -> None:
        bodies: List[Mapping[str, Any]] = []

        def fake_request(url: str, **kwargs: Any) -> Any:
            self.assertTrue(url.endswith("/api/v3/command"))
            self.assertEqual(kwargs.get("method"), "POST")
            bodies.append(kwargs.get("body") or {})
            return {"name": "EpisodeSearch"}

        with patch("projectionist.connectors.sonarr.request_json", side_effect=fake_request):
            client = SonarrClient("http://sonarr.test", "key")
            client.search_episodes(list(range(1, 4)))
        self.assertEqual(bodies[0]["name"], "EpisodeSearch")
        self.assertNotEqual(bodies[0]["name"], "MissingEpisodeSearch")
        self.assertEqual(bodies[0]["episodeIds"], [1, 2, 3])

    def test_list_commands_and_cancel_hit_command_endpoints(self) -> None:
        calls: List[Dict[str, Any]] = []

        def fake_request(url: str, **kwargs: Any) -> Any:
            calls.append({"url": url, "method": kwargs.get("method", "GET")})
            if kwargs.get("method") == "DELETE":
                self.assertTrue(url.endswith("/api/v3/command/77"))
                return None
            self.assertTrue(url.endswith("/api/v3/command"))
            return [{"id": 77, "name": "EpisodeSearch", "status": "queued"}]

        with patch("projectionist.connectors.sonarr.request_json", side_effect=fake_request):
            client = SonarrClient("http://sonarr.test", "key")
            listed = client.list_commands()
            client.cancel_command(77)
        self.assertEqual(listed[0]["id"], 77)
        self.assertEqual(calls[0]["method"], "GET")
        self.assertEqual(calls[1]["method"], "DELETE")

    def test_episode_search_chunk_size_is_in_locked_range(self) -> None:
        self.assertGreaterEqual(EPISODE_SEARCH_CHUNK, 40)
        self.assertLessEqual(EPISODE_SEARCH_CHUNK, 50)


class SonarrMissingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "sonarr-missing-test-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        reset_sonarr_missing_for_tests()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True, "open_auto_provision": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "sonarr_url": "http://sonarr.test",
                    "sonarr_api_key": "secret",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        reset_sonarr_missing_for_tests()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _login_owner(self) -> None:
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email=None,
            plex_user_id="1",
            role="owner",
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("owner-1"))

    def _login_member(self) -> None:
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email=None,
            plex_user_id="2",
            role="member",
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))

    def _wait_until(self, predicate, *, timeout: float = 3.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        payload: Dict[str, Any] = {}
        while time.time() < deadline:
            resp = self.client.get("/api/admin/sonarr/missing/status")
            self.assertEqual(resp.status_code, 200, resp.text)
            payload = resp.json()
            if predicate(payload):
                return payload
            time.sleep(0.02)
        self.fail(f"status never matched: {payload}")
        return payload

    def _wait_idle(self) -> Dict[str, Any]:
        return self._wait_until(lambda payload: not payload.get("busy"))

    def test_member_gets_403_on_scan_status_and_search(self) -> None:
        self._login_member()
        self.assertEqual(self.client.post("/api/admin/sonarr/missing/scan", json={}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/sonarr/missing/status").status_code, 403)
        self.assertEqual(
            self.client.post("/api/admin/sonarr/missing/search", json={"search_all": True}).status_code,
            403,
        )
        self.assertEqual(self.client.post("/api/admin/sonarr/missing/cancel", json={}).status_code, 403)

    def test_scan_returns_immediately_then_status_has_result(self) -> None:
        self._login_owner()
        fake = FakeSonarr()
        with patch("projectionist.web.app.SonarrClient", return_value=fake):
            started = time.monotonic()
            resp = self.client.post(
                "/api/admin/sonarr/missing/scan",
                json={"include_specials": False},
            )
            elapsed = time.monotonic() - started
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertLess(elapsed, 0.5, "scan must not block the request thread")
        body = resp.json()
        self.assertTrue(body.get("job_id"))
        self.assertTrue(body.get("accepted"))
        self.assertTrue(body.get("busy"))
        status = self._wait_idle()
        self.assertEqual(status["phase"], "done")
        self.assertEqual(status["result"]["scan_count"], 2)
        self.assertIn("Library scan found 2", status["result"]["summary"])

    def test_search_all_uses_last_scan_and_episode_search_batches(self) -> None:
        self._login_owner()
        fake = FakeSonarr()
        with patch("projectionist.web.app.SonarrClient", return_value=fake):
            self.client.post("/api/admin/sonarr/missing/scan", json={})
            self._wait_idle()
            resp = self.client.post("/api/admin/sonarr/missing/search", json={"search_all": True})
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertTrue(resp.json().get("accepted"))
            status = self._wait_until(
                lambda payload: payload.get("phase") in {"executing", "searched", "error"}
            )
        self.assertEqual(fake.search_calls, [[11, 31]])
        self.assertEqual(status["phase"], "executing")
        self.assertTrue(status["busy"])
        self.assertLess(int(status.get("percent") or 0), 100)
        self.assertTrue(status.get("can_cancel"))
        self.assertEqual(status["execution"]["queued"], 1)
        self.assertEqual(status["execution"]["kind"], "command")
        last_path = Path(self._tmpdir.name) / "sonarr_missing_last.json"
        self.assertTrue(last_path.is_file())
        with patch("projectionist.web.app.SonarrClient", return_value=fake):
            fake.complete_commands()
            finished = self._wait_idle()
        self.assertEqual(finished["phase"], "searched")
        self.assertEqual(finished["percent"], 100)
        self.assertEqual(finished["execution"]["completed"], 1)
        self.assertFalse(finished.get("can_cancel"))

    def test_cancel_stops_queued_sonarr_commands_not_started(self) -> None:
        self._login_owner()
        fake = FakeSonarr()
        fake.search_episodes([11])
        fake.search_episodes([31])
        fake.commands[0]["status"] = "started"
        with patch("projectionist.web.app.SonarrClient", return_value=fake):
            from projectionist.library import sonarr_missing as missing

            store = missing.progress_store()
            store.begin(kind="search")
            store.set_commands(
                [dict(item) for item in fake.commands],
                searches_queued=2,
                searches_total=2,
            )
            store.update("executing", "Waiting on Sonarr to run EpisodeSearch…")
            resp = self.client.post("/api/admin/sonarr/missing/cancel", json={})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(fake.cancelled_ids, [501])
        self.assertEqual(body["execution"]["cancelled"], 1)
        self.assertEqual(body["execution"]["running"], 1)
        self.assertIn(body["phase"], {"executing", "cancelled"})
        self.assertNotIn("SABnzbd", json.dumps(body))


class CommandProgressTests(unittest.TestCase):
    def test_normalize_maps_sonarr_status_values(self) -> None:
        self.assertEqual(normalize_command_status("queued"), "queued")
        self.assertEqual(normalize_command_status("started"), "started")
        self.assertEqual(normalize_command_status("completed"), "completed")
        self.assertEqual(normalize_command_status("failed"), "failed")
        self.assertEqual(normalize_command_status("aborted"), "aborted")
        self.assertEqual(normalize_command_status("cancelled"), "cancelled")

    def test_summarize_counts_queued_running_completed_failed_not_sab(self) -> None:
        tracked = [
            {"id": 1, "name": "EpisodeSearch", "status": "queued"},
            {"id": 2, "name": "EpisodeSearch", "status": "started", "message": "Doctor Who"},
            {"id": 3, "name": "EpisodeSearch", "status": "completed", "ended": "2026-09-21T17:02:00Z"},
            {
                "id": 4,
                "name": "EpisodeSearch",
                "status": "failed",
                "exception": "Command failed: index is unavailable",
            },
        ]
        summary = summarize_episode_search_commands(tracked, live=[], pending_submit=2)
        self.assertEqual(summary["queued"], 1)
        self.assertEqual(summary["running"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["pending_submit"], 2)
        self.assertEqual(summary["total"], 6)
        self.assertEqual(summary["finished"], 2)
        self.assertLess(summary["percent"], 100)
        self.assertEqual(summary["current"]["id"], 2)
        self.assertIn("index is unavailable", summary["last_error"])
        self.assertIn("Sonarr", summary["throttle_note"])
        self.assertNotIn("SABnzbd", summary["throttle_note"])
        self.assertEqual(summary["kind"], "command")

    def test_summarize_merges_live_sonarr_status_over_stale_tracked(self) -> None:
        tracked = [{"id": 9, "name": "EpisodeSearch", "status": "queued"}]
        live = [{"id": 9, "name": "EpisodeSearch", "status": "completed", "ended": "2026-09-21T17:09:00Z"}]
        summary = summarize_episode_search_commands(tracked, live)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["queued"], 0)

    def test_refresh_keeps_executing_until_sonarr_commands_finish(self) -> None:
        from projectionist.library import sonarr_missing as missing

        reset_sonarr_missing_for_tests()
        fake = FakeSonarr()
        store = missing.progress_store()
        store.begin(kind="search")
        queued = queue_episode_searches(fake, [11, 31], chunk_size=50)
        store.set_commands(queued["commands"], searches_queued=1, searches_total=1)
        store.update("executing", "Waiting on Sonarr to run EpisodeSearch…")
        snap = refresh_execution(fake, store)
        self.assertEqual(snap["phase"], "executing")
        self.assertTrue(snap["busy"])
        self.assertLess(int(snap["percent"] or 0), 100)
        self.assertEqual(snap["execution"]["queued"], 1)
        fake.complete_commands()
        snap = refresh_execution(fake, store)
        self.assertEqual(snap["phase"], "searched")
        self.assertFalse(snap["busy"])
        self.assertEqual(snap["percent"], 100)
        self.assertEqual(snap["execution"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
