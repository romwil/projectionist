"""Phase 1 tests: repository-memory read path, insight persistence, activity, and per-turn injection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from curatorx.agent.tools import ToolRegistry, build_system_prompt
from curatorx.config_store import Settings
from curatorx.library.db import DEFAULT_LENS_ID, Database


def _seed_entity(db: Database, *, entity_type: str = "person", name: str = "Akira Kurosawa") -> str:
    saved = db.save_repository_research(
        entity_type=entity_type,
        name=name,
        payload={
            "identity": {"name": name},
            "sources_checked": {"tmdb": {"status": "ok"}},
            "profile": {"biography": "Public biography text."},
            "warnings": [],
        },
        external_ids={"tmdb_id": 5026},
    )
    return saved["entity_id"]


class RepositoryMemoryDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "curatorx.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_get_repository_entity_returns_snapshot_and_freshness(self) -> None:
        _seed_entity(self.db)
        record = self.db.get_repository_entity("Akira Kurosawa")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["entity_type"], "person")
        self.assertEqual(record["snapshot"]["profile"]["biography"], "Public biography text.")
        self.assertIsNotNone(record["fetched_at"])
        self.assertEqual(record["external_ids"], {"tmdb_id": 5026})

    def test_get_repository_entity_is_case_insensitive_and_none_when_unknown(self) -> None:
        _seed_entity(self.db)
        self.assertIsNotNone(self.db.get_repository_entity("akira kurosawa"))
        self.assertIsNone(self.db.get_repository_entity("Nobody Here"))

    def test_search_repository_memory_matches_name_fuzzily(self) -> None:
        _seed_entity(self.db, name="Akira Kurosawa")
        _seed_entity(self.db, entity_type="title", name="Seven Samurai")
        matches = self.db.search_repository_memory("kurosawa")
        self.assertEqual([m["name"] for m in matches], ["Akira Kurosawa"])
        self.assertEqual(matches[0]["entity_type"], "person")

    def test_save_and_list_repository_insight_with_citations(self) -> None:
        entity_id = _seed_entity(self.db)
        saved = self.db.save_repository_insight(
            entity_id,
            "Defined the modern action-ensemble structure.",
            [{"source": "Wikipedia", "url": "https://example.org", "note": "overview"}],
        )
        insights = self.db.list_repository_insights(entity_id)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["id"], saved["id"])
        self.assertEqual(insights[0]["citations"][0]["source"], "Wikipedia")
        self.assertEqual(insights[0]["citations"][0]["ref"], "https://example.org")

    def test_save_repository_insight_rejects_unknown_entity(self) -> None:
        with self.assertRaises(ValueError):
            self.db.save_repository_insight("does-not-exist", "orphan insight")

    def test_record_entity_discussion_increments(self) -> None:
        entity_id = _seed_entity(self.db)
        self.db.record_entity_discussion(entity_id)
        self.db.record_entity_discussion(entity_id)
        record = self.db.get_repository_entity("Akira Kurosawa")
        assert record is not None
        self.assertEqual(record["discussion_count"], 2)
        self.assertIsNotNone(record["last_discussed_at"])

    def test_record_entity_discussion_never_raises_on_bad_id(self) -> None:
        # Best-effort: an unknown id is silently ignored, never crashing a turn.
        self.db.record_entity_discussion("")
        self.db.record_entity_discussion("unknown")


class RepositoryMemoryToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "curatorx.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_recall_repo_memory_unknown_entity(self) -> None:
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        payload = json.loads(await registry.execute("recall_repo_memory", {"name": "Nobody"}))
        self.assertFalse(payload["known"])

    async def test_recall_repo_memory_returns_snapshot_and_records_activity(self) -> None:
        _seed_entity(self.db)
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        payload = json.loads(await registry.execute("recall_repo_memory", {"name": "Akira Kurosawa"}))
        self.assertTrue(payload["known"])
        self.assertEqual(payload["snapshot"]["profile"]["biography"], "Public biography text.")
        self.assertIn("known_since", payload["freshness"])
        self.assertEqual(payload["discussion_count"], 1)
        self.assertFalse(payload["frequently_discussed"])

    async def test_recall_repo_memory_marks_frequently_discussed(self) -> None:
        _seed_entity(self.db)
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        for _ in range(3):
            payload = json.loads(await registry.execute("recall_repo_memory", {"name": "Akira Kurosawa"}))
        self.assertTrue(payload["frequently_discussed"])

    async def test_search_memory_tool(self) -> None:
        _seed_entity(self.db, entity_type="title", name="Ran")
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        payload = json.loads(await registry.execute("search_memory", {"query": "Ran"}))
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["matches"][0]["name"], "Ran")

    async def test_save_repo_insight_by_name(self) -> None:
        _seed_entity(self.db)
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        payload = json.loads(
            await registry.execute(
                "save_repo_insight",
                {
                    "name": "Akira Kurosawa",
                    "insight": "Frequent collaborator with Toshiro Mifune.",
                    "citations": [{"source": "TMDB"}],
                },
            )
        )
        self.assertTrue(payload["saved"])
        recall = json.loads(await registry.execute("recall_repo_memory", {"name": "Akira Kurosawa"}))
        self.assertEqual(recall["insights"][0]["insight"], "Frequent collaborator with Toshiro Mifune.")

    async def test_save_repo_insight_unknown_entity_errors(self) -> None:
        registry = ToolRegistry(self.db, Settings(), DEFAULT_LENS_ID)
        payload = json.loads(
            await registry.execute("save_repo_insight", {"name": "Ghost", "insight": "x"})
        )
        self.assertFalse(payload["saved"])
        self.assertIn("error", payload)


class MemoryInjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "curatorx.db")
        for user_id, name in (("adult-a", "A"), ("adult-b", "B")):
            self.db.create_local_user(user_id=user_id, display_name=name, password_hash="x", role="member")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_prompt_injects_signed_in_user_notes_and_resume_line(self) -> None:
        self.db.add_user_memory_note("adult-a", kind="self_disclosure", text="Studying Italian neorealism")
        self.db.add_user_memory_note("adult-a", kind="follow_up", text="finish the De Sica marathon")
        prompt = build_system_prompt(self.db, DEFAULT_LENS_ID, user_id="adult-a", user_role="member")
        self.assertIn("Studying Italian neorealism", prompt)
        self.assertIn("Resume where you left off", prompt)
        self.assertIn("finish the De Sica marathon", prompt)

    def test_prompt_never_leaks_another_users_notes(self) -> None:
        self.db.add_user_memory_note("adult-b", kind="self_disclosure", text="secret about B")
        prompt = build_system_prompt(self.db, DEFAULT_LENS_ID, user_id="adult-a", user_role="member")
        self.assertNotIn("secret about B", prompt)

    def test_prompt_injects_nothing_without_signed_in_user(self) -> None:
        self.db.add_user_memory_note("adult-a", kind="self_disclosure", text="private note")
        prompt = build_system_prompt(self.db, DEFAULT_LENS_ID)
        self.assertNotIn("private note", prompt)
        self.assertNotIn("What you already know about this signed-in user", prompt)

    def test_prompt_advertises_persistent_memory(self) -> None:
        prompt = build_system_prompt(self.db, DEFAULT_LENS_ID)
        self.assertIn("PERSISTENT", prompt)
        self.assertIn("recall_repo_memory", prompt)
        # The no-web-browsing guardrail must remain intact.
        self.assertIn("cannot arbitrarily browse or scrape", prompt)


if __name__ == "__main__":
    unittest.main()
