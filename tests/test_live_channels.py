"""Focused unit tests for Live Channels foundation + household delight."""

from __future__ import annotations

import os
import tempfile
import threading
import time
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
    DUAL_WATCH_HINT,
    apply_youth_filter_to_on_now,
    build_guide_snapshot,
    build_on_now_snapshot,
    pick_now_and_next,
    program_airing_progress,
)
from projectionist.live_channels.stream_proxy import (
    rewrite_hls_playlist,
    tunarr_master_url,
    validate_stream_path,
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
    def test_empty_inputs_with_youth_no_chaos(self) -> None:
        pack = propose_starter_pack(taste_clusters=[], motifs=[], collections=[])
        self.assertTrue(pack["empty_library"])
        sources = {p["source"] for p in pack["proposals"]}
        self.assertNotIn("chaos", sources)
        self.assertIn("youth", sources)
        self.assertGreaterEqual(pack["count"], 1)

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

    def test_lifecycle_progress_logs_alone_not_ready(self) -> None:
        from projectionist.live_channels.lifecycle_progress import (
            build_lifecycle_status,
            logs_indicate_ready,
            logs_look_transient,
            reset_progress_for_tests,
        )

        reset_progress_for_tests()
        self.assertTrue(logs_indicate_ready("boot…\nTunarr is ready!\n"))
        self.assertFalse(logs_indicate_ready("still starting"))
        self.assertTrue(logs_look_transient("Meilisearch ECONNREFUSED during boot"))
        settings = Settings(
            tunarr=TunarrSettings(url="http://tunarr.test:18765", docker_orchestration=True),
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
                "transient_noise": False,
            },
        ):
            status = build_lifecycle_status(settings)
        # Log banner is soft — HTTP must respond before ready.
        self.assertFalse(status["ready"])
        self.assertTrue(status["still_starting"])
        self.assertEqual(status["phase"], "waiting_ready")
        self.assertIn("HTTP", status["message"])
        reset_progress_for_tests()

    def test_lifecycle_progress_ready_requires_http(self) -> None:
        from projectionist.live_channels.lifecycle_progress import (
            build_lifecycle_status,
            reset_progress_for_tests,
        )

        reset_progress_for_tests()
        settings = Settings(
            tunarr=TunarrSettings(url="http://tunarr.test:18765", docker_orchestration=True),
        )
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
                "container_id": "cid12",
                "logs_ready": False,
                "log_snippet": "",
            },
        ):
            status = build_lifecycle_status(settings)
        self.assertTrue(status["ready"])
        self.assertTrue(status["http_ready"])
        self.assertEqual(status["phase"], "ready")
        self.assertEqual(status["percent"], 100)
        reset_progress_for_tests()

    def test_wait_for_tunarr_ready_still_starting(self) -> None:
        from projectionist.live_channels.lifecycle_progress import wait_for_tunarr_ready

        with patch(
            "projectionist.live_channels.lifecycle_progress.probe_tunarr_http_ready",
            return_value=False,
        ):
            result = wait_for_tunarr_ready(
                "http://tunarr.test:18765",
                timeout_s=0.05,
                interval_s=0.01,
            )
        self.assertFalse(result["ready"])
        self.assertTrue(result["still_starting"])
        self.assertIn("still starting", result["message"].lower())

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

    def test_parse_and_resolve_media_binds(self) -> None:
        from projectionist.live_channels.docker import (
            binds_include,
            normalize_bind_spec,
            parse_media_binds,
            resolve_media_binds,
        )

        self.assertEqual(
            parse_media_binds("/mnt/user/data/media:/data/media:ro"),
            ["/mnt/user/data/media:/data/media:ro"],
        )
        self.assertEqual(
            normalize_bind_spec("/mnt/user/data/media:/data/media:ro"),
            "/mnt/user/data/media:/data/media",
        )
        self.assertTrue(
            binds_include(
                ["/config/tunarr:/config", "/mnt/user/data/media:/data/media:ro"],
                ["/mnt/user/data/media:/data/media:ro"],
            )
        )
        self.assertFalse(
            binds_include(["/config/tunarr:/config"], ["/mnt/user/data/media:/data/media:ro"])
        )
        settings = Settings(
            tunarr=TunarrSettings(
                media_binds=["/host/media:/data/media:ro"],
            )
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECTIONIST_TUNARR_MEDIA_BINDS", None)
            os.environ.pop("CURATORX_TUNARR_MEDIA_BINDS", None)
            self.assertEqual(
                resolve_media_binds(settings),
                ["/host/media:/data/media:ro"],
            )
        with patch.dict(
            os.environ,
            {"PROJECTIONIST_TUNARR_MEDIA_BINDS": "/env/media:/data/media:ro"},
            clear=False,
        ):
            self.assertEqual(
                resolve_media_binds(settings),
                ["/env/media:/data/media:ro"],
            )

    def test_create_includes_media_binds(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
            media_binds=["/mnt/user/data/media:/data/media:ro"],
        )
        create_bodies: list[dict] = []

        def fake_request(method, path, **kwargs):
            if method == "GET" and path.startswith("/containers/json"):
                return 200, []
            if method == "GET" and path.endswith("/json"):
                return 404, None
            if method == "POST" and path.startswith("/containers/create"):
                create_bodies.append(kwargs.get("json_body") or {})
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
            result = life.start(config_volume="/tmp/tunarr-vol")
        self.assertTrue(result.ok)
        binds = (create_bodies[0].get("HostConfig") or {}).get("Binds") or []
        self.assertIn("/tmp/tunarr-vol:/config", binds)
        self.assertIn("/mnt/user/data/media:/data/media:ro", binds)

    def test_running_without_media_binds_recreates(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
            host_port=18765,
            hdhr_port=15004,
            media_binds=["/mnt/user/data/media:/data/media:ro"],
        )
        calls: list[str] = []
        create_bodies: list[dict] = []

        def fake_request(method, path, **kwargs):
            calls.append(f"{method} {path}")
            if method == "GET" and path.endswith("/json"):
                return (
                    200,
                    {
                        "State": {"Running": True, "Status": "running"},
                        "HostConfig": {
                            "Binds": ["/mnt/user/appdata/projectionist/config/tunarr:/config"]
                        },
                        "NetworkSettings": {
                            "Ports": {
                                "8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18765"}],
                                "5004/tcp": [{"HostIp": "0.0.0.0", "HostPort": "15004"}],
                            }
                        },
                    },
                )
            if method == "POST" and "/stop" in path:
                return 204, None
            if method == "DELETE" and path.startswith("/containers/"):
                return 204, None
            if method == "POST" and path.startswith("/containers/create"):
                create_bodies.append(kwargs.get("json_body") or {})
                return 201, {"Id": "recreated1"}
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
            result = life.start(
                config_volume="/mnt/user/appdata/projectionist/config/tunarr"
            )
        self.assertTrue(result.ok)
        self.assertTrue(any("DELETE" in c for c in calls))
        binds = (create_bodies[0].get("HostConfig") or {}).get("Binds") or []
        self.assertIn("/mnt/user/data/media:/data/media:ro", binds)
        self.assertEqual(life.host_port, 18765)

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
            name="Mystery",
            number=102,
            source="motif",
            programming_mode=ProgrammingMode.SHUFFLE,
        )
        payload = recipe.to_dict()
        self.assertEqual(payload["programming_mode"], "shuffle")
        self.assertEqual(payload["number"], 102)

    def test_chaos_wire_value_normalizes_to_shuffle(self) -> None:
        from projectionist.live_channels.recipes import (
            normalize_programming_mode,
            recipe_from_mapping,
        )

        self.assertEqual(
            normalize_programming_mode("chaos"), ProgrammingMode.SHUFFLE
        )
        recipe = recipe_from_mapping(
            {"name": "Legacy", "number": 100, "source": "chaos", "programming_mode": "chaos"}
        )
        self.assertEqual(recipe.programming_mode, ProgrammingMode.SHUFFLE)
        self.assertEqual(recipe.source, "chaos")


class CraftOptionsTests(unittest.TestCase):
    def test_next_channel_number_and_recipe(self) -> None:
        from projectionist.live_channels.craft import (
            build_craft_options,
            next_channel_number,
            recipe_from_craft_payload,
        )

        self.assertEqual(next_channel_number([], base=100), 100)
        self.assertEqual(next_channel_number([100, 102], base=100), 103)
        recipe = recipe_from_craft_payload(
            {"source": "motif", "motif": "heist", "number": 0},
            default_number=110,
        )
        self.assertEqual(recipe.number, 110)
        self.assertEqual(recipe.source, "motif")
        self.assertEqual(recipe.motif, "heist")
        self.assertTrue(recipe.name)
        opts = build_craft_options(None, existing_channel_numbers=[100])
        self.assertEqual(opts["next_channel_number"], 101)
        self.assertTrue(opts["sources"])
        source_ids = {s["id"] for s in opts["sources"]}
        mode_ids = {m["id"] for m in opts["programming_modes"]}
        self.assertNotIn("chaos", source_ids)
        self.assertNotIn("chaos", mode_ids)
        self.assertEqual(mode_ids, {"shuffle", "sequential"})

    def test_includes_plex_collections_and_empty_hint(self) -> None:
        from projectionist.connectors.plex_collections import PlexCollection
        from projectionist.live_channels.craft import build_craft_options

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            plex_movie_section="1",
            plex_tv_section="2",
        )
        with patch(
            "projectionist.connectors.plex_collections.list_collections",
            side_effect=lambda client, section_id: (
                [
                    PlexCollection(
                        rating_key="99",
                        title="Alien Timeline",
                        section_id=str(section_id),
                        media_type="movie",
                    ),
                    PlexCollection(
                        rating_key="100",
                        title="[CuratorX] Temp Night",
                        section_id=str(section_id),
                        media_type="movie",
                    ),
                ]
                if str(section_id) == "1"
                else []
            ),
        ), patch(
            "projectionist.connectors.plex.PlexClient",
            return_value=MagicMock(),
        ):
            opts = build_craft_options(None, settings=settings)
        titles = [row["title"] for row in opts["collections"]]
        self.assertIn("Alien Timeline", titles)
        self.assertNotIn("[CuratorX] Temp Night", titles)
        self.assertEqual(opts["collections"][0]["source"], "plex")
        self.assertEqual(opts["collections_empty_reason"], "")

        bare = build_craft_options(None, settings=Settings())
        self.assertEqual(bare["collections"], [])
        self.assertEqual(bare["collections_empty_reason"], "error")
        self.assertTrue(bare["collections_empty_hint"])

    def test_returns_all_plex_collections_no_hard_cap(self) -> None:
        from projectionist.connectors.plex_collections import PlexCollection
        from projectionist.live_channels.craft import build_craft_options

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            plex_movie_section="1",
            plex_tv_section="",
        )
        many = [
            PlexCollection(
                rating_key=str(i),
                title=f"Collection {i:03d}",
                section_id="1",
                media_type="movie",
            )
            for i in range(1, 183)
        ]
        with patch(
            "projectionist.connectors.plex_collections.list_collections",
            return_value=many,
        ), patch(
            "projectionist.connectors.plex.PlexClient",
            return_value=MagicMock(),
        ):
            opts = build_craft_options(None, settings=settings)
        self.assertEqual(opts["collections_total"], 182)
        self.assertEqual(len(opts["collections"]), 182)
        self.assertEqual(opts["collections"][-1]["title"], "Collection 182")


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

    def test_prefer_real_titles_does_not_steal_next_episode(self) -> None:
        from projectionist.live_channels.guide import (
            _prefer_real_titles_over_flex,
            _relabel_flex_program_placeholders,
        )

        slots = _prefer_real_titles_over_flex(
            {
                "now": {
                    "title": "Gilligan's Island · Up next",
                    "episode_title": None,
                    "is_flex": True,
                    "seconds_elapsed": 1012,
                    "seconds_remaining": 788,
                },
                "next": {
                    "title": "Gilligan's Island",
                    "episode_title": "The Big Gold Strike",
                    "is_flex": False,
                    "content_rating": "TV-G",
                },
            }
        )
        self.assertTrue(slots["now"]["is_flex"])
        self.assertEqual(slots["now"]["title"], "Gilligan's Island · Up next")
        self.assertIsNone(slots["now"].get("episode_title"))
        self.assertEqual(slots["next"]["episode_title"], "The Big Gold Strike")

        programs = _relabel_flex_program_placeholders(
            [
                {
                    "title": "Gilligan's Island · Up next",
                    "is_flex": True,
                    "start": 1.0,
                    "stop": 2.0,
                },
                {
                    "title": "Gilligan's Island",
                    "episode_title": "The Big Gold Strike",
                    "is_flex": False,
                    "start": 2.0,
                    "stop": 3.0,
                },
            ]
        )
        self.assertEqual(programs[0]["title"], "Gilligan's Island · Up next")
        self.assertTrue(programs[0]["is_flex"])
        self.assertEqual(programs[1]["episode_title"], "The Big Gold Strike")

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

    def test_dual_watch_hint_on_snapshot(self) -> None:
        snap = build_on_now_snapshot(Settings())
        self.assertIn("Projectionist", snap["plex_hint"])
        self.assertEqual(snap["watch_hint"], DUAL_WATCH_HINT)

    def test_guide_snapshot_includes_programs(self) -> None:
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        now = 1_700_000_100.0
        client = MagicMock()
        client.list_channels.return_value = [
            {"id": "ch-1", "name": "Chaos Night", "number": 100, "icon": {"path": "http://x/a.png"}},
        ]
        client.get_all_channel_guides.return_value = {
            "ch-1": {
                "programs": [
                    {
                        "title": "Heat",
                        "episodeTitle": "Night one",
                        "start": now - 60,
                        "stop": now + 3600,
                        "contentRating": "R",
                    },
                    {"title": "Ronin", "start": now + 3600, "stop": now + 7200},
                ]
            },
        }
        snap = build_guide_snapshot(settings, client=client, now=now, hours=6)
        self.assertTrue(snap["ready"])
        self.assertEqual(snap["channels"][0]["icon_url"], "http://x/a.png")
        self.assertEqual(len(snap["channels"][0]["programs"]), 2)
        self.assertEqual(snap["channels"][0]["now"]["episode_title"], "Night one")

    def test_guide_reads_nested_tunarr_program_titles(self) -> None:
        """Tunarr TvGuideProgram nests titles under ``program`` (top-level title null)."""
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        now = 1_700_000_100.0
        now_ms = int(now * 1000)
        client = MagicMock()
        client.list_channels.return_value = [
            {"id": "ch-1", "name": "Mystery", "number": 100},
        ]
        client.get_all_channel_guides.return_value = {
            "ch-1": {
                "programs": [
                    {
                        "type": "content",
                        "title": None,
                        "start": now_ms - 60_000,
                        "stop": now_ms + 3_600_000,
                        "duration": 3_660_000,
                        "program": {
                            "type": "episode",
                            "title": "Hostage (1)",
                            "show": {"title": "Homicide: Life on the Street", "rating": "TV-14"},
                        },
                    },
                    {
                        "type": "content",
                        "title": None,
                        "start": now_ms + 3_600_000,
                        "stop": now_ms + 7_200_000,
                        "duration": 3_600_000,
                        "program": {"type": "movie", "title": "Heat", "rating": "R"},
                    },
                ]
            },
        }
        client.get_now_playing.return_value = None
        snap = build_guide_snapshot(settings, client=client, now=now, hours=6)
        row = snap["channels"][0]
        self.assertEqual(len(row["programs"]), 2)
        self.assertEqual(row["now"]["title"], "Homicide: Life on the Street")
        self.assertEqual(row["now"]["episode_title"], "Hostage (1)")
        self.assertEqual(row["now"]["content_rating"], "TV-14")
        self.assertEqual(row["next"]["title"], "Heat")
        self.assertEqual(row["programs"][0]["title"], "Homicide: Life on the Street")

    def test_guide_flex_placeholder_keeps_up_next_label(self) -> None:
        """Flex pads must stay labeled as Up next — not the following movie/episode.

        Painting Seven Samurai onto the flex cell while Continuity airs was the
        Gilligan “Big Gold Strike vs Eight Is Enough” OSD lie.
        """
        settings = Settings(
            features=FeatureFlags(live_channels_enabled=True),
            tunarr=TunarrSettings(url="http://tunarr.test"),
        )
        now = 1_700_000_100.0
        now_ms = int(now * 1000)
        client = MagicMock()
        client.list_channels.return_value = [
            {"id": "ch-4", "name": "Kung Fu Theater", "number": 104},
        ]
        client.get_all_channel_guides.return_value = {
            "ch-4": {
                "programs": [
                    {
                        "type": "flex",
                        "title": "Kung Fu Theater · Up next",
                        "start": now_ms - 60_000,
                        "stop": now_ms + 3_600_000,
                        "duration": 3_660_000,
                    },
                    {
                        "type": "content",
                        "title": None,
                        "start": now_ms + 3_600_000,
                        "stop": now_ms + 7_200_000,
                        "duration": 3_600_000,
                        "program": {"type": "movie", "title": "Seven Samurai"},
                    },
                ]
            },
        }
        client.get_now_playing.return_value = {
            "type": "flex",
            "title": "Kung Fu Theater · Up next",
            "start": now_ms - 60_000,
            "stop": now_ms + 3_600_000,
        }
        snap = build_guide_snapshot(settings, client=client, now=now, hours=6)
        row = snap["channels"][0]
        self.assertTrue(row["now"]["is_flex"])
        self.assertEqual(row["now"]["title"], "Kung Fu Theater · Up next")
        self.assertEqual(row["next"]["title"], "Seven Samurai")
        self.assertEqual(row["programs"][0]["title"], "Kung Fu Theater · Up next")
        self.assertTrue(row["programs"][0]["is_flex"])
        self.assertEqual(row["programs"][1]["title"], "Seven Samurai")


class StreamProxyTests(unittest.TestCase):
    def test_validate_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            validate_stream_path("../secret")
        self.assertEqual(validate_stream_path("hls/stream.m3u8"), "hls/stream.m3u8")

    def test_rewrite_playlist_stays_on_proxy(self) -> None:
        body = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhls/stream.m3u8\n"
        out = rewrite_hls_playlist(
            body,
            channel_id="abc",
            tunarr_base="http://tunarr.lan:8000",
            playlist_path="index.m3u8",
        )
        self.assertIn("/api/live-channels/stream/abc/hls/stream.m3u8", out)
        self.assertNotIn("tunarr.lan", out)
        self.assertTrue(tunarr_master_url("http://t", "abc").endswith(".m3u8?mode=hls"))

    def test_rewrite_root_relative_tunarr_paths(self) -> None:
        """Tunarr master/media playlists use /stream/channels/{id}/… paths."""
        cid = "0bac6317-d1d0-44f2-844f-197d155eb3e5"
        body = (
            "#EXTM3U\n"
            f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",URI="/stream/channels/{cid}/hls/stream.m3u8"\n'
            "#EXT-X-STREAM-INF:BANDWIDTH=1\n"
            f"/stream/channels/{cid}/hls/stream.m3u8\n"
        )
        out = rewrite_hls_playlist(
            body,
            channel_id=cid,
            tunarr_base="http://host.docker.internal:18765",
            playlist_path="index.m3u8",
        )
        self.assertIn(f"/api/live-channels/stream/{cid}/hls/stream.m3u8", out)
        self.assertNotIn(f"/stream/channels/{cid}/stream/channels/", out)
        self.assertNotIn("host.docker.internal", out)

        media = (
            "#EXTM3U\n#EXTINF:4.0,\n"
            f"/stream/channels/{cid}/hls/data000000.ts\n"
        )
        media_out = rewrite_hls_playlist(
            media,
            channel_id=cid,
            tunarr_base="http://host.docker.internal:18765",
            playlist_path="hls/stream.m3u8",
        )
        self.assertEqual(
            media_out.strip().splitlines()[-1],
            f"/api/live-channels/stream/{cid}/hls/data000000.ts",
        )

    def test_rewrite_strips_alternate_audio_media_tags(self) -> None:
        """Tunarr AUDIO groups (often URI-less) stall hls.js — proxy serves muxed only."""
        from projectionist.live_channels.stream_proxy import sanitize_browser_hls_master

        cid = "59bc2df4-eca9-4ab8-9012-c42ffec358be"
        body = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:6\n"
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="eng",'
            'NAME="English (AC3 Mono)",DEFAULT=YES,AUTOSELECT=YES,CHANNELS="1"\n'
            '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",LANGUAGE="eng",'
            f'NAME="English",URI="/stream/channels/{cid}/hls/stream.m3u8"\n'
            '#EXT-X-STREAM-INF:BANDWIDTH=2411200,RESOLUTION=1920x1080,'
            'CODECS="avc1.640028,mp4a.40.2",AUDIO="audio"\n'
            f"/stream/channels/{cid}/hls/stream.m3u8\n"
        )
        sanitized = sanitize_browser_hls_master(body)
        self.assertNotIn("EXT-X-MEDIA", sanitized)
        self.assertNotIn('AUDIO="audio"', sanitized)
        self.assertIn("EXT-X-STREAM-INF", sanitized)

        out = rewrite_hls_playlist(
            body,
            channel_id=cid,
            tunarr_base="http://host.docker.internal:18765",
            playlist_path="index.m3u8",
        )
        self.assertNotIn("EXT-X-MEDIA", out)
        self.assertNotIn('AUDIO="audio"', out)
        self.assertIn(f"/api/live-channels/stream/{cid}/hls/stream.m3u8", out)

    def test_sanitize_strips_audio_attr_when_first_on_stream_inf(self) -> None:
        """AUDIO= as the first STREAM-INF attribute must still be removed."""
        from projectionist.live_channels.stream_proxy import sanitize_browser_hls_master

        body = (
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:AUDIO="audio",BANDWIDTH=2411200,RESOLUTION=1920x1080,'
            'CODECS="avc1.640028,mp4a.40.2"\n'
            "hls/stream.m3u8\n"
        )
        sanitized = sanitize_browser_hls_master(body)
        self.assertNotIn("AUDIO=", sanitized)
        self.assertNotIn(",,", sanitized)
        self.assertIn(
            '#EXT-X-STREAM-INF:BANDWIDTH=2411200,RESOLUTION=1920x1080,'
            'CODECS="avc1.640028,mp4a.40.2"',
            sanitized,
        )

    def test_sanitize_strips_audio_attr_mid_stream_inf(self) -> None:
        """AUDIO= between other STREAM-INF attributes must leave clean commas."""
        from projectionist.live_channels.stream_proxy import sanitize_browser_hls_master

        body = (
            "#EXTM3U\n"
            '#EXT-X-STREAM-INF:BANDWIDTH=2411200,AUDIO="audio",RESOLUTION=1920x1080,'
            'CODECS="avc1.640028,mp4a.40.2"\n'
            "hls/stream.m3u8\n"
        )
        sanitized = sanitize_browser_hls_master(body)
        self.assertNotIn("AUDIO=", sanitized)
        self.assertNotIn(",,", sanitized)
        self.assertIn(
            "#EXT-X-STREAM-INF:BANDWIDTH=2411200,RESOLUTION=1920x1080,"
            'CODECS="avc1.640028,mp4a.40.2"',
            sanitized,
        )


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
        from projectionist.live_channels.plex_attach import (
            build_plex_attach,
            host_port_for_plex,
            xmltv_url,
        )

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
        self.assertEqual(attach["manual_address"], "tunarr.test:8000")
        self.assertEqual(host_port_for_plex("http://tunarr.test:8000/"), "tunarr.test:8000")
        self.assertGreaterEqual(len(attach["steps"]), 4)
        joined = " ".join(f"{s['title']} {s['body']}" for s in attach["steps"]).lower()
        self.assertIn("tuner setup", joined)
        self.assertIn("no xmltv option", joined)
        self.assertIn("postal code", joined)
        self.assertIn("temporary", joined)
        self.assertIn("attach tunarr guide in plex", joined)
        self.assertIn("pms api", joined)
        self.assertIn("xmltv", joined)
        self.assertIn("don't see your hdhomerun", joined)
        self.assertNotIn("wipe", joined)
        # Must not claim a DVR Settings paste box.
        self.assertNotIn("dvr settings → add", joined)
        self.assertNotIn("paste the guide url below, then refresh", joined)
        first_tuner = next(s for s in attach["steps"] if "tuner setup" in s["title"].lower())
        self.assertIn("no xmltv", first_tuner["body"].lower())
        api_step = next(s for s in attach["steps"] if "projectionist" in s["title"].lower())
        self.assertIn("attach tunarr guide", api_step["body"].lower())
        warning = attach["coexistence"]["guide_warning"].lower()
        self.assertIn("attach tunarr guide in plex", warning)
        self.assertIn("pms api", warning)
        self.assertTrue(attach["coexistence"].get("api_attach"))
        self.assertEqual(attach["coexistence"]["mode"], "additional_tuner")
        self.assertEqual(attach["existing_livetv"]["status"], "detected")

    def test_prune_dead_grabber_devices_skips_ota_and_tunarr(self) -> None:
        import xml.etree.ElementTree as ET

        from projectionist.live_channels.plex_attach import prune_dead_grabber_devices

        devices = ET.fromstring(
            """
            <MediaContainer size="3">
              <Device key="1" uuid="device://tv.plex.grabbers.hdhomerun/106010D2"
                uri="http://10.10.3.164:80" deviceId="106010D2" status="alive"
                make="Silicondust" title="OTA"/>
              <Device key="10" uuid="device://tv.plex.grabbers.hdhomerun/"
                uri="http://10.10.1.202:7007/api/channels.m3u" deviceId=""
                status="dead" make="Unknown" title=""/>
              <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr"
                uri="http://10.10.1.202:18765" deviceId="Tunarr" status="alive"
                make="Tunarr - Silicondust" title="Projectionist"/>
            </MediaContainer>
            """
        )
        deleted_paths: list[str] = []

        def fake_xml(client, path, *, method="GET", timeout=None):
            del client, timeout
            if path.startswith("/media/grabbers/devices/") and method == "DELETE":
                deleted_paths.append(path)
                return ET.fromstring('<MediaContainer size="0" status="0"/>')
            if path.startswith("/media/grabbers/devices"):
                return devices
            raise AssertionError(f"unexpected {method} {path}")

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="tok",
            tunarr=TunarrSettings(public_url="http://10.10.1.202:18765"),
        )
        with patch(
            "projectionist.live_channels.plex_attach._plex_xml",
            side_effect=fake_xml,
        ):
            result = prune_dead_grabber_devices(settings)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["deleted"]), 1)
        self.assertEqual(result["deleted"][0]["key"], "10")
        self.assertEqual(deleted_paths, ["/media/grabbers/devices/10"])

    def test_attach_tunarr_xmltv_reuses_existing_xmltv_dvr(self) -> None:
        from unittest.mock import MagicMock, patch
        import xml.etree.ElementTree as ET
        from projectionist.live_channels.plex_attach import attach_tunarr_xmltv_to_plex

        devices = ET.fromstring(
            """
            <MediaContainer>
              <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr"
                uri="http://10.10.1.202:18765" deviceId="Tunarr" title="Projectionist"
                make="Tunarr - Silicondust" status="alive" state="enabled"/>
            </MediaContainer>
            """
        )
        dvrs = ET.fromstring(
            """
            <MediaContainer>
              <Dvr key="8" lineup="lineup://tv.plex.providers.epg.cloud/abc#Local"
                epgIdentifier="tv.plex.providers.epg.cloud:8">
                <Device key="1" uuid="device://tv.plex.grabbers.hdhomerun/OTA" deviceId="OTA"/>
              </Dvr>
              <Dvr key="12"
                lineup="lineup://tv.plex.providers.epg.xmltv/http://10.10.1.202:18765/api/xmltv.xml#Projectionist"
                epgIdentifier="tv.plex.providers.epg.xmltv:12">
                <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr" deviceId="Tunarr"/>
              </Dvr>
            </MediaContainer>
            """
        )
        cmap = ET.fromstring(
            """
            <MediaContainer>
              <ChannelMapping channelKey="C100.1" deviceIdentifier="100" lineupIdentifier="100"/>
              <ChannelMapping channelKey="C101.1" deviceIdentifier="101" lineupIdentifier="101"/>
            </MediaContainer>
            """
        )
        put_ok = ET.fromstring('<MediaContainer size="0" status="0"/>')
        reload_ok = ET.fromstring('<MediaContainer size="0"/>')

        def fake_xml(client, path, *, method="GET", timeout=None):
            if path.startswith("/media/grabbers/devices") and method == "GET" and "channelmap" not in path:
                return devices
            if path.startswith("/livetv/dvrs") and method == "GET":
                return dvrs
            if path.startswith("/livetv/epg/channelmap"):
                return cmap
            if "channelmap" in path and method == "PUT":
                return put_ok
            if path.endswith("/reloadGuide") and method == "POST":
                return reload_ok
            raise AssertionError(f"unexpected {method} {path}")

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            tunarr=TunarrSettings(
                url="http://host.docker.internal:18765",
                public_url="http://10.10.1.202:18765",
            ),
        )
        mock_client = MagicMock()
        mock_client.base_url = "http://plex.test:32400"
        mock_client.token = "token"
        mock_client.timeout = 10
        with patch(
            "projectionist.live_channels.plex_attach._plex_xml", side_effect=fake_xml
        ), patch(
            "projectionist.live_channels.plex_attach.count_tunarr_hdhr_channels",
            return_value=2,
        ), patch(
            "projectionist.live_channels.plex_attach.scan_plex_device_channels",
            return_value={"ok": True, "count": 2, "message": "ok"},
        ), patch(
            "projectionist.live_channels.plex_attach.prune_dead_grabber_devices",
            return_value={"ok": True, "deleted": []},
        ), patch(
            "projectionist.connectors.http.request_empty"
        ), patch("projectionist.connectors.plex.PlexClient", return_value=mock_client):
            result = attach_tunarr_xmltv_to_plex(settings)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["dvr_key"], "12")
        self.assertEqual(result["mapped"], 2)
        self.assertEqual(result["expected"], 2)
        self.assertIn("reused_xmltv_dvr", result["steps"])

    def test_refresh_surfaces_short_map_and_reattaches(self) -> None:
        """Post-publish refresh must not claim success when Plex still has a stale short map."""
        from unittest.mock import MagicMock, patch
        import xml.etree.ElementTree as ET
        from projectionist.live_channels.plex_attach import refresh_plex_live_tv_channels

        devices = ET.fromstring(
            """
            <MediaContainer>
              <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr"
                uri="http://10.10.1.202:18765" deviceId="Tunarr" title="Projectionist"
                make="Tunarr - Silicondust" status="alive" state="enabled"/>
            </MediaContainer>
            """
        )
        dvrs = ET.fromstring(
            """
            <MediaContainer>
              <Dvr key="12"
                lineup="lineup://tv.plex.providers.epg.xmltv/http://10.10.1.202:18765/api/xmltv.xml#Projectionist">
                <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr"/>
                <ChannelMapping channelKey="C100.1" deviceIdentifier="100" lineupIdentifier="100" enabled="1"/>
                <ChannelMapping channelKey="C101.1" deviceIdentifier="101" lineupIdentifier="101" enabled="1"/>
                <ChannelMapping channelKey="C102.1" deviceIdentifier="102" lineupIdentifier="102" enabled="1"/>
                <ChannelMapping channelKey="C103.1" deviceIdentifier="103" lineupIdentifier="103" enabled="1"/>
              </Dvr>
            </MediaContainer>
            """
        )
        short_cmap = ET.fromstring(
            """
            <MediaContainer>
              <ChannelMapping channelKey="C100.1" deviceIdentifier="100" lineupIdentifier="100"/>
              <ChannelMapping channelKey="C101.1" deviceIdentifier="101" lineupIdentifier="101"/>
              <ChannelMapping channelKey="C102.1" deviceIdentifier="102" lineupIdentifier="102"/>
              <ChannelMapping channelKey="C103.1" deviceIdentifier="103" lineupIdentifier="103"/>
            </MediaContainer>
            """
        )
        full_cmap = ET.fromstring(
            """
            <MediaContainer>
              <ChannelMapping channelKey="C100.1" deviceIdentifier="100" lineupIdentifier="100"/>
              <ChannelMapping channelKey="C101.1" deviceIdentifier="101" lineupIdentifier="101"/>
              <ChannelMapping channelKey="C102.1" deviceIdentifier="102" lineupIdentifier="102"/>
              <ChannelMapping channelKey="C103.1" deviceIdentifier="103" lineupIdentifier="103"/>
              <ChannelMapping channelKey="C104.1" deviceIdentifier="104" lineupIdentifier="104"/>
              <ChannelMapping channelKey="C105.1" deviceIdentifier="105" lineupIdentifier="105"/>
            </MediaContainer>
            """
        )
        put_ok = ET.fromstring('<MediaContainer size="0" status="0"/>')
        state = {"phase": "short"}

        def fake_xml(client, path, *, method="GET", timeout=None):
            if method == "DELETE":
                return put_ok
            if path.startswith("/media/grabbers/tv.plex.grabbers.hdhomerun/devices") and method == "POST":
                return devices
            if path.startswith("/media/grabbers/devices") and method == "GET" and "channelmap" not in path:
                return devices
            if path.startswith("/livetv/dvrs") and method == "GET":
                return dvrs
            if path.startswith("/livetv/dvrs") and method == "POST":
                return dvrs
            if path.startswith("/livetv/epg/channelmap"):
                return full_cmap if state["phase"] == "full" else short_cmap
            if "channelmap" in path and method == "PUT":
                return put_ok
            raise AssertionError(f"unexpected {method} {path}")

        def fake_scan(client, device_key, *, expected=0, timeout=45):
            if state["phase"] == "short":
                # First refresh sees stale 4 → triggers recreate.
                state["phase"] = "full"
                return {"ok": False, "count": 4, "message": "stale"}
            return {"ok": True, "count": 6, "message": "ok"}

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            tunarr=TunarrSettings(public_url="http://10.10.1.202:18765"),
        )
        mock_client = MagicMock()
        mock_client.base_url = "http://plex.test:32400"
        mock_client.token = "token"
        mock_client.timeout = 10
        with patch(
            "projectionist.live_channels.plex_attach._plex_xml", side_effect=fake_xml
        ), patch(
            "projectionist.live_channels.plex_attach.count_tunarr_hdhr_channels",
            return_value=6,
        ), patch(
            "projectionist.live_channels.plex_attach.scan_plex_device_channels",
            side_effect=fake_scan,
        ), patch(
            "projectionist.live_channels.plex_attach.prune_dead_grabber_devices",
            return_value={"ok": True, "deleted": []},
        ), patch(
            "projectionist.connectors.http.request_empty"
        ), patch("projectionist.connectors.plex.PlexClient", return_value=mock_client):
            result = refresh_plex_live_tv_channels(settings)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mapped"], 6)
        self.assertEqual(result["expected"], 6)
        self.assertIn("recreate_stale_device_channels", result.get("steps") or [])

    def test_refresh_missing_device_runs_full_attach(self) -> None:
        from unittest.mock import patch
        import xml.etree.ElementTree as ET
        from projectionist.live_channels.plex_attach import refresh_plex_live_tv_channels

        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            tunarr=TunarrSettings(public_url="http://10.10.1.202:18765"),
        )
        empty = ET.fromstring("<MediaContainer/>")
        with patch(
            "projectionist.live_channels.plex_attach.count_tunarr_hdhr_channels",
            return_value=6,
        ), patch(
            "projectionist.live_channels.plex_attach._plex_xml",
            return_value=empty,
        ), patch(
            "projectionist.live_channels.plex_attach.attach_tunarr_xmltv_to_plex",
            return_value={
                "ok": True,
                "mapped": 6,
                "expected": 6,
                "message": "Mapped 6/6",
                "steps": ["registered_device"],
            },
        ) as attach, patch(
            "projectionist.connectors.plex.PlexClient"
        ):
            result = refresh_plex_live_tv_channels(settings)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mapped"], 6)
        attach.assert_called_once()
        self.assertTrue(attach.call_args.kwargs.get("force_recreate"))

    def test_refresh_dead_device_without_attach_returns_error(self) -> None:
        """Dead Tunarr + allow_attach=False must error, not attempt channelmap."""
        from unittest.mock import MagicMock, patch
        import xml.etree.ElementTree as ET
        from projectionist.live_channels.plex_attach import refresh_plex_live_tv_channels

        devices = ET.fromstring(
            """
            <MediaContainer>
              <Device key="11" uuid="device://tv.plex.grabbers.hdhomerun/Tunarr"
                uri="http://10.10.1.202:18765" deviceId="Tunarr" title="Projectionist"
                make="Tunarr - Silicondust" status="dead" state="enabled"/>
            </MediaContainer>
            """
        )
        settings = Settings(
            plex_url="http://plex.test:32400",
            plex_token="token",
            tunarr=TunarrSettings(public_url="http://10.10.1.202:18765"),
        )
        mock_client = MagicMock()
        mock_client.base_url = "http://plex.test:32400"
        mock_client.token = "token"
        mock_client.timeout = 10
        put_channelmap = MagicMock()
        with patch(
            "projectionist.live_channels.plex_attach.count_tunarr_hdhr_channels",
            return_value=6,
        ), patch(
            "projectionist.live_channels.plex_attach._plex_xml",
            return_value=devices,
        ), patch(
            "projectionist.live_channels.plex_attach.attach_tunarr_xmltv_to_plex",
        ) as attach, patch(
            "projectionist.live_channels.plex_attach._put_device_channelmap",
            put_channelmap,
        ), patch(
            "projectionist.live_channels.plex_attach.scan_plex_device_channels",
        ) as scan, patch("projectionist.connectors.plex.PlexClient", return_value=mock_client):
            result = refresh_plex_live_tv_channels(settings, allow_attach=False)
        self.assertFalse(result["ok"])
        self.assertTrue(result["attach_needed"])
        self.assertEqual(result["mapped"], 0)
        self.assertEqual(result["expected"], 6)
        self.assertTrue(result["device_present"])
        self.assertEqual(result["device_status"], "dead")
        self.assertIn("dead", result["message"].lower())
        attach.assert_not_called()
        put_channelmap.assert_not_called()
        scan.assert_not_called()

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
        self.assertEqual(attach["manual_address"], "10.10.1.202:8000")
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
        client.list_media_source_libraries.return_value = [
            {
                "id": "lib-movies",
                "name": "Movies",
                "mediaType": "movies",
                "externalKey": "1",
                "enabled": False,
            },
            {
                "id": "lib-magic",
                "name": "Magical Media",
                "mediaType": "movies",
                "externalKey": "99",
                "enabled": False,
            },
        ]
        client.set_library_enabled.return_value = {"id": "lib-movies", "enabled": True}
        client.scan_library.return_value = {}
        client.ensure_plex_stream_path_direct.return_value = {
            "ok": True,
            "changed": True,
            "streamPath": "direct",
        }
        with patch(
            "projectionist.live_channels.publish._plex_identity_hints",
            return_value=("mid", "Home"),
        ):
            result = wire_plex_media_source(
                client,
                plex_url="http://plex.test:32400",
                plex_token="tok",
                settings=Settings(plex_movie_section="1", plex_tv_section="2"),
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        client.ensure_plex_stream_path_direct.assert_called_once()
        self.assertEqual(result["plex_stream"]["streamPath"], "direct")
        body = client.create_media_source.call_args.args[0]
        self.assertEqual(body["pathReplacements"], [])
        self.assertIn("userId", body)
        self.assertIn("username", body)
        self.assertNotEqual(body.get("userId"), "tok")
        client.set_library_enabled.assert_called()
        self.assertTrue(result["libraries"]["enabled"])
        enabled_ids = {row["id"] for row in result["libraries"]["enabled"]}
        self.assertEqual(enabled_ids, {"lib-movies"})
        skipped_names = {row["name"] for row in result["libraries"].get("skipped") or []}
        self.assertIn("Magical Media", skipped_names)

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
        with_icon = channel_create_body(
            recipe,
            transcode_config_id="ce5cfbdb-603d-47cd-85ff-6ddbe51f33c4",
            icon_url="http://10.10.1.202:18765/images/tunarr.png",
        )
        self.assertEqual(
            with_icon["channel"]["icon"]["path"],
            "http://10.10.1.202:18765/images/tunarr.png",
        )
        self.assertEqual(with_icon["channel"]["icon"]["width"], 256)
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
        content = programming_body_for_recipe(
            recipe,
            programs=[
                {"id": "prog-1", "duration": 5_400_000, "title": "Heat"},
                {"id": "prog-2", "duration": 7_200_000, "title": "Alien"},
            ],
        )
        self.assertEqual(content["lineup"][0]["type"], "content")
        self.assertEqual(content["lineup"][0]["id"], "prog-1")

    def test_publish_recipes_creates_channels(self) -> None:
        from projectionist.live_channels.publish import publish_recipes

        client = MagicMock()
        client.base_url = "http://tunarr.test:8000"
        client.list_media_sources.return_value = []
        client.list_channels.return_value = []
        client.list_sessions.return_value = {}
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
        _filler = {
            "ok": False,
            "ready": False,
            "filler_list_id": "",
            "program_count": 0,
            "message": "no filler",
        }
        with patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={
                "ok": True,
                "labels": {},
                "warmed": [],
                "count_aligned": 0,
                "count_warmed_ok": 0,
            },
        ), patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value=_filler,
        ):
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
        client.base_url = "http://tunarr.test:8000"
        client.list_media_sources.return_value = []
        client.list_channels.return_value = [{"id": "x", "name": "Chaos", "number": 100}]
        client.list_sessions.return_value = {}
        client.default_transcode_config_id.return_value = "tc-default"
        client.set_channel_programming.return_value = {"totalPrograms": 0, "lineup": []}
        _filler = {
            "ok": False,
            "ready": False,
            "filler_list_id": "",
            "program_count": 0,
            "message": "no filler",
        }
        # Default fill_programming=True refreshes existing empty stations.
        with patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={
                "ok": True,
                "labels": {},
                "warmed": [],
                "count_aligned": 0,
                "count_warmed_ok": 0,
            },
        ), patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value=_filler,
        ):
            result = publish_recipes(
                client,
                [ChannelRecipe(name="Chaos", number=100, source="chaos")],
            )
        self.assertEqual(result["count_skipped"], 0)
        self.assertEqual(result["count_programming_updated"], 1)
        client.create_channel.assert_not_called()
        client.set_channel_programming.assert_called()

        client2 = MagicMock()
        client2.base_url = "http://tunarr.test:8000"
        client2.list_media_sources.return_value = []
        client2.list_channels.return_value = [{"id": "x", "name": "Chaos", "number": 100}]
        client2.list_sessions.return_value = {}
        client2.default_transcode_config_id.return_value = "tc-default"
        with patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={
                "ok": True,
                "labels": {},
                "warmed": [],
                "count_aligned": 0,
                "count_warmed_ok": 0,
            },
        ), patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value=_filler,
        ):
            skipped = publish_recipes(
                client2,
                [ChannelRecipe(name="Chaos", number=100, source="chaos")],
                fill_programming=False,
            )
        self.assertEqual(skipped["count_skipped"], 1)
        client2.create_channel.assert_not_called()

    def test_publish_fills_content_from_library_catalog(self) -> None:
        from projectionist.live_channels.publish import publish_recipes

        client = MagicMock()
        client.list_media_sources.return_value = [
            {"id": "ms-1", "type": "plex", "uri": "http://plex"}
        ]
        client.list_media_source_libraries.return_value = [
            {
                "id": "lib-m",
                "name": "Movies",
                "mediaType": "movies",
                "externalKey": "1",
                "enabled": False,
            }
        ]
        client.set_library_enabled.return_value = {"enabled": True}
        client.scan_library.return_value = {}
        client.list_library_programs.return_value = [
            {
                "type": "content",
                "id": "p1",
                "duration": 5_400_000,
                "program": {
                    "uuid": "p1",
                    "title": "Alien",
                    "type": "movie",
                    "genres": ["Science Fiction"],
                },
            },
            {
                "type": "content",
                "id": "p2",
                "duration": 6_000_000,
                "program": {
                    "uuid": "p2",
                    "title": "Heat",
                    "type": "movie",
                    "genres": ["Crime"],
                },
            },
        ]
        client.base_url = "http://tunarr.test:8000"
        client.list_channels.return_value = []
        client.list_sessions.return_value = {}
        client.default_transcode_config_id.return_value = "tc"
        client.create_channel.side_effect = lambda body: {
            "id": "ch-101",
            "name": body["channel"]["name"],
            "number": body["channel"]["number"],
        }
        client.set_channel_programming.return_value = {"totalPrograms": 1}

        with patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={
                "ok": True,
                "labels": {},
                "warmed": [],
                "count_aligned": 0,
                "count_warmed_ok": 0,
            },
        ), patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value={
                "ok": False,
                "ready": False,
                "filler_list_id": "",
                "program_count": 0,
                "message": "no filler",
            },
        ):
            result = publish_recipes(
                client,
                [ChannelRecipe(name="Sci-Fi", number=101, source="motif")],
                settings=Settings(plex_movie_section="1", plex_tv_section="2"),
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["count_content_filled"], 1)
        body = client.set_channel_programming.call_args.args[1]
        if body.get("type") == "random":
            content_ids = list(body.get("programs") or [])
        else:
            content_ids = [
                row["id"] for row in body.get("lineup") or [] if row.get("type") == "content"
            ]
        # Sci-Fi motif matches Alien (p1); Heat may pad. Shuffle may use random slots.
        self.assertIn("p1", content_ids)


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


class PlayheadAlignAndWarmTests(unittest.TestCase):
    def test_should_align_playhead_past_eof_and_cold_deep(self) -> None:
        from projectionist.live_channels.publish import should_align_playhead

        self.assertTrue(
            should_align_playhead(
                elapsed_ms=10_000_000,
                program_duration_ms=5_000_000,
                has_session=True,
            )
        )
        self.assertFalse(
            should_align_playhead(
                elapsed_ms=60_000,
                program_duration_ms=5_000_000,
                has_session=True,
            )
        )
        self.assertTrue(
            should_align_playhead(
                elapsed_ms=6 * 60 * 1000,
                program_duration_ms=5_000_000,
                has_session=False,
            )
        )
        self.assertFalse(
            should_align_playhead(
                elapsed_ms=30_000,
                program_duration_ms=5_000_000,
                has_session=False,
            )
        )

    def test_align_channel_playhead_updates_start_time(self) -> None:
        from projectionist.live_channels.publish import (
            align_channel_playhead_to_program_start,
        )

        now_ms = 1_800_000_000_000
        prog_start = now_ms - (40 * 60 * 1000)
        channel = {
            "id": "ch-1",
            "name": "Mystery",
            "number": 100,
            "startTime": now_ms - (3 * 60 * 60 * 1000),
            "duration": 10_000_000,
            "transcodeConfigId": "tc-1",
            "icon": {"path": "http://10.10.1.202:18765/images/tunarr.png"},
            "offline": {"mode": "pic"},
        }
        client = MagicMock()
        client.get_now_playing.return_value = {
            "type": "content",
            "start": prog_start,
            "duration": 90 * 60 * 1000,
            "program": {"title": "Flight 7500"},
        }
        with patch("projectionist.live_channels.publish.time.time", return_value=now_ms / 1000):
            result = align_channel_playhead_to_program_start(
                client, channel, has_session=False, min_elapsed_ms=5 * 60 * 1000
            )
        self.assertTrue(result["aligned"])
        self.assertEqual(result["title"], "Flight 7500")
        client.update_channel.assert_called_once()
        body = client.update_channel.call_args.args[1]
        self.assertEqual(body["startTime"], channel["startTime"] + (40 * 60 * 1000))

    def test_align_skips_flex_and_snaps_future_start_time(self) -> None:
        from projectionist.live_channels.publish import (
            align_channel_playhead_to_program_start,
            snap_future_channel_start_time,
        )

        now_ms = 1_800_000_000_000
        duration = 7 * 24 * 60 * 60 * 1000
        channel = {
            "id": "ch-gilligan",
            "name": "Gilligan's Island",
            "number": 105,
            "startTime": now_ms + (6 * 60 * 1000),  # 6 minutes ahead
            "duration": duration,
            "transcodeConfigId": "tc-1",
            "icon": {"path": "http://10.10.1.202:18765/images/tunarr.png"},
            "offline": {"mode": "pic"},
        }
        client = MagicMock()
        snap = snap_future_channel_start_time(client, channel, now_ms=now_ms)
        self.assertTrue(snap["snapped"])
        self.assertLessEqual(snap["start_time_ms"], now_ms)
        self.assertEqual(
            snap["start_time_ms"],
            channel["startTime"] - duration,
        )

        client.get_now_playing.return_value = {
            "type": "flex",
            "title": "Gilligan's Island · Up next",
            "start": now_ms - (16 * 60 * 1000),
            "duration": 30 * 60 * 1000,
            "stop": now_ms + (14 * 60 * 1000),
        }
        with patch("projectionist.live_channels.publish.time.time", return_value=now_ms / 1000):
            result = align_channel_playhead_to_program_start(
                client, channel, has_session=False, min_elapsed_ms=5 * 60 * 1000
            )
        self.assertEqual(result.get("reason"), "flex_skip")
        # Snap may update once; must not apply flex elapsed as a second push forward.
        self.assertTrue(result.get("aligned") or result.get("snap", {}).get("snapped"))
        bodies = [c.args[1]["startTime"] for c in client.update_channel.call_args_list]
        self.assertTrue(bodies)
        self.assertTrue(all(st <= now_ms for st in bodies))

    def test_warm_channel_stream_ready_when_media_playlist_has_segments(self) -> None:
        from projectionist.live_channels.publish import warm_channel_stream

        client = MagicMock()
        client.base_url = "http://tunarr.test:8000"
        playlist = "#EXTM3U\n#EXTINF:4.0,\ndata000.ts\n"

        class _Resp:
            def __init__(self, body: bytes) -> None:
                self._body = body

            def read(self, _n: int = -1) -> bytes:
                return self._body

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        def fake_urlopen(req: object, timeout: int = 0) -> _Resp:  # noqa: ARG001
            url = getattr(req, "full_url", None) or str(req)
            if "stream.m3u8" in url or ".m3u8" in url:
                return _Resp(playlist.encode())
            return _Resp(b"\x00" * 250_000)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = warm_channel_stream(client, "ch-1", timeout=5)
        self.assertTrue(result["ok"])
        self.assertTrue(result["playlist_ready"])
        self.assertGreaterEqual(result["ts_bytes"], 200_000)

    def test_prepare_channels_for_playback_aligns_and_warms(self) -> None:
        from projectionist.live_channels.publish import prepare_channels_for_playback

        client = MagicMock()
        client.base_url = "http://tunarr.test:8000"
        client.list_sessions.return_value = {}
        client.list_channels.return_value = [
            {
                "id": "ch-1",
                "name": "Chaos",
                "number": 102,
                "startTime": 1_700_000_000_000,
                "duration": 100_000_000,
                "transcodeConfigId": "tc-1",
                "icon": {
                    "path": "http://10.10.1.202:18765/images/tunarr.png",
                    "width": 256,
                    "duration": 0,
                    "position": "bottom-right",
                },
                "offline": {"mode": "pic"},
            }
        ]
        with patch(
            "projectionist.live_channels.publish.align_channel_playhead_to_program_start",
            return_value={"ok": True, "aligned": True, "channel_id": "ch-1"},
        ) as align, patch(
            "projectionist.live_channels.publish.warm_channel_stream",
            return_value={"ok": True, "channel_id": "ch-1", "ts_bytes": 300_000},
        ) as warm:
            result = prepare_channels_for_playback(client, icon_url="")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count_aligned"], 1)
        self.assertEqual(result["count_warmed_ok"], 1)
        align.assert_called_once()
        warm.assert_called_once()

    def test_prepare_skips_active_sessions_and_caps_warm_budget(self) -> None:
        from projectionist.live_channels.publish import prepare_channels_for_playback

        client = MagicMock()
        client.base_url = "http://tunarr.test:8000"
        client.list_sessions.return_value = {
            "ch-live": [{"type": "hls", "state": "started"}],
        }
        client.list_channels.return_value = [
            {
                "id": "ch-live",
                "name": "Mystery",
                "number": 100,
                "startTime": 1_700_000_000_000,
                "duration": 100_000_000,
                "transcodeConfigId": "tc-1",
                "icon": {"path": ""},
                "offline": {"mode": "pic"},
            },
            {
                "id": "ch-cold-a",
                "name": "Sci-Fi",
                "number": 101,
                "startTime": 1_700_000_000_000,
                "duration": 100_000_000,
                "transcodeConfigId": "tc-1",
                "icon": {"path": ""},
                "offline": {"mode": "pic"},
            },
            {
                "id": "ch-cold-b",
                "name": "Chaos",
                "number": 102,
                "startTime": 1_700_000_000_000,
                "duration": 100_000_000,
                "transcodeConfigId": "tc-1",
                "icon": {"path": ""},
                "offline": {"mode": "pic"},
            },
        ]
        with patch(
            "projectionist.live_channels.publish.align_channel_playhead_to_program_start",
            return_value={"ok": True, "aligned": True, "channel_id": "x"},
        ) as align, patch(
            "projectionist.live_channels.publish.warm_channel_stream",
            return_value={"ok": True, "channel_id": "x", "ts_bytes": 0},
        ) as warm:
            result = prepare_channels_for_playback(
                client,
                icon_url="",
                skip_active_sessions=True,
                max_warm_channels=1,
                pull_ts=False,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["count_skipped_active"], 1)
        self.assertEqual(result["count_warmed_skipped"], 2)  # live + budget
        self.assertEqual(warm.call_count, 1)
        self.assertEqual(warm.call_args.kwargs.get("pull_ts"), False)
        # Active channel must not be aligned via start-over helper.
        aligned_ids = {call.args[1]["id"] for call in align.call_args_list}
        self.assertNotIn("ch-live", aligned_ids)


class ContinuityFillerTests(unittest.TestCase):
    def test_parse_filler_binds_multi_path_and_host_only(self) -> None:
        from projectionist.live_channels.filler import (
            filler_container_paths,
            parse_filler_binds,
        )

        binds = parse_filler_binds(
            [
                "/mnt/user/bumpers",
                "/mnt/user/trailers:/data/filler/trailers:ro",
                "/mnt/user/bumpers",  # dedupe
            ]
        )
        self.assertEqual(len(binds), 2)
        self.assertTrue(binds[0].startswith("/mnt/user/bumpers:/data/filler/"))
        self.assertEqual(binds[1], "/mnt/user/trailers:/data/filler/trailers:ro")
        self.assertEqual(
            filler_container_paths(binds),
            [binds[0].split(":")[1], "/data/filler/trailers"],
        )

    def test_ensure_local_filler_source_skips_noop_update(self) -> None:
        from projectionist.live_channels.filler import ensure_local_filler_source

        client = MagicMock()
        client.list_media_sources.return_value = [
            {
                "id": "local-1",
                "type": "local",
                "name": "Projectionist Fillers",
                "paths": ["/data/filler/a", "/data/filler/b"],
            }
        ]
        client.list_media_source_libraries.return_value = [
            {"id": "lib-f", "name": "Fillers", "enabled": True}
        ]
        result = ensure_local_filler_source(
            client,
            container_paths=["/data/filler/a", "/data/filler/b"],
            scan=True,
        )
        self.assertTrue(result["ok"])
        client.update_media_source.assert_not_called()
        client.scan_library.assert_not_called()

    def test_ensure_local_filler_source_force_scan(self) -> None:
        from projectionist.live_channels.filler import ensure_local_filler_source

        client = MagicMock()
        client.list_media_sources.return_value = [
            {
                "id": "local-1",
                "type": "local",
                "name": "Projectionist Fillers",
                "paths": ["/data/filler/a"],
            }
        ]
        client.list_media_source_libraries.return_value = [
            {"id": "lib-f", "name": "Fillers", "enabled": True}
        ]
        result = ensure_local_filler_source(
            client,
            container_paths=["/data/filler/a"],
            scan=True,
            force_scan=True,
        )
        self.assertTrue(result["ok"])
        client.update_media_source.assert_not_called()
        client.scan_library.assert_called_once_with("local-1", "lib-f", force=True)

    def test_ensure_local_filler_source_update_includes_id(self) -> None:
        from projectionist.live_channels.filler import ensure_local_filler_source

        client = MagicMock()
        client.list_media_sources.return_value = [
            {
                "id": "local-1",
                "type": "local",
                "name": "Projectionist Fillers",
                "paths": ["/data/filler/old"],
            }
        ]
        client.list_media_source_libraries.return_value = [
            {"id": "lib-f", "name": "Fillers", "enabled": True}
        ]
        result = ensure_local_filler_source(
            client,
            container_paths=["/data/filler/a"],
            scan=True,
        )
        self.assertTrue(result["paths_changed"])
        msid, body = client.update_media_source.call_args.args
        self.assertEqual(msid, "local-1")
        self.assertEqual(body["id"], "local-1")
        self.assertEqual(body["paths"], ["/data/filler/a"])
        client.scan_library.assert_called_once()

    def test_ensure_media_libraries_skips_scan_when_already_enabled(self) -> None:
        from projectionist.live_channels.publish import ensure_media_libraries_enabled

        client = MagicMock()
        client.list_media_sources.return_value = [{"id": "ms-1", "type": "plex"}]
        client.list_media_source_libraries.return_value = [
            {
                "id": "lib-m",
                "name": "Movies",
                "mediaType": "movies",
                "externalKey": "1",
                "enabled": True,
            }
        ]
        settings = Settings(plex_movie_section="1", plex_tv_section="2")
        result = ensure_media_libraries_enabled(
            client, media_source_id="ms-1", scan=True, settings=settings
        )
        self.assertEqual(len(result["enabled"]), 1)
        client.scan_library.assert_not_called()
        ensure_media_libraries_enabled(
            client,
            media_source_id="ms-1",
            scan=True,
            force_scan=True,
            settings=settings,
        )
        client.scan_library.assert_called_once()

    def test_ensure_media_libraries_disables_unconfigured_enabled(self) -> None:
        from projectionist.live_channels.publish import ensure_media_libraries_enabled

        client = MagicMock()
        client.list_media_source_libraries.return_value = [
            {
                "id": "lib-m",
                "name": "Movies",
                "mediaType": "movies",
                "externalKey": "1",
                "enabled": True,
            },
            {
                "id": "lib-magic",
                "name": "Magical Media",
                "mediaType": "movies",
                "externalKey": "7",
                "enabled": True,
            },
        ]
        settings = Settings(plex_movie_section="1", plex_tv_section="2")
        result = ensure_media_libraries_enabled(
            client, media_source_id="ms-1", scan=False, settings=settings
        )
        self.assertEqual({row["name"] for row in result["enabled"]}, {"Movies"})
        disable_calls = [
            c for c in client.set_library_enabled.call_args_list if c.args[2:] == () and c.kwargs.get("enabled") is False
            or (len(c.args) >= 3 and c.args[2] is False)
            or c.kwargs.get("enabled") is False
        ]
        # Prefer kwargs form used by production code: enabled=False
        found = False
        for c in client.set_library_enabled.call_args_list:
            args, kwargs = c
            if args[:2] == ("ms-1", "lib-magic") and kwargs.get("enabled") is False:
                found = True
        self.assertTrue(found, client.set_library_enabled.call_args_list)

    def test_ensure_media_libraries_skips_unconfigured_sections(self) -> None:
        from projectionist.live_channels.publish import ensure_media_libraries_enabled

        client = MagicMock()
        client.list_media_source_libraries.return_value = [
            {
                "id": "lib-m",
                "name": "Movies",
                "mediaType": "movies",
                "externalKey": "1",
                "enabled": False,
            },
            {
                "id": "lib-tv",
                "name": "TV Shows",
                "mediaType": "shows",
                "externalKey": "2",
                "enabled": False,
            },
            {
                "id": "lib-magic",
                "name": "Magical Media",
                "mediaType": "movies",
                "externalKey": "7",
                "enabled": False,
            },
        ]
        settings = Settings(plex_movie_section="1", plex_tv_section="2")
        result = ensure_media_libraries_enabled(
            client, media_source_id="ms-1", scan=True, settings=settings
        )
        enabled_names = {row["name"] for row in result["enabled"]}
        self.assertEqual(enabled_names, {"Movies", "TV Shows"})
        skipped = {row["name"] for row in result["skipped"]}
        self.assertEqual(skipped, {"Magical Media"})
        enabled_ids = {c.args[1] for c in client.set_library_enabled.call_args_list}
        self.assertEqual(enabled_ids, {"lib-m", "lib-tv"})

    def test_ensure_continuity_filler_list_unions_and_shuffles(self) -> None:

        from projectionist.live_channels.filler import ensure_continuity_filler_list

        client = MagicMock()
        client.list_filler_lists.return_value = []
        client.list_media_sources.return_value = []
        client.create_media_source.return_value = {"id": "local-1"}
        client.list_media_source_libraries.return_value = [
            {"id": "lib-f", "name": "Fillers", "enabled": True}
        ]
        client.list_library_programs.return_value = [
            {
                "type": "content",
                "id": f"s{i}",
                "duration": 30_000 + i * 1000,
                "program": {"uuid": f"s{i}", "title": f"Short {i}", "type": "other_video"},
            }
            for i in range(5)
        ]
        client.create_filler_list.return_value = {"id": "fl-1"}
        settings = Settings(
            tunarr=TunarrSettings(
                filler_binds=["/mnt/a:/data/filler/a:ro", "/mnt/b:/data/filler/b:ro"]
            )
        )
        rng = __import__("random").Random(0)
        result = ensure_continuity_filler_list(
            client, settings, shuffle=True, rng=rng, scan=True
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["filler_list_id"], "fl-1")
        self.assertEqual(result["program_count"], 5)
        body = client.create_filler_list.call_args.args[0]
        ids = [row["id"] for row in body["programs"]]
        self.assertEqual(sorted(ids), ["s0", "s1", "s2", "s3", "s4"])
        # Seeded shuffle is deterministic and not path-order identity.
        self.assertNotEqual(ids, ["s0", "s1", "s2", "s3", "s4"])

    def test_pad_lineup_caps_flex_at_15_minutes(self) -> None:
        from projectionist.live_channels.filler import pad_lineup_with_flex
        from projectionist.live_channels.publish import programming_body_for_recipe

        # 22-minute commercial-cut episode starting on the hour → 8 min flex to :30.
        lined = pad_lineup_with_flex(
            [{"type": "content", "id": "ep1", "duration": 22 * 60 * 1000}],
            max_flex_ms=15 * 60 * 1000,
            start_time_ms=0,
        )
        self.assertEqual(lined[0]["type"], "content")
        self.assertEqual(lined[1]["type"], "flex")
        self.assertEqual(lined[1]["duration"], 8 * 60 * 1000)
        self.assertLessEqual(lined[1]["duration"], 15 * 60 * 1000)

        # Gap larger than cap is skipped (do not insert oversized flex).
        long = pad_lineup_with_flex(
            [{"type": "content", "id": "ep1", "duration": 10 * 60 * 1000}],
            max_flex_ms=5 * 60 * 1000,
            start_time_ms=0,
        )
        self.assertEqual(len(long), 1)

        body = programming_body_for_recipe(
            ChannelRecipe(name="TV", number=100, source="chaos", media_scope="tv"),
            programs=[{"id": "ep1", "duration": 22 * 60 * 1000}],
            pad_lineups=True,
            max_flex_ms=15 * 60 * 1000,
            start_time_ms=0,
        )
        flexes = [row for row in body["lineup"] if row["type"] == "flex"]
        self.assertEqual(len(flexes), 1)
        self.assertLessEqual(flexes[0]["duration"], 15 * 60 * 1000)

    def test_media_scope_filters_movies_from_tv_recipe(self) -> None:
        from projectionist.live_channels.publish import collect_programs_for_recipe

        client = MagicMock()
        catalog = [
            {
                "type": "content",
                "id": "m1",
                "duration": 5_400_000,
                "program": {"uuid": "m1", "title": "Heat", "type": "movie"},
            },
            {
                "type": "content",
                "id": "e1",
                "duration": 1_320_000,
                "program": {"uuid": "e1", "title": "Pilot", "type": "episode"},
            },
        ]
        recipe = ChannelRecipe(
            name="TV Only",
            number=100,
            source="chaos",
            programming_mode=ProgrammingMode.CHAOS,
            media_scope="tv",
        )
        picked = collect_programs_for_recipe(client, recipe, catalog=catalog, media_scope="tv")
        self.assertEqual([p["id"] for p in picked], ["e1"])
        movies = ChannelRecipe(
            name="Movies",
            number=101,
            source="chaos",
            programming_mode=ProgrammingMode.CHAOS,
            media_scope="movies",
        )
        picked_m = collect_programs_for_recipe(
            client, movies, catalog=catalog, media_scope="movies"
        )
        self.assertEqual([p["id"] for p in picked_m], ["m1"])

    def test_repair_jumpstart_attaches_continuity(self) -> None:
        from projectionist.live_channels.filler import repair_jumpstart_stations

        client = MagicMock()
        client.list_channels.return_value = [
            {
                "id": "ch-m",
                "name": "Mystery",
                "number": 100,
                "transcodeConfigId": "tc-1",
                "duration": 0,
                "startTime": 1,
                "offline": {"mode": "pic"},
                "icon": {"path": "", "width": 0, "duration": 0, "position": "bottom-right"},
            }
        ]
        client.update_channel.return_value = {"id": "ch-m"}
        settings = Settings(tunarr=TunarrSettings())
        with patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value={
                "ok": True,
                "ready": True,
                "filler_list_id": "fl-1",
                "program_count": 3,
                "message": "ready",
            },
        ), patch(
            "projectionist.live_channels.publish.refill_channel_lineup",
            return_value={
                "ok": True,
                "program_count": 10,
                "padded": True,
            },
        ), patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={"ok": True, "count_aligned": 1, "count_warmed_ok": 1},
        ):
            result = repair_jumpstart_stations(client, settings, refill_lineups=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["count_attached"], 1)
        put_body = client.update_channel.call_args.args[1]
        self.assertEqual(put_body["fillerCollections"][0]["id"], "fl-1")
        self.assertIn("Up next", put_body["guideFlexTitle"])

        # Idempotent: already attached → no second PUT when force=False path.
        client.list_channels.return_value = [
            {
                "id": "ch-m",
                "name": "Mystery",
                "number": 100,
                "transcodeConfigId": "tc-1",
                "duration": 0,
                "startTime": 1,
                "fillerCollections": [{"id": "fl-1", "weight": 100, "cooldownSeconds": 1800}],
                "guideFlexTitle": "Mystery · Up next",
                "offline": {"mode": "pic"},
                "icon": {"path": "", "width": 0, "duration": 0, "position": "bottom-right"},
            }
        ]
        client.update_channel.reset_mock()
        with patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value={
                "ok": True,
                "ready": True,
                "filler_list_id": "fl-1",
                "program_count": 3,
                "message": "ready",
            },
        ), patch(
            "projectionist.live_channels.publish.refill_channel_lineup",
            return_value={"ok": True, "program_count": 10, "padded": False},
        ), patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={"ok": True},
        ):
            again = repair_jumpstart_stations(client, settings, refill_lineups=False)
        self.assertIn("ch-m", again["already_ok"])
        client.update_channel.assert_not_called()

    def test_enrich_channels_fetches_filler_collections(self) -> None:
        from projectionist.live_channels.filler import (
            continuity_installation_status,
            enrich_channels_with_filler_collections,
        )

        client = MagicMock()
        client.list_channels.return_value = [
            {"id": "ch-1", "name": "Mystery", "number": 100},
            {
                "id": "ch-2",
                "name": "Chaos",
                "number": 102,
                "fillerCollections": [{"id": "fl-1", "weight": 100}],
            },
        ]
        client.get_channel.return_value = {
            "id": "ch-1",
            "fillerCollections": [{"id": "fl-1", "weight": 100}],
            "guideFlexTitle": "Mystery · Up next",
        }
        client.list_filler_lists.return_value = [
            {"id": "fl-1", "name": "Projectionist Continuity", "contentCount": 80}
        ]
        client.get_filler_list_programs.return_value = [
            {"duration": 60_000},
            {"duration": 60_000},
        ]
        enriched = enrich_channels_with_filler_collections(
            client, client.list_channels.return_value
        )
        self.assertEqual(len(enriched[0]["fillerCollections"]), 1)
        client.get_channel.assert_called_once_with("ch-1")

        status = continuity_installation_status(client, Settings(tunarr=TunarrSettings()))
        self.assertEqual(status["attached_count"], 2)
        self.assertEqual(status["station_count"], 2)
        self.assertTrue(status["ok"])

    def test_continuity_progress_store_phases(self) -> None:
        from projectionist.live_channels.continuity_progress import (
            build_continuity_job_status,
            progress_store,
            reset_progress_for_tests,
            start_continuity_repair_job,
        )

        reset_progress_for_tests()
        store = progress_store()
        self.assertTrue(store.begin(mode="repair"))
        self.assertFalse(store.begin(mode="repair"))
        store.set_phase("scanning_filler", "Scanning")
        snap = build_continuity_job_status()
        self.assertEqual(snap["phase"], "scanning_filler")
        self.assertTrue(snap["busy"])
        store.set_done("All good", result={"ok": True})
        snap = build_continuity_job_status()
        self.assertEqual(snap["phase"], "done")
        self.assertFalse(snap["busy"])
        reset_progress_for_tests()
        done = threading.Event()

        def runner() -> None:
            progress_store().set_done("ok", result={"ok": True})
            done.set()

        accepted = start_continuity_repair_job(runner, mode="rescan")
        self.assertTrue(accepted["accepted"])
        self.assertTrue(done.wait(timeout=2))
        reset_progress_for_tests()

        failed = threading.Event()

        def boom() -> None:
            failed.set()
            raise RuntimeError("async boom")

        accepted = start_continuity_repair_job(boom, mode="repair")
        self.assertTrue(accepted["accepted"])
        self.assertTrue(failed.wait(timeout=2))
        deadline = time.time() + 2
        snap = progress_store().snapshot()
        while time.time() < deadline and snap.get("busy"):
            time.sleep(0.02)
            snap = progress_store().snapshot()
        self.assertEqual(snap.get("phase"), "error", snap)
        self.assertFalse(snap.get("busy"), snap)
        reset_progress_for_tests()

    def test_docker_includes_filler_binds_without_dropping_media(self) -> None:
        life = TunarrDockerLifecycle(
            socket_path="/tmp/fake.sock",
            orchestration=True,
            media_binds=["/mnt/user/data/media:/data/media:ro"],
            filler_binds=["/mnt/user/bumpers:/data/filler/bumpers:ro"],
        )
        create_bodies: list[dict] = []

        def fake_request(method, path, **kwargs):
            if method == "GET" and path.startswith("/containers/json"):
                return 200, []
            if method == "GET" and path.endswith("/json"):
                return 404, None
            if method == "POST" and path.startswith("/containers/create"):
                create_bodies.append(kwargs.get("json_body") or {})
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
            result = life.start(config_volume="/tmp/tunarr-vol")
        self.assertTrue(result.ok)
        binds = (create_bodies[0].get("HostConfig") or {}).get("Binds") or []
        self.assertIn("/mnt/user/data/media:/data/media:ro", binds)
        self.assertIn("/mnt/user/bumpers:/data/filler/bumpers:ro", binds)


class CollectionIdMatchTests(unittest.TestCase):
    """ratingKey → Tunarr externalKey matching + honest publish feedback."""

    def _catalog(self) -> list[dict]:
        return [
            {
                "id": "u1",
                "duration": 5_400_000,
                "program": {
                    "uuid": "u1",
                    "title": "Enter the Dragon",
                    "type": "movie",
                    "externalKey": "plex|ms1|1001",
                },
            },
            {
                "id": "u2",
                "duration": 6_000_000,
                "program": {
                    "uuid": "u2",
                    "title": "The Matrix",
                    "type": "movie",
                    "externalKey": "1002",
                },
            },
            {
                "id": "u3",
                "duration": 7_000_000,
                "program": {
                    "uuid": "u3",
                    "title": "Random Pad",
                    "type": "movie",
                    "externalKey": "9999",
                },
            },
        ]

    def test_id_first_match_no_library_pad(self) -> None:
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        recipe = ChannelRecipe(
            name="Martial Arts",
            number=105,
            source="collection",
            programming_mode=ProgrammingMode.SEQUENTIAL,
            collection_id="55",
            item_hints=("Enter the Dragon", "The Matrix"),
            item_rating_keys=("1001", "1002"),
        )
        stats: dict = {}
        picked = collect_programs_for_recipe(
            client, recipe, catalog=self._catalog(), match_stats=stats
        )
        self.assertEqual([p["title"] for p in picked], ["Enter the Dragon", "The Matrix"])
        self.assertEqual(stats["matched"], 2)
        self.assertEqual(stats["match_total"], 2)
        # Must not pad with Random Pad when IDs resolve.
        self.assertNotIn("Random Pad", [p["title"] for p in picked])

    def test_shuffle_randomizes_id_pool(self) -> None:
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        # Larger pool so shuffle is observable across many seeds.
        catalog = []
        keys = []
        for i in range(12):
            kid = str(2000 + i)
            keys.append(kid)
            catalog.append(
                {
                    "id": f"p{i}",
                    "duration": 5_000_000 + i,
                    "program": {
                        "uuid": f"p{i}",
                        "title": f"Title {i}",
                        "type": "movie",
                        "externalKey": kid,
                    },
                }
            )
        recipe = ChannelRecipe(
            name="Pool",
            number=106,
            source="collection",
            programming_mode=ProgrammingMode.SHUFFLE,
            item_rating_keys=tuple(keys),
        )
        orders = set()
        for _ in range(20):
            picked = collect_programs_for_recipe(client, recipe, catalog=catalog)
            orders.add(tuple(p["id"] for p in picked))
        self.assertGreater(len(orders), 1)

    def test_match_feedback_note_copy(self) -> None:
        from projectionist.live_channels.publish import match_feedback_note

        note = match_feedback_note(matched=12, match_total=14, program_count=12)
        self.assertIn("Matched 12/14", note)
        self.assertIn("lineup 12 program", note)
        self.assertNotIn("real titles", note)

    def test_refill_uses_stored_collection_recipe(self) -> None:
        from projectionist.config_store import Settings, TunarrSettings
        from projectionist.live_channels.publish import (
            recipe_from_station_meta,
            set_station_meta,
        )
        from projectionist.live_channels.recipes import ProgrammingMode

        settings = Settings(tunarr=TunarrSettings())
        set_station_meta(
            settings,
            "ch-1",
            media_scope="movies",
            collection_id="55",
            collection_title="Martial Arts",
            programming_mode="shuffle",
            source="collection",
        )
        recipe = recipe_from_station_meta(settings, "ch-1", name="Martial Arts", number=105)
        assert recipe is not None
        self.assertEqual(recipe.source, "collection")
        self.assertEqual(recipe.collection_id, "55")
        self.assertEqual(recipe.programming_mode, ProgrammingMode.SHUFFLE)

    def test_repair_skips_chaos_wipe_when_lineup_already_filled(self) -> None:
        """Continuity repair must not Chaos-refill a station that already has programs."""
        from projectionist.config_store import Settings, TunarrSettings
        from projectionist.live_channels.filler import repair_jumpstart_stations

        client = MagicMock()
        client.list_channels.return_value = [
            {
                "id": "ch-gilligan",
                "name": "Gilligan's Island",
                "number": 105,
                "programCount": 30,
                "duration": 80_000_000,
                "transcodeConfigId": "tc-1",
                "startTime": 1,
                "offline": {"mode": "pic"},
                "icon": {"path": "", "width": 0, "duration": 0, "position": "bottom-right"},
            }
        ]
        client.update_channel.return_value = {"id": "ch-gilligan"}
        settings = Settings(tunarr=TunarrSettings())
        with patch(
            "projectionist.live_channels.filler.ensure_continuity_filler_list",
            return_value={
                "ok": True,
                "ready": True,
                "filler_list_id": "fl-1",
                "program_count": 3,
                "message": "ready",
            },
        ), patch(
            "projectionist.live_channels.publish.refill_channel_lineup",
        ) as refill_mock, patch(
            "projectionist.live_channels.publish.prepare_channels_for_playback",
            return_value={"ok": True},
        ):
            repair_jumpstart_stations(client, settings, refill_lineups=True)
        refill_mock.assert_not_called()

    def test_collect_expands_show_rating_key_via_descendants(self) -> None:
        """Plex show collection children must expand to Tunarr episode descendants."""
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        client.list_library_programs.return_value = []
        client.search_programs.return_value = {
            "results": [
                {
                    "type": "show",
                    "title": "Gilligan's Island",
                    "uuid": "show-uuid-1",
                    "externalKey": "185565",
                    "identifiers": [
                        {"type": "plex", "id": "185565", "sourceId": "src"}
                    ],
                }
            ]
        }
        client.list_program_descendants.return_value = [
            {
                "type": "content",
                "id": "ep-1",
                "duration": 1_500_000,
                "program": {
                    "uuid": "ep-1",
                    "type": "episode",
                    "title": "Two on a Raft",
                    "identifiers": [{"type": "plex", "id": "185567", "sourceId": "src"}],
                },
            },
            {
                "type": "content",
                "id": "ep-2",
                "duration": 1_500_000,
                "program": {
                    "uuid": "ep-2",
                    "type": "episode",
                    "title": "Home Sweet Hut",
                    "identifiers": [{"type": "plex", "id": "185568", "sourceId": "src"}],
                },
            },
        ]
        recipe = ChannelRecipe(
            name="Gilligan's Island",
            number=105,
            source="collection",
            programming_mode=ProgrammingMode.SEQUENTIAL,
            collection_id="99",
            collection_title="Gilligan's Island",
            item_hints=("Gilligan's Island",),
            item_rating_keys=("185565",),
        )
        picked = collect_programs_for_recipe(client, recipe, catalog=[], media_scope="tv")
        self.assertEqual([p["id"] for p in picked], ["ep-1", "ep-2"])
        client.list_program_descendants.assert_called_with("show-uuid-1")

    def test_collect_does_not_random_pad_collection_recipes(self) -> None:
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        catalog = [
            {
                "id": f"x{i}",
                "duration": 3_600_000,
                "title": f"Unrelated {i}",
                "type": "movie",
                "genres": [],
            }
            for i in range(20)
        ]
        recipe = ChannelRecipe(
            name="Gilligan's Island",
            number=105,
            source="collection",
            programming_mode=ProgrammingMode.SEQUENTIAL,
            collection_id="99",
            collection_title="Gilligan's Island",
            item_hints=("Gilligan's Island",),
            item_rating_keys=(),
        )
        client.search_programs.return_value = {"results": []}
        picked = collect_programs_for_recipe(
            client, recipe, catalog=catalog, media_scope="both"
        )
        # Without a resolvable show, return empty — never pad with Unrelated movies.
        self.assertEqual(picked, [])

    def test_collect_full_run_show_exceeds_soft_thirty(self) -> None:
        """Show expand must return the full episode pool, not truncate at ~30."""
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        client.list_library_programs.return_value = []
        client.search_programs.return_value = {
            "results": [
                {
                    "type": "show",
                    "title": "Gilligan's Island",
                    "uuid": "show-uuid-full",
                    "externalKey": "185565",
                    "identifiers": [
                        {"type": "plex", "id": "185565", "sourceId": "src"}
                    ],
                }
            ]
        }
        episodes = [
            {
                "type": "content",
                "id": f"ep-{i}",
                "duration": 1_500_000,
                "program": {
                    "uuid": f"ep-{i}",
                    "type": "episode",
                    "title": f"Episode {i}",
                    "identifiers": [
                        {"type": "plex", "id": str(200000 + i), "sourceId": "src"}
                    ],
                },
            }
            for i in range(1, 61)
        ]
        client.list_program_descendants.return_value = episodes
        recipe = ChannelRecipe(
            name="Gilligan's Island",
            number=105,
            source="collection",
            programming_mode=ProgrammingMode.SHUFFLE,
            collection_id="99",
            collection_title="Gilligan's Island",
            item_hints=("Gilligan's Island",),
            item_rating_keys=("185565",),
        )
        stats: dict = {}
        picked = collect_programs_for_recipe(
            client,
            recipe,
            catalog=[],
            media_scope="tv",
            match_stats=stats,
        )
        self.assertEqual(len(picked), 60)
        self.assertGreater(len(picked), 30)
        self.assertTrue(stats.get("full_run"))
        client.list_program_descendants.assert_called_with("show-uuid-full")


class CraftFiltersTests(unittest.TestCase):
    def test_normalize_decade_and_and_stack(self) -> None:
        from projectionist.live_channels.filters import (
            apply_craft_filters_to_pool,
            normalize_craft_filters,
        )

        craft = normalize_craft_filters(
            {"genres": ["Action"], "decade": "1970s", "themes": ["martial arts"]}
        )
        self.assertEqual(craft.year_from, 1970)
        self.assertEqual(craft.year_to, 1979)
        self.assertEqual(craft.genres, ("Action",))
        pool = [
            {
                "id": "1",
                "duration": 5_000_000,
                "title": "Enter the Dragon",
                "type": "movie",
                "genres": ["Action"],
                "year": 1973,
                "plex_keys": ["100"],
            },
            {
                "id": "2",
                "duration": 5_000_000,
                "title": "Drama Night",
                "type": "movie",
                "genres": ["Drama"],
                "year": 1975,
                "plex_keys": ["101"],
            },
        ]
        # Theme requires library ratingKeys — without them Tunarr-side match fails.
        filtered = apply_craft_filters_to_pool(pool, craft)
        self.assertEqual(filtered, [])
        with_keys = apply_craft_filters_to_pool(
            pool, craft, allowed_rating_keys={"100"}
        )
        self.assertEqual([p["id"] for p in with_keys], ["1"])

    def test_exclusion_skips_rating_keys(self) -> None:
        from projectionist.live_channels.filters import (
            CraftFilters,
            apply_craft_filters_to_pool,
        )

        pool = [
            {
                "id": "1",
                "duration": 5_000_000,
                "title": "Keep",
                "plex_keys": ["10"],
            },
            {
                "id": "2",
                "duration": 5_000_000,
                "title": "Skip",
                "plex_keys": ["99"],
            },
        ]
        out = apply_craft_filters_to_pool(
            pool, CraftFilters(), excluded_rating_keys={"99"}
        )
        self.assertEqual([p["id"] for p in out], ["1"])

    def test_zero_library_craft_matches_yield_empty_pool(self) -> None:
        """Library craft match of 0 must not fall back to the unfiltered Tunarr pool."""
        from projectionist.live_channels.publish import collect_programs_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        client = MagicMock()
        # Tunarr-side genre/year would keep "Enter the Dragon" — that is the leak.
        catalog = [
            {
                "id": "1",
                "duration": 5_000_000,
                "program": {
                    "uuid": "1",
                    "title": "Enter the Dragon",
                    "type": "movie",
                    "genres": ["Action"],
                    "year": 1973,
                    "externalKey": "100",
                },
            },
            {
                "id": "2",
                "duration": 5_000_000,
                "program": {
                    "uuid": "2",
                    "title": "Heat",
                    "type": "movie",
                    "genres": ["Action"],
                    "year": 1995,
                    "externalKey": "101",
                },
            },
        ]
        recipe = ChannelRecipe(
            name="No Library Hits",
            number=130,
            source="chaos",
            programming_mode=ProgrammingMode.SHUFFLE,
            media_scope="movies",
            craft_filters={"genres": ["Action"], "year_from": 1970, "year_to": 1979},
        )
        mock_jm = MagicMock()
        mock_jm.db = object()
        with (
            patch(
                "projectionist.web.jobs.get_job_manager",
                return_value=mock_jm,
            ),
            patch(
                "projectionist.live_channels.filters.library_items_matching_filters",
                return_value={"total_matched": 0, "items": [], "rating_keys": []},
            ),
            patch(
                "projectionist.live_channels.filters.exclusion_rating_keys",
                return_value=set(),
            ),
        ):
            picked = collect_programs_for_recipe(
                client, recipe, catalog=catalog, media_scope="movies"
            )
        self.assertEqual(picked, [])

    def test_shuffle_programming_uses_random_slots(self) -> None:
        from projectionist.live_channels.publish import programming_body_for_recipe
        from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

        recipe = ChannelRecipe(
            name="70s Action",
            number=120,
            source="chaos",
            programming_mode=ProgrammingMode.SHUFFLE,
        )
        body = programming_body_for_recipe(
            recipe,
            programs=[
                {
                    "id": "m1",
                    "duration": 5_400_000,
                    "title": "Heat",
                    "type": "movie",
                },
                {
                    "id": "m2",
                    "duration": 7_200_000,
                    "title": "Alien",
                    "type": "movie",
                },
            ],
            pad_lineups=True,
            max_flex_ms=0,
        )
        self.assertEqual(body["type"], "random")
        self.assertEqual(body["programs"], ["m1", "m2"])
        self.assertEqual(body["schedule"]["type"], "random")
        self.assertTrue(
            any(slot.get("type") == "movie" for slot in body["schedule"]["slots"])
        )

    def test_recipe_persists_craft_filters(self) -> None:
        from projectionist.live_channels.recipes import recipe_from_mapping

        recipe = recipe_from_mapping(
            {
                "name": "Martial Arts 70s",
                "number": 121,
                "source": "motif",
                "motif": "martial arts",
                "media_scope": "movies",
                "craft_filters": {
                    "genres": ["Action"],
                    "decade": 1970,
                    "themes": ["martial arts"],
                },
            }
        )
        payload = recipe.to_dict()
        self.assertEqual(payload["craft_filters"]["genres"], ["Action"])
        self.assertEqual(payload["craft_filters"]["year_from"], 1970)
        self.assertIn("martial arts", payload["craft_filters"]["motifs"])

    def test_schedule_slots_client(self) -> None:
        from projectionist.connectors.tunarr import TunarrClient

        client = TunarrClient("http://tunarr.test:8000")
        with patch(
            "projectionist.connectors.tunarr.request_json",
            return_value={"lineup": [], "seed": [1], "discardCount": 0, "startTime": 1},
        ) as req:
            result = client.schedule_slots(
                "ch-1",
                {
                    "type": "random",
                    "flexPreference": "end",
                    "maxDays": 1,
                    "padMs": 0,
                    "padStyle": "slot",
                    "randomDistribution": "uniform",
                    "lockWeights": False,
                    "slots": [],
                },
            )
        self.assertEqual(result["seed"], [1])
        self.assertIn("/channels/ch-1/schedule-slots", req.call_args.args[0])


class StationRefreshTests(unittest.TestCase):
    def test_refresh_skips_when_disabled(self) -> None:
        from projectionist.live_channels.publish import refresh_stations_with_stored_recipes

        settings = Settings(features=FeatureFlags(live_channels_enabled=False))
        result = refresh_stations_with_stored_recipes(MagicMock(), settings=settings)
        self.assertTrue(result.get("skipped"))


if __name__ == "__main__":
    unittest.main()
