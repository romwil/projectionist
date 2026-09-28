"""Phase C — Curator village consult_persona tests."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from projectionist.agent.curator import _append_persona_consult_blocks, household_tool_summary
from projectionist.agent.tools import TOOL_DEFINITIONS, ToolRegistry, build_system_prompt
from projectionist.agent.village import (
    CONSULT_MAX_ANSWER_CHARS,
    _deterministic_specialty_answer,
    build_shared_consult_context,
    cancel_unpromised_persona_consults,
    clip_consult_answer,
    consult_quote_lead,
    gather_specialty_context,
    pending_consult_human_copy,
    quote_block_from_consult,
    resolve_village_sibling,
    run_persona_consult,
)
from projectionist.config_store import Settings
from projectionist.library.db import BOOTSTRAP_OWNER_ID, DEFAULT_LENS_ID, Database
from projectionist.telemetry.llm_usage import PURPOSE_PERSONA_CONSULT, VALID_PURPOSES


class TestVillageResolve(unittest.TestCase):
    def test_resolves_archetype_aliases(self) -> None:
        for raw, expected_id, expected_name in (
            ("Scholar", "academic-critic", "The Professor"),
            ("enthusiast", "enthusiastic-scout", "Spark"),
            ("Concierge", "classic-curator", "The Steward"),
            ("Companion", "night-owl-host", "The Host"),
            ("academic-critic", "academic-critic", "The Professor"),
            ("The Professor", "academic-critic", "The Professor"),
            ("Spark", "enthusiastic-scout", "Spark"),
        ):
            sibling = resolve_village_sibling(raw)
            self.assertIsNotNone(sibling)
            assert sibling is not None
            self.assertEqual(sibling.template_id, expected_id)
            self.assertEqual(sibling.display_name, expected_name)

    def test_unknown_persona(self) -> None:
        self.assertIsNone(resolve_village_sibling("mystery-bot"))


class TestConsultPersonaTool(unittest.IsolatedAsyncioTestCase):
    async def test_unpromised_callback_is_cancelled_on_disconnect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.ensure_chat_session("thread-disconnected", DEFAULT_LENS_ID)
            settings = Settings()
            settings.llm_api_key = "test-key"
            registry = ToolRegistry(
                db,
                settings,
                DEFAULT_LENS_ID,
                session_id="thread-disconnected",
            )
            sibling = resolve_village_sibling("Scholar")
            assert sibling is not None
            cancelled = asyncio.Event()

            async def hanging_chat(*args, **kwargs):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            with (
                patch("projectionist.agent.providers.get_chat_provider", return_value=object()),
                patch("projectionist.telemetry.llm_track.tracked_chat", side_effect=hanging_chat),
                patch("projectionist.agent.village.CONSULT_TIMEOUT_S", 0.01),
                patch("projectionist.agent.village.CONSULT_HARD_TIMEOUT_S", 1.0),
            ):
                result = await run_persona_consult(
                    registry,
                    sibling,
                    question="Will this be cancelled?",
                    shared={"question": "Will this be cancelled?"},
                    specialty={"specialty": "citations"},
                    session_id="thread-disconnected",
                )
                self.assertTrue(result.get("pending"))

                cancel_unpromised_persona_consults("thread-disconnected")
                await asyncio.wait_for(cancelled.wait(), timeout=0.2)

    async def test_soft_timeout_keeps_consult_running_and_persists_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_local_user(
                user_id="u1",
                display_name="Adult",
                password_hash="x",
                role="member",
            )
            db.ensure_chat_session("thread-1", DEFAULT_LENS_ID, user_id="u1")
            settings = Settings()
            settings.llm_api_key = "test-key"
            registry = ToolRegistry(
                db,
                settings,
                DEFAULT_LENS_ID,
                user_id="u1",
                user_role="member",
                session_id="thread-1",
            )
            sibling = resolve_village_sibling("Scholar")
            assert sibling is not None
            release = asyncio.Event()

            async def delayed_chat(*args, **kwargs):
                await release.wait()
                return {
                    "choices": [{
                        "message": {
                            "content": "The archive points to two precise neighbors.",
                        },
                    }],
                }

            with (
                patch("projectionist.agent.providers.get_chat_provider", return_value=object()),
                patch("projectionist.telemetry.llm_track.tracked_chat", side_effect=delayed_chat),
                patch("projectionist.agent.village.CONSULT_TIMEOUT_S", 0.01),
                patch("projectionist.agent.village.CONSULT_HARD_TIMEOUT_S", 1.0),
            ):
                result = await run_persona_consult(
                    registry,
                    sibling,
                    question="What does the archive suggest?",
                    shared={"question": "What does the archive suggest?"},
                    specialty={"specialty": "citations"},
                    session_id="thread-1",
                )

                self.assertTrue(result.get("pending"))
                self.assertEqual(result.get("code"), "consult_pending")
                self.assertFalse(result.get("quote_ok"))

                pending_block = quote_block_from_consult(result)
                assert pending_block is not None
                db.save_chat_message(
                    "thread-1",
                    "jefferson-reply",
                    "assistant",
                    [{"type": "text", "content": "I left Scholar a note."}, pending_block],
                )
                release.set()

                for _ in range(50):
                    history = db.chat_history("thread-1")
                    if len(history) == 2:
                        break
                    await asyncio.sleep(0.01)

            self.assertEqual(len(history), 2)
            callback = history[-1]
            self.assertNotEqual(callback["id"], "jefferson-reply")
            self.assertIn("called back", callback["blocks"][0]["content"])
            self.assertEqual(callback["blocks"][1]["type"], "persona_consult")
            self.assertEqual(
                callback["blocks"][1]["payload"]["consult_id"],
                result["consult_id"],
            )

    async def test_long_professor_answer_is_not_clipped_at_900(self) -> None:
        lore = (
            "The pylon/crystal mythology in Land of the Lost (1974-1977) is a "
            "genuinely fascinating case of serialized world-building that deepened "
            "considerably across its run. Season 1 established the core mechanics. "
            "Season 2 is where the lore sharpens, owing substantially to David Gerrold. "
        ) * 6
        self.assertGreater(len(lore.strip()), 900)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            settings = Settings()
            settings.llm_api_key = "test-key"
            registry = ToolRegistry(db, settings, DEFAULT_LENS_ID, session_id="thread-lore")
            sibling = resolve_village_sibling("The Professor")
            assert sibling is not None

            async def long_chat(*args, **kwargs):
                return {"choices": [{"message": {"content": lore}}]}

            with (
                patch("projectionist.agent.providers.get_chat_provider", return_value=object()),
                patch("projectionist.telemetry.llm_track.tracked_chat", side_effect=long_chat),
            ):
                result = await run_persona_consult(
                    registry,
                    sibling,
                    question="How did the pylon mythology evolve?",
                    shared={"question": "How did the pylon mythology evolve?"},
                    specialty={"specialty": "citations"},
                    session_id="thread-lore",
                )

            self.assertTrue(result.get("quote_ok"))
            answer = result.get("answer") or ""
            self.assertGreater(len(answer), 900)
            self.assertFalse(str(answer).endswith("…"))
            self.assertIn("David Gerrold", answer)

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

    async def test_legacy_guest_role_is_not_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            registry = ToolRegistry(
                db, Settings(), DEFAULT_LENS_ID, user_id="guest-1", user_role="guest"
            )
            with patch(
                "projectionist.agent.village.run_persona_consult",
                new_callable=AsyncMock,
            ) as mock_run:
                mock_run.return_value = {
                    "ok": True,
                    "persona": "Companion",
                    "persona_id": "night-owl-host",
                    "specialty": "mood",
                    "answer": "Something cozy.",
                    "quote_lead": "I asked Companion and they said",
                    "quote_ok": True,
                    "source": "llm",
                }
                result = json.loads(
                    await registry.execute(
                        "consult_persona",
                        {"persona": "Companion", "question": "What mood fits tonight?"},
                    )
                )
            self.assertNotEqual(result.get("code"), "consult_privacy")
            mock_run.assert_called_once()

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
            self.assertEqual(result.get("persona"), "Spark")
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


class TestConsultAnswerClip(unittest.TestCase):
    def test_floor_is_above_the_old_900_char_mid_sentence_cut(self) -> None:
        self.assertGreaterEqual(CONSULT_MAX_ANSWER_CHARS, 4000)

    def test_professor_lore_paragraph_is_not_ellipsis_clipped(self) -> None:
        # Repro: Land of the Lost village quote ended mid-sentence with "…" at 900.
        body = (
            "The pylon/crystal mythology in Land of the Lost (1974-1977) is a "
            "serialized world-building case that deepened across its run. "
        )
        lore = (body * 12).strip()
        self.assertGreater(len(lore), 900)
        self.assertLess(len(lore), CONSULT_MAX_ANSWER_CHARS)
        kept = clip_consult_answer(lore)
        self.assertEqual(kept, lore)
        self.assertFalse(kept.endswith("…"))

    def test_runaway_reply_clips_at_sentence_not_mid_word(self) -> None:
        sentences = [
            f"Sentence {i} finishes cleanly with a cited neighbor from the archive."
            for i in range(140)
        ]
        runaway = " ".join(sentences)
        self.assertGreater(len(runaway), CONSULT_MAX_ANSWER_CHARS)
        clipped = clip_consult_answer(runaway)
        self.assertLessEqual(len(clipped), CONSULT_MAX_ANSWER_CHARS)
        self.assertTrue(clipped.endswith("."))
        self.assertFalse(clipped.endswith("…"))
        self.assertNotIn("neighb…", clipped)


class TestConsultQuoteBlocks(unittest.TestCase):
    def test_callback_save_does_not_recreate_deleted_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.ensure_chat_session("deleted-thread", DEFAULT_LENS_ID)
            self.assertTrue(db.delete_chat_thread("deleted-thread"))

            saved = db.save_chat_message_if_thread_exists(
                "deleted-thread",
                "late-callback",
                "assistant",
                [{"type": "text", "content": "Too late"}],
            )

            self.assertFalse(saved)
            with db.connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE id = ?",
                    ("late-callback",),
                ).fetchone()[0]
            self.assertEqual(count, 0)

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

    def test_pending_consult_uses_human_copy_not_json(self) -> None:
        sibling = resolve_village_sibling("The Professor")
        assert sibling is not None
        copy = pending_consult_human_copy(sibling.display_name)
        self.assertEqual(copy, "The Professor has not called back")
        self.assertNotIn("{", copy)
        self.assertNotIn("pending", copy.casefold())

        payload = {
            "ok": True,
            "pending": True,
            "code": "consult_pending",
            "consult_id": "abc123",
            "persona": sibling.display_name,
            "persona_id": sibling.template_id,
            "specialty": sibling.specialty,
            "question": "Compare the two cuts",
            "message": copy,
        }
        block = quote_block_from_consult(payload)
        self.assertIsNotNone(block)
        assert block is not None
        lead = str(block["payload"].get("lead") or "")
        message = str(block["payload"].get("message") or "")
        self.assertIn("not called back", lead)
        self.assertIn("not called back", message)
        self.assertNotIn("{", lead)
        self.assertNotIn("consult_pending", lead)

    def test_household_summary_for_consult(self) -> None:
        self.assertEqual(
            household_tool_summary(
                json.dumps({"quote_ok": True, "persona": "Companion", "answer": "x"})
            ),
            "Asked Companion",
        )
        self.assertEqual(
            household_tool_summary(
                json.dumps({"pending": True, "persona": "Scholar"})
            ),
            "Left Scholar a message",
        )
        self.assertEqual(
            household_tool_summary(json.dumps({"code": "consult_timeout", "busy": True})),
            "Sibling busy",
        )


class TestScholarWalkVillage(unittest.IsolatedAsyncioTestCase):
    async def test_professor_specialty_gathers_walk_and_seminar_lead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "walks.db")
            db.ensure_bootstrap_owner()
            list_id = uuid.uuid4().hex
            db.create_curated_list(
                list_id=list_id,
                user_id=None,
                name="Kurosawa Lab",
                description="Study the masters",
                list_kind="course",
            )
            db.add_curated_list_item(
                item_id=uuid.uuid4().hex,
                list_id=list_id,
                user_id=None,
                tmdb_id=1000,
                tvdb_id=None,
                media_type="movie",
                title="Rashomon",
            )
            db.set_curated_list_visibility(list_id, visibility="published")
            registry = ToolRegistry(
                db,
                Settings(),
                DEFAULT_LENS_ID,
                user_id=BOOTSTRAP_OWNER_ID,
                user_role="member",
            )
            sibling = resolve_village_sibling("The Professor")
            assert sibling is not None
            specialty = await gather_specialty_context(
                registry,
                sibling,
                {"question": "Open a silent seminar on Kurosawa", "title": "Kurosawa"},
            )
            walk = specialty.get("scholar_walk") or {}
            self.assertEqual(walk.get("kind"), "silent_seminar")
            self.assertFalse(walk.get("public"))
            self.assertIn("Rashomon", walk.get("stop_titles") or [])

            lead = consult_quote_lead(sibling, specialty)
            self.assertIn("silent seminar", lead.casefold())
            self.assertIn(sibling.display_name, lead)

            answer = _deterministic_specialty_answer(
                sibling, specialty, "Open a silent seminar on Kurosawa"
            )
            self.assertIn("seminar", answer.casefold())

            fallback = await run_persona_consult(
                registry,
                sibling,
                question="Open a silent seminar on Kurosawa",
                shared={"question": "Open a silent seminar on Kurosawa"},
                specialty=specialty,
            )
            self.assertTrue(fallback.get("quote_ok"))
            self.assertIn("silent seminar", str(fallback.get("quote_lead") or "").casefold())

    async def test_gap_walk_in_village_still_needs_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "gaps.db")
            db.ensure_bootstrap_owner()
            list_id = uuid.uuid4().hex
            db.create_curated_list(
                list_id=list_id,
                user_id=None,
                name="Kurosawa Lab",
                list_kind="course",
            )
            db.add_curated_list_item(
                item_id=uuid.uuid4().hex,
                list_id=list_id,
                user_id=None,
                tmdb_id=2001,
                tvdb_id=None,
                media_type="movie",
                title="Dersu Uzala",
            )
            db.set_curated_list_visibility(list_id, visibility="published")
            registry = ToolRegistry(
                db,
                Settings(),
                DEFAULT_LENS_ID,
                user_id=BOOTSTRAP_OWNER_ID,
                user_role="member",
            )
            sibling = resolve_village_sibling("Scholar")
            assert sibling is not None
            specialty = await gather_specialty_context(
                registry,
                sibling,
                {"question": "Draft a gap reading list for Kurosawa"},
            )
            walk = specialty.get("scholar_walk") or {}
            self.assertEqual(walk.get("kind"), "gap_reading_list")
            self.assertTrue(walk.get("needs_confirm"))
            answer = _deterministic_specialty_answer(
                sibling, specialty, "Draft a gap reading list for Kurosawa"
            )
            self.assertIn("confirm", answer.casefold())
            self.assertNotIn("Dersu Uzala", answer)


if __name__ == "__main__":
    unittest.main()
