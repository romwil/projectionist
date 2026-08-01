"""Phase C — Curator village consult_persona tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from projectionist.agent.curator import _append_persona_consult_blocks, household_tool_summary
from projectionist.agent.tools import TOOL_DEFINITIONS, ToolRegistry, build_system_prompt
from projectionist.agent.village import (
    build_shared_consult_context,
    quote_block_from_consult,
    resolve_village_sibling,
)
from projectionist.config_store import Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.telemetry.llm_usage import PURPOSE_PERSONA_CONSULT, VALID_PURPOSES


class TestVillageResolve(unittest.TestCase):
    def test_resolves_archetype_aliases(self) -> None:
        for raw, expected_id, expected_name in (
            ("Scholar", "academic-critic", "Scholar"),
            ("enthusiast", "enthusiastic-scout", "Enthusiast"),
            ("Concierge", "classic-curator", "Concierge"),
            ("Companion", "night-owl-host", "Companion"),
            ("academic-critic", "academic-critic", "Scholar"),
        ):
            sibling = resolve_village_sibling(raw)
            self.assertIsNotNone(sibling)
            assert sibling is not None
            self.assertEqual(sibling.template_id, expected_id)
            self.assertEqual(sibling.display_name, expected_name)

    def test_unknown_persona(self) -> None:
        self.assertIsNone(resolve_village_sibling("mystery-bot"))


class TestConsultPersonaTool(unittest.IsolatedAsyncioTestCase):
    async def test_tool_definition_present(self) -> None:
        names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
        self.assertIn("consult_persona", names)
        self.assertIn(PURPOSE_PERSONA_CONSULT, VALID_PURPOSES)

    async def test_youth_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db, Settings(), DEFAULT_LENS_ID, user_id="u1", user_role="member", is_youth=True
            )
            result = json.loads(
                await registry.execute(
                    "consult_persona",
                    {"persona": "Scholar", "question": "Compare these two directors"},
                )
            )
            self.assertFalse(result.get("quote_ok"))
            self.assertEqual(result.get("code"), "consult_privacy")
            self.assertEqual(registry.persona_consults, [])

    async def test_guest_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db, Settings(), DEFAULT_LENS_ID, user_id="guest-1", user_role="guest"
            )
            result = json.loads(
                await registry.execute(
                    "consult_persona",
                    {"persona": "Companion", "question": "What mood fits tonight?"},
                )
            )
            self.assertEqual(result.get("code"), "consult_privacy")

    async def test_max_one_consult_per_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db, Settings(), DEFAULT_LENS_ID, user_id="u1", user_role="member"
            )
            with patch(
                "projectionist.agent.village.run_persona_consult",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = {
                    "ok": True,
                    "persona": "Scholar",
                    "persona_id": "academic-critic",
                    "specialty": "citations",
                    "answer": "Two cited neighbors from your memory.",
                    "quote_lead": "I asked Scholar and they said",
                    "quote_ok": True,
                    "source": "llm",
                }
                first = json.loads(
                    await registry.execute(
                        "consult_persona",
                        {"persona": "Scholar", "question": "Deep filmography digression"},
                    )
                )
                second = json.loads(
                    await registry.execute(
                        "consult_persona",
                        {"persona": "Enthusiast", "question": "What's hot tonight?"},
                    )
                )
            self.assertTrue(first.get("quote_ok"))
            self.assertEqual(second.get("code"), "consult_limit")
            self.assertEqual(len(registry.persona_consults), 1)

    async def test_specialty_only_without_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db, Settings(), DEFAULT_LENS_ID, user_id="u1", user_role="member"
            )
            result = json.loads(
                await registry.execute(
                    "consult_persona",
                    {"persona": "Enthusiast", "question": "What's the heat for tonight?"},
                )
            )
            self.assertTrue(result.get("quote_ok"))
            self.assertEqual(result.get("persona"), "Enthusiast")
            self.assertEqual(result.get("source"), "specialty_only")
            self.assertTrue(result.get("answer"))

    async def test_concierge_acquire_registers_pending_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings()
            # Enable Seerr so acquire path can mint a confirmation token.
            settings.features.seerr_enabled = True
            settings.seerr.enabled = True
            settings.seerr.url = "http://seerr.test"
            settings.seerr.api_key = "test-key"
            registry = ToolRegistry(
                db, settings, DEFAULT_LENS_ID, user_id="u1", user_role="member"
            )
            with patch(
                "projectionist.acquire.build_acquire_path",
                return_value={
                    "title": "Heat",
                    "confirmation_token": "tok-abc",
                    "steps": [{"step": 1, "action": "find", "status": "done"}],
                },
            ):
                result = json.loads(
                    await registry.execute(
                        "consult_persona",
                        {
                            "persona": "Concierge",
                            "question": "How do we get Heat?",
                            "title": "Heat",
                            "media_type": "movie",
                            "tmdb_id": 949,
                        },
                    )
                )
            self.assertTrue(result.get("quote_ok"))
            tokens = registry.pending_tokens
            self.assertTrue(any(t.get("token") == "tok-abc" for t in tokens))

    async def test_shared_context_includes_memory_and_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_local_user(
                user_id="u1", display_name="Adult", password_hash="x", role="member"
            )
            db.ensure_chat_session("s1", DEFAULT_LENS_ID, user_id="u1")
            db.update_thread_title("s1", "Nolan deep dive")
            from projectionist.memory import UserMemoryService

            UserMemoryService(db).remember(
                caller_id="u1", kind="callback", text="Loved bleak UK comedy last month"
            )
            shared = build_shared_consult_context(
                db,
                user_id="u1",
                user_role="member",
                question="Who else fits that mood?",
            )
            self.assertEqual(shared["user_id"], "u1")
            self.assertTrue(any("bleak UK comedy" in m for m in shared["memory_excerpts"]))
            self.assertIn("Nolan deep dive", shared["recent_thread_titles"])

    async def test_system_prompt_mentions_village(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            prompt = build_system_prompt(db, DEFAULT_LENS_ID, user_id="u1", user_role="member")
            self.assertIn("consult_persona", prompt)
            self.assertIn("I asked", prompt)


class TestConsultQuoteBlocks(unittest.TestCase):
    def test_quote_block_and_append(self) -> None:
        payload = {
            "quote_ok": True,
            "persona": "Scholar",
            "persona_id": "academic-critic",
            "specialty": "citations",
            "answer": "Two cited neighbors.",
            "quote_lead": "I asked Scholar and they said",
        }
        block = quote_block_from_consult(payload)
        self.assertIsNotNone(block)
        assert block is not None
        self.assertEqual(block["type"], "persona_consult")
        self.assertIn("I asked Scholar", block["payload"]["lead"])

        class _Reg:
            persona_consults = [payload]
            is_youth = False
            settings = Settings()

        blocks: list = [{"type": "text", "content": "Here is my take."}]
        _append_persona_consult_blocks(blocks, _Reg())  # type: ignore[arg-type]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1]["type"], "persona_consult")

    def test_household_summary_for_consult(self) -> None:
        self.assertEqual(
            household_tool_summary(
                json.dumps({"quote_ok": True, "persona": "Companion", "answer": "x"})
            ),
            "Asked Companion",
        )
        self.assertEqual(
            household_tool_summary(json.dumps({"code": "consult_timeout", "busy": True})),
            "Sibling busy",
        )


if __name__ == "__main__":
    unittest.main()
