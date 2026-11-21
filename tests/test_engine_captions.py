"""ENG-007 caption fallback: household-language titles can remux; others wait."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.engine.captions import CAPTION_FALLBACK_REASON, caption_fallback_reason
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import MediaAsset


def _asset(subs: bool) -> MediaAsset:
    streams = [
        MediaStream(index=0, codec_type="video", codec="h264", level="41"),
        MediaStream(index=1, codec_type="audio", codec="aac"),
    ]
    if subs:
        streams.append(
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="en", subtitle_kind="text")
        )
    return MediaAsset(
        rating_key="121986",
        readable=True,
        probe=ProbeResult("mkv", "matroska", 10, 1, 1, streams),
    )


class CaptionFallbackTests(unittest.TestCase):
    def test_household_language_with_subs_can_use_the_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(True),
                title_language="en",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, "")

    def test_other_language_with_subs_stays_on_plex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(True),
                title_language="ja",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, CAPTION_FALLBACK_REASON)

    def test_no_captions_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reason = caption_fallback_reason(
                _asset(False),
                title_language="ja",
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertEqual(reason, "")

    def test_setting_defaults_off(self) -> None:
        self.assertFalse(Settings().engine.play_through_projectionist)
        turned = Settings.from_mapping({"engine": {"play_through_projectionist": True}})
        self.assertTrue(turned.engine.play_through_projectionist)
