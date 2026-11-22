"""ENG-014: copies made ahead of time. The tests do not start a library encode."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from projectionist.engine.copies import (
    DEFAULT_BUDGET_BYTES,
    copy_folder_problem,
    in_copy_window,
    run_copy_pass,
    titles_within_budget,
)
from projectionist.engine.planner import plan_playback
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import SAFARI
from projectionist.engine.source import MediaAsset

_ZONE = ZoneInfo("America/New_York")


def _when(hour: int, minute: int) -> datetime:
    return datetime(2026, 11, 22, hour, minute, tzinfo=_ZONE)


def _probe(container: str, video: str, audio: str, *, size: int = 1000) -> ProbeResult:
    return ProbeResult(
        container,
        container,
        600.0,
        4_000_000,
        size,
        [
            MediaStream(
                index=0,
                codec_type="video",
                codec=video,
                level="41",
                width=1920,
                height=1080,
            ),
            MediaStream(
                index=1,
                codec_type="audio",
                codec=audio,
                language="eng",
                channels=2,
            ),
        ],
    )


def _asset(key: str, container: str, video: str, audio: str, path: Path) -> MediaAsset:
    return MediaAsset(
        rating_key=key,
        local_path=str(path),
        readable=True,
        probe=_probe(container, video, audio),
    )


class CopyFolderTests(unittest.TestCase):
    def test_refuses_a_folder_inside_a_plex_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            library = root / "movies"
            library.mkdir()
            inside = library / "copies"
            inside.mkdir()
            sibling = root / "copies"
            sibling.mkdir()
            extra = root / "movies-extra"
            extra.mkdir()
            link = root / "link"
            link.symlink_to(inside, target_is_directory=True)

            self.assertIn("inside", copy_folder_problem(inside, [library]).lower())
            self.assertIn(
                "inside", copy_folder_problem(Path(str(library) + "/"), [library]).lower()
            )
            self.assertIn("inside", copy_folder_problem(link, [library]).lower())
            self.assertIn("library", copy_folder_problem(root, [library]).lower())
            self.assertEqual(copy_folder_problem(sibling, [library]), "")
            self.assertEqual(copy_folder_problem(extra, [library]), "")

            blocked = sibling / "locked"
            blocked.mkdir()
            blocked.chmod(0)
            try:
                self.assertIn("writable", copy_folder_problem(blocked, [library]).lower())
            finally:
                blocked.chmod(0o700)


class CopyQueueTests(unittest.TestCase):
    def test_budget_stops_before_the_title_that_would_pass_it(self) -> None:
        titles = [
            {
                "rating_key": "wide",
                "title": "Wide",
                "above_1080p": True,
                "watch_count": 1,
                "file_size": 100,
            },
            {
                "rating_key": "often",
                "title": "Often",
                "above_1080p": False,
                "watch_count": 9,
                "file_size": 80,
            },
            {
                "rating_key": "later",
                "title": "Later",
                "above_1080p": False,
                "watch_count": 4,
                "file_size": 10,
            },
        ]
        chosen = titles_within_budget(titles, budget_bytes=150, used_bytes=0)
        self.assertEqual([row["rating_key"] for row in chosen], ["wide"])
        self.assertEqual(DEFAULT_BUDGET_BYTES, 200 * 1024 * 1024 * 1024)

    def test_overnight_window_and_a_partial_is_not_a_ready_copy(self) -> None:
        titles = [
            {
                "rating_key": "wide",
                "title": "Wide",
                "above_1080p": True,
                "watch_count": 1,
                "file_size": 40,
            },
            {
                "rating_key": "often",
                "title": "Often",
                "above_1080p": False,
                "watch_count": 9,
                "file_size": 40,
            },
        ]
        calls: list[str] = []

        def runner(command: list[str], destination: Path) -> str:
            calls.append(command[-1])
            self.assertEqual(command[:6], ["nice", "-n", "19", "ionice", "-c", "3"])
            destination.write_bytes(b"partial")
            return "partial"

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            source = output / "source.mkv"
            source.write_bytes(b"source")
            with patch(
                "projectionist.engine.media_slot.shutil.which", return_value="/usr/bin/nice"
            ):
                asleep = run_copy_pass(
                    titles,
                    output,
                    budget_bytes=200,
                    now=_when(12, 0),
                    runner=runner,
                    source_for=lambda _key: source,
                )
                self.assertEqual(calls, [])
                self.assertEqual(asleep["status"], "asleep")

                started = run_copy_pass(
                    titles,
                    output,
                    budget_bytes=200,
                    now=_when(1, 0),
                    runner=runner,
                    source_for=lambda _key: source,
                )
                self.assertEqual(started["rating_key"], "wide")
                self.assertFalse(started["ready"])
                self.assertTrue((output / "wide.part").is_file())
                self.assertFalse((output / "wide.mp4").exists())

                def finish(command: list[str], destination: Path) -> str:
                    calls.append(Path(command[-1]).name)
                    destination.write_bytes(b"done")
                    return "complete"

                again = run_copy_pass(
                    titles,
                    output,
                    budget_bytes=200,
                    now=_when(5, 59),
                    runner=finish,
                    source_for=lambda _key: source,
                )
        self.assertEqual(again["rating_key"], "wide")
        self.assertTrue(again["ready"])
        self.assertEqual(again["resumed"], True)
        self.assertIn("wide.part", calls[0])
        self.assertTrue(in_copy_window(_when(1, 0)))
        self.assertTrue(in_copy_window(_when(5, 59)))
        self.assertFalse(in_copy_window(_when(0, 59)))
        self.assertFalse(in_copy_window(_when(6, 0)))


class CopyPlannerTests(unittest.TestCase):
    def test_a_ready_copy_plays_instead_of_a_live_transcode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _asset("wide", "mkv", "vp9", "aac", root / "wide.mkv")
            ready = _asset("wide", "mp4", "h264", "aac", root / "wide.mp4")
            without = plan_playback(source, SAFARI)
            with_copy = plan_playback(source, SAFARI, ready_copy=ready)
        self.assertEqual(without["plan"], "source-transcode")
        self.assertIn(with_copy["plan"], {"direct", "remux"})
        self.assertTrue(with_copy["from_copy"])

    def test_the_scheduled_task_does_not_encode_during_tests(self) -> None:
        import asyncio

        from projectionist.config_store import Settings
        from projectionist.scheduler.tasks.copies import run

        result = asyncio.run(run(None, Settings(), lambda: False))
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["processed"], 0)
