"""PRD-004: a one-pick answer shows that title as the first and only primary card."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from projectionist.agent.curator import (
    CuratorAgent,
    bind_cards_to_answer,
    is_single_pick_request,
)
from projectionist.agent.providers import _normalize_anthropic_response
from projectionist.agent.tools import ToolRegistry
from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.models.schemas import TitleCard

# The 2026-11-02 evidence: rejected film first, ruled-out series next, the pick ninth.
TRACE = [
    ("All Monsters Attack", "movie", "11"),
    ("Bluey", "show", "12"),
    ("Gravity Falls", "show", "13"),
    ("Avatar: The Last Airbender", "show", "14"),
    ("Hilda", "show", "15"),
    ("Steven Universe", "show", "16"),
    ("The Iron Giant", "movie", "17"),
    ("Coco", "movie", "18"),
    ("Paddington 2", "movie", "19"),
]

FINAL_TEXT = (
    "I first looked at All Monsters Attack, but it is too scary for little ones, and the "
    "series (Bluey, Gravity Falls) are not a single sitting. My pick for tonight: "
    "**Paddington 2** (2017). Warm, funny, and short enough for a school night."
)


def _block(items):
    return [{"type": "title_cards", "items": [{"title": t, "media_type": m, "rating_key": k} for t, m, k in items]}]


class SinglePickIntentTests(unittest.TestCase):
    def test_single_pick_phrasings(self) -> None:
        for ask in (
            "Pick one family movie for tonight",
            "recommend a movie for the kids",
            "What should we watch tonight?",
            "Just one, please",
            "give me a single film",
            "suggest me a scary show",
        ):
            with self.subTest(ask=ask):
                self.assertTrue(is_single_pick_request(ask))

    def test_list_and_lookup_asks_are_not_single_pick(self) -> None:
        for ask in (
            "Give me some heist movies",
            "Show me a few comedies",
            "find 5 westerns",
            "Do I have a movie with Tom Hanks?",
            "list documentaries about space",
        ):
            with self.subTest(ask=ask):
                self.assertFalse(is_single_pick_request(ask))


class BindCardsTests(unittest.TestCase):
    def test_one_pick_emits_only_the_named_pick(self) -> None:
        blocks = bind_cards_to_answer(
            _block(TRACE), final_text=FINAL_TEXT, user_message="Pick one family movie for tonight"
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual([item["rating_key"] for item in blocks[0]["items"]], ["19"])
        self.assertEqual(blocks[0]["primary_count"], 1)

    def test_bold_pick_beats_an_earlier_plain_mention(self) -> None:
        blocks = bind_cards_to_answer(_block(TRACE), final_text=FINAL_TEXT, user_message="any ideas?")
        items = blocks[0]["items"]
        self.assertEqual(items[0]["title"], "Paddington 2")
        self.assertEqual(len(items), len(TRACE))

    def test_multi_pick_leads_with_named_titles_in_mention_order(self) -> None:
        trace = [("Ronin", "movie", "1"), ("Heat", "movie", "2"), ("Thief", "movie", "3"), ("Heat 2", "movie", "4")]
        text = "Two to start: **Thief** (1981), then **Heat** (1995)."
        blocks = bind_cards_to_answer(_block(trace), final_text=text, user_message="some heist movies")
        self.assertEqual([i["title"] for i in blocks[0]["items"]], ["Thief", "Heat", "Ronin", "Heat 2"])

    def test_title_link_counts_as_a_name(self) -> None:
        trace = [("Ronin", "movie", "1"), ("Heat", "movie", "2")]
        text = "Try [this one](/title/2) tonight."
        blocks = bind_cards_to_answer(_block(trace), final_text=text, user_message="pick a movie")
        self.assertEqual([i["rating_key"] for i in blocks[0]["items"]], ["2"])

    def test_pick_in_the_owned_block_still_leads(self) -> None:
        blocks = [
            {"type": "title_cards", "heading": "Notable gaps", "items": [{"title": "Ronin", "rating_key": ""}]},
            {"type": "title_cards", "heading": "Already in library", "items": [{"title": "Heat", "rating_key": "2"}]},
        ]
        out = bind_cards_to_answer(blocks, final_text="Watch **Heat**.", user_message="what can I watch")
        self.assertEqual(out[0]["heading"], "Already in library")
        self.assertEqual(out[0]["items"][0]["title"], "Heat")

    def test_unnamed_answer_leaves_the_strip_alone(self) -> None:
        original = _block(TRACE)
        self.assertEqual(
            bind_cards_to_answer(original, final_text="Here you go.", user_message="pick one movie"),
            original,
        )


class OnePickTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_turn_first_card_is_the_pick_and_only_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            agent = CuratorAgent(
                db,
                Settings(llm_provider="anthropic", llm_api_key="k", llm_model="claude-sonnet-4-6"),
            )
            tool_round = _normalize_anthropic_response(
                {
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "search_library", "input": {"query": "family"}}
                    ],
                    "stop_reason": "tool_use",
                }
            )
            text_round = _normalize_anthropic_response(
                {"content": [{"type": "text", "text": FINAL_TEXT}], "stop_reason": "end_turn"}
            )
            calls = {"n": 0}

            async def mock_chat(messages, tools=None):
                calls["n"] += 1
                return tool_round if calls["n"] == 1 else text_round

            async def fake_execute(self, name, arguments):
                for title, media_type, key in TRACE:
                    self._cards.append(
                        TitleCard(title=title, media_type=media_type, rating_key=key, in_library=True)
                    )
                return json.dumps({"returned": len(TRACE)})

            agent.provider = MagicMock()
            agent.provider.chat = AsyncMock(side_effect=mock_chat)
            with patch.object(ToolRegistry, "execute", fake_execute):
                result = await agent.run("s1", "Pick one family movie for tonight")

            card_blocks = [b for b in result["message"]["blocks"] if b.get("type") == "title_cards"]
            self.assertEqual(len(card_blocks), 1)
            self.assertEqual([i["title"] for i in card_blocks[0]["items"]], ["Paddington 2"])
            viewport = [b for b in result["message"]["blocks"] if b.get("action") == "open_viewport"]
            self.assertEqual([i["title"] for i in viewport[0]["payload"]["items"]], ["Paddington 2"])


if __name__ == "__main__":
    unittest.main()
