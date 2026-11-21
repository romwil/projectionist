"""Text captions are extracted before Play. Picture captions stay on Plex."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.engine.caption_prep import (
    PREP_TIMEOUT_S,
    drain_caption_queue,
    enqueue_caption_prep,
    enqueue_recent_arrivals,
    extract_text_captions,
    has_unprepared_text,
    note_caption_titles,
    prepared_tracks,
)
from projectionist.engine.captions import (
    CAPTION_FALLBACK_REASON,
    CAPTION_PENDING_REASON,
    caption_fallback_reason,
    prepare_webvtt_renditions,
)
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import MediaAsset
from projectionist.config_store import Settings
from projectionist.library.db import Database

_VTT = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nReady ahead of play\n"


def _streams(*, text: bool = False, image: bool = False) -> list[MediaStream]:
    rows = [
        MediaStream(index=0, codec_type="video", codec="h264", level="41", width=1920, height=1080),
        MediaStream(index=1, codec_type="audio", codec="aac"),
    ]
    if text:
        rows.append(
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text")
        )
    if image:
        rows.append(
            MediaStream(
                index=4,
                codec_type="subtitle",
                codec="hdmv_pgs_subtitle",
                language="eng",
                subtitle_kind="image",
            )
        )
    return rows


def _asset(root: Path, *, text: bool = False, image: bool = False) -> MediaAsset:
    media = root / "film.mkv"
    if not media.exists():
        media.write_bytes(b"mkv")
    return MediaAsset(
        rating_key="161755",
        readable=True,
        local_path=str(media),
        probe=ProbeResult("mkv", "matroska", 600.0, 4_000_000, media.stat().st_size, _streams(text=text, image=image)),
    )


class CaptionPrepTests(unittest.TestCase):
    def test_ahead_of_time_extract_uses_a_long_timeout_and_play_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)
            media = Path(str(asset.local_path))

            def fake_run(cmd, **kwargs):
                binary_at = cmd.index("/usr/bin/ffmpeg")
                self.assertEqual(cmd[binary_at + 1 : binary_at + 5], ["-y", "-i", str(media), "-map"])
                self.assertEqual(cmd[binary_at + 5], "0:2")
                self.assertEqual(cmd[binary_at + 6 : binary_at + 8], ["-f", "webvtt"])
                self.assertGreaterEqual(kwargs["timeout"], 600)
                self.assertNotEqual(kwargs["timeout"], 20)
                self.assertEqual(kwargs["timeout"], PREP_TIMEOUT_S)
                self.assertNotIn("shell", kwargs)
                Path(cmd[-1]).write_text(_VTT, encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0)

            with patch(
                "projectionist.library.episode_investigate.capabilities.resolve_ffmpeg",
                return_value="/usr/bin/ffmpeg",
            ), patch("projectionist.engine.caption_prep.subprocess.run", side_effect=fake_run):
                status = extract_text_captions(asset, data_dir=root)
            with patch(
                "projectionist.engine.caption_prep.subprocess.run",
                side_effect=AssertionError("play must not extract captions"),
            ):
                renditions = prepare_webvtt_renditions(
                    asset, title_language="ja", settings=Settings(), data_dir=root
                )
                reason = caption_fallback_reason(
                    asset,
                    title_language="ja",
                    settings=Settings(),
                    data_dir=root,
                    renditions=renditions,
                )
            self.assertEqual(status, "ready")
            self.assertEqual(reason, "")
            self.assertEqual(renditions[0].track_id, "s2")
            self.assertIn("Ready ahead of play", renditions[0].webvtt)
            stored = root / "subtitles" / "161755" / "prepared" / "s2.vtt"
            self.assertTrue(stored.is_file())
            self.assertTrue((root / "subtitles" / "161755" / "prepared.json").is_file())

    def test_a_stuck_extract_stays_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)

            def fake_run(cmd, **kwargs):
                raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout") or 1)

            with patch(
                "projectionist.library.episode_investigate.capabilities.resolve_ffmpeg",
                return_value="/usr/bin/ffmpeg",
            ), patch("projectionist.engine.caption_prep.subprocess.run", side_effect=fake_run):
                status = extract_text_captions(asset, data_dir=root)
            reason = caption_fallback_reason(
                asset, title_language="ja", settings=Settings(), data_dir=root
            )
        self.assertEqual(status, "failed")
        self.assertEqual(reason, CAPTION_PENDING_REASON)

    def test_picture_only_is_not_turned_into_webvtt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, image=True)

            def extract(source: Path, index: int, dest: Path) -> None:
                raise AssertionError("picture captions must not be extracted")

            status = extract_text_captions(asset, data_dir=root, extractor=extract)
            reason = caption_fallback_reason(
                asset, title_language="ja", settings=Settings(), data_dir=root
            )
            queued = enqueue_caption_prep(["161755"], data_dir=root, reason="title")
        self.assertEqual(status, "picture")
        self.assertEqual(reason, CAPTION_FALLBACK_REASON)
        self.assertEqual(prepared_tracks(asset, data_dir=root), [])
        self.assertEqual(queued, [])

    def test_a_queued_title_is_ready_on_the_next_play(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)
            note_caption_titles(["161755"], data_dir=root, reason="play", force=True)
            queued = json.loads((root / "caption_prep_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queued["items"][0]["rating_key"], "161755")
            self.assertEqual(queued["items"][0]["reason"], "play")

            def extract(source: Path, index: int, dest: Path) -> None:
                dest.write_text(_VTT, encoding="utf-8")

            first = caption_fallback_reason(
                asset, title_language="ja", settings=Settings(), data_dir=root
            )
            result = drain_caption_queue(
                data_dir=root,
                locate=lambda key: asset,
                should_stop=lambda: False,
                extractor=extract,
            )
            second_renditions = prepare_webvtt_renditions(
                asset, title_language="ja", settings=Settings(), data_dir=root
            )
            second = caption_fallback_reason(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
                renditions=second_renditions,
            )
        self.assertEqual(first, CAPTION_PENDING_REASON)
        self.assertEqual(result["processed"], 1)
        self.assertFalse(result["has_more"])
        self.assertEqual(second, "")
        self.assertIn("Ready ahead of play", second_renditions[0].webvtt)

    def test_a_failed_extract_waits_before_the_next_try(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)
            enqueue_caption_prep(["161755"], data_dir=root, reason="play", force=True)

            def extract(source: Path, index: int, dest: Path) -> None:
                return

            first = drain_caption_queue(
                data_dir=root,
                locate=lambda key: asset,
                should_stop=lambda: False,
                extractor=extract,
            )
            second = drain_caption_queue(
                data_dir=root,
                locate=lambda key: asset,
                should_stop=lambda: False,
                extractor=extract,
            )
        self.assertEqual(first["processed"], 0)
        self.assertEqual(second["processed"], 0)
        self.assertFalse(second["has_more"])

    def test_a_replaced_file_is_not_served_from_the_old_webvtt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)

            def extract(source: Path, index: int, dest: Path) -> None:
                dest.write_text(_VTT, encoding="utf-8")

            self.assertEqual(extract_text_captions(asset, data_dir=root, extractor=extract), "ready")
            media = Path(str(asset.local_path))
            media.write_bytes(b"mkv-replaced")
            stale = MediaAsset(
                rating_key=asset.rating_key,
                readable=True,
                local_path=str(media),
                probe=asset.probe,
            )
            self.assertEqual(prepared_tracks(stale, data_dir=root), [])
            reason = caption_fallback_reason(
                stale, title_language="ja", settings=Settings(), data_dir=root
            )
        self.assertEqual(reason, CAPTION_PENDING_REASON)

    def test_recent_arrivals_queue_movies_and_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = Database(root / "projectionist.db")
            now = int(time.time())
            show_id = db.upsert_library_item(
                {"rating_key": "show-1", "media_type": "show", "title": "Peep Show", "added_at": now}
            )
            db.upsert_library_item(
                {"rating_key": "66167", "media_type": "movie", "title": "13 Assassins", "added_at": now}
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "local-zero",
                    "season_number": 1,
                    "episode_number": 1,
                    "title": "Local Zero",
                    "added_at": now,
                }
            )
            added = enqueue_recent_arrivals(db, data_dir=root, limit=10)
        self.assertIn("66167", added)
        self.assertIn("local-zero", added)
        self.assertNotIn("show-1", added)

    def test_a_library_scan_does_not_queue_titles_that_are_not_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = Database(root / "projectionist.db")
            old = int(time.time()) - 40 * 24 * 3600
            show_id = db.upsert_library_item(
                {"rating_key": "show-old", "media_type": "show", "title": "Old Show", "added_at": old}
            )
            db.upsert_library_item(
                {"rating_key": "134335", "media_type": "movie", "title": "Mulholland Drive", "added_at": old}
            )
            db.upsert_library_episode(
                {
                    "show_item_id": show_id,
                    "rating_key": "229258",
                    "season_number": 3,
                    "episode_number": 16,
                    "title": "The Lady and the Tiger and the Lawyer",
                    "added_at": old,
                }
            )
            added = enqueue_recent_arrivals(db, data_dir=root, limit=40)
            queued = json.loads((root / "caption_prep_queue.json").read_text(encoding="utf-8")) if (root / "caption_prep_queue.json").is_file() else {"items": []}
        self.assertEqual(added, [])
        self.assertEqual(queued["items"], [])

    def test_a_playing_title_is_not_stuck_behind_the_arrival_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enqueue_caption_prep([str(index) for index in range(1, 201)], data_dir=root, reason="arrival")
            moved = note_caption_titles(["161755"], data_dir=root, reason="play", force=True)
            queued = json.loads((root / "caption_prep_queue.json").read_text(encoding="utf-8"))
        self.assertEqual(moved, None)
        items = queued["items"]
        self.assertLessEqual(len(items), 200)
        self.assertEqual(items[0]["rating_key"], "161755")
        self.assertEqual(items[0]["reason"], "play")
        self.assertNotEqual(items[-1]["rating_key"], "161755")

    def test_a_timed_out_extract_does_not_keep_a_partial_cue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = _asset(root, text=True)

            def fake_run(cmd, **kwargs):
                Path(cmd[-1]).write_text(_VTT, encoding="utf-8")
                raise subprocess.TimeoutExpired(cmd, timeout=kwargs.get("timeout") or 1)

            with patch(
                "projectionist.library.episode_investigate.capabilities.resolve_ffmpeg",
                return_value="/usr/bin/ffmpeg",
            ), patch("projectionist.engine.caption_prep.subprocess.run", side_effect=fake_run):
                status = extract_text_captions(asset, data_dir=root)
            manifest = root / "subtitles" / "161755" / "prepared.json"
            stored = root / "subtitles" / "161755" / "prepared" / "s2.vtt"
            self.assertEqual(status, "failed")
            self.assertEqual(prepared_tracks(asset, data_dir=root), [])
            self.assertFalse(stored.exists())
            if manifest.is_file():
                saved = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertNotEqual(saved.get("status"), "ready")
            self.assertTrue(has_unprepared_text(asset, data_dir=root))

    def test_one_prepared_english_track_covers_the_other_english_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            english = [
                MediaStream(index=0, codec_type="video", codec="h264"),
                MediaStream(index=1, codec_type="audio", codec="aac"),
                MediaStream(
                    index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text"
                ),
                MediaStream(
                    index=3, codec_type="subtitle", codec="subrip", language="en", subtitle_kind="text"
                ),
            ]
            asset = MediaAsset(
                rating_key="161755",
                readable=True,
                local_path=str(media),
                probe=ProbeResult("mkv", "matroska", 600.0, 1, media.stat().st_size, english),
            )
            calls: list[int] = []

            def extract(source: Path, index: int, dest: Path) -> None:
                del source
                calls.append(index)
                dest.write_text(_VTT, encoding="utf-8")

            self.assertEqual(extract_text_captions(asset, data_dir=root, extractor=extract), "ready")
            self.assertEqual(calls, [2])
            self.assertFalse(has_unprepared_text(asset, data_dir=root))
            self.assertEqual(extract_text_captions(asset, data_dir=root, extractor=extract), "ready")
            self.assertEqual(calls, [2])

            uncovered = MediaAsset(
                rating_key="161755",
                readable=True,
                local_path=str(media),
                probe=ProbeResult(
                    "mkv",
                    "matroska",
                    600.0,
                    1,
                    media.stat().st_size,
                    english
                    + [
                        MediaStream(
                            index=4,
                            codec_type="subtitle",
                            codec="subrip",
                            language="jpn",
                            subtitle_kind="text",
                        )
                    ],
                ),
            )
            self.assertTrue(has_unprepared_text(uncovered, data_dir=root))
            media.write_bytes(b"mkv-replaced")
            stale = MediaAsset(
                rating_key="161755",
                readable=True,
                local_path=str(media),
                probe=ProbeResult("mkv", "matroska", 600.0, 1, media.stat().st_size, english),
            )
            self.assertTrue(has_unprepared_text(stale, data_dir=root))
