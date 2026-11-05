"""Player-facing subtitle proxy: embedded + sidecar tracks become fetchable WebVTT."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from projectionist.connectors.plex import PlexClient, PlexSubtitleStream
from projectionist.library.subtitles import (
    IMAGE_SUBTITLE_NOTE,
    decorate_subtitle_row,
    fetch_subtitle_vtt,
    is_our_subtitle_proxy_url,
    list_item_subtitles,
    live_subtitles_payload,
    sanitize_live_plex_streams,
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
PGS_SIDECAR = PlexSubtitleStream(
    id="9004",
    language="English",
    language_code="eng",
    format="pgs",
    key="/library/streams/9004",
    display_title="English (PGS Overlay)",
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
        self.assertFalse(row["image"])
        self.assertEqual(row["proxy_url"], "/api/library/items/123/subtitles/9001/file")
        self.assertNotIn("SECRET", str(row))
        self.assertNotIn("X-Plex-Token", str(row))

    def test_image_track_is_listed_but_not_selectable(self) -> None:
        self.assertFalse(subtitle_is_renderable(PGS.to_dict()))
        row = decorate_subtitle_row("123", PGS.to_dict())
        self.assertFalse(row["renderable"])
        self.assertTrue(row["image"])
        self.assertEqual(row["proxy_url"], "")
        self.assertEqual(row["unavailable_reason"], IMAGE_SUBTITLE_NOTE)

    def test_overlay_sidecar_with_plex_key_is_not_a_text_proxy(self) -> None:
        self.assertFalse(subtitle_is_renderable(PGS_SIDECAR.to_dict()))
        row = decorate_subtitle_row("55", PGS_SIDECAR.to_dict())
        self.assertFalse(row["renderable"])
        self.assertEqual(row["proxy_url"], "")
        self.assertFalse(is_our_subtitle_proxy_url("/library/streams/9004"))
        self.assertFalse(is_our_subtitle_proxy_url("plex://streams/9004"))
        self.assertTrue(is_our_subtitle_proxy_url("/api/library/items/55/subtitles/9001/file"))

    def test_overlay_label_is_not_renderable_even_when_format_says_srt(self) -> None:
        row = {
            "id": "8",
            "format": "srt",
            "key": "/library/streams/8",
            "display_title": "English (PGS Overlay)",
        }
        self.assertFalse(subtitle_is_renderable(row))
        decorated = decorate_subtitle_row("55", row)
        self.assertEqual(decorated["proxy_url"], "")

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
        self.assertTrue(is_our_subtitle_proxy_url(payload["plex_streams"][0]["proxy_url"]))

    def test_live_payload_does_not_advertise_overlay_sidecar_as_text(self) -> None:
        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        with patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "list_subtitle_streams", return_value=[PGS_SIDECAR]
        ):
            payload = live_subtitles_payload(
                _Settings(), channel_id="104", now_program={"title": "Heat", "plex_rating_key": "55"}
            )
        row = payload["plex_streams"][0]
        self.assertEqual(row["proxy_url"], "")
        self.assertFalse(row["renderable"])
        self.assertNotIn("plex://", str(payload))
        self.assertNotIn("/library/streams/", str(row.get("proxy_url") or ""))

    def test_sanitize_strips_plex_and_pms_urls(self) -> None:
        rows = sanitize_live_plex_streams(
            [
                {
                    "id": "1",
                    "renderable": True,
                    "proxy_url": "/api/library/items/55/subtitles/1/file",
                },
                {"id": "2", "renderable": True, "proxy_url": "plex://streams/2"},
                {"id": "3", "renderable": True, "proxy_url": "/library/streams/3"},
                {
                    "id": "4",
                    "renderable": False,
                    "proxy_url": "/api/library/items/55/subtitles/4/file",
                },
            ]
        )
        self.assertEqual(rows[0]["proxy_url"], "/api/library/items/55/subtitles/1/file")
        self.assertEqual(rows[1]["proxy_url"], "")
        self.assertFalse(rows[1]["renderable"])
        self.assertEqual(rows[2]["proxy_url"], "")
        self.assertEqual(rows[3]["proxy_url"], "")


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
        from projectionist.web import library_routes as library_mod

        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        listed = {
            "ok": True,
            "streams": [
                decorate_subtitle_row("123", EMBEDDED.to_dict()),
                decorate_subtitle_row("123", PGS.to_dict()),
            ],
        }
        with patch.object(library_mod, "_settings", return_value=_Settings()), patch(
            "projectionist.library.subtitles.list_item_subtitles", return_value=listed
        ), patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "fetch_subtitle_bytes", **fetch
        ):
            return library_mod.library_item_subtitle_file_endpoint("123", stream_id, user=None)

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
        self.assertNotIn("Plex", str(ctx.exception.detail))
        self.assertIn("text", str(ctx.exception.detail).lower())


# -- Household subtitle cache -------------------------------------------------

GOOD_SRT = b"1\n00:00:01,000 --> 00:00:03,000\nBonjour, hello there\n\n2\n00:00:04,000 --> 00:00:05,000\nBye\n"
FRENCH_TEXT = PlexSubtitleStream(
    id="7001", language="French", language_code="fra", format="srt", key="/library/streams/7001", external=True
)
ENGLISH_TEXT = PlexSubtitleStream(
    id="7002", language="English", language_code="eng", format="srt", key="/library/streams/7002", external=True
)
ENGLISH_PGS = PlexSubtitleStream(id="7003", language="English", language_code="eng", format="pgs", key="")

_OS_ENV = ("PROJECTIONIST_OPENSUBTITLES_API_KEY", "OPENSUBTITLES_API_KEY")


class _KeySettings(_Settings):
    def __init__(self, key: str = "os-key") -> None:
        self.opensubtitles_api_key = key


class _FakePlex:
    def __init__(self, streams=(), body: bytes = GOOD_SRT) -> None:
        self.streams = list(streams)
        self.body = body
        self.listed = 0
        self.fetched: list[str] = []

    def list_subtitle_streams(self, rating_key):
        self.listed += 1
        return list(self.streams)

    def fetch_subtitle_bytes(self, path):
        self.fetched.append(path)
        return self.body

    def media_file_paths(self, rating_key, include_leaves=False):
        return []


class _FakeOpenSubtitles:
    def __init__(self, *, body: bytes = GOOD_SRT, language: str = "en", hang: float = 0.0) -> None:
        self.body = body
        self.language = language
        self.hang = hang
        self.searches: list[dict] = []
        self.downloads: list = []

    def search(self, params):
        self.searches.append(dict(params))
        if self.hang:
            import time as _time

            _time.sleep(self.hang)
        return [
            {
                "attributes": {
                    "language": self.language,
                    "hearing_impaired": False,
                    "files": [{"file_id": 501, "file_name": "movie.srt"}],
                }
            }
        ]

    def download(self, file_id):
        self.downloads.append(file_id)
        return self.body, 50, None


def _library_db(tmp: str):
    import time as _time

    from projectionist.library.db import Database

    db = Database(Path(tmp) / "library.db")
    now = _time.time()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO library_items (rating_key, media_type, title, year, imdb_id, original_language, updated_at) "
            "VALUES ('100', 'movie', 'Amélie', 2001, 'tt0211915', 'fr', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO library_items (rating_key, media_type, title, year, imdb_id, original_language, updated_at) "
            "VALUES ('200', 'movie', 'Heat', 1995, 'tt0113277', 'en', ?)",
            (now,),
        )
        conn.execute(
            "INSERT INTO library_items (rating_key, media_type, title, year, imdb_id, original_language, updated_at) "
            "VALUES ('300', 'show', 'Lupin', 2021, 'tt2531336', 'fr', ?)",
            (now,),
        )
        show_id = conn.execute("SELECT id FROM library_items WHERE rating_key = '300'").fetchone()[0]
        conn.execute(
            "INSERT INTO library_episodes (show_item_id, rating_key, season_number, episode_number, title) "
            "VALUES (?, '301', 2, 3, 'Chapter 8')",
            (show_id,),
        )
    return db


class HouseholdSubtitleCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        import os
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.db = _library_db(self._tmp.name)
        self._env = patch.dict(os.environ, {"DATA_DIR": self._tmp.name})
        self._env.start()
        for name in _OS_ENV:
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def _ensure(self, key, *, plex, os_client=None, settings=None, **kwargs):
        from projectionist.library import subtitle_cache

        with patch.object(subtitle_cache, "OpenSubtitlesClient", return_value=os_client):
            return subtitle_cache.ensure_household_subtitle(
                settings or _KeySettings(),
                key,
                db=self.db,
                data_dir=self.data_dir,
                plex_client=plex,
                **kwargs,
            )

    def test_pgs_only_movie_gets_cached_srt_and_vtt(self) -> None:
        from projectionist.library.subtitle_cache import cache_path, cached_subtitle_vtt

        plex = _FakePlex([PGS, ENGLISH_PGS])
        opensubs = _FakeOpenSubtitles()
        result = self._ensure("100", plex=plex, os_client=opensubs)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["source"], "opensubtitles")
        path = cache_path("100", "en", data_dir=self.data_dir)
        self.assertEqual(path, self.data_dir / "subtitles" / "100" / "en.srt")
        self.assertTrue(path.is_file())
        self.assertEqual(plex.fetched, [], "bitmap tracks are never fetched as text")
        vtt = cached_subtitle_vtt("100", "cached-en", data_dir=self.data_dir)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:01.000 --> 00:00:03.000", vtt)
        self.assertEqual(result["track"]["proxy_url"], "/api/library/items/100/subtitles/cached-en/file")
        self.assertTrue(is_our_subtitle_proxy_url(result["track"]["proxy_url"]))

    def test_cached_file_route_serves_vtt(self) -> None:
        from projectionist.web import library_routes as library_mod

        self._ensure("100", plex=_FakePlex([PGS]), os_client=_FakeOpenSubtitles())
        resp = library_mod.library_item_subtitle_file_endpoint("100", "cached-en", user=None)
        self.assertTrue(resp.media_type.startswith("text/vtt"))
        self.assertIn("Bonjour", resp.body.decode())

    def test_english_movie_without_text_track_still_gets_a_file(self) -> None:
        opensubs = _FakeOpenSubtitles()
        result = self._ensure("200", plex=_FakePlex([ENGLISH_PGS]), os_client=opensubs)
        self.assertTrue(result["ok"], result)
        self.assertEqual(opensubs.searches[0].get("imdb_id"), "113277")
        self.assertEqual(opensubs.searches[0].get("year"), 1995)
        self.assertTrue((self.data_dir / "subtitles" / "200" / "en.srt").is_file())

    def test_episode_uses_parent_show_lookup(self) -> None:
        opensubs = _FakeOpenSubtitles()
        result = self._ensure("301", plex=_FakePlex([]), os_client=opensubs)
        self.assertTrue(result["ok"], result)
        query = opensubs.searches[0]
        self.assertEqual(query["parent_imdb_id"], "2531336")
        self.assertEqual(query["season_number"], 2)
        self.assertEqual(query["episode_number"], 3)
        self.assertNotIn("imdb_id", query)

    def test_plex_text_track_is_copied_without_opensubtitles(self) -> None:
        plex = _FakePlex([FRENCH_TEXT, ENGLISH_TEXT])
        opensubs = _FakeOpenSubtitles()
        result = self._ensure("100", plex=plex, os_client=opensubs)
        self.assertEqual(result["source"], "plex")
        self.assertEqual(opensubs.searches, [])
        self.assertTrue(plex.fetched and "7002" in plex.fetched[0])
        from projectionist.library.subtitle_state import get_state

        self.assertEqual(get_state(self.db, "100", "en")["status"], "cached")

    def test_cached_file_is_not_downloaded_again(self) -> None:
        opensubs = _FakeOpenSubtitles()
        self._ensure("200", plex=_FakePlex([]), os_client=opensubs)
        plex = _FakePlex([ENGLISH_TEXT])
        again = self._ensure("200", plex=plex, os_client=opensubs)
        self.assertEqual(again["reason"], "already_cached")
        self.assertEqual(len(opensubs.searches), 1)
        self.assertEqual(len(opensubs.downloads), 1)
        self.assertEqual(plex.listed, 0)

    def test_no_key_means_no_opensubtitles_call_and_plex_copy_still_works(self) -> None:
        opensubs = _FakeOpenSubtitles()
        miss = self._ensure("200", plex=_FakePlex([ENGLISH_PGS]), os_client=opensubs, settings=_KeySettings(""))
        self.assertEqual(miss["reason"], "no_opensubtitles_key")
        self.assertFalse(miss["opensubtitles_configured"])
        self.assertEqual(opensubs.searches, [])
        copied = self._ensure("100", plex=_FakePlex([ENGLISH_TEXT]), os_client=opensubs, settings=_KeySettings(""))
        self.assertEqual(copied["source"], "plex")
        self.assertEqual(opensubs.searches, [])

    def test_empty_body_is_not_cached(self) -> None:
        from projectionist.library.subtitle_state import get_state

        for body in (b"", b"   \n", b"<html><body>Error</body></html>"):
            result = self._ensure("200", plex=_FakePlex([]), os_client=_FakeOpenSubtitles(body=body))
            self.assertFalse(result["ok"])
            self.assertIsNone(result["track"])
            self.assertFalse((self.data_dir / "subtitles" / "200" / "en.srt").exists())
        state = get_state(self.db, "200", "en")
        self.assertEqual(state["status"], "retry")
        listed = list_item_subtitles(_Settings(), "200", db=self.db, data_dir=self.data_dir)
        self.assertFalse(any(str(r.get("id")).startswith("cached-") for r in listed["streams"]))

    def test_empty_plex_text_falls_through_and_is_not_cached(self) -> None:
        plex = _FakePlex([ENGLISH_TEXT], body=b"")
        result = self._ensure("200", plex=plex, os_client=None, settings=_KeySettings(""))
        self.assertFalse(result["ok"])
        self.assertFalse((self.data_dir / "subtitles" / "200").exists())

    def test_list_puts_cached_track_first_with_title_language(self) -> None:
        self._ensure("100", plex=_FakePlex([PGS]), os_client=_FakeOpenSubtitles())
        client = PlexClient("http://plex.test:32400", "SECRET-TOKEN")
        with patch("projectionist.library.subtitles.plex_client_from_settings", return_value=client), patch.object(
            client, "list_subtitle_streams", return_value=[PGS]
        ):
            listed = list_item_subtitles(_Settings(), "100", db=self.db, data_dir=self.data_dir)
        self.assertEqual(listed["streams"][0]["id"], "cached-en")
        self.assertTrue(listed["has_preferred"])
        self.assertEqual(listed["title_language"], "fr")
        self.assertEqual(listed["media_type"], "movie")

    def test_live_payload_carries_cache_language_and_media_type(self) -> None:
        self._ensure("100", plex=_FakePlex([PGS]), os_client=_FakeOpenSubtitles())
        with patch("projectionist.library.subtitles.plex_client_from_settings", return_value=None):
            payload = live_subtitles_payload(
                _Settings(),
                channel_id="9",
                now_program={"title": "Amélie", "plex_rating_key": "100", "media_type": "movie"},
                db=self.db,
                data_dir=self.data_dir,
            )
        self.assertEqual(payload["original_language"], "fr")
        self.assertEqual(payload["media_type"], "movie")
        self.assertEqual(payload["cached_track"]["id"], "cached-en")
        self.assertEqual(payload["plex_streams"][0]["proxy_url"], "/api/library/items/100/subtitles/cached-en/file")

    def test_live_payload_flex_never_lists_or_fetches(self) -> None:
        with patch("projectionist.library.subtitles.list_item_subtitles") as listed:
            payload = live_subtitles_payload(
                _Settings(),
                channel_id="9",
                now_program={"title": "Between programs", "plex_rating_key": "100", "is_flex": True},
                db=self.db,
            )
        listed.assert_not_called()
        self.assertFalse(payload["can_download"])
        self.assertTrue(payload["is_flex"])


if __name__ == "__main__":
    unittest.main()
