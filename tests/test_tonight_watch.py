"""TN-01 / TN-02 / XC-03: tonight is For you + continue, with playable honesty."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from typing import Optional
from unittest import skipUnless
from unittest.mock import patch

from projectionist.config_store import Settings, YouthSettings
from projectionist.library.db import Database
from projectionist.library.plot_kinship import plot_link_json, specific_plot_link
from projectionist.library.tonight import TONIGHT_EMPTY_NOTE, build_tonight_watch

BAKE_PLOT = "Amateur bakers compete around a signature bake inside a failing colony."
SPY_PLOT = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."
HOUSE_JUNK = (
    "The team try to cure complex and rare diseases from very ill ordinary people "
    "in the United States of America."
)
BEAUTY_JUNK = (
    "They uncover a sexually transmitted virus that transforms ordinary people "
    "into visions of physical perfection, but with terrifying consequences."
)

try:
    from projectionist.mcp import server as mcp_server
    from projectionist.mcp.mode import set_mcp_mode

    HAS_MCP = True
except Exception:  # noqa: BLE001
    HAS_MCP = False


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 2015,
        "genres": ["Drama"],
        "keywords": [],
        "summary": "",
        "view_count": 0,
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


def _explainable_neighbor(db: Database, seed_id: int, peer_id: int, *, seed_text: str, peer_text: str) -> None:
    link = specific_plot_link(seed_text=seed_text, peer_text=peer_text, shelf_labels=set())
    link_json = plot_link_json(link) or "{}"
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO item_neighbors
                (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(seed_id), int(peer_id), 0.92, 0.8, 1 if link else 0, link_json),
        )


def _ensure_user(db: Database, user_id: str) -> None:
    db.upsert_plex_user(
        user_id=user_id,
        display_name=user_id.title(),
        email=f"{user_id}@example.com",
        plex_user_id=f"plex-{user_id}",
        role="member",
    )


def _insert_completion(
    db: Database,
    *,
    user_id: Optional[str],
    rating_key: str,
    completed_at_ms: int,
    media_type: str = "movie",
    parent_rating_key: Optional[str] = None,
) -> None:
    if user_id:
        _ensure_user(db, user_id)
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    completion_id = f"cmp-{uuid.uuid4().hex[:12]}"
    source_user_key = str(user_id or "household")
    now = time.time()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO watch_events (
                id, source, source_event_id, source_event_kind, server_machine_id,
                source_user_key, user_id, rating_key, parent_rating_key, media_type,
                occurred_at_ms, terminal, manual, payload_hash, ingested_at
            ) VALUES (?, 'plex', ?, 'scrobble', 'server', ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (
                event_id,
                event_id,
                source_user_key,
                user_id,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms,
                f"hash-{event_id}",
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO watch_sessions (
                id, user_id, source_user_key, rating_key, parent_rating_key, media_type,
                started_at_ms, ended_at_ms, first_event_id, last_event_id,
                client_count, event_count, algorithm_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?, ?)
            """,
            (
                session_id,
                user_id,
                source_user_key,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms - 1000,
                completed_at_ms,
                event_id,
                event_id,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO watch_completions (
                id, session_id, user_id, rating_key, parent_rating_key, media_type,
                completed_at_ms, confidence, basis, threshold_pct, evidence_event_id,
                algorithm_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'certain', 'threshold', 0.9, ?, 1, ?)
            """,
            (
                completion_id,
                session_id,
                user_id,
                rating_key,
                parent_rating_key,
                media_type,
                completed_at_ms,
                event_id,
                now,
            ),
        )


def _seed_house_contagion(db: Database) -> None:
    house = _title(
        db,
        rating_key="rk-house",
        tmdb_id=1408,
        title="House",
        year=2004,
        media_type="show",
        summary="A diagnostician leads a team through rare medical mysteries.",
    )
    contagion = _title(
        db,
        rating_key="rk-contagion",
        tmdb_id=99,
        title="Contagion",
        year=2011,
        summary=SPY_PLOT,
        runtime_minutes=106,
    )
    _explainable_neighbor(db, house, contagion, seed_text=BAKE_PLOT, peer_text=SPY_PLOT)
    db.upsert_library_episode(
        {
            "show_item_id": house,
            "rating_key": "ep-not-cancer",
            "season_number": 8,
            "episode_number": 2,
            "title": "Not Cancer",
            "summary": BAKE_PLOT,
        }
    )
    _insert_completion(
        db,
        user_id="will",
        rating_key="ep-not-cancer",
        parent_rating_key="rk-house",
        media_type="episode",
        completed_at_ms=1_700_000_000_000,
    )


def _seed_the_bear_paused(db: Database) -> int:
    show = _title(
        db,
        rating_key="rk-bear",
        tmdb_id=2000,
        title="The Bear",
        year=2022,
        media_type="show",
        summary="A young chef returns home to run a family sandwich shop.",
    )
    db.upsert_library_episode(
        {
            "show_item_id": show,
            "rating_key": "ep-bear-s2e3",
            "season_number": 2,
            "episode_number": 3,
            "title": "Sundae",
            "view_count": 1,
        }
    )
    db.upsert_library_episode(
        {
            "show_item_id": show,
            "rating_key": "ep-bear-s2e4",
            "season_number": 2,
            "episode_number": 4,
            "title": "Honeydew",
            "view_count": 0,
            "view_offset_ms": 12 * 60_000,
            "duration_ms": 30 * 60_000,
        }
    )
    db.update_show_episode_rollups(show)
    return show


class TonightWatchBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_house_peer_is_watched_bridge_and_playable(self) -> None:
        """TN-01 / XC-03: first item is a named library bridge."""
        _seed_house_contagion(self.db)
        payload = build_tonight_watch(self.db)
        self.assertEqual(payload["mode"], "watched_bridge")
        self.assertFalse(payload["empty"])
        self.assertIsNone(payload["note"])
        self.assertGreaterEqual(len(payload["items"]), 1)
        first = payload["items"][0]
        self.assertEqual(first["title"], "Contagion")
        self.assertEqual((first.get("explanation") or {}).get("kind"), "watched_bridge")
        self.assertTrue(first["in_library"])
        self.assertTrue(first["playable"])
        self.assertEqual(first["rating_key"], "rk-contagion")
        self.assertNotIn("Good pick for tonight", json.dumps(payload))

    def test_junk_only_overlap_is_empty_with_note(self) -> None:
        """TN-01 Success: ordinary-people overlap is empty, not a cosine guess."""
        house = _title(
            self.db,
            rating_key="rk-house",
            tmdb_id=1408,
            title="House",
            year=2004,
            media_type="show",
            summary=HOUSE_JUNK,
        )
        peer = _title(
            self.db,
            rating_key="rk-beauty",
            tmdb_id=99,
            title="The Beauty",
            year=2026,
            summary=BEAUTY_JUNK,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO item_neighbors
                    (item_id, neighbor_id, score, surprise_score, explainable, plot_link_json)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    house,
                    peer,
                    0.91,
                    0.8,
                    '{"sentence":"Both stories turn on an ordinary people.","terms":["ordinary people"]}',
                ),
            )
        self.db.upsert_library_episode(
            {
                "show_item_id": house,
                "rating_key": "ep-not-cancer",
                "season_number": 8,
                "episode_number": 2,
                "title": "Not Cancer",
                "summary": "",
            }
        )
        _insert_completion(
            self.db,
            user_id="will",
            rating_key="ep-not-cancer",
            parent_rating_key="rk-house",
            media_type="episode",
            completed_at_ms=1_700_000_000_000,
        )
        payload = build_tonight_watch(self.db)
        self.assertTrue(payload["empty"])
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["note"], TONIGHT_EMPTY_NOTE)
        blob = json.dumps(payload).lower()
        self.assertNotIn("ordinary people", blob)
        self.assertNotIn("watch tonight", blob)

    def test_in_progress_tv_is_continue_not_watched_bridge(self) -> None:
        """TN-02 Success: paused episode is continue with season/episode."""
        _seed_house_contagion(self.db)
        _seed_the_bear_paused(self.db)
        payload = build_tonight_watch(self.db)
        continue_titles = [item["title"] for item in payload["continue"]]
        self.assertIn("The Bear", continue_titles)
        bear = next(item for item in payload["continue"] if item["title"] == "The Bear")
        self.assertEqual(bear["season"], 2)
        self.assertEqual(bear["episode"], 4)
        self.assertEqual(bear["kind"], "continue")
        self.assertNotEqual(bear.get("kind"), "watched_bridge")
        self.assertIn("S2E4", bear["sentence"])
        self.assertIn("paused 12 minutes in", bear["sentence"])
        self.assertTrue(bear["in_library"])
        self.assertTrue(bear["playable"])
        item_titles = {item["title"] for item in payload["items"]}
        self.assertNotIn("The Bear", item_titles)
        for item in payload["items"]:
            self.assertEqual((item.get("explanation") or {}).get("kind"), "watched_bridge")

    def test_runtime_max_filters_and_does_not_invent(self) -> None:
        _seed_house_contagion(self.db)
        empty = build_tonight_watch(self.db, runtime_max=90)
        self.assertTrue(empty["empty"])
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["note"], TONIGHT_EMPTY_NOTE)
        kept = build_tonight_watch(self.db, runtime_max=120)
        self.assertEqual(kept["items"][0]["title"], "Contagion")

    def test_cap_is_at_most_eight(self) -> None:
        seed = _title(self.db, rating_key="rk-seed", title="Seed Film", year=2010, summary=BAKE_PLOT, view_count=1)
        _insert_completion(self.db, user_id="will", rating_key="rk-seed", completed_at_ms=1_700_000_000_000)
        for i in range(12):
            peer = _title(
                self.db,
                rating_key=f"rk-peer-{i}",
                tmdb_id=3000 + i,
                title=f"Peer {i}",
                year=2011 + i,
                summary=SPY_PLOT,
            )
            _explainable_neighbor(self.db, seed, peer, seed_text=BAKE_PLOT, peer_text=SPY_PLOT)
        payload = build_tonight_watch(self.db, limit=50)
        self.assertLessEqual(len(payload["items"]), 8)


class TonightAgentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_in_app_tool_uses_same_builder(self) -> None:
        from projectionist.agent.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            _seed_house_contagion(db)
            registry = ToolRegistry(db, Settings(), "default")
            raw = await registry.execute("what_to_watch_tonight", {"limit": 8})
            payload = json.loads(raw)
            self.assertEqual(payload["mode"], "watched_bridge")
            self.assertEqual(payload["items"][0]["title"], "Contagion")
            self.assertEqual(
                (payload["items"][0].get("explanation") or {}).get("kind"),
                "watched_bridge",
            )
            self.assertNotIn("Good pick for tonight", raw)
            self.assertTrue(any(card.title == "Contagion" for card in registry.cards))

    @patch("projectionist.agent.tools.search_library")
    async def test_mood_does_not_invent_search_substitutes(self, mock_search) -> None:
        from projectionist.agent.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(db, Settings(), "default")
            payload = json.loads(
                await registry.execute("what_to_watch_tonight", {"mood": "dark thriller", "limit": 5})
            )
            mock_search.assert_not_called()
            self.assertTrue(payload["empty"])
            self.assertEqual(payload["note"], TONIGHT_EMPTY_NOTE)


@skipUnless(HAS_MCP, "mcp package not installed")
class TonightMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        set_mcp_mode("full")
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        self._tmpdir.cleanup()
        set_mcp_mode("privacy")

    def test_mcp_tonight_is_for_you_not_fts(self) -> None:
        _seed_house_contagion(self.db)
        with patch.object(mcp_server, "_database", return_value=self.db), patch(
            "projectionist.library.query.query_library"
        ) as mocked_query:
            payload = json.loads(mcp_server.what_to_watch_tonight(limit=8))
        mocked_query.assert_not_called()
        self.assertEqual(payload["mode"], "watched_bridge")
        self.assertEqual(payload["items"][0]["explanation"]["kind"], "watched_bridge")
        self.assertTrue(payload["items"][0]["in_library"])
        self.assertIn("continue", payload)

    def test_mcp_tonight_ignores_watch_tonight_fts(self) -> None:
        """query='watch tonight' is not a tool argument and never hits FTS."""
        self.assertNotIn("query", mcp_server.what_to_watch_tonight.__code__.co_varnames)

    def test_privacy_mode_still_errors(self) -> None:
        set_mcp_mode("privacy")
        with patch.object(mcp_server, "_database", side_effect=AssertionError("should not hit db")):
            payload = json.loads(mcp_server.what_to_watch_tonight())
        self.assertIn("error", payload)
        self.assertIn("full MCP", payload["error"])

    def test_upcoming_premieres_copy_is_recently_added(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-new",
                "media_type": "movie",
                "title": "Fresh Arrival",
                "year": 2026,
                "added_at": int(time.time()),
            }
        )
        with patch.object(mcp_server, "_database", return_value=self.db):
            payload = json.loads(mcp_server.upcoming_premieres(limit=5))
        note = str(payload.get("note") or "").lower()
        self.assertIn("recently added", note)
        dumped = json.dumps(payload).lower()
        self.assertNotIn("premiered", dumped)
        if payload.get("items"):
            self.assertTrue(payload["items"][0].get("in_library"))


class TonightYouthAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_youth_tonight_never_names_over_ceiling(self) -> None:
        from projectionist.agent.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings(youth=YouthSettings(max_content_rating="PG-13"))
            for key, title, rating in (
                ("rk-pg", "Robot Friends", "PG"),
                ("rk-r", "Grim Harvest", "R"),
                ("rk-none", "Unlabeled Reel", ""),
            ):
                db.upsert_library_item(
                    {
                        "rating_key": key,
                        "media_type": "movie",
                        "title": title,
                        "year": 2001,
                        "content_rating": rating,
                        "summary": "A film about robots and friendship.",
                        "genres": ["Adventure"],
                        "view_count": 0,
                    }
                )
            registry = ToolRegistry(db, settings, "default", is_youth=True)
            payload = json.loads(await registry.execute("what_to_watch_tonight", {}))
            titles = {item["title"] for item in payload.get("items") or []}
            self.assertNotIn("Grim Harvest", titles)
            self.assertNotIn("Unlabeled Reel", titles)
            self.assertNotIn("Grim Harvest", {card.title for card in registry.cards})
            self.assertTrue(payload.get("empty"))


if __name__ == "__main__":
    unittest.main()
