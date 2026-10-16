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
            with (
                patch("projectionist.live_channels.guide.TunarrClient", RefuseTunarr),
                patch("projectionist.connectors.tunarr.TunarrClient", RefuseTunarr),
                patch(
                    "projectionist.connectors.tunarr.tunarr_reachable",
                    side_effect=AssertionError("tunarr reachability"),
                ),
            ):
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
            self.assertTrue(str(flex["title"]).endswith("· Up next"))
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
            with patch("projectionist.live_channels.guide.TunarrClient", RefuseTunarr):
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

    def test_flex_slot_does_not_start_a_play_session(self) -> None:
        now = 1_700_000_000.0
        # First title is 120s and began 5s before `now`, so flex starts at +115s.
        flex_now = now + 115 + 1

        def fail_start(*args, **kwargs):
            raise AssertionError("flex must not start library playback")

        with self._dir() as data_dir:
            save_schedule(_lineup(now=now), data_dir=data_dir)
            source = play_source_for_channel(
                None,
                _settings(data_dir),
                SimpleNamespace(id="owner"),
                "ch-mystery",
                now=flex_now,
                start_playback_fn=fail_start,
            )
        self.assertTrue(source["is_flex"])
        self.assertEqual(source["stream_url"], "")
        self.assertTrue(str(source["title"]).endswith("· Up next"))

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
            with patch("projectionist.connectors.tunarr.TunarrClient", RefuseTunarr):
                doc = import_tunarr_lineup(data_dir)
            self.assertIsNotNone(doc)
            channel = doc["channels"]["ch-1"]
            self.assertEqual(channel["name"], "Gilligan's Island")
            self.assertEqual(channel["items"][0]["plex_rating_key"], "185000")
            self.assertEqual(channel["items"][1]["type"], "flex")

    def _dir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
