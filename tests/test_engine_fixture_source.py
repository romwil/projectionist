"""Fixture media source: local clips, no Plex."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import load_merged_settings
from projectionist.engine.fixture_source import (
    FIXTURE_ENV,
    FixtureMediaError,
    FixtureMediaSource,
    install_fixture_library,
    try_fixture_media_source,
)
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import public_media
from projectionist.library.subtitle_cache import cache_path


def _probe(path: str, **_kwargs: object) -> ProbeResult:
    del path
    return ProbeResult(
        container="mp4",
        format_name="mp4",
        duration_s=48,
        bitrate=250_000,
        size=1000,
        streams=[
            MediaStream(index=0, codec_type="video", codec="h264", width=320, height=240),
            MediaStream(index=1, codec_type="audio", codec="aac", channels=2),
        ],
    )


class _Library:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def upsert_library_item(self, item: dict) -> int:
        self.items.append(dict(item))
        return len(self.items)


class FixtureMediaSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._prior = os.environ.get(FIXTURE_ENV)
        os.environ.pop(FIXTURE_ENV, None)

    def tearDown(self) -> None:
        if self._prior is None:
            os.environ.pop(FIXTURE_ENV, None)
        else:
            os.environ[FIXTURE_ENV] = self._prior
        self._tmp.cleanup()

    def _catalog(self, titles: list[dict]) -> None:
        (self.root / "catalog.json").write_text(
            json.dumps({"duration_s": 48, "cue": "FIXTURE CUE NORTH WINDOW", "titles": titles}),
            encoding="utf-8",
        )

    def test_unset_env_is_not_a_fixture_run(self) -> None:
        self.assertIsNone(try_fixture_media_source())
        self.assertEqual(install_fixture_library(_Library(), self.root), 0)

    def test_set_env_without_a_catalog_does_not_fall_through(self) -> None:
        os.environ[FIXTURE_ENV] = str(self.root)
        with self.assertRaises(FixtureMediaError):
            try_fixture_media_source()

    def test_locate_reads_the_catalog_and_hides_the_path(self) -> None:
        (self.root / "clip.mp4").write_bytes(b"not-a-real-media-file")
        self._catalog(
            [
                {
                    "rating_key": "fx-h264-aac-mp4",
                    "file": "clip.mp4",
                    "title": "H.264 AAC MP4",
                    "kind": "mp4-aac",
                }
            ]
        )
        source = FixtureMediaSource(self.root, probe=_probe)
        asset = source.locate("fx-h264-aac-mp4", cache_dir=self.root)
        self.assertTrue(asset.readable)
        self.assertEqual(asset.probe.container if asset.probe else "", "mp4")
        body = json.dumps(public_media(asset))
        self.assertNotIn("clip.mp4", body)
        self.assertNotIn(str(self.root), body)
        missing = source.locate("fx-missing")
        self.assertFalse(missing.readable)
        self.assertIn("no file", missing.reason)
        offer = source.source_transcode(reason="MPEG-2 video is not playable", source_reason="codec")
        self.assertEqual(offer["provider"], "fixture")
        self.assertEqual(offer["plan"], "source-transcode")
        self.assertFalse(offer["playable"])

    def test_a_probe_failure_stays_on_the_fixture_file(self) -> None:
        (self.root / "clip.mp4").write_bytes(b"clip")
        self._catalog(
            [
                {
                    "rating_key": "fx-h264-aac-mp4",
                    "file": "clip.mp4",
                    "title": "H.264 AAC MP4",
                    "kind": "mp4-aac",
                }
            ]
        )

        def _boom(path: str, **_kwargs: object) -> ProbeResult:
            del path
            raise RuntimeError("ffprobe failed")

        asset = FixtureMediaSource(self.root, probe=_boom).locate("fx-h264-aac-mp4")
        self.assertTrue(asset.readable)
        self.assertIsNone(asset.probe)
        self.assertIn("Could not read", asset.reason)
        self.assertNotIn("clip.mp4", asset.reason)

    def test_unreadable_catalog_is_an_error(self) -> None:
        (self.root / "catalog.json").write_text("{", encoding="utf-8")
        with self.assertRaises(FixtureMediaError):
            FixtureMediaSource(self.root, probe=_probe)

    def test_catalog_cannot_name_a_path_outside_the_directory(self) -> None:
        self._catalog(
            [{"rating_key": "fx-escape", "file": "../secret.mp4", "title": "Escape", "kind": "mp4-aac"}]
        )
        with self.assertRaises(FixtureMediaError):
            FixtureMediaSource(self.root, probe=_probe)

    def test_install_seeds_the_library_captions_and_engine_switch(self) -> None:
        (self.root / "clip.mp4").write_bytes(b"clip")
        (self.root / "cue.srt").write_text(
            "1\n00:00:00,500 --> 00:00:08,000\nFIXTURE CUE NORTH WINDOW\n",
            encoding="utf-8",
        )
        self._catalog(
            [
                {
                    "rating_key": "fx-h264-flac-srt",
                    "file": "clip.mp4",
                    "title": "H.264 FLAC captions",
                    "kind": "flac",
                    "original_language": "ja",
                    "subtitle": "cue.srt",
                }
            ]
        )
        os.environ[FIXTURE_ENV] = str(self.root)
        data = self.root / "data"
        data.mkdir()
        library = _Library()
        count = install_fixture_library(library, data)
        self.assertEqual(count, 1)
        self.assertEqual(library.items[0]["original_language"], "ja")
        self.assertEqual(library.items[0]["duration_ms"], 48_000)
        cached = cache_path("fx-h264-flac-srt", "en", data_dir=data)
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertIn("FIXTURE CUE NORTH WINDOW", cached.read_text(encoding="utf-8"))
        self.assertTrue(load_merged_settings(data).engine.play_through_projectionist)

    def test_household_source_does_not_construct_plex(self) -> None:
        (self.root / "clip.mp4").write_bytes(b"clip")
        self._catalog(
            [
                {
                    "rating_key": "fx-h264-aac-mp4",
                    "file": "clip.mp4",
                    "title": "H.264 AAC MP4",
                    "kind": "mp4-aac",
                }
            ]
        )
        os.environ[FIXTURE_ENV] = str(self.root)
        from projectionist.engine.routes import household_media_source
        from projectionist.config_store import Settings

        with patch(
            "projectionist.engine.routes.PlexMediaSource",
            side_effect=AssertionError("Plex media source"),
        ):
            source = household_media_source(Settings(), None)
        self.assertIsInstance(source, FixtureMediaSource)
        offer = source.source_transcode(reason="picture", source_reason="codec")
        self.assertEqual(offer["provider"], "fixture")


if __name__ == "__main__":
    unittest.main()
