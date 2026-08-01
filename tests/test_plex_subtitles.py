"""Plex subtitle list / search / download helpers (P1e)."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from projectionist.connectors.plex import PlexClient, PlexSubtitleStream
from projectionist.library.subtitles import (
    DOWNLOAD_SOFT_FAIL,
    NO_CAPTIONS_AIRING,
    download_preferred_subtitles,
    has_preferred_subtitle,
    language_matches,
    list_item_subtitles,
    live_subtitles_payload,
    normalize_subtitle_language,
    preferred_subtitle_languages,
    srt_to_vtt,
)


class PlexSubtitleClientTests(unittest.TestCase):
    def _client(self) -> PlexClient:
        return PlexClient("http://plex.test:32400", "token")

    def test_list_subtitle_streams_parses_labels(self) -> None:
        xml = """
        <MediaContainer>
          <Video ratingKey="42" type="movie" title="Heat">
            <Media>
              <Part>
                <Stream id="1" streamType="1" codec="h264" />
                <Stream id="2" streamType="2" codec="aac" />
                <Stream id="9" streamType="3" language="English" languageCode="eng"
                        displayTitle="English (SRT External)" format="srt"
                        key="/library/streams/9" external="1" hearingImpaired="1" />
                <Stream id="10" streamType="3" language="Spanish" languageCode="spa"
                        displayTitle="Spanish" format="srt" forced="1"
                        key="/library/streams/10" />
              </Part>
            </Media>
          </Video>
        </MediaContainer>
        """
        client = self._client()
        with patch.object(client, "_request_xml", return_value=ET.fromstring(xml)):
            streams = client.list_subtitle_streams("42")
        self.assertEqual(len(streams), 2)
        self.assertTrue(streams[0].hearing_impaired)
        self.assertTrue(streams[0].external)
        self.assertIn("SDH", streams[0].to_dict()["label"])
        self.assertTrue(streams[1].forced)

    def test_search_and_download_hit_pms_paths(self) -> None:
        client = self._client()
        search_xml = """
        <MediaContainer>
          <Stream id="99" key="provider://sub/99" languageCode="en"
                  displayTitle="English" format="srt" />
        </MediaContainer>
        """
        paths: list[str] = []

        def fake_xml(path: str):
            paths.append(path)
            return ET.fromstring(search_xml)

        empty_paths: list[str] = []

        def fake_empty(path: str, *, method: str = "GET") -> None:
            empty_paths.append(f"{method}:{path}")

        with patch.object(client, "_request_xml", side_effect=fake_xml):
            hits = client.search_subtitles("42", language="en")
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].searchable)
        self.assertIn("/library/metadata/42/subtitles?", paths[0])
        self.assertIn("language=en", paths[0])

        with patch.object(client, "_request_empty", side_effect=fake_empty):
            client.download_subtitle("42", "provider://sub/99")
        self.assertEqual(len(empty_paths), 1)
        self.assertTrue(empty_paths[0].startswith("PUT:"))
        self.assertIn("key=provider", empty_paths[0])


class SubtitleServiceTests(unittest.TestCase):
    def test_normalize_and_match_language(self) -> None:
        self.assertEqual(normalize_subtitle_language("en-US"), "en")
        self.assertEqual(normalize_subtitle_language("eng"), "eng")
        stream = PlexSubtitleStream(id="1", language="English", language_code="eng")
        self.assertTrue(language_matches(stream, "en"))
        self.assertTrue(has_preferred_subtitle([stream], ["en"]))

    def test_srt_to_vtt(self) -> None:
        srt = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        vtt = srt_to_vtt(srt)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:01.000 --> 00:00:02.000", vtt)
        self.assertNotIn("\n1\n", f"\n{vtt}")

    def test_list_and_download_soft_fail(self) -> None:
        class _Tunarr:
            subtitle_language_primary = "en"
            subtitle_language_fallback = ""

        class _Settings:
            plex_url = "http://plex.test:32400"
            plex_token = "token"
            tunarr = _Tunarr()

        settings = _Settings()
        client = PlexClient("http://plex.test:32400", "token")

        with patch(
            "projectionist.library.subtitles.plex_client_from_settings",
            return_value=client,
        ), patch.object(client, "list_subtitle_streams", return_value=[]), patch.object(
            client, "search_subtitles", return_value=[]
        ):
            listed = list_item_subtitles(settings, "1")
            self.assertTrue(listed["ok"])
            self.assertFalse(listed["has_preferred"])
            result = download_preferred_subtitles(settings, "1")
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "none_found")
            self.assertIn("Plex couldn’t find", result["message"])
            self.assertEqual(result["message"], DOWNLOAD_SOFT_FAIL)

        bare = type("S", (), {"plex_url": "", "plex_token": "", "tunarr": _Tunarr()})()
        listed = list_item_subtitles(bare, "1")
        self.assertFalse(listed["ok"])
        self.assertEqual(listed["reason"], "plex_unconfigured")

    def test_live_payload_honest_empty_without_mapping(self) -> None:
        class _Tunarr:
            subtitle_language_primary = "en"
            subtitle_language_fallback = "es"

        class _Settings:
            plex_url = ""
            plex_token = ""
            tunarr = _Tunarr()

        payload = live_subtitles_payload(
            _Settings(),
            channel_id="ch-1",
            now_program={"title": "OTA News", "plex_rating_key": None},
        )
        self.assertEqual(payload["empty_message"], NO_CAPTIONS_AIRING)
        self.assertEqual(payload["reason"], "no_plex_mapping")
        self.assertEqual(preferred_subtitle_languages(_Settings()), ["en", "es"])


class ChannelCreateSubtitlesTests(unittest.TestCase):
    def test_channel_create_body_respects_settings_default(self) -> None:
        from projectionist.config_store import TunarrSettings
        from projectionist.live_channels.publish import channel_create_body
        from projectionist.live_channels.recipes import ChannelRecipe

        recipe = ChannelRecipe(name="Mystery", number=100, source="motif")
        off = channel_create_body(
            recipe,
            transcode_config_id="tc-1",
            channel_id="cid-1",
            start_time_ms=1_700_000_000_000,
        )
        self.assertFalse(off["channel"]["subtitlesEnabled"])

        class _Settings:
            tunarr = TunarrSettings(subtitles_enabled_default=True)

        on = channel_create_body(
            recipe,
            transcode_config_id="tc-1",
            channel_id="cid-2",
            start_time_ms=1_700_000_000_000,
            settings=_Settings(),
        )
        self.assertTrue(on["channel"]["subtitlesEnabled"])


class GuidePlexKeyTests(unittest.TestCase):
    def test_normalize_program_extracts_plex_rating_key(self) -> None:
        from projectionist.live_channels.guide import _normalize_program

        now = _normalize_program(
            {
                "title": "Heat",
                "start": 1_700_000_000_000,
                "stop": 1_700_007_200_000,
                "externalKey": "plex|src|4242",
            }
        )
        self.assertEqual(now["plex_rating_key"], "4242")


if __name__ == "__main__":
    unittest.main()
