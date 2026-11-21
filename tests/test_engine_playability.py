"""ENG-011: the library playability report follows the planner. No file paths."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.engine.captions import CAPTION_FALLBACK_REASON, CAPTION_PENDING_REASON
from projectionist.engine.playability import (
    LibraryTitle,
    build_playability_report,
    hardware_sentence,
    library_titles,
    profiles_for_report,
)
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import SAFARI, profile_from_mapping
from projectionist.engine.source import MediaAsset
from projectionist.library.db import Database
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


def _probe(container: str, streams: list[MediaStream]) -> ProbeResult:
    return ProbeResult(container, container, 600.0, 4_000_000, 1000, streams)


def _av(container: str, video: str, audio: str, *, subs: list[MediaStream] | None = None) -> list[MediaStream]:
    rows = [
        MediaStream(index=0, codec_type="video", codec=video, level="41", width=1920, height=1080),
        MediaStream(index=1, codec_type="audio", codec=audio, language="eng", channels=2),
    ]
    rows.extend(subs or [])
    return rows


def _asset(
    key: str,
    container: str,
    video: str,
    audio: str,
    *,
    subs: list[MediaStream] | None = None,
    readable: bool = True,
    reason: str = "",
) -> MediaAsset:
    return MediaAsset(
        rating_key=key,
        source_path=f"/secret/library/{key}.{container}",
        local_path=f"/also/secret/{key}.{container}",
        readable=readable,
        reason=reason,
        probe=_probe(container, _av(container, video, audio, subs=subs)) if readable else None,
    )


def _text_sub() -> MediaStream:
    return MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text")


def _picture_sub() -> MediaStream:
    return MediaStream(
        index=2,
        codec_type="subtitle",
        codec="hdmv_pgs_subtitle",
        language="eng",
        subtitle_kind="image",
    )


class PlayabilityReportTests(unittest.TestCase):
    def test_tiers_follow_the_planner(self) -> None:
        titles = [
            LibraryTitle("direct", "Direct Feature", "en"),
            LibraryTitle("remux", "Remux Feature", "en"),
            LibraryTitle("pending", "Pending Captions", "ja"),
            LibraryTitle("picture", "Picture Captions", "ja"),
            LibraryTitle("audio", "Audio Feature", "en"),
            LibraryTitle("video", "Video Feature", "en"),
            LibraryTitle("missing", "Missing Feature", "en"),
        ]
        assets = {
            "direct": _asset("direct", "mp4", "h264", "aac"),
            "remux": _asset("remux", "mkv", "h264", "aac"),
            "pending": _asset("pending", "mkv", "h264", "aac", subs=[_text_sub()]),
            "picture": _asset("picture", "mkv", "h264", "aac", subs=[_picture_sub()]),
            "audio": _asset("audio", "mkv", "h264", "eac3"),
            "video": _asset("video", "mkv", "hevc", "aac"),
            "missing": _asset("missing", "mkv", "h264", "aac", readable=False, reason="No path mapping for this file"),
        }
        browser = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [{"codec": "h264", "max_level": "5.2"}],
                "audio": ["aac"],
                "captions": ["webvtt"],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            report = build_playability_report(
                titles,
                assets,
                [SAFARI, browser],
                settings=Settings(),
                data_dir=Path(tmp),
            )
        blob = json.dumps(report)
        self.assertNotIn("/secret", blob)
        self.assertNotIn("local_path", blob)
        self.assertNotIn("source_path", blob)

        safari = report["profiles"][0]
        by_key = {row["rating_key"]: row for row in safari["titles"]}
        self.assertEqual(by_key["direct"]["tier"], "direct")
        self.assertEqual(by_key["direct"]["label"], "Serve the file")
        self.assertEqual(by_key["direct"]["plan"], "direct")
        self.assertEqual(by_key["remux"]["tier"], "remux")
        self.assertEqual(by_key["remux"]["label"], "Remux")
        self.assertEqual(by_key["remux"]["plan"], "remux")
        self.assertEqual(by_key["pending"]["tier"], "captions-pending")
        self.assertEqual(by_key["pending"]["reason"], CAPTION_PENDING_REASON)
        self.assertNotEqual(by_key["pending"]["reason"], CAPTION_FALLBACK_REASON)
        self.assertEqual(by_key["picture"]["tier"], "needs-ocr")
        self.assertEqual(by_key["picture"]["label"], "Picture captions that are not text yet")
        self.assertEqual(by_key["picture"]["reason"], CAPTION_FALLBACK_REASON)
        self.assertEqual(by_key["audio"]["tier"], "remux")
        self.assertEqual(by_key["video"]["tier"], "remux")
        self.assertEqual(by_key["missing"]["tier"], "not-playable")
        self.assertEqual(by_key["missing"]["label"], "Not playable through the engine")
        self.assertEqual(safari["shares"]["direct"]["count"], 1)
        self.assertEqual(safari["shares"]["remux"]["count"], 3)
        self.assertEqual(safari["shares"]["captions-pending"]["count"], 1)
        self.assertEqual(safari["shares"]["needs-ocr"]["count"], 1)
        self.assertEqual(safari["shares"]["source-transcode"]["count"], 0)
        self.assertEqual(safari["hardware"], hardware_sentence(0))
        self.assertIn("0 titles", safari["hardware"])

        web = report["profiles"][1]
        web_rows = {row["rating_key"]: row for row in web["titles"]}
        self.assertEqual(web["profile"], "web")
        self.assertEqual(web_rows["direct"]["tier"], "direct")
        self.assertEqual(web_rows["remux"]["tier"], "remux")
        self.assertEqual(web_rows["audio"]["tier"], "audio")
        self.assertEqual(web_rows["audio"]["label"], "Audio-only")
        self.assertEqual(web_rows["audio"]["plan"], "audio")
        self.assertEqual(web_rows["video"]["tier"], "source-transcode")
        self.assertEqual(web_rows["video"]["label"], "Ask the media source to transcode")
        self.assertEqual(web_rows["video"]["plan"], "full")
        self.assertEqual(web["shares"]["source-transcode"]["count"], 1)
        self.assertEqual(web["hardware"], "A GPU with Quick Sync would let 1 title play without Plex.")
        self.assertEqual(web_rows["pending"]["reason"], CAPTION_PENDING_REASON)
        self.assertEqual(web_rows["picture"]["reason"], CAPTION_FALLBACK_REASON)
        self.assertNotEqual(web_rows["pending"]["reason"], web_rows["picture"]["reason"])
        self.assertEqual(web["shares"]["captions-pending"]["count"], 1)
        self.assertEqual(web["shares"]["needs-ocr"]["count"], 1)

    def test_library_titles_include_a_movie_and_an_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "projectionist.db")
            show_id = db.upsert_library_item(
                {
                    "rating_key": "show-1",
                    "media_type": "show",
                    "title": "A Series",
                    "original_language": "ja",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "movie-1",
                    "media_type": "movie",
                    "title": "A Film",
                    "original_language": "en",
                }
            )
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO library_episodes
                        (show_item_id, rating_key, season_number, episode_number, title)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (show_id, "episode-1", 1, 2, "The Second"),
                )
            found = {row.rating_key: row for row in library_titles(db)}
        self.assertEqual(found["movie-1"].title, "A Film")
        self.assertEqual(found["movie-1"].title_language, "en")
        self.assertEqual(found["episode-1"].title, "The Second")
        self.assertEqual(found["episode-1"].title_language, "ja")
        self.assertNotIn("show-1", found)

    def test_a_browser_profile_object_is_an_input(self) -> None:
        profiles = profiles_for_report(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [{"codec": "h264", "max_level": "4.0"}],
                "audio": ["aac"],
            }
        )
        ids = [profile.id for profile in profiles]
        self.assertIn("web", ids)
        self.assertIn("safari", ids)
        web = next(profile for profile in profiles if profile.id == "web")
        self.assertEqual(web.video[0].max_level, "4.0")


class PlayabilityRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-playability-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test:32400",
                    "plex_token": "server-token",
                    "features": {"multi_user_enabled": False},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        self.db.upsert_library_item(
            {"rating_key": "direct", "media_type": "movie", "title": "Direct Feature", "original_language": "en"}
        )
        self.db.upsert_library_item(
            {"rating_key": "remux", "media_type": "movie", "title": "Remux Feature", "original_language": "en"}
        )
        self.db.upsert_library_item(
            {
                "rating_key": "pending",
                "media_type": "movie",
                "title": "Pending Captions",
                "original_language": "ja",
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "picture",
                "media_type": "movie",
                "title": "Picture Captions",
                "original_language": "ja",
            }
        )
        self.assets = {
            "direct": _asset("direct", "mp4", "h264", "aac"),
            "remux": _asset("remux", "mkv", "h264", "aac"),
            "pending": _asset("pending", "mkv", "h264", "aac", subs=[_text_sub()]),
            "picture": _asset("picture", "mkv", "h264", "aac", subs=[_picture_sub()]),
        }

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        self._tmpdir.cleanup()

    def test_owner_refresh_lists_each_tier_and_get_reads_it_back(self) -> None:
        calls: list[str] = []

        def locate(_settings, _db, _data_dir, rating_key: str):
            calls.append(rating_key)
            return self.assets[rating_key]

        with patch("projectionist.engine.routes.describe_title", side_effect=locate):
            empty = self.client.get("/api/playback/playability")
            self.assertEqual(empty.status_code, 200)
            self.assertEqual(empty.json()["profiles"], [])
            refreshed = self.client.post(
                "/api/playback/playability",
                json={
                    "profile": {
                        "id": "web",
                        "containers": ["mp4", "hls-fmp4"],
                        "video": [{"codec": "h264", "max_level": "5.2"}],
                        "audio": ["aac"],
                        "captions": ["webvtt"],
                    }
                },
            )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        body = refreshed.json()
        self.assertEqual(sorted(calls), ["direct", "pending", "picture", "remux"])
        self.assertNotIn("/secret", json.dumps(body))
        ids = [row["profile"] for row in body["profiles"]]
        self.assertIn("web", ids)
        self.assertIn("safari", ids)
        web = next(row for row in body["profiles"] if row["profile"] == "web")
        listed = {row["rating_key"]: row for row in web["titles"]}
        self.assertEqual(listed["direct"]["label"], "Serve the file")
        self.assertEqual(listed["remux"]["label"], "Remux")
        self.assertEqual(listed["pending"]["reason"], CAPTION_PENDING_REASON)
        self.assertEqual(listed["picture"]["label"], "Picture captions that are not text yet")
        again = self.client.get("/api/playback/playability")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(
            {row["rating_key"] for row in again.json()["profiles"][0]["titles"]},
            {"direct", "remux", "pending", "picture"},
        )

    def test_unknown_profile_name_is_rejected(self) -> None:
        refused = self.client.post("/api/playback/playability", json={"profile": "nope"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("Unknown device profile", refused.json()["detail"])
