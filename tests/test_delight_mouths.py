"""HV-02 / HV-03 / YT-02 / YT-03 — chat, poster why, pick-for-me, youth YIR leak check."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from projectionist.agent.tools import ToolRegistry
from projectionist.config_store import Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.library.feeds import feed_for_you, feed_pick_for_me
from projectionist.library.plot_kinship import KINSHIP_CACHE_NOT_READY_NOTE
from projectionist.notifications.recommendation_reasons import list_linked_unwatched
from projectionist.watch_tracker.correlate import rebuild_watch_derivations
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.year_in_review.snapshot import build_reel_for_user
from tests.test_household_bridges import (
    BAKE_PLOT,
    SPY_PLOT,
    _explainable_neighbor,
    _insert_completion,
    _title,
)


class ChatMouthTests(unittest.IsolatedAsyncioTestCase):
    async def test_similar_title_why_matches_for_you_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            house = _title(
                db,
                rating_key="house",
                title="House",
                year=2004,
                view_count=1,
                summary=BAKE_PLOT,
            )
            contagion = _title(
                db,
                rating_key="contagion",
                title="Contagion",
                year=2011,
                view_count=0,
                summary=SPY_PLOT,
            )
            _explainable_neighbor(
                db, house, contagion, seed_text=BAKE_PLOT, peer_text=SPY_PLOT
            )
            _insert_completion(db, user_id="owner-1", rating_key="house", completed_at_ms=1_700_000_000_000)

            feed = feed_for_you(db, limit=8)
            self.assertTrue(feed["items"])
            sentence = str((feed["items"][0].get("explanation") or {}).get("sentence") or "")
            self.assertTrue(sentence)
            self.assertEqual((feed["items"][0].get("explanation") or {}).get("kind"), "watched_bridge")

            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            similar = json.loads(
                await registry.execute("find_similar_titles", {"title": "House", "year": 2004})
            )
            self.assertTrue(similar["items"])
            self.assertEqual(similar["items"][0]["title"], "Contagion")
            self.assertEqual(similar["items"][0]["explanation"]["sentence"], sentence)
            self.assertEqual(registry.cards[0].recommendation_reason, sentence)

    async def test_empty_for_you_uses_note_not_cosine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = _title(db, rating_key="seed", title="Seed", year=1999, summary="A quiet farm.")
            peer = _title(
                db,
                rating_key="peer",
                title="Cosine Peer",
                year=2001,
                summary="Unrelated city thriller.",
            )
            db.set_neighbors(seed, [(peer, 0.99, 0.05)])

            empty = feed_for_you(db, limit=8)
            self.assertTrue(empty["empty"])
            self.assertIn("not a cosine guess", str(empty.get("note") or "").lower())

            registry = ToolRegistry(db, Settings(), DEFAULT_LENS_ID)
            for_you = json.loads(await registry.execute("get_for_you", {}))
            self.assertTrue(for_you.get("empty"))
            self.assertEqual(for_you.get("note"), empty["note"])
            self.assertEqual(for_you.get("items"), [])

            similar = json.loads(
                await registry.execute("find_similar_titles", {"item_id": seed})
            )
            self.assertEqual(similar["items"], [])
            self.assertEqual(similar["note"], KINSHIP_CACHE_NOT_READY_NOTE)
            self.assertFalse(any(c.title == "Cosine Peer" for c in registry.cards))


class PickForMeMouthTests(unittest.TestCase):
    def test_named_bridge_or_no_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            seed = _title(
                db,
                rating_key="pad-1",
                title="Paddington",
                year=2014,
                view_count=1,
                content_rating="PG",
                summary=BAKE_PLOT,
            )
            peer = _title(
                db,
                rating_key="pad-2",
                title="Paddington 2",
                year=2017,
                view_count=0,
                content_rating="PG",
                summary=SPY_PLOT,
            )
            filler = _title(
                db,
                rating_key="random-g",
                title="Random G",
                year=2020,
                view_count=0,
                content_rating="G",
                summary="A gentle talking animal picnic.",
            )
            adult = _title(
                db,
                rating_key="adult-r",
                title="Adult R",
                year=2018,
                view_count=0,
                content_rating="R",
                summary="A violent heist after dark.",
            )
            _explainable_neighbor(db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT)
            _insert_completion(db, user_id="youth-1", rating_key="pad-1", completed_at_ms=1_700_000_000_000)

            named = list_linked_unwatched(db, limit=8, youth_max_rating="PG-13")
            self.assertTrue(named)
            sentence = str((named[0].get("explanation") or {}).get("sentence") or "")
            self.assertTrue(sentence)
            self.assertNotIn("Unwatched pick for you", sentence)

            feed = feed_pick_for_me(
                db,
                limit=8,
                youth_max_rating="PG-13",
                filler_items=[
                    {"id": filler, "title": "Random G", "content_rating": "G"},
                    {"id": adult, "title": "Adult R", "content_rating": "R", "why": "Unwatched pick for you"},
                ],
            )
            titles = [item["title"] for item in feed["items"]]
            self.assertIn("Paddington 2", titles)
            self.assertNotIn("Adult R", titles)
            self.assertEqual(feed["items"][0].get("why"), sentence)
            filler_row = next(item for item in feed["items"] if item["title"] == "Random G")
            self.assertFalse(filler_row.get("why"))
            self.assertNotIn("Unwatched pick for you", json.dumps(feed))


class YouthYearInReviewLeakTests(unittest.TestCase):
    def test_youth_reel_does_not_mix_adult_finishes(self) -> None:
        from projectionist.watch_tracker.rollups import year_bounds_ms

        year = 2024
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_plex_user(
                user_id="owner-1",
                display_name="Owner",
                email="owner@example.com",
                plex_user_id="111",
                role="owner",
            )
            db.upsert_plex_user(
                user_id="youth-1",
                display_name="Youth",
                email="youth@example.com",
                plex_user_id="222",
                role="member",
            )
            with db.connect() as conn:
                conn.execute("UPDATE users SET is_youth = 1 WHERE id = ?", ("youth-1",))
            db.update_user_profile("owner-1", year_in_review_opt_in=True)
            db.update_user_profile("youth-1", year_in_review_opt_in=True)

            start_ms, _ = year_bounds_ms(year)
            events = []
            for i, title in enumerate(("Heat", "Casino", "Goodfellas")):
                key = f"adult-r-{i}"
                db.upsert_library_item(
                    {
                        "rating_key": key,
                        "media_type": "movie",
                        "title": title,
                        "year": 1995 + i,
                        "content_rating": "R",
                        "genres": ["Crime"],
                    }
                )
                events.append(
                    WatchEventInput(
                        source="plex_history",
                        source_event_id=f"owner-{key}",
                        source_event_kind="history_played",
                        server_machine_id="srv",
                        source_user_key="111",
                        rating_key=key,
                        media_type="movie",
                        occurred_at_ms=start_ms + (i + 1) * 86_400_000,
                        terminal=True,
                    )
                )
            for i, title in enumerate(("Paddington", "Kid Film 0", "Kid Film 1", "Kid Film 2")):
                key = "youth-g" if i == 0 else f"youth-extra-{i}"
                db.upsert_library_item(
                    {
                        "rating_key": key,
                        "media_type": "movie",
                        "title": title,
                        "year": 2010 + i,
                        "content_rating": "G" if i else "PG",
                        "genres": ["Family"],
                    }
                )
                events.append(
                    WatchEventInput(
                        source="plex_history",
                        source_event_id=f"youth-{key}",
                        source_event_kind="history_played",
                        server_machine_id="srv",
                        source_user_key="222",
                        rating_key=key,
                        media_type="movie",
                        occurred_at_ms=start_ms + (i + 10) * 86_400_000,
                        terminal=True,
                    )
                )
            ingest_watch_events(db, events)
            rebuild_watch_derivations(db, user_id="owner-1")
            rebuild_watch_derivations(db, user_id="youth-1")

            youth_empty = build_reel_for_user(db, user_id="youth-1", year=1999)
            self.assertEqual(youth_empty["status"], "empty")
            self.assertEqual(youth_empty["reel"].get("chapters") or [], [])

            youth = build_reel_for_user(db, user_id="youth-1", year=year)
            owner = build_reel_for_user(db, user_id="owner-1", year=year)
            youth_blob = json.dumps(youth["reel"])
            owner_blob = json.dumps(owner["reel"])
            self.assertNotIn("Heat", youth_blob)
            self.assertNotIn("Casino", youth_blob)
            self.assertNotIn("Goodfellas", youth_blob)
            self.assertIn("Paddington", youth_blob)
            self.assertIn("Heat", owner_blob)
            self.assertNotIn("Paddington", owner_blob)


if __name__ == "__main__":
    unittest.main()
