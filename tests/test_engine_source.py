"""ENG-001: Plex path mapping and cached ffprobe. No file paths leave the public payload."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.config_store import EngineSettings, Settings
from projectionist.engine.pathmap import PathMapError, map_plex_path, normalize_mappings
from projectionist.engine.probe import probe_file
from projectionist.engine.source import PlexMediaSource, plex_lookup_reason, public_media


_PROBE = {
    "format": {
        "format_name": "matroska,webm",
        "duration": "600.066",
        "bit_rate": "4500000",
        "size": "337500000",
    },
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "profile": "High",
            "level": 41,
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuv420p",
            "bit_rate": "4000000",
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "ac3",
            "channels": 2,
            "bit_rate": "192000",
            "tags": {"language": "eng"},
        },
        {
            "index": 2,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "tags": {"language": "eng"},
        },
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "hdmv_pgs_subtitle",
            "tags": {"language": "fre"},
        },
    ],
}


class PathMapTests(unittest.TestCase):
    def test_longest_prefix_wins(self) -> None:
        mappings = normalize_mappings(
            [
                {"plex_prefix": "/data", "container_prefix": "/short"},
                {"plex_prefix": "/data/media/movies", "container_prefix": "/movies"},
            ]
        )
        mapped = map_plex_path("/data/media/movies/3 Ninjas (1992)/3 Ninjas (1992).mkv", mappings)
        self.assertEqual(mapped, "/movies/3 Ninjas (1992)/3 Ninjas (1992).mkv")

    def test_prefix_does_not_match_a_sibling_directory(self) -> None:
        mappings = normalize_mappings(
            [{"plex_prefix": "/data/media", "container_prefix": "/media"}]
        )
        self.assertIsNone(map_plex_path("/data/media-extra/film.mkv", mappings))
        self.assertEqual(map_plex_path("/data/media/film.mkv", mappings), "/media/film.mkv")

    def test_rejects_relative_and_traversal_prefixes(self) -> None:
        with self.assertRaises(PathMapError):
            normalize_mappings([{"plex_prefix": "data/media", "container_prefix": "/media"}])
        with self.assertRaises(PathMapError):
            normalize_mappings([{"plex_prefix": "/data/../etc", "container_prefix": "/media"}])
        with self.assertRaises(PathMapError):
            normalize_mappings([{"plex_prefix": "/data", "container_prefix": "/media/../etc"}])

    def test_unmapped_visible_file_is_used_and_missing_file_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            source = PlexMediaSource(
                mappings=[],
                path_lookup=lambda key: [str(media)] if key == "visible" else ["/plex/only/film.mkv"],
                is_file=lambda path: Path(path).is_file(),
                probe=lambda path, **kwargs: None,
                identity_lookup=lambda key: {},
            )
            visible = source.locate("visible")
            self.assertTrue(visible.readable)
            self.assertEqual(visible.local_path, str(media))
            missing = source.locate("missing")
            self.assertFalse(missing.readable)
            self.assertIn("path mapping", missing.reason.lower())

    def test_explicit_mapping_does_not_fall_through_when_the_target_is_missing(self) -> None:
        mappings = normalize_mappings(
            [{"plex_prefix": "/plex/movies", "container_prefix": "/movies"}]
        )
        source = PlexMediaSource(
            mappings=mappings,
            path_lookup=lambda key: ["/plex/movies/gone.mkv"],
            is_file=lambda path: False,
            probe=lambda path, **kwargs: None,
            identity_lookup=lambda key: {},
        )
        asset = source.locate("1")
        self.assertFalse(asset.readable)
        self.assertIsNone(asset.local_path)


class MediaSlotTests(unittest.TestCase):
    def test_ffprobe_and_ffmpeg_share_one_low_priority_slot(self) -> None:
        import threading
        import time

        from projectionist.engine.media_slot import media_command, run_media_tool

        def which(name: str):
            if name in {"nice", "ionice"}:
                return f"/usr/bin/{name}"
            return None

        with patch("projectionist.engine.media_slot.shutil.which", side_effect=which):
            command = media_command(["ffprobe", "-v", "error"])
        self.assertEqual(command[:6], ["nice", "-n", "19", "ionice", "-c", "3"])
        self.assertEqual(command[6], "ffprobe")
        inflight = {"n": 0, "max": 0}

        def runner(cmd, **kwargs):
            del cmd, kwargs
            inflight["n"] += 1
            inflight["max"] = max(inflight["max"], inflight["n"])
            time.sleep(0.05)
            inflight["n"] -= 1
            return "ok"

        threads = [
            threading.Thread(target=lambda: run_media_tool(["ffprobe"], runner))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(inflight["max"], 1)


class PlexLookupReasonTests(unittest.TestCase):
    def test_a_timeout_is_not_described_as_a_missing_file(self) -> None:
        self.assertIn("timed out", plex_lookup_reason(TimeoutError("timed out")).lower())
        self.assertIn(
            "timed out",
            plex_lookup_reason(RuntimeError("Timeout requesting http://plex/library/metadata/229258")).lower(),
        )
        self.assertIn(
            "timed out",
            plex_lookup_reason(RuntimeError("Circuit open for 10.10.1.200:32400; retry in 36s")).lower(),
        )
        self.assertNotIn("did not report a file", plex_lookup_reason(TimeoutError("timed out")).lower())

    def test_an_empty_part_list_stays_a_missing_file(self) -> None:
        source = PlexMediaSource(
            mappings=[],
            path_lookup=lambda key: [],
            is_file=lambda path: False,
            probe=lambda path, **kwargs: None,
        )
        asset = source.locate("229258")
        self.assertFalse(asset.readable)
        self.assertIn("did not report a file", asset.reason.lower())
        self.assertNotIn("timed out", asset.reason.lower())

        def explode(key: str):
            raise RuntimeError("Timeout requesting http://plex/library/metadata/229258")

        timed = PlexMediaSource(
            mappings=[],
            path_lookup=explode,
            is_file=lambda path: False,
            probe=lambda path, **kwargs: None,
        ).locate("229258")
        self.assertIn("timed out", timed.reason.lower())
        self.assertNotIn("did not report a file", timed.reason.lower())


class ProbeCacheTests(unittest.TestCase):
    def test_second_probe_uses_the_cache_until_mtime_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv-bytes")
            cache = Path(tmp) / "cache"
            calls = {"n": 0}

            def runner(cmd, **kwargs):
                calls["n"] += 1
                completed = MagicMock()
                completed.returncode = 0
                completed.stdout = json.dumps(_PROBE)
                completed.stderr = ""
                return completed

            first = probe_file(str(media), cache_dir=cache, runner=runner, ffprobe="ffprobe")
            second = probe_file(str(media), cache_dir=cache, runner=runner, ffprobe="ffprobe")
            self.assertEqual(calls["n"], 1)
            self.assertEqual(first.container, "mkv")
            self.assertEqual(second.duration_s, 600.066)
            video = next(stream for stream in second.streams if stream.codec_type == "video")
            self.assertEqual(video.codec, "h264")
            self.assertEqual(video.level, "41")
            text = next(stream for stream in second.streams if stream.codec == "subrip")
            image = next(stream for stream in second.streams if stream.codec == "hdmv_pgs_subtitle")
            self.assertEqual(text.subtitle_kind, "text")
            self.assertEqual(image.subtitle_kind, "image")
            self.assertEqual(text.language, "eng")

            media.write_bytes(b"mkv-bytes-changed")
            probe_file(str(media), cache_dir=cache, runner=runner, ffprobe="ffprobe")
            self.assertEqual(calls["n"], 2)


class PublicMediaTests(unittest.TestCase):
    def test_public_payload_omits_file_paths_and_keeps_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")

            def runner(cmd, **kwargs):
                completed = MagicMock()
                completed.returncode = 0
                completed.stdout = json.dumps(_PROBE)
                completed.stderr = ""
                return completed

            source = PlexMediaSource(
                mappings=[],
                path_lookup=lambda key: [str(media)],
                is_file=lambda path: Path(path).is_file(),
                identity_lookup=lambda key: {"tmdb_id": 8856, "imdb_id": "tt0103596"},
            )
            asset = source.locate("121986", cache_dir=Path(tmp) / "cache", runner=runner, ffprobe="ffprobe")
            payload = public_media(asset)
            blob = json.dumps(payload)
            self.assertNotIn(str(media), blob)
            self.assertNotIn("local_path", payload)
            self.assertNotIn("source_path", payload)
            self.assertTrue(payload["readable"])
            self.assertEqual(payload["identity"]["imdb_id"], "tt0103596")
            self.assertEqual(payload["container"], "mkv")
            self.assertEqual(payload["streams"][1]["codec"], "ac3")

    def test_main_10_probe_records_ten_bit(self) -> None:
        from projectionist.engine.probe import parse_ffprobe

        payload = json.loads(json.dumps(_PROBE))
        payload["streams"][0]["codec_name"] = "hevc"
        payload["streams"][0]["profile"] = "Main 10"
        payload["streams"][0]["pix_fmt"] = "yuv420p10le"
        payload["streams"][0]["bits_per_raw_sample"] = "10"
        video = parse_ffprobe(payload).streams[0]
        self.assertEqual(video.codec, "hevc")
        self.assertEqual(video.bit_depth, 10)


class EngineSettingsRoundTripTests(unittest.TestCase):
    def test_path_mappings_survive_settings_load(self) -> None:
        raw = {
            "engine": {
                "path_mappings": [
                    {"plex_prefix": "/data/media/movies", "container_prefix": "/movies"},
                    {"plex_prefix": "not-absolute", "container_prefix": "/nope"},
                ]
            }
        }
        settings = Settings.from_mapping(raw)
        self.assertIsInstance(settings.engine, EngineSettings)
        self.assertEqual(len(settings.engine.path_mappings), 1)
        self.assertEqual(settings.engine.path_mappings[0]["container_prefix"], "/movies")
        again = Settings.from_mapping(
            {"engine": {"path_mappings": settings.engine.path_mappings}}
        )
        self.assertEqual(again.engine.path_mappings, settings.engine.path_mappings)
