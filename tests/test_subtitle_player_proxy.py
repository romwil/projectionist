"""Player-facing subtitle proxy: embedded + sidecar tracks become fetchable WebVTT."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from projectionist.connectors.plex import PlexClient, PlexSubtitleStream
from projectionist.library.subtitles import (
    IMAGE_SUBTITLE_NOTE,
    decorate_subtitle_row,
    fetch_subtitle_vtt,
    list_item_subtitles,
    live_subtitles_payload,
    srt_to_vtt,
    subtitle_fetch_paths,
    subtitle_is_renderable,
)


class _Tunarr:
    subtitle_language_primary = "en"
    subtitle_language_fallback = ""


class _Settings:
    plex_url = "http://plex.test:32400"
    plex_token = "SECRET-TOKEN"
    tunarr = _Tunarr()


EMBEDDED = PlexSubtitleStream(
    id="9001", language="English", language_code="eng", format="srt", key="", display_title="English (SRT)"
)
SIDECAR = PlexSubtitleStream(
    id="9002", language="English", language_code="eng", format="srt", key="/library/streams/9002", external=True
)
PGS = PlexSubtitleStream(
    id="9003", language="Japanese", language_code="jpn", format="pgs", key=""
)


class FetchPathTests(unittest.TestCase):
    def test_embedded_track_without_key_gets_stream_route(self) -> None:
        paths = subtitle_fetch_paths(EMBEDDED.to_dict())
        self.assertEqual(paths[0], "/library/streams/9001?encoding=utf-8&format=srt")
        self.assertIn("/library/streams/9001", paths)

    def test_sidecar_srt_prefers_native_file(self) -> None:
        paths = subtitle_fetch_paths(SIDECAR.to_dict())
        self.assertEqual(paths[0], "/library/streams/9002?encoding=utf-8")

    def test_ass_sidecar_asks_plex_for_srt(self) -> None:
        row = {**SIDECAR.to_dict(), "format": "ass"}
        self.assertTrue(subtitle_fetch_paths(row)[0].endswith("format=srt"))

    def test_non_numeric_id_without_key_has_no_path(self) -> None:
        self.assertEqual(subtitle_fetch_paths({"id": "abc", "key": ""}), [])


class DecorateTests(unittest.TestCase):
    def test_embedded_text_track_is_renderable_with_proxy_url_and_no_token(self) -> None:
        row = decorate_subtitle_row("123", EMBEDDED.to_dict())
        self.assertTrue(row["renderable"])
        self.assertEqual(row["proxy_url"], "/api/library/items/123/subtitles/9001/file")
        self.assertNotIn("SECRET", str(row))
        self.assertNotIn("X-Plex-Token", str(row))

    def test_image_track_is_listed_but_not_selectable(self) -> None:
        self.assertFalse(subtitle_is_renderable(PGS.to_dict()))
        row = decorate_subtitle_row("123", PGS.to_dict())
        self.assertFalse(row["renderable"])
        self.assertEqual(row["proxy_url"], "")
        self.assertEqual(row["unavailable_reason"], IMAGE_SUBTITLE_NOTE)

    def test_list_item_subtitles_decorates_every_row(self) -> None:
        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        with patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "list_subtitle_streams", return_value=[EMBEDDED, SIDECAR, PGS]
        ):
            listed = list_item_subtitles(_Settings(), "123")
        urls = [row["proxy_url"] for row in listed["streams"]]
        self.assertEqual(
            urls,
            [
                "/api/library/items/123/subtitles/9001/file",
                "/api/library/items/123/subtitles/9002/file",
                "",
            ],
        )

    def test_live_payload_carries_embedded_proxy_urls(self) -> None:
        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        with patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "list_subtitle_streams", return_value=[EMBEDDED]
        ):
            payload = live_subtitles_payload(
                _Settings(), channel_id="104", now_program={"title": "Drunken Master", "plex_rating_key": "55"}
            )
        self.assertEqual(payload["plex_streams"][0]["proxy_url"], "/api/library/items/55/subtitles/9001/file")


class FetchVttTests(unittest.TestCase):
    def test_falls_back_to_next_path_and_returns_vtt(self) -> None:
        client = PlexClient("http://plex.test:32400", "t")
        calls: list[str] = []

        def fake_fetch(path: str) -> bytes:
            calls.append(path)
            if "format=srt" in path:
                raise RuntimeError("HTTP Error 404")
            return b"\xef\xbb\xbf1\r\n00:00:01,500 --> 00:00:03,000\r\nHello there\r\n"

        with patch.object(client, "fetch_subtitle_bytes", side_effect=fake_fetch):
            vtt = fetch_subtitle_vtt(client, EMBEDDED.to_dict())
        self.assertEqual(len(calls), 2)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:01.500 --> 00:00:03.000", vtt)
        self.assertIn("Hello there", vtt)

    def test_all_paths_failing_raises_last_error(self) -> None:
        client = PlexClient("http://plex.test:32400", "t")
        with patch.object(client, "fetch_subtitle_bytes", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                fetch_subtitle_vtt(client, EMBEDDED.to_dict())

    def test_empty_body_is_an_error_not_blank_captions(self) -> None:
        client = PlexClient("http://plex.test:32400", "t")
        with patch.object(client, "fetch_subtitle_bytes", return_value=b"  \n"):
            with self.assertRaises(ValueError):
                fetch_subtitle_vtt(client, EMBEDDED.to_dict())

    def test_numeric_only_cue_text_survives_srt_conversion(self) -> None:
        vtt = srt_to_vtt("1\n00:00:01,000 --> 00:00:02,000\n42\n\n2\n00:00:03,000 --> 00:00:04,000\nBye\n")
        self.assertIn("\n42\n", vtt)
        self.assertNotIn("\n2\n00:00:03", vtt)


class FileRouteTests(unittest.TestCase):
    """Call the route function directly (no DATA_DIR / auth middleware needed)."""

    def _call(self, stream_id: str, *, fetch):
        from projectionist.web import app as app_mod

        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        listed = {
            "ok": True,
            "streams": [
                decorate_subtitle_row("123", EMBEDDED.to_dict()),
                decorate_subtitle_row("123", PGS.to_dict()),
            ],
        }
        with patch.object(app_mod, "_settings", return_value=_Settings()), patch(
            "projectionist.library.subtitles.list_item_subtitles", return_value=listed
        ), patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "fetch_subtitle_bytes", **fetch
        ):
            return app_mod.library_item_subtitle_file_endpoint("123", stream_id, user=None)

    def test_route_serves_vtt_without_token(self) -> None:
        resp = self._call("9001", fetch={"return_value": b"1\n00:00:01,000 --> 00:00:02,000\nHi\n"})
        self.assertTrue(resp.media_type.startswith("text/vtt"))
        body = resp.body.decode()
        self.assertIn("Hi", body)
        self.assertNotIn("SECRET", body)

    def test_image_track_is_415_with_honest_copy(self) -> None:
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            self._call("9003", fetch={"return_value": b""})
        self.assertEqual(ctx.exception.status_code, 415)
        self.assertIn("picture-based", ctx.exception.detail)

    def test_unknown_track_is_404(self) -> None:
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            self._call("404", fetch={"return_value": b""})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_plex_failure_is_502(self) -> None:
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            self._call("9001", fetch={"side_effect": RuntimeError("down")})
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
