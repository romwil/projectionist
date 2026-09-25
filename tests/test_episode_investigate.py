"""Episode investigation fusion, OSHash, apply, stills, capabilities."""

from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from projectionist.library.admin_execution import reset_admin_execution_for_tests
from projectionist.library.episode_investigate.apply import apply_rows, plex_proper_path, undo_apply
from projectionist.library.episode_investigate.capabilities import (
    FFMPEG_NOTE,
    health_payload,
    llm_accepts_images,
    resolve_ffmpeg,
    resolve_ffprobe,
)
from projectionist.library.episode_investigate.catalog import list_investigate_shows, merge_tmdb_runtimes
from projectionist.library.episode_investigate.filenames import (
    claimed_from_path,
    parse_season_episode,
    plex_proper_name,
)
from projectionist.library.episode_investigate.ffmpeg import extract_stills, probe_runtime_seconds
from projectionist.library.episode_investigate.fusion import default_selected, fuse_row, runtime_matches
from projectionist.library.episode_investigate.oshash import file_oshash, parse_opensubtitles_payload
from projectionist.library.episode_investigate.stills import resolve_still, stills_dir
from projectionist.library.episode_investigate.vision import parse_vision_json, vision_user_prompt
from projectionist.library.db import Database


def _show(**overrides):
    row = {"id": 1, "title": "The Bear", "tmdb_id": 136315, "tvdb_id": 414005}
    row.update(overrides)
    return row


def _catalog():
    return [
        {"season": 1, "episode": 1, "title": "System", "runtime_minutes": 30, "sonarr_episode_id": 11},
        {"season": 1, "episode": 2, "title": "Hands", "runtime_minutes": 31, "sonarr_episode_id": 12},
        {"season": 1, "episode": 7, "title": "Braciole", "runtime_minutes": 47, "sonarr_episode_id": 17},
    ]


class FilenamesTests(unittest.TestCase):
    def test_parse_does_not_treat_scene_as_special(self) -> None:
        self.assertEqual(parse_season_episode("the.bear.s01e07.720p.hdtv.mkv"), (1, 7))
        self.assertEqual(parse_season_episode("The Bear - 1x02 - Hands.mkv"), (1, 2))
        self.assertIsNone(parse_season_episode("random-scene-release.mkv"))
        claimed = claimed_from_path("/tv/The.Bear.S01E07.mkv")
        self.assertFalse(claimed["evidence"])
        self.assertEqual(claimed["label"], "S01E07")

    def test_plex_proper_name(self) -> None:
        name = plex_proper_name("The Bear", 1, 7, "Braciole: Part 2", ext=".mkv")
        self.assertEqual(name, "The Bear - S01E07 - Braciole Part 2.mkv")


class FusionTests(unittest.TestCase):
    def test_runtime_slack(self) -> None:
        self.assertTrue(runtime_matches(30 * 60 + 40, 30))
        self.assertFalse(runtime_matches(47 * 60, 30))

    def test_filename_is_not_used_as_evidence(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=None,
            opensubtitles=None,
            vision=None,
        )
        self.assertEqual(fused["confidence"], "uncertain")
        self.assertFalse(fused["selected_default"])

    def test_two_signals_are_certain(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=47 * 60,
            opensubtitles={"found": True, "season": 1, "episode": 7, "series_title": "The Bear"},
            vision={"scope": "this_series", "season": 1, "episode": 7, "confidence": 0.8},
        )
        self.assertEqual(fused["confidence"], "certain")
        self.assertEqual(fused["proposed"]["episode"], 7)
        self.assertTrue(fused["same_show"])
        self.assertTrue(default_selected("certain"))

    def test_vision_household_is_uncertain_not_applied(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=None,
            opensubtitles=None,
            vision={
                "scope": "household",
                "series_title": "The Studio",
                "season": 1,
                "episode": 1,
                "confidence": 0.9,
            },
            household_titles=["The Studio"],
        )
        self.assertEqual(fused["confidence"], "uncertain")
        self.assertEqual(fused["proposed"]["scope"], "household")
        self.assertFalse(fused["same_show"])
        self.assertFalse(fused["selected_default"])

    def test_unique_runtime_is_likely(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=47 * 60,
            opensubtitles=None,
            vision=None,
        )
        self.assertEqual(fused["confidence"], "likely")
        self.assertEqual(fused["proposed"]["title"], "Braciole")
        self.assertTrue(fused["selected_default"])


class OshashTests(unittest.TestCase):
    def test_hash_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clip.bin"
            head = b"\x01" * 65536
            tail = b"\x02" * 65536
            path.write_bytes(head + b"mid" + tail)
            digest = file_oshash(str(path))
            self.assertEqual(len(digest or ""), 16)
            size = path.stat().st_size
            expected = size
            for chunk in (head, tail):
                for offset in range(0, 65536, 8):
                    expected = (expected + struct.unpack("<Q", chunk[offset : offset + 8])[0]) & 0xFFFFFFFFFFFFFFFF
            self.assertEqual(digest, f"{expected:016x}")

    def test_parse_opensubtitles(self) -> None:
        parsed = parse_opensubtitles_payload(
            {
                "data": [
                    {
                        "attributes": {
                            "feature_details": {
                                "season_number": 1,
                                "episode_number": 7,
                                "title": "Braciole",
                                "parent_title": "The Bear",
                            }
                        }
                    }
                ]
            }
        )
        self.assertEqual(parsed["episode"], 7)
        self.assertEqual(parsed["series_title"], "The Bear")


class VisionParseTests(unittest.TestCase):
    def test_constrained_json(self) -> None:
        parsed = parse_vision_json(
            '```json\n{"scope":"this_series","season":1,"episode":2,"confidence":0.7,"reason":"kitchen"}\n```'
        )
        self.assertEqual(parsed["scope"], "this_series")
        self.assertEqual(parsed["episode"], 2)
        self.assertTrue("this series" in vision_user_prompt(this_series="The Bear", household_shows=["The Studio"]))

    def test_unknown_scope_on_garbage(self) -> None:
        parsed = parse_vision_json("not json")
        self.assertEqual(parsed["scope"], "unknown")


class FfmpegTests(unittest.TestCase):
    def test_probe_parses_duration(self) -> None:
        def runner(*_args, **_kwargs):
            return SimpleNamespace(returncode=0, stdout="1845.2\n", stderr="")

        self.assertEqual(probe_runtime_seconds("/tv/a.mkv", ffprobe="/bin/ffprobe", runner=runner), 1845.2)

    def test_extract_builds_three_outputs(self) -> None:
        calls = []

        def runner(cmd, **_kwargs):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"jpeg")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.mkv"
            src.write_bytes(b"video")
            dest = Path(tmp) / "stills"
            written = extract_stills(
                str(src),
                dest,
                ffmpeg="/bin/ffmpeg",
                runtime_seconds=100,
                runner=runner,
            )
        self.assertEqual(len(written), 3)
        self.assertEqual(len(calls), 3)
        self.assertIn("-ss", calls[0])


class ApplyTests(unittest.TestCase):
    def test_same_show_renames_and_records_undo(self) -> None:
        renamed = []

        def rename(src, dest):
            renamed.append((src, dest))

        def exists(path):
            return path.endswith("mislabel.mkv")

        row = {
            "id": "9",
            "file_id": 9,
            "series_id": 4,
            "path": "/tv/The Bear/Season 01/mislabel.mkv",
            "sonarr": {"episode_id": 11, "season": 1, "episode": 1},
            "proposed": {
                "scope": "this_series",
                "series_title": "The Bear",
                "tmdb_id": 136315,
                "season": 1,
                "episode": 7,
                "title": "Braciole",
                "sonarr_episode_id": 17,
            },
        }
        remaps = []
        result = apply_rows(
            SimpleNamespace(sonarr_url="", sonarr_api_key=""),
            _show(),
            [row],
            ["9"],
            rename=rename,
            exists=exists,
            sonarr_remap=lambda _settings, **kwargs: remaps.append(kwargs) or {"ok": True},
            plex_refresh=lambda _s: None,
        )
        self.assertEqual(result["applied"], 1)
        self.assertTrue(renamed[0][1].endswith("The Bear - S01E07 - Braciole.mkv"))
        self.assertEqual(remaps[0]["target_episode_id"], 17)
        undone = undo_apply(
            SimpleNamespace(),
            result,
            rename=rename,
            exists=lambda path: path.endswith("The Bear - S01E07 - Braciole.mkv"),
            sonarr_remap=lambda _settings, **kwargs: remaps.append(kwargs) or {"ok": True},
            plex_refresh=lambda _s: None,
        )
        self.assertEqual(undone["restored"], 1)

    def test_other_show_is_skipped(self) -> None:
        result = apply_rows(
            SimpleNamespace(),
            _show(),
            [
                {
                    "id": "1",
                    "path": "/tv/x.mkv",
                    "proposed": {
                        "scope": "household",
                        "series_title": "The Studio",
                        "season": 1,
                        "episode": 1,
                    },
                }
            ],
            ["1"],
            rename=lambda *_a: None,
            exists=lambda _p: True,
            sonarr_remap=lambda **_k: {},
            plex_refresh=lambda _s: None,
        )
        self.assertEqual(result["applied"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_plex_proper_path_stays_in_folder(self) -> None:
        dest = plex_proper_path(
            "The Bear",
            {"season": 2, "episode": 1, "title": "Beef"},
            "/tv/The Bear/Season 02/wrong.mkv",
        )
        self.assertEqual(dest, "/tv/The Bear/Season 02/The Bear - S02E01 - Beef.mkv")


class CatalogAndStillsTests(unittest.TestCase):
    def test_list_shows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.upsert_library_items(
                [
                    {
                        "rating_key": "rk-show",
                        "media_type": "show",
                        "title": "The Bear",
                        "year": 2022,
                        "tmdb_id": 136315,
                        "tvdb_id": 414005,
                        "season_count": 3,
                    }
                ]
            )
            items = list_investigate_shows(db)
            self.assertEqual(items[0]["title"], "The Bear")
            self.assertEqual(items[0]["tmdb_id"], 136315)

    def test_merge_tmdb_runtimes(self) -> None:
        merged = merge_tmdb_runtimes(
            [{"season": 1, "episode": 1, "title": "System", "runtime_minutes": None, "sonarr_episode_id": 11}],
            [{"season": 1, "episode": 1, "title": "System", "runtime_minutes": 30, "still_url": "http://x"}],
        )
        self.assertEqual(merged[0]["runtime_minutes"], 30)

    def test_still_path_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dest = stills_dir(root, "abc", "9")
            dest.mkdir(parents=True)
            (dest / "0.jpg").write_bytes(b"x")
            self.assertIsNotNone(resolve_still(root, "abc", "9", "0.jpg"))
            self.assertIsNone(resolve_still(root, "abc", "9", "../0.jpg"))
            self.assertIsNone(resolve_still(root, "../abc", "9", "0.jpg"))


class CapabilitiesTests(unittest.TestCase):
    def test_vision_default_openai(self) -> None:
        self.assertTrue(llm_accepts_images(SimpleNamespace(llm_provider="openai", llm_model="gpt-4o-mini")))
        self.assertTrue(llm_accepts_images(SimpleNamespace(llm_provider="anthropic", llm_model="claude-sonnet-4-6")))
        self.assertFalse(llm_accepts_images(SimpleNamespace(llm_provider="ollama", llm_model="llama3.2")))
        payload = health_payload(
            SimpleNamespace(
                llm_provider="openai",
                llm_model="gpt-4o-mini",
                tmdb_api_key="t",
                sonarr_url="http://sonarr",
                sonarr_api_key="k",
            )
        )
        self.assertTrue(payload["available"])
        self.assertTrue(payload["vision"]["default_on"])
        self.assertTrue(payload["vision"]["leaves_lan"])
        self.assertFalse(payload["acrcloud"]["available"])
        self.assertFalse(payload["acrcloud"]["deferred"])
        self.assertIn("container", FFMPEG_NOTE)
        self.assertIn("FFMPEG_PATH", FFMPEG_NOTE)
        self.assertNotIn("Install a host binary", FFMPEG_NOTE)
        self.assertNotIn("not bundled", FFMPEG_NOTE)

    def test_resolve_uses_path_binaries(self) -> None:
        with patch.dict(os.environ, {"FFMPEG_PATH": "", "FFPROBE_PATH": ""}, clear=False), patch(
            "projectionist.library.episode_investigate.capabilities.shutil.which",
            side_effect=lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
        ):
            self.assertEqual(resolve_ffmpeg(), "/usr/bin/ffmpeg")
            self.assertEqual(resolve_ffprobe(), "/usr/bin/ffprobe")
            payload = health_payload()
            self.assertTrue(payload["ffmpeg"]["available"])
            self.assertEqual(payload["ffmpeg"]["path"], "/usr/bin/ffmpeg")
            self.assertEqual(payload["ffmpeg"]["note"], "")
            self.assertTrue(payload["ffprobe"]["available"])
            self.assertEqual(payload["ffprobe"]["path"], "/usr/bin/ffprobe")

    def test_resolve_prefers_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ffmpeg = Path(tmp) / "custom-ffmpeg"
            ffprobe = Path(tmp) / "custom-ffprobe"
            ffmpeg.write_text("#!/bin/sh\n")
            ffprobe.write_text("#!/bin/sh\n")
            ffmpeg.chmod(0o755)
            ffprobe.chmod(0o755)
            with patch.dict(
                os.environ,
                {"FFMPEG_PATH": str(ffmpeg), "FFPROBE_PATH": str(ffprobe)},
                clear=False,
            ), patch(
                "projectionist.library.episode_investigate.capabilities.shutil.which",
                return_value="/usr/bin/should-not-win",
            ):
                self.assertEqual(resolve_ffmpeg(), str(ffmpeg))
                self.assertEqual(resolve_ffprobe(), str(ffprobe))

    def test_health_note_when_binaries_missing(self) -> None:
        with patch.dict(os.environ, {"FFMPEG_PATH": "", "FFPROBE_PATH": ""}, clear=False), patch(
            "projectionist.library.episode_investigate.capabilities.shutil.which",
            return_value=None,
        ):
            payload = health_payload()
            self.assertFalse(payload["ffmpeg"]["available"])
            self.assertEqual(payload["ffmpeg"]["note"], FFMPEG_NOTE)
            self.assertIn("Image includes ffmpeg", payload["ffmpeg"]["note"])
            self.assertFalse(payload["ffprobe"]["available"])


class JobHappyPathTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_admin_execution_for_tests()

    def test_investigate_one_fuses_without_binaries(self) -> None:
        from projectionist.library.episode_investigate.job import investigate_one

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "The.Bear.S01E01.mkv"
            path.write_bytes(b"not-a-video")
            with patch(
                "projectionist.library.episode_investigate.job.probe_runtime_seconds",
                return_value=47 * 60,
            ), patch(
                "projectionist.library.episode_investigate.job.extract_stills",
                return_value=[],
            ), patch(
                "projectionist.library.episode_investigate.job.file_oshash",
                return_value="abc",
            ), patch(
                "projectionist.library.episode_investigate.job.lookup_opensubtitles",
                return_value={"found": True, "season": 1, "episode": 7, "series_title": "The Bear"},
            ):
                row = investigate_one(
                    SimpleNamespace(llm_provider="ollama", llm_model="llama3", tmdb_api_key=""),
                    _show(),
                    {
                        "id": "9",
                        "file_id": 9,
                        "series_id": 4,
                        "path": str(path),
                        "claimed": claimed_from_path(str(path)),
                        "sonarr": {"season": 1, "episode": 1, "title": "System", "evidence": False},
                    },
                    catalog=_catalog(),
                    use_vision=False,
                    household=["The Bear"],
                    job_id="job1",
                    data_dir=Path(tmp),
                )
        self.assertEqual(row["confidence"], "certain")
        self.assertEqual(row["proposed"]["episode"], 7)
        self.assertFalse(row["claimed"]["evidence"])


class CatalogSonarrTests(unittest.TestCase):
    def test_list_episode_files_filters_season(self) -> None:
        from projectionist.library.episode_investigate.catalog import list_episode_files

        class _Series:
            id = 4
            title = "The Bear"
            tmdb_id = 136315

        class _Client:
            def series_by_tvdb_id(self, _tvdb):
                return _Series()

            def episode_files(self, _series_id):
                return [
                    {"id": 9, "path": "/tv/The Bear/Season 01/a.mkv", "size": 10, "seasonNumber": 1},
                    {"id": 10, "path": "/tv/The Bear/Season 02/b.mkv", "size": 10, "seasonNumber": 2},
                ]

            def episodes(self, _series_id):
                return [
                    {
                        "id": 11,
                        "seasonNumber": 1,
                        "episodeNumber": 1,
                        "title": "System",
                        "episodeFileId": 9,
                        "runtime": 30,
                    },
                    {
                        "id": 21,
                        "seasonNumber": 2,
                        "episodeNumber": 1,
                        "title": "Beef",
                        "episodeFileId": 10,
                        "runtime": 30,
                    },
                ]

        settings = SimpleNamespace(sonarr_url="http://sonarr", sonarr_api_key="k", sonarr_root_folder="/tv")
        inventory = list_episode_files(settings, _show(), season=1, client=_Client())
        self.assertTrue(inventory["ok"])
        self.assertEqual(len(inventory["files"]), 1)
        self.assertEqual(inventory["files"][0]["file_id"], 9)
        self.assertFalse(inventory["files"][0]["claimed"]["evidence"])

    def test_missing_sonarr_is_error(self) -> None:
        from projectionist.library.episode_investigate.catalog import list_episode_files

        inventory = list_episode_files(SimpleNamespace(sonarr_url="", sonarr_api_key=""), _show())
        self.assertFalse(inventory["ok"])


class JobOrchestrationTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_admin_execution_for_tests()

    def test_start_and_apply_and_undo(self) -> None:
        from projectionist.library.episode_investigate.job import (
            start_apply_job,
            start_investigate_job,
            start_undo_job,
        )

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.upsert_library_items(
                [
                    {
                        "rating_key": "rk-bear",
                        "media_type": "show",
                        "title": "The Bear",
                        "tmdb_id": 136315,
                        "tvdb_id": 414005,
                    }
                ]
            )
            show_id = int(db.library_item_by_title("The Bear", media_type="show")["id"])
            inventory = {
                "ok": True,
                "files": [
                    {
                        "id": "9",
                        "file_id": 9,
                        "series_id": 4,
                        "path": "/tv/a.mkv",
                        "claimed": {"filename": "a.mkv", "label": "S01E01", "evidence": False},
                        "sonarr": {"season": 1, "episode": 1, "episode_id": 11, "evidence": False},
                    }
                ],
                "catalog": _catalog(),
                "series_id": 4,
                "seasons": [1],
            }
            row = {
                "id": "9",
                "file_id": 9,
                "series_id": 4,
                "path": "/tv/The Bear/Season 01/a.mkv",
                "filename": "a.mkv",
                "same_show": True,
                "confidence": "likely",
                "sonarr": {"episode_id": 11, "season": 1, "episode": 1},
                "proposed": {
                    "scope": "this_series",
                    "series_title": "The Bear",
                    "tmdb_id": 136315,
                    "season": 1,
                    "episode": 7,
                    "title": "Braciole",
                    "sonarr_episode_id": 17,
                },
            }
            with patch(
                "projectionist.library.episode_investigate.job.list_episode_files",
                return_value=inventory,
            ), patch(
                "projectionist.library.episode_investigate.job.investigate_files",
                return_value=[row],
            ):
                started = start_investigate_job(
                    db,
                    SimpleNamespace(llm_provider="ollama", llm_model="llama3"),
                    show_id=show_id,
                    use_vision=False,
                    data_dir=Path(tmp),
                )
            self.assertTrue(started.get("accepted"))
            applied = start_apply_job(
                SimpleNamespace(),
                file_ids=["9"],
                rows=[row],
                show=_show(),
            )
            self.assertTrue(applied.get("accepted"))
            # Wait briefly for the apply worker
            import time

            for _ in range(20):
                from projectionist.library.episode_investigate.job import build_apply_status

                snap = build_apply_status()
                if not snap.get("busy") and snap.get("result"):
                    break
                time.sleep(0.05)
            apply_id = (build_apply_status().get("result") or {}).get("apply_id")
            if apply_id:
                with patch(
                    "projectionist.library.episode_investigate.job.undo_apply",
                    return_value={"apply_id": apply_id, "restored": 1, "failed": 0},
                ):
                    undone = start_undo_job(SimpleNamespace(), apply_id=apply_id)
                self.assertTrue(undone.get("accepted"))


class RemapAndVisionTests(unittest.TestCase):
    def test_remap_falls_back_to_rescan(self) -> None:
        from projectionist.library.episode_investigate.apply import remap_sonarr_episode_file

        calls = []

        def fake_json(url, **kwargs):
            calls.append((url, kwargs.get("method"), kwargs.get("body")))
            if "manualimport" in url and "command" not in url:
                raise RuntimeError("no probe")
            if kwargs.get("body", {}).get("name") == "ManualImport":
                raise RuntimeError("no import")
            return {"id": 1}

        with patch("projectionist.library.episode_investigate.apply.request_json", side_effect=fake_json):
            result = remap_sonarr_episode_file(
                SimpleNamespace(sonarr_url="http://sonarr", sonarr_api_key="k"),
                file_id=9,
                series_id=4,
                from_path="/tv/a.mkv",
                to_path="/tv/b.mkv",
                target_episode_id=17,
            )
        self.assertEqual(result["mode"], "rescan")
        self.assertTrue(any((call[2] or {}).get("name") == "RescanSeries" for call in calls))

    def test_identify_from_stills_uses_chat(self) -> None:
        from projectionist.library.episode_investigate.vision import identify_from_stills

        async def chat(_messages):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "scope": "this_series",
                                    "season": 1,
                                    "episode": 7,
                                    "confidence": 0.8,
                                    "episode_title": "Braciole",
                                }
                            )
                        }
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            still = Path(tmp) / "0.jpg"
            still.write_bytes(b"jpeg")
            parsed = identify_from_stills(
                SimpleNamespace(llm_provider="openai", llm_model="gpt-4o-mini"),
                [still],
                this_series="The Bear",
                household_shows=["The Studio"],
                chat=chat,
            )
        self.assertEqual(parsed["episode"], 7)

    def test_lookup_opensubtitles_uses_fetch(self) -> None:
        from projectionist.library.episode_investigate.oshash import lookup_opensubtitles

        def fetch(digest, key):
            self.assertEqual(digest, "abcd")
            self.assertEqual(key, "k")
            return {
                "data": [
                    {
                        "attributes": {
                            "feature_details": {
                                "season_number": 1,
                                "episode_number": 2,
                                "parent_title": "The Bear",
                            }
                        }
                    }
                ]
            }

        parsed = lookup_opensubtitles("abcd", api_key="k", fetch=fetch)
        self.assertEqual(parsed["episode"], 2)

    def test_tmdb_season_parse(self) -> None:
        from projectionist.library.episode_investigate.tmdb_stills import season_episodes

        class _Tmdb:
            timeout = 5

            def _url(self, path, **_params):
                return f"http://tmdb{path}"

            def backdrop_url(self, path, size="w300"):
                return f"http://img/{size}{path}"

        with patch(
            "projectionist.library.episode_investigate.tmdb_stills.request_json",
            return_value={
                "episodes": [
                    {"episode_number": 1, "name": "System", "runtime": 30, "still_path": "/x.jpg"},
                ]
            },
        ):
            rows = season_episodes(_Tmdb(), 136315, 1)
        self.assertEqual(rows[0]["title"], "System")
        self.assertTrue(rows[0]["still_url"].endswith("/x.jpg"))


class IdentifyLaneTests(unittest.TestCase):
    def tearDown(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import reset_identify_throttle_for_tests

        reset_identify_throttle_for_tests()
        for key in (
            "PROJECTIONIST_ACRCLOUD_HOST",
            "PROJECTIONIST_ACRCLOUD_ACCESS_KEY",
            "PROJECTIONIST_ACRCLOUD_ACCESS_SECRET",
            "ACRCLOUD_HOST",
            "ACRCLOUD_ACCESS_KEY",
            "ACRCLOUD_ACCESS_SECRET",
        ):
            os.environ.pop(key, None)

    def test_theme_title_strips_to_series(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import series_title_from_acr

        self.assertEqual(series_title_from_acr("The Bear (Main Title Theme)"), "The Bear")
        self.assertEqual(series_title_from_acr("The Studio Theme"), "The Studio")

    def test_hmac_and_parse(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import parse_identify_payload, sign_identify

        signature = sign_identify(access_key="key", access_secret="secret", timestamp="1700000000")
        self.assertTrue(signature)
        parsed = parse_identify_payload(
            {
                "status": {"code": 0, "msg": "Success"},
                "metadata": {"music": [{"title": "The Bear Main Title", "score": 100}]},
            }
        )
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["series_title"], "The Bear")
        miss = parse_identify_payload({"status": {"code": 1001, "msg": "No result"}})
        self.assertFalse(miss["found"])
        self.assertTrue(miss["ok"])

    def test_map_prefers_this_show(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import map_acr_title_to_tmdb

        mapped = map_acr_title_to_tmdb(
            "The Bear Theme",
            search=lambda _q: [
                {"id": 9, "name": "Other"},
                {"id": 136315, "name": "The Bear"},
            ],
            this_show=_show(),
        )
        self.assertEqual(mapped["tmdb_id"], 136315)

    def test_host_rejects_broadcast(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import normalize_identify_host

        self.assertEqual(
            normalize_identify_host("identify-eu-west-1.acrcloud.com"),
            "identify-eu-west-1.acrcloud.com",
        )
        with self.assertRaises(ValueError):
            normalize_identify_host("bm-us-west-2.acrcloud.com")

    def test_fusion_identify_this_show_does_not_pick_episode(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=None,
            opensubtitles=None,
            vision=None,
            identify={
                "found": True,
                "mapped": True,
                "title": "The Bear Main Title",
                "series_title": "The Bear",
                "tmdb_id": 136315,
            },
        )
        self.assertEqual(fused["confidence"], "uncertain")
        self.assertTrue(any("Identify heard this series" in item for item in fused["reasons"]))
        self.assertIsNone(fused["proposed"]["episode"])
        self.assertFalse(fused["new_show"])

    def test_fusion_unmapped_is_uncertain_evidence(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=None,
            opensubtitles=None,
            vision=None,
            identify={"found": True, "mapped": False, "title": "Random Cue", "series_title": "Random Cue"},
        )
        self.assertEqual(fused["confidence"], "uncertain")
        self.assertTrue(any("not a known series" in item for item in fused["reasons"]))

    def test_fusion_new_show_requires_opt_in(self) -> None:
        fused = fuse_row(
            show=_show(),
            catalog=_catalog(),
            runtime_seconds=None,
            opensubtitles=None,
            vision=None,
            household_titles=["The Bear"],
            household_tmdb_ids=[136315],
            identify={
                "found": True,
                "mapped": True,
                "title": "The Studio Theme",
                "series_title": "The Studio",
                "tmdb_id": 222222,
            },
        )
        self.assertTrue(fused["new_show"])
        self.assertTrue(fused["create_attach"])
        self.assertTrue(fused["create_opt_in_required"])
        self.assertEqual(fused["proposed"]["scope"], "new_show")
        self.assertFalse(fused["selected_default"])

    def test_apply_new_show_skips_without_opt_in(self) -> None:
        result = apply_rows(
            SimpleNamespace(),
            _show(),
            [
                {
                    "id": "1",
                    "path": "/tv/x.mkv",
                    "new_show": True,
                    "create_attach": True,
                    "proposed": {
                        "scope": "new_show",
                        "series_title": "The Studio",
                        "tmdb_id": 222222,
                    },
                }
            ],
            ["1"],
            rename=lambda *_a: None,
            exists=lambda _p: True,
            sonarr_remap=lambda **_k: {},
            plex_refresh=lambda _s: None,
        )
        self.assertEqual(result["applied"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertIn("opt in", result["skipped_rows"][0]["reason"])

    def test_apply_new_show_creates_when_opted_in(self) -> None:
        created = []
        result = apply_rows(
            SimpleNamespace(),
            _show(),
            [
                {
                    "id": "1",
                    "file_id": 1,
                    "path": "/tv/x.mkv",
                    "new_show": True,
                    "create_attach": True,
                    "proposed": {
                        "scope": "new_show",
                        "series_title": "The Studio",
                        "tmdb_id": 222222,
                        "tvdb_id": 99,
                    },
                }
            ],
            ["1"],
            create_opt_in=["1"],
            rename=lambda *_a: None,
            exists=lambda _p: True,
            sonarr_remap=lambda **_k: {},
            plex_refresh=lambda _s: None,
            create_series=lambda _settings, proposed: created.append(proposed) or {
                "series_id": 8,
                "created": True,
                "title": "The Studio",
            },
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(result["applied"], 1)
        self.assertTrue(result["changes"][0]["created_series"]["created"])
        self.assertFalse(result["changes"][0]["attached"])

    def test_clip_uses_forty_percent(self) -> None:
        from projectionist.library.episode_investigate.ffmpeg import extract_identify_clip

        calls = []

        def runner(cmd, **_kwargs):
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"RIFF")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.mkv"
            src.write_bytes(b"video")
            dest = Path(tmp) / "identify.wav"
            written = extract_identify_clip(
                str(src),
                dest,
                ffmpeg="/bin/ffmpeg",
                runtime_seconds=100,
                runner=runner,
            )
        self.assertEqual(written, dest)
        self.assertIn("-ss", calls[0])
        self.assertEqual(calls[0][calls[0].index("-ss") + 1], "40.00")
        self.assertEqual(calls[0][calls[0].index("-t") + 1], "12.00")

    def test_one_identify_per_file_and_miss_is_not_failure(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import identify_file
        from projectionist.library.episode_investigate.job import investigate_one

        fetches = []

        def fetch(_url, _sample, _name, _fields):
            fetches.append(1)
            raise RuntimeError("network down")

        settings = SimpleNamespace(
            llm_provider="ollama",
            llm_model="llama3",
            tmdb_api_key="",
            acrcloud=SimpleNamespace(host="identify-us-west-2.acrcloud.com", access_key="k", access_secret="s"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.mkv"
            path.write_bytes(b"video")
            with patch(
                "projectionist.library.episode_investigate.job.probe_runtime_seconds",
                return_value=100,
            ), patch(
                "projectionist.library.episode_investigate.job.extract_stills",
                return_value=[],
            ), patch(
                "projectionist.library.episode_investigate.job.file_oshash",
                return_value=None,
            ), patch(
                "projectionist.library.episode_investigate.acrcloud.extract_identify_clip",
                return_value=path,
            ), patch(
                "projectionist.library.episode_investigate.acrcloud.identify_bytes",
                side_effect=lambda *_a, **_k: {"found": False, "ok": True, "title": "", "message": "miss"},
            ):
                row = investigate_one(
                    settings,
                    _show(),
                    {
                        "id": "9",
                        "file_id": 9,
                        "series_id": 4,
                        "path": str(path),
                        "claimed": {"filename": "a.mkv", "label": "S01E01", "evidence": False},
                        "sonarr": {"season": 1, "episode": 1, "evidence": False},
                    },
                    catalog=_catalog(),
                    use_vision=False,
                    household=["The Bear"],
                    job_id="job1",
                    data_dir=Path(tmp),
                )
            first = identify_file(
                str(path),
                Path(tmp),
                settings=settings,
                file_key="same-ep",
                extract=lambda *_a, **_k: path,
                fetch=fetch,
            )
            second = identify_file(
                str(path),
                Path(tmp),
                settings=settings,
                file_key="same-ep",
                extract=lambda *_a, **_k: path,
                fetch=fetch,
            )
        self.assertEqual(row["confidence"], "uncertain")
        self.assertFalse((row.get("identify") or {}).get("found"))
        self.assertIsNone(second)
        self.assertIsNotNone(first)

    def test_env_wins_over_settings(self) -> None:
        from projectionist.config_store import AcrcloudSettings, Settings, save_settings, load_merged_settings
        from projectionist.library.episode_investigate.capabilities import acrcloud_config, health_payload

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_settings(
                data_dir,
                Settings(
                    acrcloud=AcrcloudSettings(
                        host="identify-us-west-2.acrcloud.com",
                        access_key="file-k",
                        access_secret="file-s",
                    )
                ),
            )
            raw = (data_dir / "settings.json").read_text(encoding="utf-8")
            self.assertIn("enc:v1:", raw)
            self.assertNotIn("file-k", raw)
            self.assertNotIn("file-s", raw)
            os.environ["PROJECTIONIST_ACRCLOUD_ACCESS_KEY"] = "env-k"
            os.environ["PROJECTIONIST_ACRCLOUD_ACCESS_SECRET"] = "env-s"
            loaded = load_merged_settings(data_dir)
            creds = acrcloud_config(loaded)
            self.assertEqual(creds["access_key"], "env-k")
            self.assertEqual(creds["access_key_source"], "env")
            health = health_payload(loaded)
            self.assertTrue(health["acrcloud"]["available"])

    def test_test_clip_never_renames(self) -> None:
        from projectionist.library.episode_investigate.acrcloud import test_identify_clip

        settings = SimpleNamespace(
            acrcloud=SimpleNamespace(
                host="identify-us-west-2.acrcloud.com",
                access_key="k",
                access_secret="s",
            )
        )
        result = test_identify_clip(
            settings=settings,
            fetch=lambda *_a, **_k: {"status": {"code": 1001, "msg": "No result"}},
        )
        self.assertFalse(result["renamed"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "silent")
