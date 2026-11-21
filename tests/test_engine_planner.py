"""ENG-002: planner order and recorded reasons. No file paths in the plan."""

from __future__ import annotations

import unittest

from projectionist.engine.planner import plan_playback
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import CHROME, SAFARI, APPLE_TV_4K
from projectionist.engine.source import MediaAsset


def _asset(container: str, streams: list[MediaStream], *, readable: bool = True, reason: str = "") -> MediaAsset:
    return MediaAsset(
        rating_key="121986",
        source_path="/secret/film.mkv",
        local_path="/also/secret/film.mkv",
        readable=readable,
        reason=reason,
        probe=ProbeResult(
            container=container,
            format_name=container,
            duration_s=600.0,
            bitrate=4_500_000,
            size=100,
            streams=streams,
        )
        if readable
        else None,
    )


def _av(container: str, video: str, audio: str, *, level: str = "41") -> MediaAsset:
    return _asset(
        container,
        [
            MediaStream(index=0, codec_type="video", codec=video, width=1920, height=1080, level=level, profile="High"),
            MediaStream(index=1, codec_type="audio", codec=audio, channels=2, language="eng"),
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text"),
            MediaStream(
                index=3,
                codec_type="subtitle",
                codec="hdmv_pgs_subtitle",
                language="fre",
                subtitle_kind="image",
            ),
        ],
    )


class PlannerTests(unittest.TestCase):
    def test_apple_tv_remuxes_mkv_h264_ac3(self) -> None:
        plan = plan_playback(_av("mkv", "h264", "ac3"), APPLE_TV_4K)
        self.assertEqual(plan["plan"], "remux")
        self.assertIn("AC-3", str(plan["reason"]))
        self.assertIn("MKV", str(plan["reason"]))
        blob = str(plan)
        self.assertNotIn("/secret", blob)
        captions = plan["captions"]
        self.assertEqual(captions[0]["kind"], "text")
        self.assertTrue(captions[0]["ready"])
        self.assertEqual(captions[1]["kind"], "image-ocr")
        self.assertFalse(captions[1]["ready"])

    def test_chrome_audio_transcodes_ac3(self) -> None:
        plan = plan_playback(_av("mkv", "h264", "ac3"), CHROME)
        self.assertEqual(plan["plan"], "audio")
        self.assertIn("AC-3", str(plan["reason"]))

    def test_chrome_full_transcodes_hevc(self) -> None:
        plan = plan_playback(_av("mkv", "hevc", "aac", level="153"), CHROME)
        self.assertEqual(plan["plan"], "full")
        self.assertIn("HEVC", str(plan["reason"]))

    def test_safari_direct_plays_mp4_h264_aac(self) -> None:
        plan = plan_playback(_av("mp4", "h264", "aac"), SAFARI)
        self.assertEqual(plan["plan"], "direct")

    def test_safari_remuxes_mkv_hevc_eac3(self) -> None:
        plan = plan_playback(_av("mkv", "hevc", "eac3", level="153"), SAFARI)
        self.assertEqual(plan["plan"], "remux")

    def test_level_above_the_profile_is_a_full_transcode(self) -> None:
        plan = plan_playback(_av("mp4", "h264", "aac", level="52"), DeviceProfileLow())
        self.assertEqual(plan["plan"], "full")

    def test_unread_file_is_plex_fallback_without_paths(self) -> None:
        asset = MediaAsset(
            rating_key="9",
            source_path="/plex/only/film.mkv",
            readable=False,
            reason="No path mapping for this file",
        )
        plan = plan_playback(asset, APPLE_TV_4K)
        self.assertEqual(plan["plan"], "plex-fallback")
        self.assertIn("path mapping", str(plan["reason"]).lower())
        self.assertNotIn("/plex", str(plan))


def DeviceProfileLow():
    from projectionist.engine.profiles import DeviceProfile, VideoCapability

    return DeviceProfile(
        id="low",
        containers=["mp4", "hls-fmp4"],
        video=[VideoCapability("h264", "4.1")],
        audio=["aac"],
    )
