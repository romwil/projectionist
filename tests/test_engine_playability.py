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
    merge_playability_reports,
    playability_progress,
    profiles_for_report,
    report_path,
    run_library_report,
    save_playability_report,
)
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.profiles import SAFARI, profile_from_mapping
from projectionist.engine.source import MediaAsset
from projectionist.library.db import Database
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


def _probe(container: str, streams: list[MediaStream]) -> ProbeResult:
    return ProbeResult(container, container, 600.0, 4_000_000, 1000, streams)


def _av(
    container: str, video: str, audio: str, *, subs: list[MediaStream] | None = None
) -> list[MediaStream]:
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
    return MediaStream(
        index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text"
    )


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
            "missing": _asset(
                "missing",
                "mkv",
                "h264",
                "aac",
                readable=False,
                reason="No path mapping for this file",
            ),
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
        self.assertEqual(web_rows["video"]["plan"], "source-transcode")
        self.assertEqual(web_rows["video"]["source_reason"], "codec")
        self.assertEqual(web_rows["video"]["provider"], "plex")
        self.assertEqual(web["shares"]["source-transcode"]["count"], 1)
        self.assertEqual(
            web["hardware"], "A GPU with Quick Sync would let 1 title play without Plex."
        )
        self.assertEqual(web_rows["pending"]["reason"], CAPTION_PENDING_REASON)
        self.assertEqual(web_rows["picture"]["reason"], CAPTION_FALLBACK_REASON)
        self.assertNotEqual(web_rows["pending"]["reason"], web_rows["picture"]["reason"])
        self.assertEqual(web["shares"]["captions-pending"]["count"], 1)
        self.assertEqual(web["shares"]["needs-ocr"]["count"], 1)
        self.assertEqual(web["source_breakdown"]["video_transcode"], 1)
        self.assertEqual(web["source_breakdown"]["codec"], 1)
        self.assertEqual(safari["source_breakdown"]["video_transcode"], 0)
        self.assertEqual(report["gpu"]["safari"], 0)
        self.assertIsNone(report["gpu"]["apple_tv"])

    def test_source_breakdown_is_planned_from_plex_metadata(self) -> None:
        """Codec, level, bit depth, size, and HDR, without ffprobe. Safari and Apple TV are the GPU counts."""
        from projectionist.engine.playability import asset_from_plex_row
        from projectionist.engine.profiles import APPLE_TV_4K, CHROME

        rows = [
            {
                "rating_key": "four-k",
                "title": "Four K",
                "container": "mkv",
                "streams": [
                    {
                        "codec_type": "video",
                        "codec": "hevc",
                        "level": "153",
                        "bit_depth": 10,
                        "width": 3840,
                        "height": 2160,
                        "hdr": "hdr10",
                    },
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "high-level",
                "title": "High Level",
                "container": "mkv",
                "streams": [
                    {
                        "codec_type": "video",
                        "codec": "hevc",
                        "level": "186",
                        "bit_depth": 8,
                        "height": 1080,
                    },
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "ten-bit",
                "title": "Ten Bit",
                "container": "mkv",
                "streams": [
                    {
                        "codec_type": "video",
                        "codec": "hevc",
                        "level": "153",
                        "bit_depth": 10,
                        "height": 1080,
                    },
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "plain",
                "title": "Plain",
                "container": "mp4",
                "streams": [
                    {"codec_type": "video", "codec": "h264", "level": "41", "height": 1080},
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
        ]
        eight_bit = profile_from_mapping(
            {
                "id": "web",
                "containers": ["mp4", "hls-fmp4"],
                "video": [
                    {"codec": "hevc", "max_level": "5.1", "bit_depth": 8},
                    {"codec": "h264", "max_level": "5.2"},
                ],
                "audio": ["aac"],
                "captions": ["webvtt"],
            }
        )
        titles = [LibraryTitle(row["rating_key"], row["title"], "en") for row in rows]
        assets = {row["rating_key"]: asset_from_plex_row(row) for row in rows}
        with tempfile.TemporaryDirectory() as tmp:
            report = build_playability_report(
                titles,
                assets,
                [CHROME, SAFARI, APPLE_TV_4K, eight_bit],
                settings=Settings(),
                data_dir=Path(tmp),
            )
        self.assertNotIn("ffprobe", json.dumps(report).lower())
        chrome = next(block for block in report["profiles"] if block["profile"] == "chrome")
        self.assertEqual(chrome["shares"]["source-transcode"]["count"], 3)
        self.assertEqual(chrome["source_breakdown"]["codec"], 3)
        self.assertEqual(chrome["source_breakdown"]["codecs"], {"hevc": 3})
        self.assertEqual(chrome["source_breakdown"]["level"], 0)
        self.assertEqual(chrome["source_breakdown"]["resolution"], 1)
        self.assertEqual(chrome["source_breakdown"]["hdr"], 1)
        self.assertEqual(chrome["source_breakdown"]["video_transcode"], 3)

        safari = next(block for block in report["profiles"] if block["profile"] == "safari")
        safari_rows = {row["rating_key"]: row for row in safari["titles"]}
        self.assertEqual(safari_rows["high-level"]["plan"], "try")
        self.assertEqual(safari_rows["four-k"]["plan"], "remux")
        self.assertEqual(safari["shares"]["try"]["count"], 1)
        self.assertEqual(safari["source_breakdown"]["video_transcode"], 0)
        self.assertEqual(safari["source_breakdown"]["codecs"], {})
        self.assertEqual(safari["source_breakdown"]["level"], 0)
        self.assertEqual(safari["source_breakdown"]["resolution"], 0)

        apple = next(block for block in report["profiles"] if block["profile"] == "apple-tv-4k-3")
        apple_rows = {row["rating_key"]: row for row in apple["titles"]}
        self.assertEqual(apple_rows["high-level"]["plan"], "try")
        self.assertEqual(apple_rows["four-k"]["plan"], "try")
        self.assertEqual(apple["shares"]["try"]["count"], 2)
        self.assertEqual(apple["source_breakdown"]["video_transcode"], 0)
        self.assertEqual(apple["source_breakdown"]["codecs"], {})
        self.assertEqual(apple["source_breakdown"]["level"], 0)

        web = next(block for block in report["profiles"] if block["profile"] == "web")
        by_key = {row["rating_key"]: row for row in web["titles"]}
        self.assertEqual(by_key["four-k"]["source_reason"], "bit_depth")
        self.assertTrue(by_key["four-k"]["above_1080p"])
        self.assertTrue(by_key["four-k"]["video_hdr"])
        self.assertEqual(by_key["high-level"]["plan"], "try")
        self.assertEqual(by_key["high-level"]["source_reason"], "")
        self.assertEqual(by_key["ten-bit"]["source_reason"], "bit_depth")
        self.assertEqual(web["source_breakdown"]["bit_depth"], 2)
        self.assertEqual(web["source_breakdown"]["level"], 0)
        self.assertEqual(web["source_breakdown"]["resolution"], 1)
        self.assertEqual(web["source_breakdown"]["hdr"], 1)
        self.assertEqual(report["gpu"], {"safari": 0, "apple_tv": 0})
        progress_keys = set(playability_progress(report)["profiles"][0])
        self.assertIn("source_breakdown", progress_keys)
        self.assertNotIn("titles", progress_keys)

    def test_video_transcode_bucket_names_codecs_per_device(self) -> None:
        """Each device names the codecs in its video-transcode bucket.

        A library listing without a level or an HDR flag must not report those
        as zero. A probed file with no HDR still reports zero.
        """
        from projectionist.engine.playability import asset_from_plex_row
        from projectionist.engine.profiles import APPLE_TV_4K, CHROME

        def video(codec: str, **extra: object) -> dict[str, object]:
            row = {
                "codec_type": "video",
                "codec": codec,
                "profile": "",
                "level": "",
                "bit_depth": 0,
                "width": 1920,
                "height": 1080,
                "hdr": "",
                "hdr_known": False,
            }
            row.update(extra)
            return row

        listing = [
            {
                "rating_key": "hevc-main10",
                "title": "Main Ten",
                "container": "mkv",
                "streams": [
                    video("hevc", profile="main 10", bit_depth=10),
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "av1-film",
                "title": "AV1 Film",
                "container": "mkv",
                "streams": [video("av1", profile="Main"), {"codec_type": "audio", "codec": "aac"}],
            },
            {
                "rating_key": "mpeg4-film",
                "title": "MPEG-4 Film",
                "container": "mkv",
                "streams": [
                    video("mpeg4", profile="Advanced Simple", width=720, height=480),
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "h264-film",
                "title": "H.264 Film",
                "container": "mkv",
                "streams": [video("h264", profile="high"), {"codec_type": "audio", "codec": "aac"}],
            },
        ]
        titles = [LibraryTitle(row["rating_key"], row["title"], "en") for row in listing]
        assets = {row["rating_key"]: asset_from_plex_row(row) for row in listing}
        with tempfile.TemporaryDirectory() as tmp:
            report = build_playability_report(
                titles,
                assets,
                [CHROME, SAFARI, APPLE_TV_4K],
                settings=Settings(),
                data_dir=Path(tmp),
            )
        chrome = next(block for block in report["profiles"] if block["profile"] == "chrome")
        safari = next(block for block in report["profiles"] if block["profile"] == "safari")
        apple = next(block for block in report["profiles"] if block["profile"] == "apple-tv-4k-3")

        self.assertEqual(chrome["source_breakdown"]["video_transcode"], 3)
        self.assertEqual(chrome["source_breakdown"]["codecs"], {"av1": 1, "hevc": 1, "mpeg4": 1})
        self.assertEqual(sum(chrome["source_breakdown"]["codecs"].values()), 3)
        self.assertIsNone(chrome["source_breakdown"]["level"])
        self.assertIsNone(chrome["source_breakdown"]["hdr"])
        self.assertEqual(chrome["source_breakdown"]["bit_depth"], 0)
        self.assertEqual(chrome["source_breakdown"]["resolution"], 0)

        self.assertEqual(safari["source_breakdown"]["video_transcode"], 2)
        self.assertEqual(safari["source_breakdown"]["codecs"], {"av1": 1, "mpeg4": 1})
        self.assertNotIn("hevc", safari["source_breakdown"]["codecs"])
        self.assertIsNone(safari["source_breakdown"]["level"])
        self.assertIsNone(safari["source_breakdown"]["hdr"])
        self.assertEqual(safari["source_breakdown"]["bit_depth"], 0)
        self.assertEqual(apple["source_breakdown"]["codecs"], safari["source_breakdown"]["codecs"])

        probed = [
            {
                "rating_key": "hevc-sdr",
                "title": "Checked SDR",
                "container": "mkv",
                "streams": [
                    video("hevc", level="153", bit_depth=8, hdr_known=True),
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
            {
                "rating_key": "h264-sdr",
                "title": "Checked H.264",
                "container": "mkv",
                "streams": [
                    video("h264", level="41", bit_depth=8, hdr_known=True),
                    {"codec_type": "audio", "codec": "aac"},
                ],
            },
        ]
        probed_titles = [LibraryTitle(row["rating_key"], row["title"], "en") for row in probed]
        probed_assets = {row["rating_key"]: asset_from_plex_row(row) for row in probed}
        with tempfile.TemporaryDirectory() as tmp:
            checked = build_playability_report(
                probed_titles,
                probed_assets,
                [CHROME],
                settings=Settings(),
                data_dir=Path(tmp),
            )
        checked_chrome = checked["profiles"][0]
        self.assertEqual(checked_chrome["source_breakdown"]["codecs"], {"hevc": 1})
        self.assertEqual(checked_chrome["source_breakdown"]["level"], 0)
        self.assertEqual(checked_chrome["source_breakdown"]["hdr"], 0)
        self.assertEqual(checked_chrome["source_breakdown"]["bit_depth"], 0)

    def test_analysis_rows_supply_hdr_and_metadata_supplies_the_ranking(self) -> None:
        """HDR10 and HLG come from stored media analysis, not the section listing.

        The listing has no HDR attribute. Watch count and file size on that
        metadata are what the copy-ahead ranking uses. This does not transcode
        and does not make a copy.
        """
        import sqlite3
        import xml.etree.ElementTree as ET

        from projectionist.connectors.plex import (
            apply_plex_media_analysis,
            read_plex_media_analysis,
            title_streams_from_element,
        )
        from projectionist.engine.playability import asset_from_plex_row
        from projectionist.engine.profiles import APPLE_TV_4K

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "library.db"
            connection = sqlite3.connect(database)
            connection.execute(
                """
                CREATE TABLE media_items (
                    id INTEGER PRIMARY KEY,
                    metadata_item_id INTEGER,
                    color_trc TEXT,
                    deleted_at INTEGER
                )
                """
            )
            connection.executemany(
                """
                INSERT INTO media_items (id, metadata_item_id, color_trc, deleted_at)
                VALUES (?, ?, ?, NULL)
                """,
                [
                    (1, 10, "smpte2084"),
                    (2, 11, "arib-std-b67"),
                    (3, 12, ""),
                    (9, 10, "bt709"),
                ],
            )
            connection.commit()
            connection.close()

            analysis = read_plex_media_analysis(database)
            by_transfer = {row["rating_key"]: row["color_trc"] for row in analysis}
            self.assertEqual(by_transfer["10"], "smpte2084")
            self.assertEqual(by_transfer["11"], "arib-std-b67")
            self.assertEqual(by_transfer["12"], "")
            self.assertNotIn("bt709", by_transfer.values())

            listing = ET.fromstring(
                """
                <MediaContainer>
                  <Video ratingKey="10" title="Often" viewCount="9">
                    <Media id="1" container="mkv" videoCodec="av1" videoResolution="1080">
                      <Part size="800" />
                    </Media>
                  </Video>
                  <Video ratingKey="11" title="Rare" viewCount="2">
                    <Media id="2" container="mkv" videoCodec="mpeg4" videoResolution="480">
                      <Part size="100" />
                    </Media>
                  </Video>
                  <Video ratingKey="12" title="Wide" viewCount="1">
                    <Media id="3" container="mkv" videoCodec="vp9" videoResolution="4k">
                      <Part size="5000" />
                    </Media>
                  </Video>
                  <Video ratingKey="13" title="Plain" viewCount="4">
                    <Media id="4" container="mp4" videoCodec="h264" videoResolution="1080">
                      <Part size="50" />
                    </Media>
                  </Video>
                </MediaContainer>
                """
            )
            rows = []
            for element in listing.findall("Video"):
                media = element.find("Media")
                self.assertIsNotNone(media)
                self.assertNotIn("colorTrc", media.attrib)
                self.assertNotIn("HDR10Present", media.attrib)
                row = title_streams_from_element(element)
                self.assertEqual(row["streams"][0]["hdr"], "")
                self.assertFalse(row["streams"][0]["hdr_known"])
                rows.append(row)
            merged = apply_plex_media_analysis(rows, analysis)
            by_rating = {row["rating_key"]: row for row in merged}
            self.assertEqual(by_rating["10"]["streams"][0]["hdr"], "hdr10")
            self.assertTrue(by_rating["10"]["streams"][0]["hdr_known"])
            self.assertEqual(by_rating["11"]["streams"][0]["hdr"], "hlg")
            self.assertTrue(by_rating["11"]["streams"][0]["hdr_known"])
            self.assertEqual(by_rating["12"]["streams"][0]["hdr"], "")
            self.assertFalse(by_rating["12"]["streams"][0]["hdr_known"])
            self.assertEqual(by_rating["10"]["view_count"], 9)
            self.assertEqual(by_rating["10"]["file_size"], 800)
            self.assertEqual(by_rating["12"]["file_size"], 5000)

            titles = [
                LibraryTitle(
                    row["rating_key"],
                    row["title"],
                    "en",
                    watch_count=int(row["view_count"]),
                    file_size=int(row["file_size"]),
                )
                for row in merged
            ]
            assets = {row["rating_key"]: asset_from_plex_row(row) for row in merged}
            report = build_playability_report(
                titles,
                assets,
                [SAFARI, APPLE_TV_4K],
                settings=Settings(),
                data_dir=root,
            )

        safari = next(block for block in report["profiles"] if block["profile"] == "safari")
        planned = {row["rating_key"]: row for row in safari["titles"]}
        self.assertEqual(planned["10"]["hdr"], "hdr10")
        self.assertEqual(planned["11"]["hdr"], "hlg")
        self.assertEqual(planned["10"]["watch_count"], 9)
        self.assertEqual(planned["10"]["file_size"], 800)
        self.assertEqual(planned["12"]["watch_count"], 1)
        self.assertEqual(planned["12"]["file_size"], 5000)
        ranking = report["copy_ahead"]
        self.assertEqual(ranking["profile"], "safari")
        self.assertEqual([row["rating_key"] for row in ranking["titles"]], ["12", "10", "11"])
        self.assertEqual(ranking["above_1080p"], 1)
        self.assertEqual(ranking["above_1080p_codecs"], {"vp9": 1})
        self.assertEqual(ranking["disk_bytes"], 5900)
        self.assertEqual(ranking["titles"][0]["above_1080p"], True)
        self.assertEqual(ranking["titles"][1]["hdr"], "hdr10")
        self.assertEqual(ranking["titles"][1]["watch_count"], 9)
        self.assertEqual(ranking["titles"][1]["file_size"], 800)
        self.assertEqual(ranking["titles"][2]["hdr"], "hlg")
        self.assertEqual(ranking["titles"][2]["watch_count"], 2)
        self.assertEqual(ranking["titles"][2]["file_size"], 100)
        self.assertNotIn("13", {row["rating_key"] for row in ranking["titles"]})
        for row in ranking["titles"]:
            self.assertGreaterEqual(row["watch_count"], 0)
            self.assertGreater(row["file_size"], 0)
        progress = playability_progress(report)
        self.assertEqual(progress["copy_ahead"]["disk_bytes"], 5900)
        self.assertNotIn("titles", progress["copy_ahead"])
        self.assertNotIn("ffprobe", json.dumps(report).lower())

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


class PlayabilityInterruptTests(unittest.TestCase):
    def test_interrupted_walk_does_not_replace_the_saved_snapshot(self) -> None:
        previous = {
            "generated_at": "2026-11-21T00:00:00+00:00",
            "complete": True,
            "message": "Ready.",
            "title_count": 2,
            "profiles": [
                {
                    "profile": "safari",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
                {
                    "profile": "chrome",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
                {
                    "profile": "web",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
            ],
        }
        checks = {"n": 0}

        def should_stop() -> bool:
            checks["n"] += 1
            return checks["n"] > 1

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = Database(root / "projectionist.db")
            db.upsert_library_item(
                {
                    "rating_key": "alpha",
                    "media_type": "movie",
                    "title": "Alpha",
                    "original_language": "en",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "beta",
                    "media_type": "movie",
                    "title": "Beta",
                    "original_language": "en",
                }
            )
            save_playability_report(root, previous)
            path = report_path(root)
            before = path.read_text(encoding="utf-8")
            result = run_library_report(
                db,
                Settings(),
                root,
                locate=lambda key: _asset(key, "mp4", "h264", "aac"),
                should_stop=should_stop,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.read_text(encoding="utf-8"), before)
        counts = {row["profile"]: row["title_count"] for row in saved["profiles"]}
        self.assertEqual(saved["complete"], True)
        self.assertEqual(saved["title_count"], 2)
        self.assertEqual(counts, {"safari": 2, "chrome": 2, "web": 2})
        self.assertEqual(result["title_count"], 2)
        self.assertEqual(
            {row["profile"]: row["title_count"] for row in result["profiles"]},
            counts,
        )

    def test_merge_ignores_a_truncated_walk(self) -> None:
        previous = {
            "generated_at": "2026-11-21T00:00:00+00:00",
            "complete": True,
            "message": "Ready.",
            "title_count": 2,
            "profiles": [
                {
                    "profile": "safari",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
                {
                    "profile": "web",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
            ],
        }
        fresh = {
            "generated_at": "2026-11-21T01:00:00+00:00",
            "complete": False,
            "message": "The walk stopped early. Refresh to finish the library.",
            "title_count": 1,
            "profiles": [
                {"profile": "safari", "title_count": 1, "titles": [{"rating_key": "alpha"}]},
                {"profile": "chrome", "title_count": 1, "titles": [{"rating_key": "alpha"}]},
            ],
        }
        merged = merge_playability_reports(previous, fresh)
        counts = {row["profile"]: row["title_count"] for row in merged["profiles"]}
        self.assertEqual(merged["complete"], True)
        self.assertEqual(merged["title_count"], 2)
        self.assertEqual(counts, {"safari": 2, "web": 2})

    def test_interrupted_walk_does_not_create_a_partial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = Database(root / "projectionist.db")
            db.upsert_library_item(
                {
                    "rating_key": "alpha",
                    "media_type": "movie",
                    "title": "Alpha",
                    "original_language": "en",
                }
            )
            run_library_report(
                db,
                Settings(),
                root,
                locate=lambda key: _asset(key, "mp4", "h264", "aac"),
                should_stop=lambda: True,
            )
            self.assertFalse(report_path(root).exists())

    def test_finished_walk_refreshes_named_profiles_and_keeps_the_browser_row(self) -> None:
        previous = {
            "generated_at": "2026-11-21T00:00:00+00:00",
            "complete": True,
            "message": "Ready.",
            "title_count": 1,
            "profiles": [
                {
                    "profile": "web",
                    "title_count": 2,
                    "titles": [{"rating_key": "alpha"}, {"rating_key": "beta"}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = Database(root / "projectionist.db")
            db.upsert_library_item(
                {
                    "rating_key": "alpha",
                    "media_type": "movie",
                    "title": "Alpha",
                    "original_language": "en",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "beta",
                    "media_type": "movie",
                    "title": "Beta",
                    "original_language": "en",
                }
            )
            save_playability_report(root, previous)
            result = run_library_report(
                db,
                Settings(),
                root,
                locate=lambda key: _asset(key, "mp4", "h264", "aac"),
                profiles=profiles_for_report("safari"),
                should_stop=lambda: False,
            )
        counts = {row["profile"]: row["title_count"] for row in result["profiles"]}
        self.assertEqual(result["complete"], True)
        self.assertEqual(result["title_count"], 2)
        self.assertEqual(counts["safari"], 2)
        self.assertEqual(counts["web"], 2)
        self.assertEqual(len(result["profiles"][0]["titles"]), 2)

    def test_two_savers_do_not_share_one_temp_file(self) -> None:
        import threading

        from projectionist.engine.playability import (
            empty_playability_report,
            load_playability_report,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            errors: list[BaseException] = []

            def write(marker: str) -> None:
                try:
                    report = empty_playability_report(message=marker)
                    report["complete"] = True
                    report["profiles"] = [{"profile": "safari", "title_count": 1, "titles": []}]
                    for _ in range(40):
                        save_playability_report(root, report)
                except BaseException as exc:  # noqa: BLE001 — the assertion is the failure
                    errors.append(exc)

            threads = [threading.Thread(target=write, args=(label,)) for label in ("one", "two")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            saved = load_playability_report(root)
            leftovers = list((root / "engine").glob("*.tmp"))
        self.assertEqual(errors, [])
        self.assertIn(saved["message"], {"one", "two"})
        self.assertEqual(saved["profiles"][0]["profile"], "safari")
        self.assertEqual(leftovers, [])


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
            {
                "rating_key": "direct",
                "media_type": "movie",
                "title": "Direct Feature",
                "original_language": "en",
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "remux",
                "media_type": "movie",
                "title": "Remux Feature",
                "original_language": "en",
            }
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

        def locate(_settings, _db, _data_dir, rating_key: str, **_extra: object):
            calls.append(rating_key)
            return self.assets[rating_key]

        def catalog(_settings):
            rows = []
            for key, asset in self.assets.items():
                probe = asset.probe
                rows.append(
                    {
                        "rating_key": key,
                        "title": key,
                        "container": probe.container if probe else "",
                        "streams": [
                            {
                                "index": stream.index,
                                "codec_type": stream.codec_type,
                                "codec": stream.codec,
                                "language": stream.language,
                                "channels": stream.channels,
                                "profile": stream.profile,
                                "level": stream.level,
                                "bit_depth": stream.bit_depth,
                            }
                            for stream in (probe.streams if probe else [])
                        ],
                    }
                )
            return rows

        def inline(target):
            target()

        with (
            patch("projectionist.engine.routes.describe_title", side_effect=locate),
            patch("projectionist.engine.playability.plex_stream_catalog", catalog),
            patch("projectionist.engine.playability.spawn_walk", inline),
        ):
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
        self.assertEqual(body["planned_from_plex"], 4)
        self.assertEqual(body["confirmed_by_ffprobe"], 4)
        self.assertFalse(body["running"])
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

    def test_refresh_does_not_probe_until_the_walk_runs_and_does_not_start_a_second_one(
        self,
    ) -> None:
        import projectionist.engine.playability as playability

        calls: list[str] = []
        started: list[object] = []

        def locate(_settings, _db, _data_dir, rating_key: str, **_extra: object):
            calls.append(rating_key)
            return self.assets[rating_key]

        def spawn(target):
            started.append(target)

        try:
            with (
                patch("projectionist.engine.routes.describe_title", side_effect=locate),
                patch("projectionist.engine.playability.spawn_walk", spawn),
            ):
                opened = self.client.get("/api/playback/playability")
                self.assertEqual(opened.status_code, 200)
                self.assertFalse(opened.json()["running"])
                self.assertEqual(calls, [])
                first = self.client.post("/api/playback/playability", json={})
                second = self.client.post("/api/playback/playability", json={})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertTrue(first.json()["running"])
            self.assertTrue(second.json()["running"])
            self.assertEqual(len(started), 1)
            self.assertEqual(calls, [])
        finally:
            playability._WALKING = False

    def test_scheduled_playability_task_does_not_walk(self) -> None:
        import asyncio

        from projectionist.library.db import Database
        from projectionist.scheduler.engine import IdleScheduler
        from projectionist.scheduler.tasks.playability_report import register
        from projectionist.scheduler.tasks.playability_report import run as scheduled

        result = asyncio.run(scheduled(None, Settings(), lambda: False))
        self.assertEqual(result, {"status": "skipped", "processed": 0, "has_more": False})
        with tempfile.TemporaryDirectory() as tmp:
            scheduler = IdleScheduler(Database(Path(tmp) / "projectionist.db"), Path(tmp))
            register(scheduler)
            state = next(
                row for row in scheduler.get_task_states() if row["name"] == "playability_report"
            )
        self.assertFalse(state["enabled"])

    def test_progress_read_does_not_include_the_full_title_lists(self) -> None:
        import projectionist.engine.playability as playability

        titles = [
            {
                "rating_key": f"title-{index}",
                "title": f"Title {index}",
                "tier": "remux",
                "label": "Remux",
                "reason": "MKV container",
            }
            for index in range(50)
        ]
        report = {
            "generated_at": "2026-11-21T00:00:00+00:00",
            "complete": False,
            "running": True,
            "phase": "ffprobe",
            "planned_from_plex": 50,
            "confirmed_by_ffprobe": 3,
            "message": "Planned from Plex metadata. Confirming files in the background.",
            "title_count": 50,
            "profiles": [
                {
                    "profile": "safari",
                    "title_count": 50,
                    "shares": {"remux": {"count": 50, "share": 1, "label": "Remux"}},
                    "top_reasons": [{"reason": "MKV container", "count": 50}],
                    "titles": titles,
                    "hardware": "A GPU with Quick Sync would let 0 titles play without Plex.",
                }
            ],
        }
        save_playability_report(self.data_dir, report)
        playability._WALKING = True
        try:
            progress = self.client.get("/api/playback/playability", params={"view": "progress"})
        finally:
            playability._WALKING = False
        self.assertEqual(progress.status_code, 200, progress.text)
        body = progress.json()
        blob = json.dumps(body)
        self.assertNotIn("title-0", blob)
        self.assertNotIn("title-49", blob)
        self.assertNotIn("titles", body["profiles"][0])
        self.assertTrue(body["running"])
        self.assertEqual(body["planned_from_plex"], 50)
        self.assertEqual(body["confirmed_by_ffprobe"], 3)
        self.assertIn("Confirming", body["message"])
        self.assertEqual(body["profiles"][0]["shares"]["remux"]["count"], 50)
        page = self.client.get(
            "/api/playback/playability",
            params={"profile": "safari", "tier": "remux", "limit": 100, "offset": 0},
        )
        self.assertEqual(page.status_code, 200, page.text)
        rows = page.json()["titles"]
        self.assertEqual(len(rows), 40)
        self.assertEqual(page.json()["total"], 50)
        self.assertEqual(rows[0]["rating_key"], "title-0")
        self.assertNotIn("title-40", {row["rating_key"] for row in rows})
        saved = json.loads(report_path(self.data_dir).read_text(encoding="utf-8"))
        self.assertEqual(len(saved["profiles"][0]["titles"]), 50)
        self.assertTrue(saved["running"])

    def test_unknown_profile_name_is_rejected(self) -> None:
        refused = self.client.post("/api/playback/playability", json={"profile": "nope"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("Unknown device profile", refused.json()["detail"])
