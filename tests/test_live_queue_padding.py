"""Rotational queue padding: slot math, feed picks, and the real lineup path."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from projectionist.library.db import Database
from projectionist.live_channels.publish import (
    apply_queue_padding,
    merge_refill_recipe_payload,
    programming_body_for_recipe,
    recipe_from_station_meta,
    set_station_meta,
    station_craft_snapshot,
)
from projectionist.live_channels.queue_padding import (
    default_queue_pad,
    feed_candidates,
    normalize_queue_pad,
    order_padded_programs,
    pad_slots,
    queue_pad_options,
    queue_pad_plan,
)
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    recipe_from_mapping,
)

ONE_HOUR = 3_600_000


class SlotMathTests(unittest.TestCase):
    def test_four_playing_up_to_five_pads_one(self) -> None:
        self.assertEqual(pad_slots(5, 4), 1)

    def test_five_playing_up_to_five_pads_none(self) -> None:
        self.assertEqual(pad_slots(5, 5), 0)

    def test_more_playing_than_slots_pads_none(self) -> None:
        self.assertEqual(pad_slots(3, 9), 0)

    def test_nothing_playing_up_to_three_pads_three(self) -> None:
        self.assertEqual(pad_slots(3, 0), 3)

    def test_up_to_is_clamped_to_one_through_five(self) -> None:
        self.assertEqual(pad_slots(99, 0), 5)
        self.assertEqual(pad_slots(0, 0), 1)
        self.assertEqual(pad_slots("bad", 0), 5)

    def test_plan_reports_feed_and_counts(self) -> None:
        plan = queue_pad_plan({"up_to": 5, "feed": "recently_released"}, 4)
        self.assertEqual(
            plan,
            {"enabled": True, "up_to": 5, "feed": "recently_released", "playing": 4, "pad": 1},
        )
        self.assertFalse(queue_pad_plan({}, 2)["enabled"])
        self.assertEqual(queue_pad_plan({}, 2)["pad"], 0)

    def test_normalize_defaults_and_rejects_unknown_feed(self) -> None:
        self.assertEqual(normalize_queue_pad(None), {})
        self.assertEqual(normalize_queue_pad({}), {})
        self.assertEqual(
            normalize_queue_pad({"up_to": 9, "feed": "bogus"}),
            {"up_to": 5, "feed": "recently_added"},
        )
        self.assertEqual(default_queue_pad(), {"up_to": 5, "feed": "recently_added"})

    def test_options_offer_one_to_five_and_two_feeds(self) -> None:
        opts = queue_pad_options()
        self.assertEqual(opts["up_to"], [1, 2, 3, 4, 5])
        self.assertEqual([f["id"] for f in opts["feeds"]], ["recently_added", "recently_released"])
        self.assertEqual(opts["default"], {"up_to": 5, "feed": "recently_added"})

    def test_order_keeps_playing_block_then_pads(self) -> None:
        playing = [{"id": "a"}, {"id": "b"}]
        pads = [{"id": "x"}]
        ordered = order_padded_programs(playing, pads)
        self.assertEqual([p["id"] for p in ordered], ["a", "b", "x"])
        self.assertTrue(ordered[-1]["queue_pad"])
        self.assertNotIn("queue_pad", ordered[0])


class RecipePersistenceTests(unittest.TestCase):
    def test_recipe_round_trips_and_clamps(self) -> None:
        recipe = recipe_from_mapping(
            {"name": "N", "number": 101, "queue_pad": {"up_to": 7, "feed": "recently_released"}}
        )
        self.assertEqual(recipe.queue_pad, {"up_to": 5, "feed": "recently_released"})
        self.assertEqual(recipe.to_dict()["queue_pad"], recipe.queue_pad)
        self.assertEqual(recipe_from_mapping({"name": "N", "number": 1}).queue_pad, {})

    def test_station_meta_persists_and_refill_keeps_it(self) -> None:
        settings = SimpleNamespace(tunarr=SimpleNamespace(station_meta={}))
        set_station_meta(
            settings,
            "ch-1",
            source="show",
            programming_mode="sequential",
            item_rating_keys=["42"],
            queue_pad={"up_to": 4, "feed": "recently_added"},
        )
        self.assertEqual(
            station_craft_snapshot(settings, "ch-1")["queue_pad"],
            {"up_to": 4, "feed": "recently_added"},
        )
        stored = recipe_from_station_meta(settings, "ch-1", name="Show", number=105)
        self.assertEqual(stored.queue_pad, {"up_to": 4, "feed": "recently_added"})
        # An Admin refill overlay with no queue_pad keeps the stored setting.
        merged = merge_refill_recipe_payload(
            {"media_scope": "tv"}, stored=stored, name="Show", number=105, stored_scope="tv"
        )
        self.assertEqual(merged.queue_pad, {"up_to": 4, "feed": "recently_added"})
        # Clearing is explicit.
        set_station_meta(settings, "ch-1", queue_pad={})
        self.assertEqual(station_craft_snapshot(settings, "ch-1")["queue_pad"], {})


def _library(tmp: str) -> Database:
    db = Database(Path(tmp) / "test.db")
    rows = [
        ("rk-old", "movie", "Old Reel", 1970, 1_000, "1970-01-01"),
        ("rk-new", "movie", "Newest Add", 2020, 9_000, "2020-06-01"),
        ("rk-mid", "movie", "Middle Add", 2010, 5_000, "2024-03-01"),
        ("rk-future", "movie", "Not Out Yet", 2099, 8_000, "2099-01-01"),
        ("rk-show", "show", "Fresh Show", 2024, 7_000, None),
    ]
    for key, media_type, title, year, added_at, release in rows:
        db.upsert_library_item(
            {
                "rating_key": key,
                "media_type": media_type,
                "title": title,
                "year": year,
                "added_at": added_at,
                "release_date": release if media_type == "movie" else None,
                "first_air_date": "2024-09-01" if media_type == "show" else None,
            }
        )
    return db


class FeedCandidateTests(unittest.TestCase):
    def test_recently_added_is_newest_first_and_honours_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _library(tmp)
            rows = feed_candidates(db, "recently_added", count=2, exclude_rating_keys=["rk-new"])
        keys = [r["rating_key"] for r in rows]
        self.assertNotIn("rk-new", keys)
        self.assertEqual(keys[0], "rk-future")  # added_at 8_000, no release filter on "added"

    def test_recently_released_skips_future_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _library(tmp)
            rows = feed_candidates(
                db, "recently_released", count=3, today=date(2026, 10, 2)
            )
        keys = [r["rating_key"] for r in rows]
        self.assertNotIn("rk-future", keys)
        self.assertEqual(keys[0], "rk-show")  # first aired 2024-09, newest release
        self.assertEqual(keys[1], "rk-mid")

    def test_media_scope_filters_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _library(tmp)
            tv = feed_candidates(db, "recently_added", count=3, media_scope="tv")
        self.assertEqual([r["rating_key"] for r in tv], ["rk-show"])

    def test_zero_slots_or_missing_db_returns_nothing(self) -> None:
        self.assertEqual(feed_candidates(None, "recently_added", count=3), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(feed_candidates(_library(tmp), "recently_added", count=0), [])


class _FakeClient:
    def list_program_descendants(self, show_id: str):
        return [
            {
                "id": f"{show_id}-ep1",
                "type": "episode",
                "duration": ONE_HOUR,
                "title": "Pilot",
                "showId": show_id,
            }
        ]


def _program(pid: str, key: str, ptype: str = "movie", title: str = "") -> dict:
    return {
        "id": pid,
        "type": ptype,
        "duration": ONE_HOUR,
        "title": title or pid,
        "externalKey": key,
        "plex_keys": [key],
    }


def _catalog() -> list:
    return [
        _program("p-new", "rk-new"),
        _program("p-mid", "rk-mid"),
        _program("p-old", "rk-old"),
        {
            "id": "show-1",
            "type": "show",
            "duration": ONE_HOUR,
            "title": "Fresh Show",
            "externalKey": "rk-show",
        },
    ]


def _recipe(**kwargs) -> ChannelRecipe:
    return recipe_from_mapping(
        {"name": "Block", "number": 120, "programming_mode": "sequential", **kwargs}
    )


def _playing(n: int) -> list:
    return [
        {"id": f"play-{i}", "duration": ONE_HOUR, "title": f"Playing {i}", "plex_keys": [f"pk-{i}"]}
        for i in range(n)
    ]


class ApplyQueuePaddingTests(unittest.TestCase):
    def _pad(self, db, programs, **recipe_kwargs):
        stats: dict = {}
        out = apply_queue_padding(
            _FakeClient(),
            _recipe(**recipe_kwargs),
            programs,
            catalog=_catalog(),
            media_scope="both",
            settings=None,
            db=db,
            stats=stats,
        )
        return out, stats

    def test_four_playing_up_to_five_adds_exactly_one_from_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out, stats = self._pad(
                _library(tmp), _playing(4), queue_pad={"up_to": 5, "feed": "recently_added"}
            )
        self.assertEqual(len(out), 5)
        self.assertEqual([p["id"] for p in out[:4]], [f"play-{i}" for i in range(4)])
        self.assertTrue(out[4]["queue_pad"])
        self.assertEqual(stats["queue_pad"]["pad"], 1)
        self.assertEqual(stats["queue_pad"]["added"], 1)

    def test_five_playing_up_to_five_adds_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out, stats = self._pad(
                _library(tmp), _playing(5), queue_pad={"up_to": 5, "feed": "recently_added"}
            )
        self.assertEqual(len(out), 5)
        self.assertFalse(any(p.get("queue_pad") for p in out))
        self.assertEqual(stats["queue_pad"]["pad"], 0)

    def test_nothing_playing_up_to_three_fills_from_chosen_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = _library(tmp)
            added, _ = self._pad(db, [], queue_pad={"up_to": 3, "feed": "recently_added"})
            released, _ = self._pad(db, [], queue_pad={"up_to": 3, "feed": "recently_released"})
        self.assertEqual(len(added), 3)
        self.assertEqual(len(released), 3)
        self.assertTrue(all(p["queue_pad"] for p in added))
        # Show feed rows resolve to one episode, never the whole series.
        self.assertIn("show-1-ep1", [p["id"] for p in released])
        # The feeds order differently: newest added vs newest released.
        self.assertEqual(added[0]["id"], "p-new")
        self.assertEqual(released[0]["id"], "show-1-ep1")

    def test_no_setting_leaves_the_lineup_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out, stats = self._pad(_library(tmp), _playing(2))
        self.assertEqual(len(out), 2)
        self.assertNotIn("queue_pad", stats)

    def test_pad_never_repeats_a_playing_title(self) -> None:
        playing = [
            {"id": "p-new", "duration": ONE_HOUR, "title": "Newest Add", "plex_keys": ["rk-new"]}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = self._pad(
                _library(tmp), playing, queue_pad={"up_to": 2, "feed": "recently_added"}
            )
        ids = [p["id"] for p in out]
        self.assertEqual(ids.count("p-new"), 1)
        self.assertEqual(len(out), 2)


class LineupOrderTests(unittest.TestCase):
    def test_padded_shuffle_channel_keeps_playing_then_pad_order(self) -> None:
        recipe = _recipe(programming_mode="shuffle", queue_pad={"up_to": 3, "feed": "recently_added"})
        programs = order_padded_programs(_playing(2), [_program("p-new", "rk-new")])
        body = programming_body_for_recipe(recipe, programs=programs, pad_lineups=False)
        self.assertEqual(body["type"], "manual")
        ids = [row["id"] for row in body["lineup"]]
        self.assertEqual(ids[-1], "p-new")
        self.assertEqual(sorted(ids[:2]), ["play-0", "play-1"])

    def test_unpadded_shuffle_channel_still_uses_random_schedule(self) -> None:
        recipe = _recipe(programming_mode="shuffle")
        programs = [_program("a", "k1"), _program("b", "k2")]
        body = programming_body_for_recipe(recipe, programs=programs, pad_lineups=False)
        self.assertEqual(body["type"], "random")

    def test_sequential_padded_lineup_is_in_order(self) -> None:
        recipe = _recipe(queue_pad={"up_to": 5, "feed": "recently_added"})
        assert recipe.programming_mode == ProgrammingMode.SEQUENTIAL
        programs = order_padded_programs(_playing(3), [_program("p-mid", "rk-mid")])
        body = programming_body_for_recipe(recipe, programs=programs, pad_lineups=False)
        self.assertEqual(
            [row["id"] for row in body["lineup"]], ["play-0", "play-1", "play-2", "p-mid"]
        )


if __name__ == "__main__":
    unittest.main()
