"""Focused unit tests for Live Channels foundation + household delight."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.config_store import FeatureFlags, Settings, TunarrSettings, load_merged_settings, save_settings
from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.live_channels.docker import (
    TunarrDockerLifecycle,
    docker_socket_available,
    orchestration_enabled,
    resolve_config_volume,
)
from projectionist.live_channels.guide import (
    apply_youth_filter_to_on_now,
    build_on_now_snapshot,
    pick_now_and_next,
    program_airing_progress,
)
from projectionist.live_channels.nudges import RELATED_ID, maybe_deliver_live_channels_ready_nudge
from projectionist.live_channels.plex_pass import check_plex_pass
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    apply_youth_gate_to_items,
)
from projectionist.live_channels.starter_pack import propose_starter_pack, propose_starter_pack_from_db
from projectionist.live_channels.status import (
    airing_rows_from_snapshot,
    build_live_channels_status,
    summarize_sessions,
)


class FeatureFlagAndTunarrSettingsTests(unittest.TestCase):
    def test_live_channels_defaults_off(self) -> None:
        settings = Settings()
        self.assertFalse(settings.features.live_channels_enabled)
        self.assertEqual(settings.tunarr.url, "")
        self.assertFalse(settings.tunarr.docker_orchestration)
        self.assertEqual(settings.tunarr.image_tag, "chrisbenincasa/tunarr:1.3.9")

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings = Settings(
                features=FeatureFlags(live_channels_enabled=True),
                tunarr=TunarrSettings(
                    url="http://tunarr.local:8000",
                    docker_orchestration=True,
                    image_tag="chrisbenincasa/tunarr:1.3.5",
                ),
            )
            save_settings(data_dir, settings)
            loaded = load_merged_settings(data_dir)
            self.assertTrue(loaded.features.live_channels_enabled)
            self.assertEqual(loaded.tunarr.url, "http://tunarr.local:8000")
            self.assertTrue(loaded.tunarr.docker_orchestration)
            self.assertEqual(loaded.tunarr.image_tag, "chrisbenincasa/tunarr:1.3.5")

    def test_tunarr_env_overrides(self) -> None:
        keys = (
            "PROJECTIONIST_TUNARR_URL",
            "PROJECTIONIST_TUNARR_IMAGE",
            "PROJECTIONIST_DOCKER_ORCHESTRATION",
            "CURATORX_TUNARR_URL",
            "CURATORX_TUNARR_IMAGE",
            "CURATORX_DOCKER_ORCHESTRATION",
        )
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                data_dir = Path(tmp)
                save_settings(data_dir, Settings())
                os.environ["PROJECTIONIST_TUNARR_URL"] = "http://env-tunarr:8000"
                os.environ["PROJECTIONIST_TUNARR_IMAGE"] = "chrisbenincasa/tunarr:1.3.9"
                os.environ["PROJECTIONIST_DOCKER_ORCHESTRATION"] = "1"
                loaded = load_merged_settings(data_dir)
                self.assertEqual(loaded.tunarr.url, "http://env-tunarr:8000")
                self.assertEqual(loaded.tunarr.image_tag, "chrisbenincasa/tunarr:1.3.9")
                self.assertTrue(loaded.tunarr.docker_orchestration)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class StarterPackTests(unittest.TestCase):
    def test_empty_inputs_with_chaos_and_youth(self) -> None:
        pack = propose_starter_pack(taste_clusters=[], motifs=[], collections=[])
        self.assertTrue(pack["empty_library"])
        sources = {p["source"] for p in pack["proposals"]}
        self.assertIn("chaos", sources)
        self.assertIn("youth", sources)
        self.assertGreaterEqual(pack["count"], 2)

    def test_uses_clusters_motifs_collections(self) -> None:
        pack = propose_starter_pack(
            taste_clusters=[{"cluster_tag": "cozy sci-fi", "weight": 0.9}],
            motifs=[{"value": "found family", "count": 12}],
            collections=[{"id": "list-1", "title": "Friday Night"}],
            max_channels=4,
        )
        sources = [p["source"] for p in pack["proposals"]]
        self.assertIn("taste_cluster", sources)
        self.assertTrue(any(p["cluster_tag"] == "cozy sci-fi" for p in pack["proposals"]))
        self.assertLessEqual(pack["count"], 4)
        self.assertEqual(pack["proposals"][0]["number"], 100)

    def test_from_db_graceful_without_methods(self) -> None:
        pack = propose_starter_pack_from_db(None, settings=Settings())
        self.assertIn("proposals", pack)


class YouthGateHookTests(unittest.TestCase):
    def test_filters_unrated_and_over_max(self) -> None:
        items = [
            {"title": "Ok", "content_rating": "PG"},
            {"title": "Blank", "content_rating": ""},
            {"title": "Mature", "content_rating": "R"},
        ]
        filtered = apply_youth_gate_to_items(items, max_rating="PG-13")
        self.assertEqual([i["title"] for i in filtered], ["Ok"])


class PlexPassPreflightTests(unittest.TestCase):
    def test_unknown_without_confirm(self) -> None:
        result = check_plex_pass(settings=Settings(plex_url="http://plex", plex_token="tok"))
        self.assertEqual(result["status"], "unknown")
        self.assertIn("machine id", result["message"].lower())

    def test_owner_confirmed(self) -> None:
        result = check_plex_pass(owner_confirmed=True)
        self.assertEqual(result["status"], "confirmed")

    def test_owner_missing(self) -> None:
        result = check_plex_pass(owner_confirmed=False)
        self.assertEqual(result["status"], "missing")


class DockerLifecycleTests(unittest.TestCase):
    def test_unavailable_without_socket(self) -> None:
        life = TunarrDockerLifecycle(socket_path="/tmp/definitely-missing-docker.sock")
        status = life.status()
        self.assertEqual(status.status, "unavailable")
        pull = life.pull()
        self.assertFalse(pull.ok)
        self.assertFalse(docker_socket_available("/tmp/definitely-missing-docker.sock"))

    def test_orchestration_reads_settings(self) -> None:
        settings = Settings(tunarr=TunarrSettings(docker_orchestration=True))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECTIONIST_DOCKER_ORCHESTRATION", None)
            os.environ.pop("CURATORX_DOCKER_ORCHESTRATION", None)
            self.assertTrue(orchestration_enabled(settings))

    def test_socket_without_orchestration_skips_engine(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/definitely-missing-docker.sock",
            orchestration=True,
        )
        # No socket → still unavailable even with orchestration flag.
        self.assertFalse(life.can_orchestrate())
        ensure = life.ensure_running(config_volume="/tmp/tunarr-cfg")
        self.assertFalse(ensure.ok)
        self.assertEqual(ensure.status, "unavailable")

    def test_engine_status_running(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
        )
        with patch(
            "projectionist.live_channels.docker.resolve_docker_socket",
            return_value="/tmp/fake.sock",
        ), patch(
            "projectionist.live_channels.docker.docker_socket_available",
            return_value=True,
        ), patch.object(
            life,
            "_engine_request",
            return_value=(200, {"State": {"Running": True, "Status": "running"}}),
        ):
            status = life.status()
        self.assertTrue(status.ok)
        self.assertEqual(status.status, "running")

    def test_ensure_running_pull_then_start(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
            image="chrisbenincasa/tunarr:1.3.5",
        )
        calls: list[str] = []
        phases: list[str] = []

        def fake_request(method, path, **kwargs):
            del kwargs
            calls.append(f"{method} {path}")
            if method == "POST" and path.startswith("/images/create"):
                return 200, None
            if method == "GET" and path.startswith("/containers/json"):
                return 200, []  # no published ports — prefer default 18765/15004
            if method == "GET" and path.endswith("/json"):
                return 404, None
            if method == "POST" and path.startswith("/containers/create"):
                return 201, {"Id": "abc123"}
            if method == "POST" and path.endswith("/start"):
                return 204, None
            raise AssertionError(f"unexpected {method} {path}")

        with patch(
            "projectionist.live_channels.docker.resolve_docker_socket",
            return_value="/tmp/fake.sock",
        ), patch(
            "projectionist.live_channels.docker.docker_socket_available",
            return_value=True,
        ), patch.object(life, "_engine_request", side_effect=fake_request), patch(
            "pathlib.Path.mkdir"
        ):
            with patch.dict(
                os.environ, {"PROJECTIONIST_HOST_IP": "10.10.1.202"}, clear=False
            ):
                result = life.ensure_running(
                    config_volume="/tmp/tunarr-vol",
                    on_phase=lambda phase, _msg="": phases.append(phase),
                )
        self.assertTrue(result.ok)
        self.assertEqual(result.status, "running")
        self.assertTrue(any("/images/create" in c for c in calls))
        self.assertTrue(any("/containers/create" in c for c in calls))
        self.assertTrue(any("/containers/json" in c for c in calls))
        self.assertEqual(
            (result.detail or {}).get("url_hint"),
            "http://host.docker.internal:18765",
        )
        self.assertEqual(
            (result.detail or {}).get("public_url_hint"),
            "http://10.10.1.202:18765",
        )
        self.assertEqual((result.detail or {}).get("host_port"), 18765)
        self.assertIn("pulling", phases)
        self.assertIn("creating", phases)
        self.assertIn("starting", phases)
        self.assertIn("waiting_ready", phases)

    def test_lifecycle_progress_ready_from_logs_marker(self) -> None:
        from projectionist.live_channels.lifecycle_progress import (
            build_lifecycle_status,
            logs_indicate_ready,
            reset_progress_for_tests,
        )

        reset_progress_for_tests()
        self.assertTrue(logs_indicate_ready("boot…\nTunarr is ready!\n"))
        self.assertFalse(logs_indicate_ready("still starting"))
        settings = Settings(
            tunarr=TunarrSettings(url="", docker_orchestration=True),
        )
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
                "container_id": "cid12",
                "logs_ready": True,
                "log_snippet": "Tunarr is ready!",
            },
        ):
            status = build_lifecycle_status(settings)
        self.assertTrue(status["ready"])
        self.assertEqual(status["phase"], "ready")
        self.assertEqual(status["percent"], 100)
        reset_progress_for_tests()

    def test_choose_free_port_skips_used(self) -> None:
        from projectionist.live_channels.docker import (
            choose_free_port,
            collect_published_host_ports,
        )

        used = collect_published_host_ports(
            [
                {
                    "Ports": [
                        {"PublicPort": 18765, "PrivatePort": 8000, "Type": "tcp"},
                        {"PublicPort": 18766, "PrivatePort": 8000, "Type": "tcp"},
                    ]
                }
            ]
        )
        self.assertEqual(used, {18765, 18766})
        self.assertEqual(choose_free_port(18765, used, attempts=8), 18767)
        self.assertIsNone(choose_free_port(18765, {18765, 18766, 18767}, attempts=3))

    def test_allocate_host_ports_probes_and_avoids_collision(self) -> None:
        from projectionist.live_channels.docker import TunarrDockerLifecycle

        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
            host_port=18765,
            hdhr_port=15004,
        )

        def fake_request(method, path, **kwargs):
            del kwargs
            if method == "GET" and path.startswith("/containers/json"):
                return 200, [
                    {
                        "Ports": [
                            {"PublicPort": 18765, "Type": "tcp"},
                            {"PublicPort": 15004, "Type": "tcp"},
                        ]
                    }
                ]
            raise AssertionError(f"unexpected {method} {path}")

        with patch(
            "projectionist.live_channels.docker.resolve_docker_socket",
            return_value="/tmp/fake.sock",
        ), patch(
            "projectionist.live_channels.docker.docker_socket_available",
            return_value=True,
        ), patch.object(life, "_engine_request", side_effect=fake_request):
            http_port, hdhr_port = life.allocate_host_ports()
        self.assertEqual(http_port, 18766)
        self.assertEqual(hdhr_port, 15005)
        self.assertEqual(life.host_port, 18766)
        self.assertEqual(life.hdhr_port, 15005)

    def test_resolve_config_volume_uses_host_data_dir(self) -> None:
        settings = Settings(tunarr=TunarrSettings(volume_path="tunarr"))
        with patch.dict(
            os.environ,
            {"PROJECTIONIST_HOST_DATA_DIR": "/mnt/user/appdata/projectionist/config"},
            clear=False,
        ):
            path = resolve_config_volume(settings, "/config")
        self.assertEqual(path, "/mnt/user/appdata/projectionist/config/tunarr")

    def test_resolve_config_volume_falls_back_to_data_dir(self) -> None:
        settings = Settings(tunarr=TunarrSettings(volume_path="tunarr"))
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECTIONIST_HOST_DATA_DIR", None)
            os.environ.pop("HOST_DATA_DIR", None)
            path = resolve_config_volume(settings, Path("/tmp/proj-data"))
        self.assertTrue(str(path).endswith("/tunarr"))
        self.assertIn("proj-data", path)


class StatusBuilderTests(unittest.TestCase):
    def test_status_includes_flag_and_reachability(self) -> None:
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test", last_publish_at="2026-07-29T12:00:00Z"),
        )
        with patch(
            "projectionist.live_channels.status.tunarr_reachable",
            return_value={"reachable": True, "tunarr_version": "1.3.2"},
        ), patch(
            "projectionist.live_channels.status.TunarrClient.list_channels",
            return_value=[{"id": "1", "name": "Chaos", "number": 100}],
        ), patch(
            "projectionist.live_channels.status.TunarrClient.list_sessions",
            return_value={},
        ), patch(
            "projectionist.live_channels.status.TunarrClient.get_guide_status",
            return_value={},
        ), patch(
            "projectionist.live_channels.status.build_on_now_snapshot",
            return_value={"channels": []},
        ):
            status = build_live_channels_status(settings)
        self.assertTrue(status["live_channels_enabled"])
        self.assertTrue(status["tunarr"]["reachability"]["reachable"])
        self.assertEqual(status["plex_pass"]["status"], "unknown")
        self.assertEqual(status["channel_count"], 1)
        self.assertTrue(status["broadcast"]["sidecar_up"])
        self.assertEqual(status["last_publish_at"], "2026-07-29T12:00:00Z")
        self.assertEqual(status["airing"], [])
        self.assertEqual(status["sessions"]["total_connections"], 0)

    def test_summarize_sessions_and_airing_rows(self) -> None:
        sessions = summarize_sessions(
            {
                "ch-1": [
                    {"type": "hls", "state": "started", "numConnections": 2},
                    {"type": "hls_direct", "state": "started", "numConnections": 1},
                ],
                "ch-2": [{"type": "hls", "state": "idle", "numConnections": 0}],
            }
        )
        self.assertEqual(sessions["active_channels"], 2)
        self.assertEqual(sessions["total_connections"], 3)
        self.assertEqual(sessions["channels"][0]["channel_id"], "ch-1")

        rows = airing_rows_from_snapshot(
            {
                "channels": [
                    {
                        "id": "ch-1",
                        "name": "Chaos",
                        "number": 100,
                        "now": {
                            "title": "Heat",
                            "started_at": 1.0,
                            "ends_at": 100.0,
                            "seconds_elapsed": 40,
                            "seconds_remaining": 59,
                            "percent": 40.4,
                            "is_paused": False,
                        },
                    },
                    {"id": "ch-2", "name": "Empty", "now": None},
                ]
            }
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Heat")
        self.assertEqual(rows[0]["percent"], 40.4)

    def test_status_includes_airing_and_sessions(self) -> None:
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        with patch(
            "projectionist.live_channels.status.tunarr_reachable",
            return_value={"reachable": True, "tunarr_version": "1.3.2"},
        ), patch(
            "projectionist.live_channels.status.TunarrClient.list_channels",
            return_value=[{"id": "ch-1", "name": "Chaos", "number": 100}],
        ), patch(
            "projectionist.live_channels.status.TunarrClient.list_sessions",
            return_value={"ch-1": [{"type": "hls", "state": "started", "numConnections": 2}]},
        ), patch(
            "projectionist.live_channels.status.TunarrClient.get_guide_status",
            return_value={"channelIds": ["ch-1"]},
        ), patch(
            "projectionist.live_channels.status.build_on_now_snapshot",
            return_value={
                "channels": [
                    {
                        "id": "ch-1",
                        "name": "Chaos",
                        "number": 100,
                        "now": {
                            "title": "Heat",
                            "started_at": 10.0,
                            "ends_at": 100.0,
                            "seconds_elapsed": 30,
                            "seconds_remaining": 60,
                            "percent": 33.3,
                            "is_paused": False,
                        },
                    }
                ]
            },
        ):
            status = build_live_channels_status(settings)
        self.assertEqual(status["sessions"]["total_connections"], 2)
        self.assertEqual(status["broadcast"]["stream_connections"], 2)
        self.assertEqual(status["airing"][0]["title"], "Heat")
        self.assertEqual(status["airing"][0]["percent"], 33.3)
        self.assertEqual(status["guide_status"]["channelIds"], ["ch-1"])


class RecipeDictTests(unittest.TestCase):
    def test_to_dict(self) -> None:
        recipe = ChannelRecipe(
            name="Chaos",
            number=102,
            source="chaos",
            programming_mode=ProgrammingMode.CHAOS,
        )
        payload = recipe.to_dict()
        self.assertEqual(payload["programming_mode"], "chaos")
        self.assertEqual(payload["number"], 102)


class OnNowGuideTests(unittest.TestCase):
    def test_program_airing_progress(self) -> None:
        now = 1_700_000_100.0
        progress = program_airing_progress(now - 600, now + 3600, now=now)
        self.assertEqual(progress["started_at"], now - 600)
        self.assertEqual(progress["ends_at"], now + 3600)
        self.assertEqual(progress["seconds_elapsed"], 600)
        self.assertEqual(progress["seconds_remaining"], 3600)
        self.assertAlmostEqual(progress["percent"], 14.3, places=1)

        paused = program_airing_progress(
            now - 600,
            now + 3600,
            now=now,
            is_paused=True,
            time_remaining=1_800_000,  # Tunarr ms
        )
        self.assertTrue(paused["is_paused"])
        self.assertEqual(paused["seconds_remaining"], 1800)
        self.assertEqual(paused["seconds_elapsed"], 2400)

    def test_pick_now_and_next(self) -> None:
        now = 1_700_000_100.0
        programs = [
            {"title": "Earlier", "start": now - 7200, "stop": now - 3600},
            {"title": "Heat", "start": now - 600, "stop": now + 3600, "contentRating": "R"},
            {"title": "Ronin", "start": now + 3600, "stop": now + 7200},
        ]
        slots = pick_now_and_next(programs, now=now)
        self.assertEqual(slots["now"]["title"], "Heat")
        self.assertEqual(slots["now"]["content_rating"], "R")
        self.assertEqual(slots["next"]["title"], "Ronin")
        self.assertEqual(slots["now"]["seconds_elapsed"], 600)
        self.assertEqual(slots["now"]["seconds_remaining"], 3600)
        self.assertAlmostEqual(slots["now"]["percent"], 14.3, places=1)
        self.assertEqual(slots["now"]["started_at"], now - 600)
        self.assertEqual(slots["now"]["ends_at"], now + 3600)

    def test_empty_when_flag_off(self) -> None:
        snap = build_on_now_snapshot(Settings())
        self.assertFalse(snap["enabled"])
        self.assertEqual(snap["channels"], [])
        self.assertEqual(snap["reason"], "live_channels_disabled")

    def test_empty_when_unreachable(self) -> None:
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        client = MagicMock()
        client.list_channels.side_effect = RuntimeError("down")
        snap = build_on_now_snapshot(settings, client=client)
        self.assertTrue(snap["enabled"])
        self.assertFalse(snap["ready"])
        self.assertEqual(snap["reason"], "tunarr_unreachable")

    def test_builds_channels_from_guide(self) -> None:
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        now = 1_700_000_100.0
        client = MagicMock()
        client.list_channels.return_value = [
            {"id": "ch-1", "name": "Chaos Night", "number": 100},
            {"id": "ch-2", "name": "Youth Hour", "number": 101},
        ]
        client.get_all_channel_guides.return_value = {
            "ch-1": {
                "programs": [
                    {
                        "title": "Heat",
                        "start": now - 60,
                        "stop": now + 3600,
                        "contentRating": "R",
                    },
                    {"title": "Ronin", "start": now + 3600, "stop": now + 7200},
                ]
            },
            "ch-2": {
                "programs": [
                    {
                        "title": "Toy Story",
                        "start": now - 60,
                        "stop": now + 3600,
                        "contentRating": "G",
                    }
                ]
            },
        }
        snap = build_on_now_snapshot(settings, client=client, now=now)
        self.assertTrue(snap["ready"])
        self.assertEqual(snap["count"], 2)
        self.assertEqual(snap["channels"][0]["now"]["title"], "Heat")
        self.assertEqual(snap["channels"][0]["now"]["seconds_elapsed"], 60)
        self.assertIsNotNone(snap["channels"][0]["now"]["percent"])

        youth = build_on_now_snapshot(
            settings, client=client, now=now, youth_max_rating="PG-13"
        )
        titles = [c["now"]["title"] for c in youth["channels"] if c.get("now")]
        self.assertEqual(titles, ["Toy Story"])

    def test_youth_filter_keeps_unrated(self) -> None:
        channels = [
            {"id": "1", "name": "A", "now": {"title": "Mystery", "content_rating": None}},
            {"id": "2", "name": "B", "now": {"title": "Heat", "content_rating": "R"}},
        ]
        filtered = apply_youth_filter_to_on_now(channels, max_rating="PG-13")
        self.assertEqual([c["id"] for c in filtered], ["1"])


class PreflightAndPublishTests(unittest.TestCase):
    def test_preflight_requires_plex(self) -> None:
        from projectionist.live_channels.preflight import run_preflight

        result = run_preflight(Settings())
        by_id = {c["id"]: c for c in result["checks"]}
        self.assertFalse(by_id["plex_reachable"]["ok"])
        self.assertFalse(result["ready"])

    def test_preflight_pass_confirm(self) -> None:
        from projectionist.live_channels.preflight import run_preflight

        settings = Settings(
            plex_url="http://plex.test",
            plex_token="tok",
            tunarr=TunarrSettings(url="http://tunarr.test", plex_pass_confirmed=True),
        )
        with patch(
            "projectionist.connectors.plex.PlexClient.server_identity",
            return_value=("mid", "Home"),
        ):
            result = run_preflight(settings, owner_confirmed_plex_pass=True)
        by_id = {c["id"]: c for c in result["checks"]}
        self.assertTrue(by_id["plex_reachable"]["ok"])
        self.assertEqual(by_id["plex_pass"]["status"], "confirmed")
        self.assertTrue(result["ready"])

    def test_plex_attach_urls(self) -> None:
        from projectionist.live_channels.plex_attach import build_plex_attach, xmltv_url

        settings = Settings(tunarr=TunarrSettings(url="http://tunarr.test:8000"))
        attach = build_plex_attach(
            settings,
            existing_livetv={
                "status": "detected",
                "ok": True,
                "device_count": 1,
                "message": "Existing Live TV setup detected — Tunarr will be added as another tuner.",
            },
        )
        self.assertEqual(attach["guide_url"], "http://tunarr.test:8000/api/xmltv.xml")
        self.assertEqual(xmltv_url("http://tunarr.test:8000/"), "http://tunarr.test:8000/api/xmltv.xml")
        self.assertGreaterEqual(len(attach["steps"]), 3)
        joined = " ".join(f"{s['title']} {s['body']}" for s in attach["steps"]).lower()
        self.assertIn("another", joined)
        self.assertNotIn("wipe", joined)
        self.assertEqual(attach["coexistence"]["mode"], "additional_tuner")
        self.assertEqual(attach["existing_livetv"]["status"], "detected")

    def test_plex_attach_prefers_public_url_over_docker_internal(self) -> None:
        from projectionist.live_channels.plex_attach import (
            build_plex_attach,
            resolve_plex_facing_tunarr_base,
        )

        settings = Settings(
            tunarr=TunarrSettings(
                url="http://host.docker.internal:8000",
                public_url="http://10.10.1.202:8000",
            )
        )
        facing = resolve_plex_facing_tunarr_base(settings)
        self.assertEqual(facing["base_url"], "http://10.10.1.202:8000")
        self.assertEqual(facing["source"], "settings.public_url")
        self.assertFalse(facing["docker_only"])

        attach = build_plex_attach(
            settings,
            existing_livetv={"status": "none", "ok": True, "device_count": 0, "message": ""},
        )
        self.assertEqual(attach["tuner_url"], "http://10.10.1.202:8000/")
        self.assertEqual(attach["guide_url"], "http://10.10.1.202:8000/api/xmltv.xml")
        self.assertNotIn("host.docker.internal", attach["tuner_url"])
        self.assertEqual(attach["tunarr_api_url"], "http://host.docker.internal:8000")
        self.assertFalse(attach["needs_lan_url"])

    def test_plex_attach_never_copies_docker_internal(self) -> None:
        from projectionist.live_channels.plex_attach import (
            build_plex_attach,
            resolve_plex_facing_tunarr_base,
        )

        settings = Settings(
            tunarr=TunarrSettings(url="http://host.docker.internal:8000")
        )
        facing = resolve_plex_facing_tunarr_base(
            settings, request_host="localhost:8788", environ={}
        )
        self.assertEqual(facing["base_url"], "")
        self.assertTrue(facing["docker_only"])

        # Without HOST_IP / public_url, copy fields must stay empty (not docker DNS).
        with patch.dict(os.environ, {}, clear=False):
            for key in (
                "PROJECTIONIST_HOST_IP",
                "HOST_IP",
                "PROJECTIONIST_TUNARR_PUBLIC_URL",
                "PROJECTIONIST_PUBLIC_URL",
                "CURATORX_HOST_IP",
                "CURATORX_TUNARR_PUBLIC_URL",
                "CURATORX_PUBLIC_URL",
            ):
                os.environ.pop(key, None)
            attach = build_plex_attach(
                settings,
                request_host="localhost:8788",
                existing_livetv={"status": "none", "ok": True, "device_count": 0, "message": ""},
            )
        self.assertEqual(attach["tuner_url"], "")
        self.assertEqual(attach["guide_url"], "")
        self.assertTrue(attach["needs_lan_url"])
        self.assertNotIn("host.docker.internal", attach.get("tuner_url") or "")
        self.assertIn("LAN", attach["warning"])

    def test_plex_attach_derives_lan_from_request_host(self) -> None:
        from projectionist.live_channels.plex_attach import resolve_plex_facing_tunarr_base

        settings = Settings(
            tunarr=TunarrSettings(url="http://host.docker.internal:8000")
        )
        facing = resolve_plex_facing_tunarr_base(
            settings,
            request_host="10.10.1.202:8788",
            environ={},
        )
        self.assertEqual(facing["base_url"], "http://10.10.1.202:8000")
        self.assertEqual(facing["source"], "derived_lan_host")
        self.assertFalse(facing["docker_only"])

    def test_derive_managed_public_url_from_host_ip(self) -> None:
        from projectionist.live_channels.plex_attach import derive_managed_public_url

        url = derive_managed_public_url(
            host_port=8000,
            environ={"PROJECTIONIST_HOST_IP": "10.10.1.202"},
        )
        self.assertEqual(url, "http://10.10.1.202:8000")
        self.assertEqual(
            derive_managed_public_url(
                host_port=8000,
                environ={"PROJECTIONIST_HOST_IP": "host.docker.internal"},
            ),
            "",
        )

    def test_plex_media_source_body_has_tunarr_required_fields(self) -> None:
        from projectionist.live_channels.publish import plex_media_source_body

        body = plex_media_source_body(
            plex_url="http://10.10.1.200:32400/",
            plex_token="tok",
            username="HomePlex",
            user_id="machine-1",
        )
        self.assertEqual(body["type"], "plex")
        self.assertEqual(body["uri"], "http://10.10.1.200:32400")
        self.assertEqual(body["accessToken"], "tok")
        self.assertEqual(body["userId"], "machine-1")
        self.assertEqual(body["username"], "HomePlex")
        self.assertEqual(body["pathReplacements"], [])
        for key in (
            "name",
            "uri",
            "accessToken",
            "userId",
            "username",
            "pathReplacements",
            "type",
        ):
            self.assertIn(key, body)

    def test_wire_plex_media_source_posts_required_keys(self) -> None:
        from projectionist.live_channels.publish import wire_plex_media_source

        client = MagicMock()
        client.list_media_sources.return_value = []
        client.create_media_source.return_value = {"id": "ms-1", "type": "plex"}
        with patch(
            "projectionist.live_channels.publish._plex_identity_hints",
            return_value=("mid", "Home"),
        ):
            result = wire_plex_media_source(
                client,
                plex_url="http://plex.test:32400",
                plex_token="tok",
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        body = client.create_media_source.call_args.args[0]
        self.assertEqual(body["pathReplacements"], [])
        self.assertIn("userId", body)
        self.assertIn("username", body)
        self.assertNotEqual(body.get("userId"), "tok")

    def test_probe_existing_livetv_unknown_without_plex(self) -> None:
        from projectionist.live_channels.plex_attach import probe_existing_plex_livetv

        result = probe_existing_plex_livetv(Settings())
        self.assertEqual(result["status"], "unknown")
        self.assertIn("additional", result["message"].lower())

    def test_fetch_tunarr_logs_prefers_api(self) -> None:
        from projectionist.live_channels.logs import fetch_tunarr_logs

        settings = Settings(tunarr=TunarrSettings(url="http://tunarr.test:8000"))
        with patch(
            "projectionist.live_channels.logs.TunarrClient.fetch_debug_logs",
            return_value="api-log",
        ):
            result = fetch_tunarr_logs(settings, lines=50)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "tunarr_api")
        self.assertEqual(result["text"], "api-log")

    def test_fetch_tunarr_logs_falls_back_to_docker(self) -> None:
        from projectionist.live_channels.logs import fetch_tunarr_logs

        settings = Settings(tunarr=TunarrSettings(url="http://tunarr.test:8000"))
        lifecycle = MagicMock()
        lifecycle.available.return_value = True
        lifecycle.container_name = "projectionist-tunarr"
        lifecycle.container_logs.return_value = "docker-log"

        with patch(
            "projectionist.live_channels.logs.TunarrClient.fetch_debug_logs",
            side_effect=RuntimeError("api down"),
        ), patch(
            "projectionist.live_channels.logs.lifecycle_from_settings",
            return_value=lifecycle,
        ):
            result = fetch_tunarr_logs(settings, lines=20)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "docker")
        self.assertEqual(result["text"], "docker-log")

    def test_channel_create_body_matches_tunarr_required_fields(self) -> None:
        from projectionist.live_channels.publish import (
            channel_create_body,
            programming_body_for_recipe,
        )

        recipe = ChannelRecipe(name="Mystery", number=100, source="motif")
        body = channel_create_body(
            recipe,
            transcode_config_id="ce5cfbdb-603d-47cd-85ff-6ddbe51f33c4",
            channel_id="97c2c8f0-2c1e-428a-a035-9d25b2c94ef6",
            start_time_ms=1_700_000_000_000,
        )
        self.assertEqual(body["type"], "new")
        channel = body["channel"]
        required = {
            "disableFillerOverlay",
            "duration",
            "groupTitle",
            "guideMinimumDuration",
            "icon",
            "id",
            "name",
            "number",
            "offline",
            "startTime",
            "stealth",
            "streamMode",
            "transcodeConfigId",
            "subtitlesEnabled",
        }
        self.assertTrue(required.issubset(channel.keys()))
        self.assertEqual(channel["name"], "Mystery")
        self.assertEqual(channel["number"], 100)
        self.assertEqual(channel["id"], "97c2c8f0-2c1e-428a-a035-9d25b2c94ef6")
        self.assertEqual(
            channel["transcodeConfigId"], "ce5cfbdb-603d-47cd-85ff-6ddbe51f33c4"
        )
        self.assertEqual(channel["streamMode"], "hls")
        self.assertEqual(channel["offline"], {"mode": "pic"})
        self.assertEqual(
            channel["icon"],
            {"path": "", "width": 0, "duration": 0, "position": "bottom-right"},
        )
        with self.assertRaises(ValueError):
            channel_create_body(recipe, transcode_config_id="")

        empty = programming_body_for_recipe(recipe)
        self.assertEqual(empty, {"type": "manual", "lineup": []})
        hinted = programming_body_for_recipe(
            ChannelRecipe(
                name="Hints",
                number=103,
                source="motif",
                item_hints=("Heat", "Alien"),
            )
        )
        self.assertEqual(hinted["type"], "manual")
        self.assertEqual(len(hinted["lineup"]), 2)
        self.assertEqual(hinted["lineup"][0], {"type": "flex", "duration": 300_000})
        self.assertNotIn("programs", hinted)

    def test_publish_recipes_creates_channels(self) -> None:
        from projectionist.live_channels.publish import publish_recipes

        client = MagicMock()
        client.list_channels.return_value = []
        client.default_transcode_config_id.return_value = "tc-default"
        client.create_channel.side_effect = lambda body: {
            "id": f"id-{body['channel']['number']}",
            "name": body["channel"]["name"],
            "number": body["channel"]["number"],
        }
        client.set_channel_programming.return_value = {"programs": []}
        recipes = [
            ChannelRecipe(name="Chaos", number=100, source="chaos", programming_mode=ProgrammingMode.CHAOS),
            ChannelRecipe(name="Motif", number=101, source="motif", programming_mode=ProgrammingMode.SHUFFLE),
        ]
        result = publish_recipes(client, recipes)
        self.assertEqual(result["count_published"], 2)
        self.assertEqual(client.create_channel.call_count, 2)
        self.assertTrue(result["ok"])
        first_body = client.create_channel.call_args_list[0].args[0]
        self.assertEqual(first_body["channel"]["transcodeConfigId"], "tc-default")
        self.assertIn("id", first_body["channel"])
        self.assertEqual(first_body["channel"]["streamMode"], "hls")

    def test_publish_skips_existing(self) -> None:
        from projectionist.live_channels.publish import publish_recipes

        client = MagicMock()
        client.list_channels.return_value = [{"id": "x", "name": "Chaos", "number": 100}]
        client.default_transcode_config_id.return_value = "tc-default"
        result = publish_recipes(
            client,
            [ChannelRecipe(name="Chaos", number=100, source="chaos")],
        )
        self.assertEqual(result["count_skipped"], 1)
        client.create_channel.assert_not_called()


class SetupTunarrCertTests(unittest.TestCase):
    def test_test_tunarr_requires_url(self) -> None:
        from projectionist.web import setup as setup_mod

        result = setup_mod.test_tunarr("")
        self.assertFalse(result["ok"])

    def test_test_tunarr_success(self) -> None:
        from projectionist.web import setup as setup_mod

        with patch(
            "projectionist.connectors.tunarr.TunarrClient.check",
            return_value={"ok": True, "tunarr_version": "1.3.2"},
        ), patch(
            "projectionist.connectors.tunarr.TunarrClient.list_channels",
            return_value=[{"id": "1"}],
        ):
            result = setup_mod.test_tunarr("http://tunarr.test")
        self.assertTrue(result["ok"])
        self.assertIn("1.3.2", result["message"])
        self.assertIn("tunarr", setup_mod.CERTIFIED_SERVICES)


class ReadyNudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_requires_opt_in_and_dedupes(self) -> None:
        settings = Settings(features=FeatureFlags(live_channels_enabled=True))
        skipped = maybe_deliver_live_channels_ready_nudge(
            self.db, settings, ready=True, channel_count=2
        )
        self.assertEqual(skipped["delivered"], 0)

        self.db.update_user_profile(
            BOOTSTRAP_OWNER_ID, nudge_opt_in=True, notify_channel_inbox=True
        )
        first = maybe_deliver_live_channels_ready_nudge(
            self.db, settings, ready=True, channel_count=2
        )
        self.assertGreaterEqual(first["delivered"], 1)
        notes = self.db.list_notifications_for_user(BOOTSTRAP_OWNER_ID, kinds=["nudge"])
        self.assertTrue(any(n.get("related_id") == RELATED_ID for n in notes))

        second = maybe_deliver_live_channels_ready_nudge(
            self.db, settings, ready=True, channel_count=2
        )
        self.assertEqual(second["delivered"], 0)


if __name__ == "__main__":
    unittest.main()
