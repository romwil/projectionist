"""ENG-004: WebVTT from the household cache. Picture captions still fall back."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.config_store import Settings
from projectionist.engine.caption_prep import PREP_TIMEOUT_S, extract_text_captions
from projectionist.engine.captions import (
    CAPTION_FALLBACK_REASON,
    CAPTION_PENDING_REASON,
    CaptionRendition,
    caption_fallback_reason,
    prepare_webvtt_renditions,
)
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import APPLE_TV_4K
from projectionist.engine.remux import write_master
from projectionist.engine.session import open_engine_session, reset_engine_sessions
from projectionist.engine.source import MediaAsset

_SRT = "1\n00:00:01,500 --> 00:00:03,000\nHello from the house\n"


def _streams(*, text: bool = False, image: bool = False) -> list[MediaStream]:
    rows = [
        MediaStream(index=0, codec_type="video", codec="h264", level="41", width=1920, height=1080),
        MediaStream(index=1, codec_type="audio", codec="aac"),
    ]
    if text:
        rows.append(
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text")
        )
        rows.append(
            MediaStream(index=3, codec_type="subtitle", codec="subrip", language="fre", subtitle_kind="text")
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


def _asset(*, text: bool = False, image: bool = False, local_path: str = "") -> MediaAsset:
    return MediaAsset(
        rating_key="121986",
        readable=True,
        local_path=local_path or None,
        probe=ProbeResult("mkv", "matroska", 600.0, 4_000_000, 1000, _streams(text=text, image=image)),
    )


def _write_cache(data_dir: Path, language: str, body: str = _SRT) -> None:
    folder = data_dir / "subtitles" / "121986"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{language}.srt").write_text(body, encoding="utf-8")


class CaptionFallbackTests(unittest.TestCase):
    def test_household_language_with_subs_can_use_the_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(text=True),
                title_language="en",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, "")

    def test_other_language_without_webvtt_stays_on_plex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(text=True),
                title_language="ja",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, CAPTION_PENDING_REASON)
        self.assertNotIn("path mapping", reason)

    def test_picture_captions_stay_on_plex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            reason = caption_fallback_reason(
                _asset(image=True, local_path=str(media)),
                title_language="ja",
                settings=Settings(),
                data_dir=root,
            )
        self.assertEqual(reason, CAPTION_FALLBACK_REASON)

    def test_no_captions_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(),
                title_language="ja",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, "")

    def test_household_cache_removes_the_caption_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_cache(root, "en")
            _write_cache(root, "es", "1\n00:00:04,000 --> 00:00:05,000\nHola\n")
            asset = _asset(image=True)
            renditions = prepare_webvtt_renditions(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
            )
            reason = caption_fallback_reason(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
                renditions=renditions,
            )
        self.assertEqual(reason, "")
        self.assertEqual([item.track_id for item in renditions], ["cached-en", "cached-es"])
        self.assertTrue(renditions[0].default)
        self.assertFalse(renditions[1].default)
        self.assertIn("00:00:01.500 --> 00:00:03.000", renditions[0].webvtt)
        self.assertIn("Hello from the house", renditions[0].webvtt)
        self.assertNotIn(str(root), renditions[0].webvtt)

    def test_household_language_offers_tracks_without_selecting_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_cache(root, "en")
            renditions = prepare_webvtt_renditions(
                _asset(),
                title_language="en",
                settings=Settings(),
                data_dir=root,
            )
        self.assertEqual(len(renditions), 1)
        self.assertFalse(renditions[0].default)

    def test_prepared_text_is_served_without_the_play_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            _write_cache(root, "en")
            seen: list[int] = []

            def extract(source: Path, index: int, dest: Path) -> None:
                seen.append(index)
                self.assertEqual(source, media)
                dest.write_text(
                    "WEBVTT\n\n00:00:08.000 --> 00:00:09.000\nDepuis le fichier\n",
                    encoding="utf-8",
                )

            asset = _asset(text=True, local_path=str(media))
            status = extract_text_captions(asset, data_dir=root, extractor=extract)
            with patch(
                "projectionist.engine.caption_prep.subprocess.run",
                side_effect=AssertionError("play must not extract captions"),
            ):
                renditions = prepare_webvtt_renditions(
                    asset,
                    title_language="ja",
                    settings=Settings(),
                    data_dir=root,
                )
                reason = caption_fallback_reason(
                    asset,
                    title_language="ja",
                    settings=Settings(),
                    data_dir=root,
                    renditions=renditions,
                )
        self.assertEqual(status, "ready")
        self.assertEqual(seen, [3])
        self.assertGreaterEqual(PREP_TIMEOUT_S, 600)
        self.assertNotEqual(PREP_TIMEOUT_S, 20)
        self.assertEqual(reason, "")
        self.assertEqual([item.language for item in renditions], ["en", "fr"])
        self.assertEqual(renditions[1].track_id, "s3")
        self.assertEqual(renditions[1].name, "French")
        self.assertFalse(renditions[1].default)
        self.assertIn("Depuis le fichier", renditions[1].webvtt)

    def test_text_not_ready_records_a_caption_fallback_not_a_path_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")

            def extract(source: Path, index: int, dest: Path) -> None:
                return

            asset = _asset(text=True, local_path=str(media))
            status = extract_text_captions(asset, data_dir=root, extractor=extract)
            renditions = prepare_webvtt_renditions(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
            )
            reason = caption_fallback_reason(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
                renditions=renditions,
            )
        self.assertEqual(status, "failed")
        self.assertEqual(renditions, [])
        self.assertEqual(reason, CAPTION_PENDING_REASON)
        self.assertNotEqual(reason, CAPTION_FALLBACK_REASON)
        self.assertNotIn("path mapping", reason)

    def test_unreadable_title_does_not_record_a_caption_fallback(self) -> None:
        asset = MediaAsset(rating_key="121986", readable=False, reason="No path mapping for this file")
        reason = caption_fallback_reason(
            asset,
            title_language="ja",
            settings=Settings(),
            data_dir=Path("."),
        )
        self.assertEqual(reason, "")

    def test_only_non_household_cache_is_still_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_cache(root, "fr", "1\n00:00:04,000 --> 00:00:05,000\nBonjour\n")
            renditions = prepare_webvtt_renditions(
                _asset(image=True),
                title_language="ja",
                settings=Settings(),
                data_dir=root,
            )
        self.assertEqual(renditions[0].language, "fr")
        self.assertTrue(renditions[0].default)

    def test_a_broken_extractor_does_not_fail_the_session_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")

            def extract(source: Path, index: int, dest: Path) -> None:
                raise RuntimeError("ffmpeg broke")

            asset = _asset(text=True, local_path=str(media))
            status = extract_text_captions(asset, data_dir=root, extractor=extract)
            renditions = prepare_webvtt_renditions(
                asset,
                title_language="ja",
                settings=Settings(),
                data_dir=root,
            )
        self.assertEqual(status, "failed")
        self.assertEqual(renditions, [])

    def test_unprepared_text_does_not_call_ffmpeg_at_play(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset(text=True, local_path=str(media))
            with patch(
                "projectionist.engine.caption_prep.subprocess.run",
                side_effect=AssertionError("play must not extract captions"),
            ):
                renditions = prepare_webvtt_renditions(
                    asset,
                    title_language="ja",
                    settings=Settings(),
                    data_dir=root,
                )
                reason = caption_fallback_reason(
                    asset,
                    title_language="ja",
                    settings=Settings(),
                    data_dir=root,
                    renditions=renditions,
                )
        self.assertEqual(renditions, [])
        self.assertEqual(reason, CAPTION_PENDING_REASON)

    def test_setting_defaults_off(self) -> None:
        self.assertFalse(Settings().engine.play_through_projectionist)
        turned = Settings.from_mapping({"engine": {"play_through_projectionist": True}})
        self.assertTrue(turned.engine.play_through_projectionist)


class CaptionPlaylistTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_engine_sessions()

    def tearDown(self) -> None:
        reset_engine_sessions()

    def test_a_captioned_title_plays_through_the_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            _write_cache(root, "en")
            asset = _asset(image=True, local_path=str(media))
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

            def runner(cmd, cwd):
                folder = Path(cwd)
                (folder / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = open_engine_session(
                asset,
                APPLE_TV_4K,
                user_id="owner",
                title="A Foreign Film",
                duration_ms=600_000,
                view_offset_ms=0,
                data_dir=root,
                runner=runner,
                ffmpeg="ffmpeg",
                force_reason=reason,
                captions=[] if reason else renditions,
            )
            self.assertEqual(reason, "")
            self.assertEqual(session.plan, "remux")
            self.assertTrue(session.playable)
            self.assertNotIn(CAPTION_FALLBACK_REASON, session.reason)
            assert session.directory is not None
            master = (session.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn('TYPE=SUBTITLES,GROUP-ID="subs"', master)
            self.assertIn('NAME="English"', master)
            self.assertIn("DEFAULT=YES", master)
            self.assertIn('LANGUAGE="en"', master)
            self.assertIn('URI="subs/cached-en.m3u8"', master)
            self.assertIn('SUBTITLES="subs"', master)
            self.assertNotIn(str(media), master)
            vtt = (session.directory / "subs" / "cached-en.vtt").read_text(encoding="utf-8")
            self.assertTrue(vtt.startswith("WEBVTT"))
            self.assertIn("Hello from the house", vtt)
            playlist = (session.directory / "subs" / "cached-en.m3u8").read_text(encoding="utf-8")
            self.assertIn("#EXT-X-PLAYLIST-TYPE:VOD", playlist)
            self.assertIn("#EXT-X-ENDLIST", playlist)
            self.assertIn("cached-en.vtt", playlist)
            self.assertIn("#EXT-X-TARGETDURATION:600", playlist)

    def test_subtitle_playlist_uses_the_probe_duration_when_the_item_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            _write_cache(root, "en")
            asset = _asset(local_path=str(media))

            def runner(cmd, cwd):
                (Path(cwd) / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            renditions = prepare_webvtt_renditions(
                asset, title_language="ja", settings=Settings(), data_dir=root
            )
            session = open_engine_session(
                asset,
                APPLE_TV_4K,
                user_id="owner",
                title="A Foreign Film",
                duration_ms=0,
                view_offset_ms=0,
                data_dir=root,
                runner=runner,
                ffmpeg="ffmpeg",
                captions=renditions,
            )
            assert session.directory is not None
            playlist = (session.directory / "subs" / "cached-en.m3u8").read_text(encoding="utf-8")
            self.assertIn("#EXT-X-TARGETDURATION:600", playlist)
            self.assertIn("#EXTINF:600.000,", playlist)

    def test_prepared_text_opens_an_engine_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset(text=True, local_path=str(media))

            def extract(source: Path, index: int, dest: Path) -> None:
                dest.write_text(
                    "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nFrom the file\n",
                    encoding="utf-8",
                )

            self.assertEqual(extract_text_captions(asset, data_dir=root, extractor=extract), "ready")
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

            def runner(cmd, cwd):
                (Path(cwd) / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            with patch(
                "projectionist.engine.caption_prep.subprocess.run",
                side_effect=AssertionError("play must not extract captions"),
            ):
                session = open_engine_session(
                    asset,
                    APPLE_TV_4K,
                    user_id="owner",
                    title="Zatoichi",
                    duration_ms=600_000,
                    view_offset_ms=0,
                    data_dir=root,
                    runner=runner,
                    ffmpeg="ffmpeg",
                    force_reason=reason,
                    captions=[] if reason else renditions,
                )
            self.assertEqual(reason, "")
            self.assertEqual(session.plan, "remux")
            self.assertTrue(session.playable)
            assert session.directory is not None
            vtt = (session.directory / "subs" / "s2.vtt").read_text(encoding="utf-8")
            self.assertIn("From the file", vtt)

    def test_text_not_ready_does_not_start_a_remux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset(text=True, local_path=str(media))
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

            def runner(cmd, cwd):
                raise AssertionError("captions that are not ready stay on the Plex path")

            session = open_engine_session(
                asset,
                APPLE_TV_4K,
                user_id="owner",
                title="Zatoichi",
                duration_ms=600_000,
                view_offset_ms=0,
                data_dir=root,
                runner=runner,
                force_reason=reason,
                captions=[] if reason else renditions,
            )
            self.assertEqual(session.plan, "plex-fallback")
            self.assertFalse(session.playable)
            self.assertEqual(session.reason, CAPTION_PENDING_REASON)
            self.assertNotEqual(session.reason, CAPTION_FALLBACK_REASON)

    def test_picture_captions_do_not_start_a_remux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset(image=True, local_path=str(media))
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

            def runner(cmd, cwd):
                raise AssertionError("picture captions must stay on the Plex path")

            session = open_engine_session(
                asset,
                APPLE_TV_4K,
                user_id="owner",
                title="Pictures",
                duration_ms=600_000,
                view_offset_ms=0,
                data_dir=root,
                runner=runner,
                force_reason=reason,
                captions=[] if reason else renditions,
            )
            self.assertEqual(session.plan, "plex-fallback")
            self.assertFalse(session.playable)
            self.assertEqual(session.reason, CAPTION_FALLBACK_REASON)
            self.assertEqual(session.master_url(), "")

    def test_a_hostile_track_id_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaked = root / "secret.vtt"
            write_master(
                root / "session",
                _asset().probe,
                file_size=100,
                duration_ms=1000,
                captions=[
                    CaptionRendition(
                        track_id="../secret",
                        language="en",
                        name="English",
                        default=True,
                        webvtt="WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nNo\n",
                    )
                ],
            )
            master = (root / "session" / "master.m3u8").read_text(encoding="utf-8")
            self.assertNotIn("SUBTITLES", master)
            self.assertFalse(leaked.exists())
            self.assertFalse((root / "secret.vtt").exists())
