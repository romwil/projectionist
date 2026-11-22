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

    def test_chrome_hevc_through_level_6_2_remuxes_and_above_that_is_a_try(self) -> None:
        """Chrome 157 accepted Main and Main 10 through level 6.2, hvc1 and hev1.

        Level 186 is 6.2, so it is a remux. A higher level idc is above that
        advertised level and is a try. A remembered miss is not tried again.
        """
        within = _av("mkv", "hevc", "aac", level="153")
        within.probe.streams[0].bit_depth = 10
        played = plan_playback(within, CHROME)
        self.assertEqual(played["plan"], "remux")
        self.assertIn("hevc up to 6.2, 10-bit", str(played["profile_answer"]["video"]))

        at_ceiling = _av("mkv", "hevc", "aac", level="186")
        at_ceiling.probe.streams[0].bit_depth = 10
        ceiling = plan_playback(at_ceiling, CHROME)
        self.assertEqual(ceiling["plan"], "remux")

        above = _av("mkv", "hevc", "aac", level="189")
        above.rating_key = "134335"
        above.probe.streams[0].bit_depth = 10
        tried = plan_playback(above, CHROME)
        self.assertEqual(tried["plan"], "try")
        self.assertIn("hevc level is above profile hevc 6.2", str(tried["profile_answer"]["video"]))
        again = plan_playback(above, CHROME, failed_tries={("134335", "chrome")})
        self.assertEqual(again["plan"], "source-transcode")
        self.assertNotEqual(again["plan"], "try")
        self.assertEqual(again["source_reason"], "level")

    def test_a_later_source_can_answer_the_same_request(self) -> None:
        class LaterSource:
            def source_transcode(self, *, reason: str, source_reason: str) -> dict:
                return {
                    "plan": "something-else",
                    "reason": reason,
                    "source_reason": source_reason,
                    "provider": "jellyfin",
                    "playable": True,
                }

        plan = plan_playback(
            _av("mkv", "av1", "aac", level="153"),
            CHROME,
            source=LaterSource(),
        )
        self.assertEqual(plan["plan"], "source-transcode")
        self.assertEqual(plan["provider"], "jellyfin")
        self.assertEqual(plan["source_reason"], "codec")
        self.assertFalse(plan["playable"])
        self.assertIn("AV1", str(plan["reason"]))

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

        # ffprobe level 186 is HEVC 6.2. The first plan is a try, not a transcode.
        above = _av("mkv", "hevc", "aac", level="186")
        above.probe.streams[0].bit_depth = 10
        tried = plan_playback(above, profile)
        self.assertEqual(tried["plan"], "try")
        self.assertIn("hevc level is above profile hevc 5.1", str(tried["reason"]))
        self.assertNotIn("playable", str(tried["reason"]))

    def test_level_above_the_profile_asks_the_source_to_transcode(self) -> None:
        plan = plan_playback(_av("mp4", "h264", "aac", level="52"), DeviceProfileLow())
        self.assertEqual(plan["plan"], "source-transcode")
        self.assertEqual(plan["source_reason"], "level")
        self.assertFalse(plan["playable"])

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
        self.assertEqual(refused["plan"], "source-transcode")
        self.assertEqual(refused["source_reason"], "codec")
        self.assertEqual(refused["profile_answer"]["video"], "hevc not in profile")
        self.assertIn("HEVC video is not playable on web", str(refused["reason"]))

        eight_bit = plan_playback(
            hevc,
            _web([VideoCapability("hevc", "5.1", bit_depth=8), VideoCapability("h264", "5.2")], ["aac"]),
        )
        self.assertEqual(eight_bit["plan"], "source-transcode")
        self.assertEqual(eight_bit["source_reason"], "bit_depth")
        self.assertEqual(eight_bit["profile_answer"]["video"], "hevc 10-bit is above profile hevc 8-bit")

    def test_an_8_bit_level_is_not_hidden_by_a_lower_10_bit_row(self) -> None:
        eight = _av("mkv", "hevc", "aac", level="153")
        eight.probe.streams[0].bit_depth = 8
        both = _web(
            [
                VideoCapability("hevc", "4.0", bit_depth=10),
                VideoCapability("hevc", "5.1", bit_depth=8),
                VideoCapability("h264", "5.2"),
            ],
            ["aac"],
        )
        self.assertEqual(plan_playback(eight, both)["plan"], "remux")
        only_ten = _web(
            [VideoCapability("hevc", "4.0", bit_depth=10), VideoCapability("h264", "5.2")],
            ["aac"],
        )
        hidden = plan_playback(eight, only_ten)
        self.assertEqual(hidden["plan"], "try")
        self.assertIn("hevc level is above profile hevc 4.0", str(hidden["profile_answer"]["video"]))
        self.assertNotEqual(hidden["plan"], "remux")
        high_ten = _av("mkv", "hevc", "aac", level="153")
        high_ten.probe.streams[0].bit_depth = 10
        above_bits = plan_playback(high_ten, both)
        self.assertEqual(above_bits["plan"], "source-transcode")
        self.assertEqual(above_bits["source_reason"], "bit_depth")

    def test_web_profile_remuxes_flac_only_when_the_browser_lists_it(self) -> None:
        # Adventures of Zatoichi is H.264 + FLAC. A reported FLAC answer remuxes.
        # A browser that does not report it stays audio-only, not a fake remux.
        film = _av("mkv", "h264", "flac", level="41")
        refused = plan_playback(film, _web([VideoCapability("h264", "5.2")], ["aac"]))
        self.assertEqual(refused["plan"], "audio")
        self.assertEqual(refused["profile_answer"]["audio"], "flac not in profile")
        self.assertEqual(refused["profile_answer"]["video"], "h264 up to 5.2")
        self.assertIn("FLAC audio is not", str(refused["reason"]))

        played = plan_playback(film, _web([VideoCapability("h264", "5.2")], ["aac", "flac"]))
        self.assertEqual(played["plan"], "remux")
        self.assertEqual(played["profile_answer"]["audio"], "flac")
        self.assertIn("FLAC", str(played["reason"]))

        opus = plan_playback(
            _av("mkv", "h264", "opus", level="41"),
            _web([VideoCapability("h264", "5.2")], ["aac", "opus"]),
        )
        self.assertEqual(opus["plan"], "remux")
        self.assertEqual(opus["profile_answer"]["audio"], "opus")
        missing_opus = plan_playback(
            _av("mkv", "h264", "opus", level="41"),
            _web([VideoCapability("h264", "5.2")], ["aac"]),
        )
        self.assertEqual(missing_opus["plan"], "audio")
        self.assertEqual(missing_opus["profile_answer"]["audio"], "opus not in profile")

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

    def test_mulholland_drive_first_plan_is_a_try(self) -> None:
        """Probed facts: HEVC Main 10, level 186 (6.2), 10-bit, HDR10, 1920×1032.

        Above the advertised HEVC level is a remux try, not a transcode and not
        a claim that the picture is playable. DTS-HD MA still needs audio work.
        """
        film = _mulholland_drive()
        video = film.probe.streams[0]
        self.assertEqual(video.profile, "Main 10")
        self.assertEqual(video.level, "186")
        self.assertEqual(video.bit_depth, 10)
        self.assertEqual(video.hdr, "hdr10")
        self.assertEqual((video.width, video.height), (1920, 1032))
        self.assertEqual(film.probe.streams[1].profile, "DTS-HD MA")
        self.assertEqual(film.probe.duration_s, 8840.299)

        safari = plan_playback(film, SAFARI)
        apple = plan_playback(film, APPLE_TV_4K)
        self.assertEqual(safari["plan"], "try")
        self.assertEqual(apple["plan"], "try")
        self.assertNotIn("playable", str(safari["reason"]))
        self.assertIn("hevc level is above profile hevc 5.1", str(safari["profile_answer"]["video"]))
        self.assertIn("dts not in profile", str(safari["profile_answer"]["audio"]))
        self.assertTrue(safari.get("audio_transcode"))
        self.assertNotIn("/secret", str(safari))

    def test_a_remembered_failure_is_not_tried_again(self) -> None:
        film = _mulholland_drive()
        again = plan_playback(film, SAFARI, failed_tries={("134335", "safari")})
        self.assertEqual(again["plan"], "source-transcode")
        self.assertNotEqual(again["plan"], "try")
        self.assertFalse(again["playable"])
        self.assertEqual(again["source_reason"], "level")
        self.assertIn("did not show a picture", str(again["reason"]))
        other_device = plan_playback(film, APPLE_TV_4K, failed_tries={("134335", "safari")})
        self.assertEqual(other_device["plan"], "try")

    def test_a_device_that_does_not_report_hdr_does_not_get_an_hdr_try(self) -> None:
        """HDR10 inside the advertised level is a try only when the device reports HDR."""
        film = _asset(
            "mkv",
            [
                MediaStream(
                    index=0,
                    codec_type="video",
                    codec="hevc",
                    profile="Main 10",
                    level="153",
                    bit_depth=10,
                    hdr="hdr10",
                    hdr_known=True,
                    width=1920,
                    height=1032,
                ),
                MediaStream(index=1, codec_type="audio", codec="aac", channels=2, language="eng"),
            ],
        )
        film.rating_key = "134335"
        silent = plan_playback(film, SAFARI)
        self.assertNotEqual(silent["plan"], "try")
        self.assertEqual(silent["plan"], "remux")

        reporting = _web(
            [VideoCapability("hevc", "5.1", ["hdr10"]), VideoCapability("h264", "5.2")],
            ["aac"],
        )
        tried = plan_playback(film, reporting)
        self.assertEqual(tried["plan"], "try")
        self.assertIn("hdr10", str(tried["profile_answer"]["video"]))
        self.assertNotIn("level is above", str(tried["profile_answer"]["video"]))

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


def _mulholland_drive() -> MediaAsset:
    """Rating key 134335. Duration 8840299 ms. The picture is above HEVC 5.1."""
    asset = _asset(
        "mkv",
        [
            MediaStream(
                index=0,
                codec_type="video",
                codec="hevc",
                profile="Main 10",
                level="186",
                bit_depth=10,
                hdr="hdr10",
                hdr_known=True,
                width=1920,
                height=1032,
            ),
            MediaStream(
                index=1,
                codec_type="audio",
                codec="dts",
                profile="DTS-HD MA",
                channels=6,
                language="eng",
            ),
        ],
    )
    asset.rating_key = "134335"
    asset.probe.duration_s = 8840.299
    return asset


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
