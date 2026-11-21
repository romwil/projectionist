"""ENG-002: planner order and recorded reasons. No file paths in the plan."""

from __future__ import annotations

import unittest

from projectionist.engine.planner import plan_playback
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import APPLE_TV_4K, CHROME, SAFARI, VideoCapability
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

    def test_hevc_level_idc_and_the_browser_level_use_the_same_scale(self) -> None:
        profile = _web(
            [VideoCapability("hevc", "5.1", bit_depth=10), VideoCapability("h264", "5.2")],
            ["aac"],
        )
        at_limit = _av("mkv", "hevc", "aac", level="153")
        at_limit.probe.streams[0].bit_depth = 10
        played = plan_playback(at_limit, profile)
        self.assertEqual(played["plan"], "remux")

        dotted = _av("mkv", "hevc", "aac", level="153.0")
        dotted.probe.streams[0].bit_depth = 10
        self.assertEqual(plan_playback(dotted, profile)["plan"], "remux")

        major_minor = _av("mkv", "hevc", "aac", level="5.1")
        major_minor.probe.streams[0].bit_depth = 10
        self.assertEqual(plan_playback(major_minor, profile)["plan"], "remux")

        # ffprobe level 186 is HEVC 6.2. Mulholland Drive is this file.
        above = _av("mkv", "hevc", "aac", level="186")
        above.probe.streams[0].bit_depth = 10
        refused = plan_playback(above, profile)
        self.assertEqual(refused["plan"], "full")
        self.assertIn("hevc level is above profile hevc 5.1", str(refused["reason"]))

    def test_level_above_the_profile_is_a_full_transcode(self) -> None:
        plan = plan_playback(_av("mp4", "h264", "aac", level="52"), DeviceProfileLow())
        self.assertEqual(plan["plan"], "full")

    def test_web_profile_remuxes_hevc_only_when_the_browser_lists_it(self) -> None:
        hevc = _av("mkv", "hevc", "aac", level="153")
        hevc.probe.streams[0].bit_depth = 10
        capable = _web(
            [VideoCapability("hevc", "5.1", bit_depth=10), VideoCapability("h264", "5.2")],
            ["aac"],
        )
        played = plan_playback(hevc, capable)
        self.assertEqual(played["plan"], "remux")
        self.assertEqual(played["profile_answer"]["video"], "hevc up to 5.1, 10-bit")
        self.assertIn("hevc up to 5.1, 10-bit", str(played["reason"]))

        refused = plan_playback(hevc, _web([VideoCapability("h264", "5.2")], ["aac"]))
        self.assertEqual(refused["plan"], "full")
        self.assertEqual(refused["profile_answer"]["video"], "hevc not in profile")
        self.assertIn("HEVC video is not playable on web", str(refused["reason"]))

        eight_bit = plan_playback(
            hevc,
            _web([VideoCapability("hevc", "5.1", bit_depth=8), VideoCapability("h264", "5.2")], ["aac"]),
        )
        self.assertEqual(eight_bit["plan"], "full")
        self.assertEqual(eight_bit["profile_answer"]["video"], "hevc 10-bit is above profile hevc 8-bit")

    def test_web_profile_remuxes_eac3_only_when_the_browser_lists_it(self) -> None:
        episode = _av("mkv", "h264", "eac3", level="41")
        refused = plan_playback(episode, _web([VideoCapability("h264", "5.2")], ["aac"]))
        self.assertEqual(refused["plan"], "audio")
        self.assertEqual(refused["profile_answer"]["audio"], "eac3 not in profile")
        self.assertEqual(refused["profile_answer"]["video"], "h264 up to 5.2")

        played = plan_playback(episode, _web([VideoCapability("h264", "5.2")], ["aac", "eac3"]))
        self.assertEqual(played["plan"], "remux")
        self.assertEqual(played["profile_answer"]["audio"], "eac3")

    def test_browser_profile_object_keeps_the_same_shape(self) -> None:
        from projectionist.engine.profiles import profile_from_mapping

        profile = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [
                    {"codec": "hevc", "max_level": "5.1", "bit_depth": 10},
                    {"codec": "h264", "max_level": "5.2"},
                ],
                "audio": ["aac", "eac3"],
                "captions": ["webvtt"],
            }
        )
        plan_asset = _av("mkv", "hevc", "eac3", level="153")
        plan_asset.probe.streams[0].bit_depth = 10
        plan = plan_playback(plan_asset, profile)
        self.assertEqual(profile.video[0].bit_depth, 10)
        self.assertEqual(plan["plan"], "remux")
        self.assertEqual(plan["profile_answer"]["audio"], "eac3")

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


def _web(video, audio):
    from projectionist.engine.profiles import DeviceProfile

    return DeviceProfile(
        id="web",
        containers=["mp4", "hls-fmp4"],
        video=video,
        audio=audio,
        captions=["webvtt"],
    )


def DeviceProfileLow():
    from projectionist.engine.profiles import DeviceProfile, VideoCapability

    return DeviceProfile(
        id="low",
        containers=["mp4", "hls-fmp4"],
        video=[VideoCapability("h264", "4.1")],
        audio=["aac"],
    )
