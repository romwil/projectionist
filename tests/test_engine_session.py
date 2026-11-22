"""ENG-003: remux sessions, recorded plans, and header-free token URLs."""

from __future__ import annotations

import unittest
from pathlib import Path

from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import APPLE_TV_4K, CHROME
from projectionist.engine.session import (
    EngineSession,
    open_engine_session,
    reset_engine_sessions,
    resolve_session_file,
    session_for_token,
)
from projectionist.engine.source import MediaAsset
from projectionist.library.playback import PlaybackError


def _asset(audio: str = "ac3") -> MediaAsset:
    return MediaAsset(
        rating_key="121986",
        source_path="/plex/film.mkv",
        local_path="",
        readable=True,
        probe=ProbeResult(
            container="mkv",
            format_name="matroska",
            duration_s=600.0,
            bitrate=4_000_000,
            size=300_000_000,
            streams=[
                MediaStream(
                    index=0, codec_type="video", codec="h264", width=1920, height=1080, level="41"
                ),
                MediaStream(index=1, codec_type="audio", codec=audio, channels=2, language="eng"),
            ],
        ),
    )


class EngineSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_engine_sessions()
        self._root = Path(self.id().replace(".", "_"))

    def tearDown(self) -> None:
        reset_engine_sessions()

    def test_remux_writes_a_vod_master_and_rejects_a_bad_token(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset()
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = cmd
                seen["cwd"] = Path(cwd)
                folder = Path(cwd)
                (folder / "init.mp4").write_bytes(b"init")
                (folder / "seg_0000.m4s").write_bytes(b"seg")
                (folder / "stream.m3u8").write_text(
                    "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:6.000,\nseg_0000.m4s\n#EXT-X-ENDLIST\n",
                    encoding="utf-8",
                )

            session = open_engine_session(
                asset,
                APPLE_TV_4K,
                user_id="owner",
                title="3 Ninjas",
                duration_ms=600_000,
                view_offset_ms=12_000,
                data_dir=Path(tmp),
                runner=runner,
                ffmpeg="ffmpeg",
            )
            self.assertEqual(session.plan, "remux")
            self.assertTrue(session.playable)
            self.assertNotIn("Authorization", session.master_url())
            self.assertIn(session.token, session.master_url())
            command = " ".join(str(part) for part in seen["cmd"])
            self.assertIn("-c copy", command)
            self.assertIn("-hls_playlist_type event", command)
            self.assertNotIn("-hls_playlist_type vod", command)
            self.assertIn(str(media), command)
            master = (session.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn("BANDWIDTH=5000000", master)
            self.assertIn("#EXT-X-VERSION:7", master)
            self.assertIn("av/stream.m3u8", master)
            playlist = resolve_session_file(session, "av/stream.m3u8").read_text(encoding="utf-8")
            self.assertIn("#EXT-X-ENDLIST", playlist)
            with self.assertRaises(PlaybackError):
                resolve_session_file(session, "../film.mkv")
            with self.assertRaises(PlaybackError):
                session_for_token(session.session_id, "wrong-token")
            self.assertEqual(
                session_for_token(session.session_id, session.token).rating_key, "121986"
            )

    def test_audio_plan_copies_video_and_is_playable(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("ac3")
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                folder = Path(cwd)
                (folder / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = open_engine_session(
                asset,
                CHROME,
                user_id="owner",
                title="3 Ninjas",
                duration_ms=600_000,
                view_offset_ms=0,
                data_dir=Path(tmp),
                runner=runner,
                ffmpeg="ffmpeg",
            )
            self.assertEqual(session.plan, "audio")
            self.assertTrue(session.playable)
            self.assertIn(session.token, session.master_url())
            self.assertIn("AC-3", session.reason)
            command = " ".join(str(part) for part in seen["cmd"])
            self.assertIn("-c:v copy", command)
            self.assertIn("-c:a aac", command)
            self.assertNotIn("-c copy", command)
            self.assertNotIn("libx264", command)

    def test_a_remembered_failure_is_not_an_engine_playlist(self) -> None:
        import tempfile

        from projectionist.engine.profiles import profile_from_mapping

        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("aac")
            asset.local_path = str(media)
            asset.probe.streams[0].codec = "hevc"
            asset.probe.streams[0].level = "186"
            asset.probe.streams[0].bit_depth = 10
            profile = profile_from_mapping(
                {
                    "id": "web",
                    "containers": ["mp4", "hls-fmp4"],
                    "video": [
                        {"codec": "hevc", "max_level": "5.1", "bit_depth": 10},
                        {"codec": "h264", "max_level": "5.2"},
                    ],
                    "audio": ["aac", "ac3", "eac3"],
                    "captions": ["webvtt"],
                }
            )

            calls = {"n": 0}

            def runner(cmd, cwd):
                calls["n"] += 1
                folder = Path(cwd)
                (folder / "init.mp4").write_bytes(b"init")
                (folder / "seg_0000.m4s").write_bytes(b"seg")
                (folder / "stream.m3u8").write_text(
                    "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:6.000,\nseg_0000.m4s\n#EXT-X-ENDLIST\n",
                    encoding="utf-8",
                )
                del cmd

            first = open_engine_session(
                asset,
                profile,
                user_id="owner",
                title="Mulholland Drive",
                duration_ms=8_840_299,
                view_offset_ms=0,
                data_dir=Path(tmp),
                runner=runner,
                ffmpeg="ffmpeg",
            )
            self.assertEqual(first.plan, "try")
            self.assertTrue(first.playable)
            self.assertIn(first.token, first.master_url())
            self.assertEqual(calls["n"], 1)
            self.assertIn("hevc level is above profile hevc 5.1", first.reason)

            from projectionist.engine.tries import record_first_frame

            record_first_frame(
                Path(tmp),
                rating_key=asset.rating_key,
                profile_id=profile.id,
                arrived=False,
            )
            reset_engine_sessions()

            def refused(cmd, cwd):
                del cmd, cwd
                raise AssertionError("a remembered miss must not start another playlist")

            session = open_engine_session(
                asset,
                profile,
                user_id="owner",
                title="Mulholland Drive",
                duration_ms=8_840_299,
                view_offset_ms=0,
                data_dir=Path(tmp),
                runner=refused,
                ffmpeg="ffmpeg",
            )
            self.assertEqual(session.plan, "source-transcode")
            self.assertEqual(session.source_reason, "level")
            self.assertEqual(session.provider, "plex")
            self.assertFalse(session.playable)
            self.assertEqual(session.master_url(), "")
            self.assertIn("did not show a picture", session.reason)
            shown = session.public()
            self.assertEqual(shown["plan"], "source-transcode")
            self.assertEqual(shown["source_reason"], "level")
            self.assertEqual(shown["provider"], "plex")
            self.assertNotIn("libx264", shown["reason"])


class _Running:
    def poll(self):
        return None


class _Finished:
    def poll(self):
        return 0


class PlaylistWaitTests(unittest.TestCase):
    def _session(self, root: Path, process: object) -> EngineSession:
        session = EngineSession(
            session_id="s1",
            token="token",
            rating_key="70373",
            user_id="owner",
            plan="remux",
            reason="",
            playable=True,
            title="Beetlejuice",
            duration_ms=1,
            view_offset_ms=0,
            profile_id="chrome",
            directory=root,
            process=process,
        )
        return session

    def test_media_playlist_waits_until_the_event_playlist_appears(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "av").mkdir()
            now = {"t": 0.0}

            def clock() -> float:
                return now["t"]

            def sleep(seconds: float) -> None:
                now["t"] += seconds
                (root / "av" / "stream.m3u8").write_text(
                    "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n",
                    encoding="utf-8",
                )

            path = resolve_session_file(
                self._session(root, _Running()),
                "av/stream.m3u8",
                wait_s=20,
                sleep=sleep,
                clock=clock,
            )
            self.assertIn("EVENT", path.read_text(encoding="utf-8"))

    def test_missing_playlist_404s_when_ffmpeg_has_already_exited(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "av").mkdir()
            slept: list[float] = []
            with self.assertRaises(PlaybackError) as caught:
                resolve_session_file(
                    self._session(root, _Finished()),
                    "av/stream.m3u8",
                    wait_s=20,
                    sleep=slept.append,
                    clock=lambda: 0.0,
                )
            self.assertEqual(caught.exception.status_code, 404)
            self.assertEqual(slept, [])

    def test_missing_playlist_404s_after_the_wait_if_ffmpeg_never_writes_it(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "av").mkdir()
            now = {"t": 0.0}

            def clock() -> float:
                return now["t"]

            def sleep(seconds: float) -> None:
                now["t"] += seconds

            with self.assertRaises(PlaybackError) as caught:
                resolve_session_file(
                    self._session(root, _Running()),
                    "av/stream.m3u8",
                    wait_s=20,
                    sleep=sleep,
                    clock=clock,
                )
            self.assertEqual(caught.exception.status_code, 404)
            self.assertGreaterEqual(now["t"], 20)
