"""Agent seasonal shelf curation + curator notes on Explore feeds."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.feeds import feed_seasonal_spotlight, preview_holiday_rail
from projectionist.library.seasonal_curation import (
    apply_seasonal_shelf_proposal,
    enrich_picks,
    normalize_proposal_picks,
)
from projectionist.web import holidays_routes


class SeasonalCurationTests(unittest.TestCase):
    def _seed_halloween_library(self, db: Database) -> dict[str, int]:
        known = db.upsert_library_item(
            {
                "rating_key": "hall1",
                "media_type": "movie",
                "title": "Classic Haunt",
                "year": 1978,
                "keywords": ["horror", "halloween"],
            }
        )
        gem = db.upsert_library_item(
            {
                "rating_key": "hall2",
                "media_type": "movie",
                "title": "Quiet Attic",
                "year": 2012,
                "keywords": ["horror", "haunted"],
            }
        )
        filler = db.upsert_library_item(
            {
                "rating_key": "hall3",
                "media_type": "movie",
                "title": "Zombie Dump",
                "year": 2024,
                "keywords": ["horror"],
            }
        )
        return {"known": known, "gem": gem, "filler": filler}

    def test_normalize_proposal_picks_filters_and_orders(self) -> None:
        picks = normalize_proposal_picks(
            [
                {"library_item_id": 2, "note": "  A gem.  "},
                {"id": 99, "note": "ignored"},
                {"library_item_id": 1, "curator_note": "Known doorway in."},
                {"library_item_id": 2, "note": "duplicate"},
            ],
            allowed_ids=[1, 2, 3],
            limit=10,
        )
        self.assertEqual(
            picks,
            [
                {"library_item_id": 2, "curator_note": "A gem."},
                {"library_item_id": 1, "curator_note": "Known doorway in."},
            ],
        )

    def test_apply_writes_notes_and_explore_feed_surfaces_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            result = apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "The doorway everyone expects — still the right opener.",
                    },
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "Quieter scare for the household that already knows the classics.",
                    },
                ],
            )
            self.assertEqual(result["applied"], 2)
            preview_ids = [int(item["id"]) for item in result["preview"]["items"]]
            self.assertEqual(preview_ids[:2], [ids["known"], ids["gem"]])
            self.assertEqual(
                result["preview"]["items"][0].get("curator_note"),
                "The doorway everyone expects — still the right opener.",
            )
            self.assertEqual(
                result["preview"]["items"][0].get("why"),
                "The doorway everyone expects — still the right opener.",
            )

            live = feed_seasonal_spotlight(
                db, today=date(2026, 10, 28), prefer_snapshot=False
            )
            self.assertEqual(live["scope_id"], "halloween")
            self.assertEqual(int(live["items"][0]["id"]), ids["known"])
            self.assertIn("doorway everyone expects", live["items"][0].get("why") or "")
            self.assertIn("Quieter scare", live["items"][1].get("curator_note") or "")

    def test_curated_pins_beat_uncurated_year_sort_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            # Without pins, newest matching title leads (year-sort dump).
            before = preview_holiday_rail(db, "halloween", limit=12)
            before_ids = [int(item["id"]) for item in before["items"]]
            self.assertEqual(before_ids[0], ids["filler"])

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {"library_item_id": ids["gem"], "curator_note": "Lead with the quiet one."},
                    {"library_item_id": ids["known"], "curator_note": "Then the classic."},
                ],
            )
            after = preview_holiday_rail(db, "halloween", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids[:2], [ids["gem"], ids["known"]])
            self.assertNotEqual(after_ids[0], ids["filler"])

    def _seed_muertos_library(self, db: Database) -> dict[str, int]:
        known = db.upsert_library_item(
            {
                "rating_key": "muertos1",
                "media_type": "movie",
                "title": "Familiar Altar",
                "year": 2017,
                "keywords": ["family", "mexico"],
            }
        )
        gem = db.upsert_library_item(
            {
                "rating_key": "muertos2",
                "media_type": "movie",
                "title": "Quiet Ofrenda",
                "year": 1999,
                "keywords": ["afterlife", "spirit"],
            }
        )
        dump = db.upsert_library_item(
            {
                "rating_key": "muertos3",
                "media_type": "movie",
                "title": "Family Reunion Dump",
                "year": 2024,
                "keywords": ["family"],
            }
        )
        return {"known": known, "gem": gem, "dump": dump}

    def test_apply_replaces_existing_pins_and_keyword_dump(self) -> None:
        """A confirmed curate replaces the shelf. Old pins and the year-sort tail must go."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            db.set_holiday_rail_title(
                "halloween",
                ids["filler"],
                curation="pin",
                pin_position=0,
                curator_note="Last year's leftover.",
            )
            # One veto must not be required for curate, and must not be the only change.
            db.set_holiday_rail_title("halloween", ids["known"], curation="exclude")

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "The quieter scare that belongs on the shelf this year.",
                    },
                ],
            )
            after = preview_holiday_rail(db, "halloween", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids, [ids["gem"]])
            self.assertNotIn(ids["filler"], after_ids)
            self.assertNotIn(ids["known"], after_ids)
            self.assertEqual(
                after["items"][0].get("curator_note"),
                "The quieter scare that belongs on the shelf this year.",
            )
            self.assertTrue(after.get("replaces_matches"))

    def test_apply_replaces_dia_de_los_muertos_the_same_way(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_muertos_library(db)
            before = preview_holiday_rail(db, "dia-de-los-muertos", limit=12)
            before_ids = [int(item["id"]) for item in before["items"]]
            self.assertEqual(before_ids[0], ids["dump"])

            apply_seasonal_shelf_proposal(
                db,
                "dia-de-los-muertos",
                [
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "The doorway everyone already knows for this night.",
                    },
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "A quieter ofrenda for the household that wants the smaller film.",
                    },
                ],
            )
            after = preview_holiday_rail(db, "dia-de-los-muertos", limit=12)
            after_ids = [int(item["id"]) for item in after["items"]]
            self.assertEqual(after_ids, [ids["known"], ids["gem"]])
            self.assertNotIn(ids["dump"], after_ids)
            self.assertIn("doorway everyone already knows", after["items"][0].get("why") or "")

            live = feed_seasonal_spotlight(
                db, today=date(2026, 11, 2), prefer_snapshot=False
            )
            self.assertEqual(live["scope_id"], "dia-de-los-muertos")
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertEqual(live_ids, [ids["known"], ids["gem"]])
            self.assertNotIn(ids["dump"], live_ids)

    def test_curated_shelf_replaces_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            from projectionist.library.feeds import build_seasonal_rail_snapshot

            built = build_seasonal_rail_snapshot(db, today=date(2026, 10, 31), limit=12)
            self.assertEqual(built["status"], "completed")
            stale_ids = [int(item["id"]) for item in built["payload"]["items"]]
            self.assertIn(ids["filler"], stale_ids)

            apply_seasonal_shelf_proposal(
                db,
                "halloween",
                [
                    {
                        "library_item_id": ids["gem"],
                        "curator_note": "Lead with the quiet one this year.",
                    },
                    {
                        "library_item_id": ids["known"],
                        "curator_note": "Then the classic doorway.",
                    },
                ],
            )
            live = feed_seasonal_spotlight(
                db, today=date(2026, 10, 31), prefer_snapshot=True
            )
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertEqual(live_ids, [ids["gem"], ids["known"]])
            self.assertFalse(live.get("from_schedule"))
            self.assertNotIn(ids["filler"], live_ids)

    def test_enrich_picks_attaches_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_halloween_library(db)
            enriched = enrich_picks(
                db,
                [{"library_item_id": ids["known"], "curator_note": "Hello"}],
            )
            self.assertEqual(enriched[0]["title"], "Classic Haunt")
            self.assertEqual(enriched[0]["year"], 1978)
            self.assertEqual(enriched[0]["curator_note"], "Hello")

    def _seed_christmas_library(self, db: Database) -> list[int]:
        ids = []
        for index, title in enumerate(("Home Alone", "The Shop Around the Corner", "Rare Noel")):
            ids.append(
                db.upsert_library_item(
                    {
                        "rating_key": f"xmas{index}",
                        "media_type": "movie",
                        "title": title,
                        "year": 1990 + index,
                        "keywords": ["christmas"],
                    }
                )
            )
        return ids

    def test_propose_reaches_the_llm_with_a_prompt_that_keeps_example_json(self) -> None:
        """The example JSON in the system prompt must not stop the curator call."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            ids = self._seed_christmas_library(db)
            previous_db = holidays_routes._db_factory
            previous_settings = holidays_routes._settings_factory
            holidays_routes._db_factory = lambda: db
            holidays_routes._settings_factory = lambda: Settings(llm_provider="ollama")
            captured: dict[str, object] = {}

            async def fake_chat(_db, _provider, messages, **_kwargs):
                captured["messages"] = messages
                roles = ("Classic", "Family", "Deep cut")
                return {
                    "content": json.dumps(
                        {
                            "theme": "A small Christmas shelf",
                            "picks": [
                                {
                                    "library_item_id": item_id,
                                    "role": roles[index],
                                    "note": "A grounded note.",
                                    "matched_because": "Keyword christmas.",
                                }
                                for index, item_id in enumerate(ids)
                            ],
                        }
                    )
                }

            try:
                with (
                    patch(
                        "projectionist.agent.providers.get_chat_provider",
                        return_value=object(),
                    ),
                    patch(
                        "projectionist.telemetry.llm_track.tracked_chat",
                        side_effect=fake_chat,
                    ),
                ):
                    result = asyncio.run(
                        holidays_routes.propose_holiday_rail_curation(
                            "christmas", None, user=None
                        )
                    )
            finally:
                holidays_routes._db_factory = previous_db
                holidays_routes._settings_factory = previous_settings

        self.assertIn("messages", captured)
        messages = captured["messages"]
        assert isinstance(messages, list)
        system = str(messages[0]["content"])
        self.assertIn('"picks"', system)
        self.assertNotIn("{limit}", system)
        self.assertIn("Aim for 3 picks", system)
        self.assertEqual(
            [int(pick["library_item_id"]) for pick in result["picks"]],
            ids,
        )

    def test_non_holiday_keyerror_is_a_plain_502_not_a_missing_holiday(self) -> None:
        previous_db = holidays_routes._db_factory
        previous_settings = holidays_routes._settings_factory
        holidays_routes._db_factory = lambda: object()
        holidays_routes._settings_factory = lambda: object()
        try:
            with patch(
                "projectionist.library.seasonal_curation.propose_seasonal_shelf",
                side_effect=KeyError("picks"),
            ):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(
                        holidays_routes.propose_holiday_rail_curation(
                            "christmas", None, user=None
                        )
                    )
        finally:
            holidays_routes._db_factory = previous_db
            holidays_routes._settings_factory = previous_settings
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn("picks", str(caught.exception.detail).lower())
        self.assertNotIn("keyerror", str(caught.exception.detail).lower())

    def test_missing_holiday_on_propose_stays_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            previous_db = holidays_routes._db_factory
            previous_settings = holidays_routes._settings_factory
            holidays_routes._db_factory = lambda: db
            holidays_routes._settings_factory = lambda: Settings(llm_provider="ollama")
            try:
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(
                        holidays_routes.propose_holiday_rail_curation(
                            "not-a-real-holiday", None, user=None
                        )
                    )
            finally:
                holidays_routes._db_factory = previous_db
                holidays_routes._settings_factory = previous_settings
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "Holiday not found")

    def test_schema_migration_adds_curator_note_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                cols = {row["name"] for row in conn.execute("PRAGMA table_info(holiday_rail_titles)")}
            self.assertIn("curator_note", cols)

    def test_prompt_asks_for_a_theme_roles_and_grounded_notes(self) -> None:
        from projectionist.library.seasonal_curation import _system_prompt

        prompt = _system_prompt(10)
        self.assertIn("10", prompt)
        self.assertNotIn("{limit}", prompt)
        self.assertIn("theme", prompt)
        for role in ("Classic", "Family", "New this year", "Deep cut", "After bedtime"):
            self.assertIn(role, prompt)
        self.assertIn("Do not invent", prompt)
        # Example JSON stays literal. str.format would have raised before this return.
        self.assertIn('"picks"', prompt)

    def test_schema_requires_a_theme_and_known_roles(self) -> None:
        from projectionist.library.seasonal_curation import parse_curator_payload

        parsed = parse_curator_payload(
            {
                "theme": "  Snowed-in comfort  ",
                "picks": [{"library_item_id": 1, "role": "Classic", "note": "A note."}],
            }
        )
        self.assertEqual(parsed["theme"], "Snowed-in comfort")
        self.assertEqual(parsed["picks"][0]["role"], "Classic")
        with self.assertRaises(ValueError):
            parse_curator_payload({"picks": []})
        with self.assertRaises(ValueError):
            parse_curator_payload(
                {"theme": "A theme", "picks": [{"library_item_id": 1, "role": "Bonus"}]}
            )

    def test_role_mix_caps_each_role(self) -> None:
        from projectionist.library.seasonal_curation import DEFAULT_ROLE_MIX, apply_role_mix

        picks = []
        for role, count in (
            ("Classic", 5),
            ("Family", 4),
            ("New this year", 2),
            ("Deep cut", 3),
            ("After bedtime", 2),
        ):
            for index in range(count):
                picks.append(
                    {
                        "library_item_id": len(picks) + 1,
                        "role": role,
                        "curator_note": f"{role} {index} belongs on the shelf.",
                        "matched_because": "keyword",
                    }
                )
        picks.append(
            {"library_item_id": 99, "role": "Classic", "curator_note": "   ", "matched_because": "plot"}
        )
        balanced = apply_role_mix(picks, DEFAULT_ROLE_MIX)
        counts: dict[str, int] = {}
        for pick in balanced:
            counts[pick["role"]] = counts.get(pick["role"], 0) + 1
            self.assertTrue(str(pick["curator_note"]).strip())
        self.assertEqual(counts, dict(DEFAULT_ROLE_MIX))

    def test_scoring_prefers_keyword_and_plot_over_weak_terms(self) -> None:
        from projectionist.library.seasonal_curation import score_seasonal_candidates

        observance = {
            "id": "christmas",
            "search_terms": ["christmas", "holiday", "winter", "family", "nutcracker"],
        }
        rows = [
            {
                "id": 1,
                "title": "Santa Claus Conquers the Martians",
                "year": 1964,
                "keywords": ["santa claus", "christmas eve"],
                "genres": ["Family"],
                "summary": "Martians kidnap Santa.",
            },
            {
                "id": 2,
                "title": "The Station",
                "year": 1988,
                "keywords": [],
                "genres": ["Drama"],
                "summary": "Strangers spend Christmas Eve snowed in at a station.",
            },
            {
                "id": 3,
                "title": "Cousins",
                "year": 2019,
                "keywords": ["family"],
                "genres": ["Family"],
                "summary": "A reunion with no particular day on the calendar.",
            },
            {
                "id": 4,
                "title": "Plain Story",
                "year": 2001,
                "keywords": [],
                "genres": ["Drama"],
                "summary": "Nothing seasonal in the plot.",
                "view_count": 2,
                "last_viewed_at": 1734681600,  # 2024-12-20, a previous Christmas window
            },
        ]
        scored = score_seasonal_candidates(rows, observance, today=date(2026, 11, 24))
        by_id = {row["library_item_id"]: row for row in scored}
        self.assertNotIn(3, by_id)
        self.assertIn(1, by_id)
        self.assertIn(2, by_id)
        self.assertIn(4, by_id)
        self.assertGreater(by_id[1]["score"], by_id[2]["score"])
        self.assertIn("keyword", by_id[1]["signals"])
        self.assertIn("plot", by_id[2]["signals"])
        self.assertIn("household", by_id[4]["signals"])
        # Owner-added "nutcracker" ships as a strong term beside the built-in Christmas keywords.
        self.assertIn("nutcracker", scored[0]["available_strong_terms"])

    def test_candidate_pool_keeps_era_variety_and_drops_weak_only(self) -> None:
        from projectionist.library.seasonal_curation import candidate_pool

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            classic = db.upsert_library_item(
                {
                    "rating_key": "xmas-classic",
                    "media_type": "movie",
                    "title": "The Shop Around the Corner",
                    "year": 1940,
                    "keywords": ["christmas"],
                    "summary": "Letters at Christmas.",
                    "genres": ["Romance"],
                    "content_rating": "NR",
                }
            )
            weak = db.upsert_library_item(
                {
                    "rating_key": "xmas-weak",
                    "media_type": "movie",
                    "title": "Winter Picnic",
                    "year": 2024,
                    "keywords": ["winter", "family"],
                    "genres": ["Family"],
                    "summary": "A cold weekend outdoors.",
                }
            )
            newest = []
            for index in range(70):
                newest.append(
                    db.upsert_library_item(
                        {
                            "rating_key": f"xmas-new-{index}",
                            "media_type": "movie",
                            "title": f"New Christmas {index}",
                            "year": 2024,
                            "keywords": ["christmas"],
                            "summary": "A new Christmas story.",
                            "genres": ["Comedy"],
                            "content_rating": "PG",
                        }
                    )
                )
            db.set_holiday_rail_title("christmas", newest[0], curation="exclude")
            pool = candidate_pool(db, "christmas", today=date(2026, 11, 24))
            ids = [row["library_item_id"] for row in pool["candidates"]]
            self.assertIn(classic, ids)
            self.assertNotIn(weak, ids)
            self.assertNotIn(newest[0], ids)
            self.assertLessEqual(len(ids), 60)
            classic_row = next(row for row in pool["candidates"] if row["library_item_id"] == classic)
            self.assertTrue(classic_row["synopsis"])
            self.assertIn("genres", classic_row)
            self.assertIn("christmas", classic_row["matching_keywords"])
            self.assertIn("youth_safe", classic_row)
            self.assertFalse(classic_row["youth_safe"])

    def test_apply_stores_theme_and_explore_hides_empty_notes_and_after_bedtime(self) -> None:
        from projectionist.library.seasonal_curation import apply_seasonal_shelf_proposal
        from projectionist.youth.apply import filter_payload_for_youth

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            classic = db.upsert_library_item(
                {
                    "rating_key": "theme-classic",
                    "media_type": "movie",
                    "title": "Classic Christmas",
                    "year": 1947,
                    "keywords": ["christmas"],
                    "content_rating": "PG",
                    "summary": "A Christmas visit.",
                }
            )
            late = db.upsert_library_item(
                {
                    "rating_key": "theme-late",
                    "media_type": "movie",
                    "title": "After the House Is Quiet",
                    "year": 1992,
                    "keywords": ["christmas"],
                    "content_rating": "PG",
                    "summary": "A Christmas argument.",
                }
            )
            blank = db.upsert_library_item(
                {
                    "rating_key": "theme-blank",
                    "media_type": "movie",
                    "title": "Untitled Card",
                    "year": 2001,
                    "keywords": ["christmas"],
                    "content_rating": "PG",
                }
            )
            result = apply_seasonal_shelf_proposal(
                db,
                "christmas",
                [
                    {
                        "library_item_id": classic,
                        "curator_note": "The visit the household already quotes.",
                        "role": "Classic",
                        "matched_because": "Keyword christmas.",
                    },
                    {
                        "library_item_id": late,
                        "note": "For after the younger members are in bed.",
                        "role": "After bedtime",
                        "matched_because": "Keyword christmas.",
                    },
                    {
                        "library_item_id": blank,
                        "curator_note": "   ",
                        "role": "Deep cut",
                    },
                ],
                theme="Letters, snow, and one late sitting",
            )
            self.assertEqual(result["preview"].get("theme"), "Letters, snow, and one late sitting")
            preview_ids = [int(item["id"]) for item in result["preview"]["items"]]
            self.assertNotIn(blank, preview_ids)
            self.assertEqual(
                result["preview"]["items"][0].get("shelf_role"),
                "Classic",
            )
            live = feed_seasonal_spotlight(db, today=date(2026, 12, 25), prefer_snapshot=False)
            self.assertEqual(live.get("theme"), "Letters, snow, and one late sitting")
            self.assertIn("Letters, snow", live["label"] + " " + live.get("theme", ""))
            live_ids = [int(item["id"]) for item in live["items"]]
            self.assertNotIn(blank, live_ids)
            self.assertTrue(all(str(item.get("curator_note") or "").strip() for item in live["items"]))
            youth = filter_payload_for_youth(
                live, user={"is_youth": True}, settings=Settings()
            )
            youth_ids = [int(item["id"]) for item in youth["items"]]
            self.assertIn(classic, youth_ids)
            self.assertNotIn(late, youth_ids)


if __name__ == "__main__":
    unittest.main()
