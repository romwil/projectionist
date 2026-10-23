"""One-title Live cycles rebuild from the station recipe and local library."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace

from projectionist.live_channels.filler import QUARTER_HOUR_MS
from projectionist.live_channels.native_schedule import (
    ensure_schedule,
    guide_programs,
    load_schedule,
    save_schedule,
)

_START_MS = QUARTER_HOUR_MS * 10
_TWENTY_MIN_MS = 20 * 60 * 1000


def _settings(data_dir: Path, station_meta: dict) -> SimpleNamespace:
    return SimpleNamespace(
        data_dir=str(data_dir),
        features=SimpleNamespace(live_channels_enabled=True),
        tunarr=SimpleNamespace(url="", station_meta=station_meta, pad_flex_max_minutes=15),
    )


def _channel(cid: str, name: str, number: int, rating_key: str, *, media_type: str) -> dict:
    return {
        "id": cid,
        "name": name,
        "number": number,
        "guide_flex_title": f"{name} · Up next",
        "icon_url": "",
        "start_time_ms": _START_MS,
        "items": [
            {
                "type": "content",
                "duration_ms": _TWENTY_MIN_MS,
                "program_id": "stuck",
                "title": "Stuck",
                "show_title": "",
                "season": 1,
                "episode": 1,
                "year": 1970,
                "overview": "",
                "content_rating": "",
                "media_type": media_type,
                "plex_rating_key": rating_key,
            }
        ],
    }


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE library_items (
            id INTEGER PRIMARY KEY,
            rating_key TEXT,
            media_type TEXT,
            title TEXT,
            year INTEGER,
            summary TEXT DEFAULT '',
            genres TEXT DEFAULT '[]',
            runtime_minutes INTEGER,
            content_rating TEXT DEFAULT '',
            collection_name TEXT DEFAULT '',
            tmdb_collection_id INTEGER
        );
        CREATE TABLE library_episodes (
            id INTEGER PRIMARY KEY,
            show_item_id INTEGER,
            rating_key TEXT,
            season_number INTEGER,
            episode_number INTEGER,
            title TEXT,
            runtime_minutes INTEGER,
            duration_ms INTEGER
        );
        CREATE TABLE library_facets (
            item_id INTEGER,
            facet_type TEXT,
            facet_value TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def _content_keys(channel: dict) -> list[str]:
    return [
        str(item.get("plex_rating_key") or "")
        for item in channel["items"]
        if item.get("type") == "content"
    ]


class ScheduleCycleTests(unittest.TestCase):
    def test_show_cycle_advances_through_episodes_and_is_saved(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-repair",
                title="The Repair Shop",
                episodes=[
                    ("ep-a", 1, 1, "Accordion"),
                    ("ep-b", 1, 2, "Clock"),
                    ("ep-c", 1, 3, "Vase"),
                ],
            )
            save_schedule(
                {
                    "version": 1,
                    "imported_from": "tunarr_sqlite",
                    "channels": {
                        "repair": _channel(
                            "repair", "The Repair Shop", 109, "ep-a", media_type="episode"
                        )
                    },
                },
                data_dir=data_dir,
            )
            settings = _settings(
                data_dir,
                {
                    "repair": {
                        "source": "show",
                        "programming_mode": "sequential",
                        "media_scope": "tv",
                        "item_hints": ["The Repair Shop"],
                        "item_rating_keys": ["show-repair"],
                    }
                },
            )
            ensure_schedule(settings, data_dir=data_dir)
            saved = load_schedule(data_dir=data_dir)
            keys = _content_keys(saved["channels"]["repair"])
            self.assertEqual(keys, ["ep-a", "ep-b", "ep-c"])
            self.assertNotEqual(keys[0], keys[1])
            flex = [
                item
                for item in saved["channels"]["repair"]["items"]
                if item.get("type") == "flex"
            ]
            self.assertEqual(len(flex), 3)
            self.assertTrue(all(item["duration_ms"] == 10 * 60 * 1000 for item in flex))
            now = _START_MS / 1000.0
            programs = guide_programs(
                saved["channels"]["repair"],
                now=now,
                window_seconds=6 * 3600,
            )
            content = [row for row in programs if row.get("type") == "content"]
            lap = [
                row["program"]["plexRatingKey"]
                for row in content[:3]
            ]
            self.assertEqual(lap, ["ep-a", "ep-b", "ep-c"])
            self.assertEqual(content[3]["program"]["plexRatingKey"], "ep-a")

    def test_shuffle_show_uses_each_episode_once_per_lap(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=2,
                show_key="show-em",
                title="Emergency!",
                episodes=[
                    ("em-1", 1, 1, "Welcome"),
                    ("em-2", 1, 2, "Brushfire"),
                    ("em-3", 1, 3, "Cooks"),
                ],
            )
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "em": _channel("em", "Emergency! Channel", 107, "em-2", media_type="episode")
                    },
                },
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "em": {
                            "source": "show",
                            "programming_mode": "shuffle",
                            "media_scope": "tv",
                            "item_hints": ["Emergency!"],
                            "item_rating_keys": ["show-em"],
                        }
                    },
                ),
                data_dir=data_dir,
            )
            keys = _content_keys(load_schedule(data_dir=data_dir)["channels"]["em"])
            self.assertEqual(sorted(keys), ["em-1", "em-2", "em-3"])
            self.assertEqual(len(keys), len(set(keys)))

    def test_two_channels_are_not_stuck_on_the_same_episode(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-repair",
                title="The Repair Shop",
                episodes=[("rs-1", 1, 1, "A"), ("rs-2", 1, 2, "B"), ("rs-3", 1, 3, "C")],
            )
            self._show_with_episodes(
                data_dir,
                show_id=2,
                show_key="show-em",
                title="Emergency!",
                episodes=[("em-1", 1, 1, "D"), ("em-2", 1, 2, "E"), ("em-3", 1, 3, "F")],
            )
            stuck = "167715"
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "repair": _channel(
                            "repair", "The Repair Shop", 109, stuck, media_type="episode"
                        ),
                        "em": _channel(
                            "em", "Emergency! Channel", 107, stuck, media_type="episode"
                        ),
                    },
                },
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "repair": {
                            "source": "show",
                            "programming_mode": "sequential",
                            "media_scope": "tv",
                            "item_hints": ["The Repair Shop"],
                            "item_rating_keys": ["show-repair"],
                        },
                        "em": {
                            "source": "show",
                            "programming_mode": "sequential",
                            "media_scope": "tv",
                            "item_hints": ["Emergency!"],
                            "item_rating_keys": ["show-em"],
                        },
                    },
                ),
                data_dir=data_dir,
            )
            saved = load_schedule(data_dir=data_dir)
            repair = _content_keys(saved["channels"]["repair"])
            emergency = _content_keys(saved["channels"]["em"])
            self.assertEqual(repair, ["rs-1", "rs-2", "rs-3"])
            self.assertEqual(emergency, ["em-1", "em-2", "em-3"])
            self.assertNotEqual(repair[0], emergency[0])
            self.assertNotIn(stuck, repair)
            self.assertNotIn(stuck, emergency)

    def test_same_show_on_two_channels_does_not_open_on_the_same_episode(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-repair",
                title="The Repair Shop",
                episodes=[("rs-1", 1, 1, "A"), ("rs-2", 1, 2, "B"), ("rs-3", 1, 3, "C")],
            )
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "a": _channel("a", "Repair A", 1, "stuck", media_type="episode"),
                        "b": _channel("b", "Repair B", 2, "stuck", media_type="episode"),
                    },
                },
                data_dir=data_dir,
            )
            recipe = {
                "source": "show",
                "programming_mode": "sequential",
                "media_scope": "tv",
                "item_hints": ["The Repair Shop"],
                "item_rating_keys": ["show-repair"],
            }
            ensure_schedule(
                _settings(data_dir, {"a": dict(recipe), "b": dict(recipe)}),
                data_dir=data_dir,
            )
            saved = load_schedule(data_dir=data_dir)
            first_a = _content_keys(saved["channels"]["a"])[0]
            first_b = _content_keys(saved["channels"]["b"])[0]
            self.assertNotEqual(first_a, first_b)

    def test_collection_of_movies_rotates_with_quarter_hour_flex(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            conn = sqlite3.connect(data_dir / "projectionist.db")
            for index, (key, title) in enumerate(
                [("m-c", "Gamma"), ("m-a", "Alpha"), ("m-b", "Beta")],
                start=1,
            ):
                conn.execute(
                    """
                    INSERT INTO library_items
                        (id, rating_key, media_type, title, year, runtime_minutes, collection_name)
                    VALUES (?, ?, 'movie', ?, 1978, 20, 'Kung Fu Nights')
                    """,
                    (index, key, title),
                )
            conn.commit()
            conn.close()
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "kf": _channel("kf", "Kung Fu Theater", 104, "m-a", media_type="movie")
                    },
                },
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "kf": {
                            "source": "collection",
                            "programming_mode": "sequential",
                            "media_scope": "movies",
                            "collection_title": "Kung Fu Nights",
                        }
                    },
                ),
                data_dir=data_dir,
            )
            channel = load_schedule(data_dir=data_dir)["channels"]["kf"]
            self.assertEqual(_content_keys(channel), ["m-a", "m-b", "m-c"])
            kinds = [item["type"] for item in channel["items"]]
            self.assertEqual(kinds[0], "content")
            self.assertEqual(kinds[1], "flex")
            self.assertEqual(channel["items"][1]["duration_ms"], 10 * 60 * 1000)

    def test_theme_movie_station_rotates_matching_library_titles(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            conn = sqlite3.connect(data_dir / "projectionist.db")
            for index, (key, title, theme) in enumerate(
                [
                    ("m1", "Drunken Master", "martial arts"),
                    ("m2", "Enter the Dragon", "martial arts"),
                    ("m3", "Not Martial", "romance"),
                ],
                start=1,
            ):
                conn.execute(
                    """
                    INSERT INTO library_items
                        (id, rating_key, media_type, title, year, runtime_minutes, genres)
                    VALUES (?, ?, 'movie', ?, 1978, 20, '[]')
                    """,
                    (index, key, title),
                )
                conn.execute(
                    "INSERT INTO library_facets (item_id, facet_type, facet_value) VALUES (?, 'theme', ?)",
                    (index, theme),
                )
            conn.commit()
            conn.close()
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "kf": _channel("kf", "Kung Fu Theater", 104, "m1", media_type="movie")
                    },
                },
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "kf": {
                            "source": "motif",
                            "programming_mode": "sequential",
                            "media_scope": "movies",
                            "item_hints": ["Kung Fu Theater"],
                            "craft_filters": {"themes": ["martial arts"]},
                        }
                    },
                ),
                data_dir=data_dir,
            )
            keys = _content_keys(load_schedule(data_dir=data_dir)["channels"]["kf"])
            self.assertEqual(keys, ["m1", "m2"])

    def test_only_one_library_item_may_repeat_and_says_so(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-solo",
                title="Solo Show",
                episodes=[("only-ep", 1, 1, "Pilot")],
            )
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "solo": _channel("solo", "Solo Show", 3, "only-ep", media_type="episode")
                    },
                },
                data_dir=data_dir,
            )
            settings = _settings(
                data_dir,
                {
                    "solo": {
                        "source": "show",
                        "programming_mode": "sequential",
                        "media_scope": "tv",
                        "item_hints": ["Solo Show"],
                        "item_rating_keys": ["show-solo"],
                    }
                },
            )
            ensure_schedule(settings, data_dir=data_dir)
            channel = load_schedule(data_dir=data_dir)["channels"]["solo"]
            self.assertEqual(_content_keys(channel), ["only-ep"])
            self.assertIn("one playable title", channel["library_repeat_note"])
            self.assertIn("will repeat", channel["library_repeat_note"])
            now = _START_MS / 1000.0
            programs = guide_programs(channel, now=now, window_seconds=4 * 3600)
            content_keys = [
                row["program"]["plexRatingKey"]
                for row in programs
                if row.get("type") == "content"
            ]
            self.assertGreater(len(content_keys), 1)
            self.assertTrue(all(key == "only-ep" for key in content_keys))
            ensure_schedule(settings, data_dir=data_dir)
            again = load_schedule(data_dir=data_dir)["channels"]["solo"]
            self.assertEqual(again["items"], channel["items"])

    def test_collection_of_twelve_does_not_air_heat_adjacent_after_rebuild(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            conn = sqlite3.connect(data_dir / "projectionist.db")
            titles = [
                ("heat", "Heat"),
                ("ronin", "Ronin"),
                ("heat2", "Heat 2"),
                ("thief", "Thief"),
                ("drive", "Drive"),
                ("le", "Le Samouraï"),
                ("miami", "Miami Vice"),
                ("collar", "The French Connection"),
                ("bullitt", "Bullitt"),
                ("getaway", "The Getaway"),
                ("to_live", "To Live and Die in L.A."),
                ("collateral", "Collateral"),
            ]
            for index, (key, title) in enumerate(titles, start=1):
                conn.execute(
                    """
                    INSERT INTO library_items
                        (id, rating_key, media_type, title, year, runtime_minutes, collection_name)
                    VALUES (?, ?, 'movie', ?, 1995, 20, 'Night Crime')
                    """,
                    (index, key, title),
                )
            conn.commit()
            conn.close()
            save_schedule(
                {
                    "version": 1,
                    "channels": {
                        "crime": _channel("crime", "Night Crime", 101, "heat", media_type="movie")
                    },
                },
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "crime": {
                            "source": "collection",
                            "programming_mode": "sequential",
                            "media_scope": "movies",
                            "collection_title": "Night Crime",
                        }
                    },
                ),
                data_dir=data_dir,
            )
            channel = load_schedule(data_dir=data_dir)["channels"]["crime"]
            keys = _content_keys(channel)
            self.assertEqual(len(keys), 12)
            self.assertEqual(len(set(keys)), 12)
            for left, right in zip(keys, keys[1:]):
                self.assertNotEqual(left, right)
            self.assertNotEqual(keys[0], keys[-1])
            self.assertNotIn("library_repeat_note", channel)

    def test_adjacent_same_key_rebuilds_unless_nonstop_show(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            conn = sqlite3.connect(data_dir / "projectionist.db")
            for index, (key, title) in enumerate(
                [("heat", "Heat"), ("ronin", "Ronin"), ("thief", "Thief")],
                start=1,
            ):
                conn.execute(
                    """
                    INSERT INTO library_items
                        (id, rating_key, media_type, title, year, runtime_minutes, collection_name)
                    VALUES (?, ?, 'movie', ?, 1995, 20, 'Night Crime')
                    """,
                    (index, key, title),
                )
            conn.commit()
            conn.close()
            stuck = _channel("crime", "Night Crime", 101, "heat", media_type="movie")
            stuck["items"] = [
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "heat-1",
                    "title": "Heat",
                    "show_title": "",
                    "media_type": "movie",
                    "plex_rating_key": "heat",
                },
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "heat-2",
                    "title": "Heat",
                    "show_title": "",
                    "media_type": "movie",
                    "plex_rating_key": "heat",
                },
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "ronin",
                    "title": "Ronin",
                    "show_title": "",
                    "media_type": "movie",
                    "plex_rating_key": "ronin",
                },
            ]
            save_schedule({"version": 1, "channels": {"crime": stuck}}, data_dir=data_dir)
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "crime": {
                            "source": "collection",
                            "programming_mode": "sequential",
                            "media_scope": "movies",
                            "collection_title": "Night Crime",
                        }
                    },
                ),
                data_dir=data_dir,
            )
            keys = _content_keys(load_schedule(data_dir=data_dir)["channels"]["crime"])
            self.assertEqual(keys, ["heat", "ronin", "thief"])
            for left, right in zip(keys, keys[1:]):
                self.assertNotEqual(left, right)

        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-g",
                title="Gilligan's Island",
                episodes=[
                    ("g1", 1, 1, "One"),
                    ("g2", 1, 2, "Two"),
                ],
            )
            channel = _channel("g", "Gilligan's Island", 105, "g1", media_type="episode")
            channel["items"] = [
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "g1-a",
                    "title": "One",
                    "show_title": "Gilligan's Island",
                    "media_type": "episode",
                    "plex_rating_key": "g1",
                },
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "g1-b",
                    "title": "One",
                    "show_title": "Gilligan's Island",
                    "media_type": "episode",
                    "plex_rating_key": "g1",
                },
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "g2",
                    "title": "Two",
                    "show_title": "Gilligan's Island",
                    "media_type": "episode",
                    "plex_rating_key": "g2",
                },
            ]
            original = _content_keys(channel)
            save_schedule({"version": 1, "channels": {"g": channel}}, data_dir=data_dir)
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "g": {
                            "source": "show",
                            "programming_mode": "sequential",
                            "media_scope": "tv",
                            "item_hints": ["Gilligan's Island"],
                            "item_rating_keys": ["show-g"],
                        }
                    },
                ),
                data_dir=data_dir,
            )
            saved = _content_keys(load_schedule(data_dir=data_dir)["channels"]["g"])
            self.assertEqual(saved, original)
            self.assertEqual(saved[0], saved[1])

    def test_multi_title_cycle_is_left_alone(self) -> None:
        with self._dir() as raw:
            data_dir = Path(raw)
            _init_db(data_dir / "projectionist.db")
            self._show_with_episodes(
                data_dir,
                show_id=1,
                show_key="show-g",
                title="Gilligan's Island",
                episodes=[
                    ("g1", 1, 1, "One"),
                    ("g2", 1, 2, "Two"),
                    ("g3", 1, 3, "Three"),
                ],
            )
            channel = _channel("g", "Gilligan's Island", 105, "g1", media_type="episode")
            channel["items"].append(
                {
                    "type": "content",
                    "duration_ms": _TWENTY_MIN_MS,
                    "program_id": "g2",
                    "title": "Two",
                    "show_title": "Gilligan's Island",
                    "season": 1,
                    "episode": 2,
                    "media_type": "episode",
                    "plex_rating_key": "g2",
                }
            )
            original = list(channel["items"])
            save_schedule(
                {"version": 1, "channels": {"g": channel}},
                data_dir=data_dir,
            )
            ensure_schedule(
                _settings(
                    data_dir,
                    {
                        "g": {
                            "source": "show",
                            "programming_mode": "sequential",
                            "media_scope": "tv",
                            "item_hints": ["Gilligan's Island"],
                            "item_rating_keys": ["show-g"],
                        }
                    },
                ),
                data_dir=data_dir,
            )
            saved = load_schedule(data_dir=data_dir)["channels"]["g"]
            self.assertEqual(_content_keys(saved), ["g1", "g2"])
            self.assertEqual(len(saved["items"]), len(original))

    def _show_with_episodes(
        self,
        data_dir: Path,
        *,
        show_id: int,
        show_key: str,
        title: str,
        episodes: list[tuple[str, int, int, str]],
    ) -> None:
        conn = sqlite3.connect(data_dir / "projectionist.db")
        conn.execute(
            """
            INSERT INTO library_items (id, rating_key, media_type, title, year, runtime_minutes)
            VALUES (?, ?, 'show', ?, 1972, 0)
            """,
            (show_id, show_key, title),
        )
        for index, (key, season, episode, name) in enumerate(episodes, start=1):
            conn.execute(
                """
                INSERT INTO library_episodes
                    (id, show_item_id, rating_key, season_number, episode_number, title,
                     runtime_minutes, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, 20, ?)
                """,
                (show_id * 100 + index, show_id, key, season, episode, name, _TWENTY_MIN_MS),
            )
        conn.commit()
        conn.close()

    def _dir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


if __name__ == "__main__":
    unittest.main()
