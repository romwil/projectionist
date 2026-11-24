"""Owner quality ceiling. The tests do not start a library encode."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.engine.playability import LibraryTitle, build_playability_report, save_playability_report
from projectionist.engine.planner import plan_playback
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import SAFARI
from projectionist.engine.quality import (
    LIST_TITLE,
    above_quality_target,
    load_replaced_titles,
    mark_title_replaced,
)
from projectionist.engine.source import MediaAsset, write_location
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache

_ZONE = ZoneInfo("America/New_York")


def _when(hour: int) -> datetime:
    return datetime(2026, 11, 22, hour, 0, tzinfo=_ZONE)


def _video(codec: str, width: int, height: int) -> ProbeResult:
    return ProbeResult(
        "mkv",
        "matroska",
        600.0,
        8_000_000,
        4_000_000_000,
        [
            MediaStream(
                index=0,
                codec_type="video",
                codec=codec,
                width=width,
                height=height,
                level="41",
            ),
            MediaStream(index=1, codec_type="audio", codec="aac", language="eng", channels=2),
        ],
    )


def _asset(key: str, codec: str, width: int, height: int, path: Path) -> MediaAsset:
    return MediaAsset(
        rating_key=key,
        source_path=str(path),
        local_path=str(path),
        readable=True,
        probe=_video(codec, width, height),
    )


class QualityCeilingTests(unittest.TestCase):
    def test_the_ceiling_defaults_to_1080p(self) -> None:
        self.assertEqual(Settings().engine.quality_ceiling, "1080p")
        blank = Settings.from_mapping({"engine": {}})
        self.assertEqual(blank.engine.quality_ceiling, "1080p")
        kept = Settings.from_mapping({"engine": {"quality_ceiling": "720p"}})
        self.assertEqual(kept.engine.quality_ceiling, "720p")
        four_k = Settings.from_mapping({"engine": {"quality_ceiling": "4k"}})
        self.assertEqual(four_k.engine.quality_ceiling, "2160p")
        unknown = Settings.from_mapping({"engine": {"quality_ceiling": "original"}})
        self.assertEqual(unknown.engine.quality_ceiling, "1080p")

    def test_the_list_names_each_title_above_the_target_and_counts_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wide = root / "wide.mkv"
            hd = root / "hd.mkv"
            wide.write_bytes(b"wide")
            hd.write_bytes(b"hd")
            titles = [
                LibraryTitle("wide", "Wide Picture", "en", file_size=8_000_000_000),
                LibraryTitle("hd", "Plain Feature", "en", file_size=1_500_000_000),
            ]
            report = build_playability_report(
                titles,
                {
                    "wide": _asset("wide", "hevc", 3840, 2160, wide),
                    "hd": _asset("hd", "h264", 1920, 1080, hd),
                },
                [SAFARI],
                settings=Settings(),
                data_dir=root,
            )
        blob = json.dumps(report)
        self.assertNotIn(str(wide), blob)
        self.assertNotIn("local_path", blob)
        listing = above_quality_target(
            report,
            ceiling="1080p",
            paths={"wide": str(wide), "hd": str(hd)},
        )
        self.assertEqual(listing["title"], LIST_TITLE)
        self.assertEqual(listing["ceiling"], "1080p")
        self.assertEqual(listing["count"], 1)
        self.assertEqual(len(listing["titles"]), 1)
        row = listing["titles"][0]
        self.assertEqual(row["title"], "Wide Picture")
        self.assertEqual(row["resolution"], "3840×2160")
        self.assertEqual(row["codec"], "hevc")
        self.assertEqual(row["file_size"], 8_000_000_000)
        self.assertEqual(row["path"], str(wide))
        self.assertEqual(
            above_quality_target(report, ceiling="2160p", paths={"wide": str(wide)})["count"],
            0,
        )
        raised = above_quality_target(report, ceiling="720p", paths={"hd": str(hd), "wide": str(wide)})
        self.assertEqual(raised["count"], 2)
        self.assertEqual([item["rating_key"] for item in raised["titles"]], ["hd", "wide"])

    def test_a_marked_title_leaves_the_list_and_the_planner_treats_it_as_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "wide.mkv"
            copy = root / "wide.mp4"
            source.write_bytes(b"source")
            copy.write_bytes(b"copy")
            film = _asset("wide", "vp9", 3840, 2160, source)
            ready = MediaAsset(
                rating_key="wide",
                local_path=str(copy),
                readable=True,
                probe=_video("h264", 1920, 1080),
            )
            report = build_playability_report(
                [LibraryTitle("wide", "Wide Picture", "en", file_size=1000)],
                {"wide": film},
                [SAFARI],
                settings=Settings(),
                data_dir=root,
            )
            before = above_quality_target(report, ceiling="1080p", paths={"wide": str(source)})
            self.assertEqual(before["count"], 1)
            saved = mark_title_replaced(root, "wide")
            self.assertEqual(saved, ["wide"])
            self.assertEqual(load_replaced_titles(root), ["wide"])
            after = above_quality_target(
                report,
                ceiling="1080p",
                replaced=saved,
                paths={"wide": str(source)},
            )
        self.assertEqual(after["count"], 0)
        self.assertEqual(after["titles"], [])
        marked = plan_playback(film, SAFARI, ready_copy=ready, replaced=True)
        self.assertTrue(marked["replaced"])
        self.assertFalse(marked["above_target"])
        self.assertTrue(marked["from_copy"])
        self.assertIn(marked["plan"], {"direct", "remux"})
        without_copy = plan_playback(film, SAFARI, replaced=True)
        self.assertTrue(without_copy["replaced"])
        self.assertFalse(without_copy["above_target"])
        self.assertFalse(without_copy.get("from_copy"))
        untouched = plan_playback(film, SAFARI)
        self.assertNotIn("replaced", untouched)
        self.assertNotIn("above_target", untouched)

    def test_make_a_1080p_copy_uses_the_existing_copy_path_for_one_title(self) -> None:
        from projectionist.engine.copies import _ffmpeg_args, remember_copy_request, run_copy_pass
        from projectionist.engine.media_slot import media_command

        calls: list[list[str]] = []

        def runner(command: list[str], destination: Path) -> str:
            calls.append(command)
            destination.write_bytes(b"done")
            return "complete"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "wide.mkv"
            source.write_bytes(b"source")
            output = root / "copies"
            output.mkdir()
            saved = remember_copy_request(root, "wide")
            self.assertEqual(saved, ["wide"])
            part = output / "wide.part"
            with patch("projectionist.engine.media_slot.shutil.which", return_value="/usr/bin/nice"):
                result = run_copy_pass(
                    [
                        {
                            "rating_key": "wide",
                            "title": "Wide Picture",
                            "requested": True,
                            "file_size": 40,
                        },
                        {
                            "rating_key": "other",
                            "title": "Other",
                            "file_size": 40,
                        },
                    ],
                    output,
                    budget_bytes=10_000,
                    now=_when(2),
                    runner=runner,
                    source_for=lambda _key: source,
                )
                expected = media_command(_ffmpeg_args(source, part))
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["rating_key"], "wide")
            self.assertTrue(result["ready"])
            self.assertEqual(calls[0], expected)
            self.assertIn("libx264", calls[0])
            self.assertTrue((output / "wide.mp4").is_file())
            self.assertFalse((output / "other.mp4").exists())


def _report() -> dict:
    return {
        "generated_at": "t",
        "complete": True,
        "message": "",
        "title_count": 2,
        "profiles": [
            {
                "profile": "safari",
                "titles": [
                    {
                        "rating_key": "wide",
                        "title": "Wide Picture",
                        "width": 3840,
                        "height": 2160,
                        "video_codec": "hevc",
                        "file_size": 8_000_000_000,
                    },
                    {
                        "rating_key": "hd",
                        "title": "Plain Feature",
                        "width": 1920,
                        "height": 1080,
                        "video_codec": "h264",
                        "file_size": 1_500_000_000,
                    },
                ],
            }
        ],
    }


class QualityCeilingRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-quality-ceiling-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": False},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        save_playability_report(self.data_dir, _report())
        media = self.data_dir / "wide.mkv"
        media.write_bytes(b"wide")
        write_location(
            self.data_dir / "engine" / "probes",
            "wide",
            source_path="/plex/wide.mkv",
            local_path=str(media),
        )
        self.media = media

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "DATA_DIR",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_the_owner_can_change_the_ceiling_and_the_report_follows(self) -> None:
        current = self.client.get("/api/playback/quality-ceiling")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json(), {"quality_ceiling": "1080p"})
        report = self.client.get("/api/playback/playability", params={"view": "progress"})
        self.assertEqual(report.status_code, 200)
        body = report.json()
        self.assertEqual(body["quality_ceiling"], "1080p")
        self.assertEqual(body["above_target"]["title"], LIST_TITLE)
        self.assertEqual(body["above_target"]["count"], 1)
        row = body["above_target"]["titles"][0]
        self.assertEqual(row["title"], "Wide Picture")
        self.assertEqual(row["resolution"], "3840×2160")
        self.assertEqual(row["codec"], "hevc")
        self.assertEqual(row["file_size"], 8_000_000_000)
        self.assertEqual(row["path"], str(self.media))
        self.assertNotIn("profiles", body["above_target"])
        saved = self.client.put(
            "/api/playback/quality-ceiling",
            json={"quality_ceiling": "2160p"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["quality_ceiling"], "2160p")
        again = self.client.get("/api/playback/playability", params={"view": "progress"})
        self.assertEqual(again.json()["above_target"]["count"], 0)
        refused = self.client.put(
            "/api/playback/quality-ceiling",
            json={"quality_ceiling": "original"},
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(self.client.get("/api/playback/quality-ceiling").json()["quality_ceiling"], "2160p")

    def test_both_actions_and_a_replaced_title_leaves_the_list(self) -> None:
        from projectionist.engine.copies import load_copy_requests

        listed = self.client.get("/api/playback/playability")
        self.assertEqual(listed.json()["above_target"]["count"], 1)
        queued = self.client.post("/api/playback/quality-target/copy", json={"rating_key": "wide"})
        self.assertEqual(queued.status_code, 200, queued.text)
        self.assertTrue(queued.json()["requested"])
        self.assertEqual(load_copy_requests(self.data_dir), ["wide"])
        self.assertEqual(queued.json()["above_target"]["count"], 1)
        self.assertEqual(list(self.data_dir.rglob("*.mp4")), [])
        marked = self.client.post(
            "/api/playback/quality-target/replaced",
            json={"rating_key": "wide"},
        )
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertTrue(marked.json()["replaced"])
        self.assertEqual(marked.json()["above_target"]["count"], 0)
        self.assertEqual(marked.json()["above_target"]["titles"], [])
        follow = self.client.get("/api/playback/playability", params={"view": "progress"})
        self.assertEqual(follow.json()["above_target"]["count"], 0)
        plan = plan_playback(
            _asset("wide", "vp9", 3840, 2160, self.media),
            SAFARI,
            replaced=True,
        )
        self.assertTrue(plan["replaced"])
        self.assertFalse(plan["above_target"])


class QualityCeilingMemberTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-quality-member-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {
                        "mode": "local",
                        "plex_login_enabled": False,
                        "local_login_enabled": True,
                    },
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        from projectionist.web.auth import _hash_password

        app_mod._db().create_local_user(
            user_id="ada",
            display_name="Ada",
            password_hash=_hash_password("correct-horse"),
            role="member",
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "DATA_DIR",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_a_member_cannot_change_the_ceiling_or_the_list(self) -> None:
        from tests.totp_login import finish_sign_in_code

        login = self.client.post(
            "/api/auth/local/login",
            json={"username": "Ada", "password": "correct-horse"},
        )
        login = finish_sign_in_code(self.client, login, "Ada", "correct-horse")
        self.assertEqual(login.status_code, 200, login.text)
        ceiling = self.client.put(
            "/api/playback/quality-ceiling",
            json={"quality_ceiling": "720p"},
        )
        self.assertEqual(ceiling.status_code, 403, ceiling.text)
        copied = self.client.post("/api/playback/quality-target/copy", json={"rating_key": "wide"})
        self.assertEqual(copied.status_code, 403, copied.text)
        marked = self.client.post(
            "/api/playback/quality-target/replaced",
            json={"rating_key": "wide"},
        )
        self.assertEqual(marked.status_code, 403, marked.text)
        report = self.client.get("/api/playback/playability")
        self.assertEqual(report.status_code, 403, report.text)
