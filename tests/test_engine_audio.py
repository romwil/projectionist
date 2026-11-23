"""ENG-012: audio-only copies the video and encodes the audio the profile can play."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from projectionist.engine.probe import MediaStream, ProbeResult, probe_file
from projectionist.engine.profiles import APPLE_TV_4K, CHROME, SAFARI, profile_from_mapping
from projectionist.engine.session import open_engine_session, reset_engine_sessions
from projectionist.engine.source import MediaAsset


def _asset(video: str, audio: str, *, level: str = "41", bit_depth: int = 8) -> MediaAsset:
    return MediaAsset(
        rating_key="161000",
        source_path="/plex/secret.mkv",
        local_path="",
        readable=True,
        probe=ProbeResult(
            container="mkv",
            format_name="matroska",
            duration_s=1500.0,
            bitrate=8_000_000,
            size=1_500_000_000,
            streams=[
                MediaStream(
                    index=0,
                    codec_type="video",
                    codec=video,
                    width=1920,
                    height=1080,
                    level=level,
                    profile="High",
                    bit_depth=bit_depth,
                ),
                MediaStream(index=1, codec_type="audio", codec=audio, channels=6, language="eng"),
            ],
        ),
    )


def _which(name: str):
    if name in {"nice", "ionice"}:
        return f"/usr/bin/{name}"
    return None


def _ffmpeg_args(command: list[str]) -> list[str]:
    if "ffmpeg" not in command:
        return command
    return command[command.index("ffmpeg") :]


class AudioTranscodeTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_engine_sessions()

    def tearDown(self) -> None:
        reset_engine_sessions()

    def _open(self, asset: MediaAsset, profile, runner, *, title: str) -> object:
        asset.local_path = asset.local_path or ""
        return open_engine_session(
            asset,
            profile,
            user_id="owner",
            title=title,
            duration_ms=1_500_000,
            view_offset_ms=0,
            data_dir=Path(asset.local_path).parent,
            runner=runner,
            ffmpeg="ffmpeg",
        )

    def test_dick_van_dyke_copies_h264_and_transcodes_eac3_for_chrome(self) -> None:
        """MKV H.264 + E-AC-3, Chrome without E-AC-3, is audio-only with the video copied."""
        chrome = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [{"codec": "h264", "max_level": "5.2"}],
                "audio": ["aac"],
                "captions": ["webvtt"],
            }
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "projectionist.engine.media_slot.shutil.which",
                side_effect=_which,
            ),
        ):
            media = Path(tmp) / "dick-van-dyke.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("h264", "eac3", level="41")
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = self._open(
                asset, chrome, runner, title="The Lady and the Tiger and the Lawyer"
            )
            command = list(seen["cmd"])
            args = _ffmpeg_args(command)
            joined = " ".join(args)
            self.assertEqual(session.plan, "audio")
            self.assertTrue(session.playable)
            self.assertIn("E-AC-3", session.reason)
            self.assertEqual(command[:6], ["nice", "-n", "19", "ionice", "-c", "3"])
            self.assertIn("-c:v copy", joined)
            self.assertIn("-c:a aac", joined)
            self.assertNotIn("-c copy", joined)
            for banned in ("libx264", "libx265", "hevc_nvenc", "h264_nvenc", "h264_vaapi"):
                self.assertNotIn(banned, args)
            master = (session.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn('CODECS="avc1.640028,mp4a.40.2"', master)
            self.assertNotIn("ec-3", master)
            self.assertNotIn("/plex", master)
            self.assertNotIn(str(media), str(session.public()))

    def test_surround_aac_publishes_the_playlist_and_names_the_layout(self) -> None:
        """5.1(side) TrueHD and DTS must not wait for ffmpeg to exit, and must not
        leave AAC with an unnamed channel layout. A lower profile max downmixes.
        """
        chrome = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [{"codec": "h264", "max_level": "5.2"}],
                "audio": ["aac"],
                "captions": ["webvtt"],
                "max_channels": 6,
            }
        )
        stereo = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [{"codec": "h264", "max_level": "5.2"}],
                "audio": ["aac"],
                "captions": ["webvtt"],
                "max_channels": 2,
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "night.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("h264", "truehd", level="41")
            asset.probe.streams[1].channels = 6
            asset.probe.streams[1].channel_layout = "5.1(side)"
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = self._open(asset, chrome, runner, title="30 Days of Night")
            args = _ffmpeg_args(list(seen["cmd"]))
            playlist = args[args.index("-hls_playlist_type") + 1]
            self.assertEqual(playlist, "event")
            self.assertNotIn("vod", args)
            self.assertEqual(args[args.index("-ac") + 1], "6")
            self.assertEqual(args[args.index("-channel_layout") + 1], "5.1")
            master = (session.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn('CODECS="avc1.640028,mp4a.40.2"', master)
            self.assertIn('CHANNELS="6"', master)

            seen.clear()
            narrow = self._open(asset, stereo, runner, title="13")
            narrow_args = _ffmpeg_args(list(seen["cmd"]))
            self.assertEqual(narrow_args[narrow_args.index("-ac") + 1], "2")
            self.assertEqual(narrow_args[narrow_args.index("-channel_layout") + 1], "stereo")
            narrow_master = (narrow.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn('CHANNELS="2"', narrow_master)
            self.assertNotIn('CHANNELS="6"', narrow_master)

    def test_dts_with_playable_hevc_is_audio_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("hevc", "dts", level="153", bit_depth=8)
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = self._open(asset, SAFARI, runner, title="A DTS film")
            joined = " ".join(_ffmpeg_args(list(seen["cmd"])))
            self.assertEqual(session.plan, "audio")
            self.assertTrue(session.playable)
            self.assertIn("DTS", session.reason)
            self.assertIn("-c:v copy", joined)
            self.assertIn("-c:a aac", joined)
            self.assertNotIn("libx265", joined)
            master = (session.directory / "master.m3u8").read_text(encoding="utf-8")
            self.assertIn("hvc1", master)
            self.assertIn("mp4a.40.2", master)

    def test_hevc_above_the_profile_tries_once_and_copies_the_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("hevc", "dts", level="186", bit_depth=10)
            asset.rating_key = "134335"
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = self._open(asset, SAFARI, runner, title="Mulholland Drive")
            joined = " ".join(_ffmpeg_args(list(seen["cmd"])))
            self.assertEqual(session.plan, "try")
            self.assertTrue(session.playable)
            self.assertIn("-c:v copy", joined)
            self.assertIn("-c:a aac", joined)
            self.assertNotIn("libx265", joined)
            self.assertNotIn("libx264", joined)

            from projectionist.engine.tries import record_first_frame

            record_first_frame(
                Path(tmp),
                rating_key="134335",
                profile_id=SAFARI.id,
                arrived=False,
            )

            def refused(cmd, cwd):
                del cmd, cwd
                raise AssertionError("a remembered miss must not start another audio transcode")

            again = self._open(asset, SAFARI, refused, title="Mulholland Drive")
            self.assertEqual(again.plan, "source-transcode")
            self.assertFalse(again.playable)
            self.assertEqual(again.master_url(), "")

    def test_truehd_on_apple_tv_copies_h264(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            asset = _asset("h264", "truehd", level="41")
            asset.local_path = str(media)
            seen: dict[str, object] = {}

            def runner(cmd, cwd):
                seen["cmd"] = list(cmd)
                Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")

            session = self._open(asset, APPLE_TV_4K, runner, title="A TrueHD film")
            joined = " ".join(_ffmpeg_args(list(seen["cmd"])))
            self.assertEqual(session.plan, "audio")
            self.assertTrue(session.playable)
            self.assertIn("-c:v copy", joined)
            self.assertIn("-c:a aac", joined)
            self.assertIn("TrueHD", session.reason)

    def test_an_audio_transcode_does_not_block_a_play_probe(self) -> None:
        from projectionist.engine.media_slot import _SLOT

        started = threading.Event()
        release = threading.Event()
        second = threading.Event()

        def hold(cmd, cwd):
            del cmd
            Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
            started.set()
            release.wait(5)

        def waiting(cmd, cwd):
            del cmd
            Path(cwd, "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
            second.set()

        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            first = _asset("h264", "eac3")
            first.local_path = str(media)
            other = _asset("h264", "dts")
            other.rating_key = "161001"
            other.local_path = str(media)

            holder = threading.Thread(
                target=lambda: self._open(first, CHROME, hold, title="Holding")
            )
            holder.start()
            self.assertTrue(started.wait(2))
            self.assertTrue(_SLOT.locked())
            seen: dict[str, object] = {}

            def play_probe() -> None:
                def runner(cmd, **kwargs):
                    del kwargs
                    completed = MagicMock()
                    completed.returncode = 0
                    completed.stdout = json.dumps(
                        {
                            "format": {
                                "format_name": "matroska",
                                "duration": "1",
                                "bit_rate": "1",
                                "size": "1",
                            },
                            "streams": [],
                        }
                    )
                    completed.stderr = ""
                    seen["probe_cmd"] = list(cmd)
                    return completed

                seen["probe"] = probe_file(
                    str(media),
                    cache_dir=Path(tmp) / "cache",
                    runner=runner,
                    ffprobe="ffprobe",
                    background=False,
                )

            prober = threading.Thread(target=play_probe)
            follower = threading.Thread(
                target=lambda: self._open(other, CHROME, waiting, title="Waiting")
            )
            try:
                prober.start()
                prober.join(1.0)
                self.assertFalse(prober.is_alive(), "a Play probe waited on the audio transcode")
                probe_cmd = list(seen["probe_cmd"])
                self.assertEqual(probe_cmd[0], "ffprobe")
                self.assertNotIn("nice", probe_cmd)

                follower.start()
                follower.join(0.3)
                self.assertFalse(
                    second.is_set(), "a second heavy ffmpeg started while the slot was held"
                )
            finally:
                release.set()
                holder.join(2)
                if follower.is_alive() or follower.ident:
                    follower.join(2)
            self.assertTrue(second.is_set())

    def test_background_ffmpeg_is_idle_and_stops_when_the_session_is_cancelled(self) -> None:
        started = threading.Event()
        finished = threading.Event()
        seen: dict[str, object] = {}

        class FakeProcess:
            def __init__(self, command, cwd, stdout, stderr):
                del cwd, stdout, stderr
                seen["cmd"] = list(command)
                started.set()

            def poll(self):
                return None

            def wait(self, timeout=None):
                del timeout
                finished.wait(2)
                return 0

            def terminate(self):
                seen["terminated"] = True
                finished.set()

            def kill(self):
                seen["killed"] = True
                finished.set()

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "projectionist.engine.media_slot.shutil.which",
                side_effect=_which,
            ),
            patch("projectionist.engine.media_slot.subprocess.Popen", FakeProcess),
        ):
            media = Path(tmp) / "film.mkv"
            media.write_bytes(b"mkv")
            from projectionist.engine.audio import start_audio_transcode

            start_audio_transcode(
                media,
                Path(tmp) / "session",
                probe=_asset("h264", "eac3").probe,
                file_size=100,
                duration_ms=1_000,
                audio_codec="aac",
                ffmpeg="ffmpeg",
                still_wanted=lambda: True,
                attach=lambda _process: False,
            )
            self.assertTrue(started.wait(2))
            finished.wait(2)
            command = list(seen["cmd"])
            self.assertEqual(command[:6], ["nice", "-n", "19", "ionice", "-c", "3"])
            self.assertIn("projectionist.engine.copied_hls", command)
            from projectionist.engine.audio import audio_transcode_command

            inner = audio_transcode_command("ffmpeg", media, "aac", output="frag")
            self.assertEqual(inner[inner.index("-c:v") + 1], "copy")
            self.assertNotIn("libx264", inner)
            self.assertTrue(seen.get("terminated"))
