"""Live guide and playback use Projectionist's lineup, not Tunarr HTTP."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from projectionist.live_channels.guide import build_guide_snapshot, build_on_now_snapshot
from projectionist.live_channels.native_schedule import (
    admin_channel_rows,
    import_tunarr_lineup,
    play_source_for_channel,
    save_schedule,
    snapshot_if_scheduled,
)


def _settings(data_dir: Path, *, url: str = "http://127.0.0.1:9") -> SimpleNamespace:
    return SimpleNamespace(
        data_dir=str(data_dir),
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(
            url=url,
            station_meta={
                "ch-mystery": {
                    "source": "show",
                    "media_scope": "movies",
                    "programming_mode": "shuffle",
                }
            },
        ),
    )


def _lineup(*, now: float) -> dict:
    start_ms = int(now * 1000) - 5_000
    return {
        "version": 1,
        "imported_from": "test",
        "channels": {
            "ch-mystery": {
                "id": "ch-mystery",
                "name": "Mystery",
                "number": 100,
                "guide_flex_title": "Mystery · Up next",
                "icon_url": "",
                "start_time_ms": start_ms,
                "items": [
                    {
                        "type": "content",
                        "duration_ms": 120_000,
                        "program_id": "prog-1",
                        "title": "The Crime Scene",
                        "show_title": "Mystery",
                        "season": 1,
                        "episode": 2,
                        "year": 1970,
                        "overview": "A case.",
                        "content_rating": "TV-PG",
                        "media_type": "episode",
                        "plex_rating_key": "163544",
                    },
                    {"type": "flex", "duration_ms": 15 * 60 * 1000},
                    {
                        "type": "content",
                        "duration_ms": 90_000,
                        "program_id": "prog-2",
                        "title": "Next Case",
                        "show_title": "Mystery",
                        "season": 1,
                        "episode": 3,
                        "media_type": "episode",
                        "plex_rating_key": "163545",
                    },
                ],
            }
        },
    }


class RefuseTunarr:
    def __init__(self, *args, **kwargs):
        raise AssertionError("Tunarr HTTP client must not be constructed")

    def __getattr__(self, name):
        raise AssertionError(f"Tunarr HTTP {name}")


class NativeScheduleTests(unittest.TestCase):
    def test_guide_and_channels_when_tunarr_http_is_refused(self) -> None:
        now = 1_700_000_000.0
        with self._dir() as data_dir:
            save_schedule(_lineup(now=now), data_dir=data_dir)
            settings = _settings(data_dir)
            with patch("urllib.request.urlopen", side_effect=AssertionError("no http")):
                on_now = build_on_now_snapshot(settings, now=now)
                guide = build_guide_snapshot(settings, now=now, hours=6)
            self.assertTrue(on_now["ready"])
            self.assertEqual(on_now["reason"], "")
            self.assertEqual(on_now["source"], "projectionist")
            self.assertEqual(len(on_now["channels"]), 1)
            channel = on_now["channels"][0]
            self.assertEqual(channel["name"], "Mystery")
            self.assertEqual(channel["number"], 100)
            self.assertEqual(channel["now"]["plex_rating_key"], "163544")
            self.assertFalse(channel["now"]["is_flex"])
            programs = guide["channels"][0]["programs"]
            flex = next(row for row in programs if row.get("is_flex"))
            self.assertEqual(flex["title"], "Between programs")
            self.assertTrue(flex["is_flex"])
            self.assertEqual(int(flex["stop"] - flex["start"]), 15 * 60)
            rows = admin_channel_rows(settings, _lineup(now=now))
            self.assertEqual(rows[0]["id"], "ch-mystery")
            self.assertEqual(rows[0]["name"], "Mystery")
            self.assertEqual(rows[0]["media_scope"], "movies")

    def test_now_playing_source_is_library_play_session(self) -> None:
        now = 1_700_000_000.0
        seen = {}

        def fake_start(db, settings, *, rating_key, user, start_over, offset_ms, fetch=None):
            del db, settings, user, fetch
            seen["rating_key"] = rating_key
            seen["start_over"] = start_over
            seen["offset_ms"] = offset_ms
            return {
                "session_id": "sess-1",
                "stream_url": "/api/library/playback/sess-1/index.m3u8",
                "duration_ms": 120_000,
                "rating_key": rating_key,
            }

        with self._dir() as data_dir:
            save_schedule(_lineup(now=now), data_dir=data_dir)
            settings = _settings(data_dir)
            with patch("urllib.request.urlopen", side_effect=AssertionError("no http")):
                source = play_source_for_channel(
                    None,
                    settings,
                    SimpleNamespace(id="owner"),
                    "ch-mystery",
                    now=now,
                    start_playback_fn=fake_start,
                )
        self.assertEqual(seen["rating_key"], "163544")
        self.assertTrue(seen["start_over"])
        self.assertGreaterEqual(seen["offset_ms"], 4_000)
        self.assertLessEqual(seen["offset_ms"], 6_000)
        self.assertIn("/api/library/playback/sess-1/index.m3u8", source["stream_url"])
        self.assertNotIn("18765", source["stream_url"])
        self.assertNotIn("tunarr", source["stream_url"].lower())
        self.assertFalse(source["is_flex"])

    def test_one_title_pool_notice_on_guide_and_watch(self) -> None:
        now = 1_700_000_000.0
        lineup = _lineup(now=now)
        lineup["channels"]["ch-mystery"]["items"] = [
            lineup["channels"]["ch-mystery"]["items"][0]
        ]
        lineup["channels"]["ch-mystery"]["library_repeat_note"] = (
            "This station has one playable title in the library — it will repeat."
        )
        with self._dir() as data_dir:
            save_schedule(lineup, data_dir=data_dir)
            settings = _settings(data_dir)
            snap = snapshot_if_scheduled(settings, now=now, include_programs=True)
            source = play_source_for_channel(
                None,
                settings,
                SimpleNamespace(id="owner"),
                "ch-mystery",
                now=now,
                start_playback_fn=lambda *args, **kwargs: {
                    "session_id": "sess",
                    "stream_url": "/api/library/playback/sess/index.m3u8",
                    "rating_key": kwargs.get("rating_key"),
                },
            )
        notice = "This station has one playable title in the library — it will repeat."
        self.assertEqual(snap["channels"][0]["pool_notice"], notice)
        self.assertEqual(source["pool_notice"], notice)

    def test_flex_without_filler_or_preroll_returns_named_slate(self) -> None:
        now = 1_700_000_000.0
        flex_now = now + 115 + 1

        def fail_start(*args, **kwargs):
            raise AssertionError("slate must not start library playback")

        with self._dir() as data_dir:
            save_schedule(_lineup(now=now), data_dir=data_dir)
            with patch(
                "projectionist.theater.preroll.list_preroll_videos",
                return_value=[
                    {
                        "id": "abc123bumper",
                        "path": "/preroll/drive-in.mp4",
                        "title": "Drive In",
                    }
                ],
            ):
                source = play_source_for_channel(
                    None,
                    _settings(data_dir),
                    SimpleNamespace(id="owner"),
                    "ch-mystery",
                    now=flex_now,
                    start_playback_fn=fail_start,
                )
        self.assertTrue(source["is_flex"])
        self.assertTrue(source["slate"])
        self.assertEqual(source["title"], "Between programs")
        self.assertEqual(source["stream_url"], "")
        self.assertIn("Between programs", source["slate_copy"])
        self.assertIn("up next:", source["slate_copy"].lower())
        self.assertIn("Next Case", source["slate_copy"])
        self.assertEqual(source["reason"], "no_filler")

    def test_flex_slot_starts_filler_then_next_title(self) -> None:
        now = 1_700_000_000.0
        # First title is 120s and began 5s before `now`, so flex starts at +115s.
        flex_now = now + 115 + 1
        after_pad = flex_now + (15 * 60)
        lineup = _lineup(now=now)
        lineup["channels"]["ch-mystery"]["filler_rating_keys"] = ["filler-88"]
        seen = []

        def fake_start(db, settings, *, rating_key, user, start_over, offset_ms, fetch=None):
            del db, settings, user, fetch
            seen.append(
                {
                    "rating_key": rating_key,
                    "start_over": start_over,
                    "offset_ms": offset_ms,
                }
            )
            return {
                "session_id": f"sess-{rating_key}",
                "stream_url": f"/api/library/playback/sess-{rating_key}/index.m3u8",
                "duration_ms": 90_000,
                "rating_key": rating_key,
            }

        with self._dir() as data_dir:
            save_schedule(lineup, data_dir=data_dir)
            settings = _settings(data_dir)
            during = play_source_for_channel(
                None,
                settings,
                SimpleNamespace(id="owner"),
                "ch-mystery",
                now=flex_now,
                start_playback_fn=fake_start,
            )
            after = play_source_for_channel(
                None,
                settings,
                SimpleNamespace(id="owner"),
                "ch-mystery",
                now=after_pad,
                start_playback_fn=fake_start,
            )
        self.assertTrue(during["is_flex"])
        self.assertEqual(during["title"], "Between programs")
        self.assertEqual(during["rating_key"], "filler-88")
        self.assertEqual(during["playback_kind"], "hls")
        self.assertIn("/api/library/playback/sess-filler-88/index.m3u8", during["stream_url"])
        self.assertEqual(seen[0]["rating_key"], "filler-88")
        self.assertTrue(seen[0]["start_over"])
        self.assertEqual(seen[0]["offset_ms"], 0)
        self.assertFalse(after["is_flex"])
        self.assertEqual(after["rating_key"], "163545")
        self.assertEqual(seen[1]["rating_key"], "163545")

    def test_flex_prefers_filler_rating_key_over_preroll_bumper(self) -> None:
        now = 1_700_000_000.0
        flex_now = now + 115 + 1
        lineup = _lineup(now=now)
        lineup["channels"]["ch-mystery"]["filler_rating_keys"] = ["filler-88"]
        seen = []

        def fake_start(db, settings, *, rating_key, user, start_over, offset_ms, fetch=None):
            del db, settings, user, start_over, offset_ms, fetch
            seen.append(rating_key)
            return {
                "session_id": f"sess-{rating_key}",
                "stream_url": f"/api/library/playback/sess-{rating_key}/index.m3u8",
                "duration_ms": 90_000,
                "rating_key": rating_key,
            }

        bumper = {
            "id": "abc123bumper",
            "path": "/preroll/scenic-sunset.mp4",
            "title": "Scenic Sunset",
        }
        with self._dir() as data_dir:
            save_schedule(lineup, data_dir=data_dir)
            with patch(
                "projectionist.theater.preroll.list_preroll_videos",
                return_value=[bumper],
            ):
                source = play_source_for_channel(
                    None,
                    _settings(data_dir),
                    SimpleNamespace(id="owner"),
                    "ch-mystery",
                    now=flex_now,
                    start_playback_fn=fake_start,
                )
        self.assertTrue(source["is_flex"])
        self.assertEqual(seen, ["filler-88"])
        self.assertEqual(source["rating_key"], "filler-88")
        self.assertEqual(source["playback_kind"], "hls")
        self.assertIn("/api/library/playback/sess-filler-88/index.m3u8", source["stream_url"])
        self.assertNotIn("/api/preroll/asset/", source["stream_url"])
        self.assertFalse(source.get("slate"))

    def test_two_minute_flex_does_not_loop_bumper_as_pad_source(self) -> None:
        now = 1_700_000_000.0
        lineup = _lineup(now=now)
        lineup["channels"]["ch-mystery"]["items"][1] = {
            "type": "flex",
            "duration_ms": 2 * 60 * 1000,
        }
        flex_now = now + 115 + 1

        def fail_start(*args, **kwargs):
            raise AssertionError("flex pad must not start library playback without filler keys")

        bumper = {
            "id": "abc123bumper",
            "path": "/preroll/scenic-sunset.mp4",
            "title": "Scenic Sunset",
        }
        with self._dir() as data_dir:
            save_schedule(lineup, data_dir=data_dir)
            with patch(
                "projectionist.theater.preroll.list_preroll_videos",
                return_value=[bumper],
            ):
                source = play_source_for_channel(
                    None,
                    _settings(data_dir),
                    SimpleNamespace(id="owner"),
                    "ch-mystery",
                    now=flex_now,
                    start_playback_fn=fail_start,
                )
        self.assertTrue(source["is_flex"])
        self.assertTrue(source["slate"])
        self.assertEqual(source["stream_url"], "")
        self.assertEqual(source["playback_kind"], "")
        self.assertNotEqual(source.get("rating_key"), "abc123bumper")
        self.assertNotIn("preroll", source["stream_url"])
        self.assertEqual(source["reason"], "no_filler")

    def test_sqlite_import_does_not_need_tunarr_process(self) -> None:
        with self._dir() as raw_dir:
            data_dir = Path(raw_dir)
            store = data_dir / "tunarr" / "tunarr"
            lineup = store / "channel-lineups"
            lineup.mkdir(parents=True)
            db_path = store / "db.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE channel (
                    uuid text PRIMARY KEY,
                    number integer,
                    name text,
                    start_time integer,
                    guide_flex_title text,
                    icon text
                );
                CREATE TABLE program (
                    uuid text PRIMARY KEY,
                    type text,
                    title text,
                    show_title text,
                    season_number integer,
                    episode integer,
                    year integer,
                    summary text,
                    rating text,
                    external_key text,
                    plex_rating_key text,
                    source_type text
                );
                """
            )
            conn.execute(
                "INSERT INTO channel VALUES (?,?,?,?,?,?)",
                (
                    "ch-1",
                    105,
                    "Gilligan's Island",
                    1_700_000_000_000,
                    "Gilligan's Island · Up next",
                    "",
                ),
            )
            conn.execute(
                "INSERT INTO program VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "prog-1",
                    "episode",
                    "Wrongway",
                    "Gilligan's Island",
                    1,
                    4,
                    1964,
                    "They get lost.",
                    "TV-G",
                    "185000",
                    "",
                    "plex",
                ),
            )
            conn.commit()
            conn.close()
            (lineup / "ch-1.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"type": "content", "id": "prog-1", "durationMs": 1500000},
                            {"type": "offline", "durationMs": 180000},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch("urllib.request.urlopen", side_effect=AssertionError("no http")):
                doc = import_tunarr_lineup(data_dir)
            self.assertIsNotNone(doc)
            channel = doc["channels"]["ch-1"]
            self.assertEqual(channel["name"], "Gilligan's Island")
            self.assertEqual(channel["items"][0]["plex_rating_key"], "185000")
            self.assertEqual(channel["items"][1]["type"], "flex")

    def test_touching_same_rating_key_is_one_airing_later_repeat_stays(self) -> None:
        """A one-title loop emits the same key in back-to-back slots.

        The Repair Shop cycle is a single episode and no flex, so each lap
        touches the next. Those collapse to one span. The same episode after
        filler is a later airing and stays, and the filler stays too.
        """
        now = 1_700_000_000.0
        ten = 10 * 60 * 1000
        flex = 15 * 60 * 1000
        lineup = {
            "version": 1,
            "imported_from": "test",
            "channels": {
                "ch-repair": {
                    "id": "ch-repair",
                    "name": "The Repair Shop",
                    "number": 109,
                    "guide_flex_title": "The Repair Shop · Up next",
                    "icon_url": "",
                    "start_time_ms": int(now * 1000),
                    "items": [
                        {
                            "type": "content",
                            "duration_ms": ten,
                            "program_id": "acc-1",
                            "title": "Accordion",
                            "show_title": "The Repair Shop",
                            "season": 1,
                            "episode": 1,
                            "media_type": "episode",
                            "plex_rating_key": "167715",
                        },
                        {
                            "type": "content",
                            "duration_ms": ten,
                            "program_id": "acc-1-copy",
                            "title": "Accordion",
                            "show_title": "The Repair Shop",
                            "season": 1,
                            "episode": 1,
                            "media_type": "episode",
                            "plex_rating_key": "167715",
                        },
                        {"type": "flex", "duration_ms": flex},
                        {
                            "type": "content",
                            "duration_ms": ten,
                            "program_id": "acc-later",
                            "title": "Accordion",
                            "show_title": "The Repair Shop",
                            "season": 1,
                            "episode": 1,
                            "media_type": "episode",
                            "plex_rating_key": "167715",
                        },
                        {"type": "flex", "duration_ms": flex},
                        {
                            "type": "content",
                            "duration_ms": ten,
                            "title": "Clock",
                            "media_type": "episode",
                            "plex_rating_key": "167800",
                        },
                    ],
                }
            },
        }
        with self._dir() as data_dir:
            save_schedule(lineup, data_dir=data_dir)
            settings = _settings(data_dir)
            guide = snapshot_if_scheduled(
                settings,
                now=now,
                window_seconds=60 * 60,
                include_programs=True,
            )
            source = play_source_for_channel(
                None,
                settings,
                SimpleNamespace(id="owner"),
                "ch-repair",
                now=now + 12 * 60,
                start_playback_fn=lambda *args, **kwargs: {
                    "session_id": "sess",
                    "stream_url": "/api/library/playback/sess/index.m3u8",
                    "rating_key": kwargs.get("rating_key"),
                },
            )
        # Playback stays on the current lap. The merged guide cell must not
        # seek twelve minutes into a ten-minute file.
        self.assertEqual(source["rating_key"], "167715")
        self.assertGreaterEqual(source["offset_ms"], 110_000)
        self.assertLessEqual(source["offset_ms"], 130_000)
        programs = guide["channels"][0]["programs"]
        accordion = [row for row in programs if row.get("plex_rating_key") == "167715"]
        self.assertEqual(len(accordion), 2)
        self.assertEqual(accordion[0]["stop"] - accordion[0]["start"], 20 * 60)
        self.assertEqual(accordion[1]["stop"] - accordion[1]["start"], 10 * 60)
        self.assertGreater(accordion[1]["start"], accordion[0]["stop"])
        flex_rows = [row for row in programs if row.get("is_flex")]
        self.assertEqual(len(flex_rows), 2)
        self.assertTrue(all(row.get("title") == "Between programs" for row in flex_rows))
        self.assertEqual(int(flex_rows[0]["stop"] - flex_rows[0]["start"]), 15 * 60)
        self.assertEqual(
            [row.get("plex_rating_key") for row in programs if not row.get("is_flex")],
            ["167715", "167715"],
        )

    def _dir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
