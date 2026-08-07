"""Phase E stretch — airing why, double feature, backup snapshot, syllabus handoff."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.double_feature import (
    build_pairing_why,
    build_title_why,
    suggest_tonight_double_feature,
)
from projectionist.live_channels.airing_why import (
    pick_youth_safe_live_station,
    station_airing_why,
)
from projectionist.live_channels.status import owner_now_playing_rows
from projectionist.syllabus.handoff import syllabus_publish_handoff
from projectionist.web.backup import build_admin_snapshot_zip


class AiringWhyTests(unittest.TestCase):
    def test_motif_one_liner(self) -> None:
        settings = Settings()
        settings.tunarr.station_meta = {
            "ch1": {
                "motif": "neo-noir rain",
                "programming_mode": "shuffle",
                "youth_safe": False,
            }
        }
        why = station_airing_why(settings, "ch1")
        self.assertIn("neo-noir rain", why)
        self.assertIn("shuffle", why)

    def test_owner_now_playing_includes_airing_why(self) -> None:
        settings = Settings()
        settings.tunarr.station_meta = {
            "abc": {"collection_title": "Comfort Comedies", "source": "collection"}
        }
        rows = owner_now_playing_rows(
            {
                "channels": [
                    {
                        "id": "abc",
                        "name": "Comfort",
                        "number": 101,
                        "now": {"title": "The Apartment", "percent": 40},
                        "next": {"title": "Tootsie", "start": 1_700_000_000},
                    }
                ]
            },
            channels=[{"id": "abc", "name": "Comfort", "number": 101}],
            engine_up=True,
            settings=settings,
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("Comfort Comedies", rows[0].get("airing_why") or "")

    def test_pick_youth_safe_station(self) -> None:
        settings = Settings()
        settings.tunarr.station_meta = {
            "kid": {"youth_safe": True, "source": "youth", "motif": "Saturday cartoons"},
            "adult": {"motif": "late night"},
        }
        pick = pick_youth_safe_live_station(
            settings,
            [
                {"id": "adult", "name": "Adult", "now": {"title": "Heat"}},
                {"id": "kid", "name": "Kids", "now": {"title": "Bluey"}},
            ],
        )
        assert pick is not None
        self.assertEqual(pick["id"], "kid")
        self.assertEqual(pick["now_title"], "Bluey")


class DoubleFeatureTests(unittest.TestCase):
    def test_pairs_two_owned_movies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            with db.connect() as conn:
                for title, year, genres, runtime in (
                    ("Heat", 1995, '["Crime","Drama"]', 170),
                    ("The Departed", 2006, '["Crime","Thriller"]', 151),
                    ("My Neighbor Totoro", 1988, '["Animation","Family"]', 86),
                ):
                    conn.execute(
                        """
                        INSERT INTO library_items (
                            rating_key, media_type, title, year, genres, view_count,
                            runtime_minutes, added_at, updated_at
                        ) VALUES (?, 'movie', ?, ?, ?, 0, ?, 1, 1)
                        """,
                        (title.lower().replace(" ", "-"), title, year, genres, runtime),
                    )
            payload = suggest_tonight_double_feature(db)
            self.assertEqual(payload["feed"], "tonight-double-feature")
            self.assertEqual(len(payload["items"]), 2)
            self.assertTrue(payload["bridge_text"])
            bridge = payload["bridge_text"].casefold()
            self.assertNotIn("from the same era", bridge)
            self.assertNotIn("first half", bridge)
            for item in payload["items"]:
                why = str(item.get("why") or item.get("recommendation_reason") or "")
                self.assertTrue(why)
                self.assertNotIn("first half", why.casefold())
                self.assertNotIn("second half", why.casefold())
                self.assertEqual(item.get("why"), item.get("recommendation_reason"))

    def test_pairing_why_cites_shared_genre_years_and_runtime(self) -> None:
        bridge = build_pairing_why(
            shared_genres={"Comedy"},
            year_a=2014,
            year_b=2022,
            year_gap=8,
            runtime_a=73,
            runtime_b=139,
        )
        self.assertIn("shared comedy", bridge.casefold())
        self.assertIn("2014", bridge)
        self.assertIn("2022", bridge)
        self.assertIn("~3h 32m", bridge)
        self.assertNotIn("same era", bridge.casefold())

    def test_pairing_why_cites_year_gap_and_same_director(self) -> None:
        bridge = build_pairing_why(
            shared_genres={"Crime", "Drama"},
            shared_directors={"Michael Mann"},
            year_a=1995,
            year_b=2023,
            year_gap=28,
            runtime_a=170,
            runtime_b=150,
        )
        self.assertIn("Michael Mann", bridge)
        self.assertIn("28 years apart", bridge)

    def test_title_why_uses_unwatched_genre_and_runtime(self) -> None:
        why = build_title_why(
            {
                "view_count": 0,
                "genres": '["Comedy","Mystery"]',
                "runtime_minutes": 139,
            },
            half="opening",
            shared_genres={"Comedy"},
        )
        self.assertIn("Still unwatched", why)
        self.assertIn("comedy", why.casefold())
        self.assertIn("139 min", why)
        self.assertNotIn("first half", why.casefold())

    def test_title_why_rewatch_signal(self) -> None:
        why = build_title_why(
            {"view_count": 2, "genres": '["Documentary"]', "runtime_minutes": 73},
            half="closing",
            shared_genres=set(),
        )
        self.assertIn("Rewatch-friendly", why)
        self.assertIn("2 plays", why)


class BackupSnapshotTests(unittest.TestCase):
    def test_zip_includes_settings_and_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "settings.json").write_text('{"features":{}}', encoding="utf-8")
            db_path = root / "projectionist.db"
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
            conn.commit()
            conn.close()

            body, filename, meta = build_admin_snapshot_zip(root)
            self.assertTrue(filename.endswith(".zip"))
            self.assertTrue(meta["settings_included"])
            self.assertTrue(meta["db_included"])
            with zipfile.ZipFile(BytesIO(body)) as zf:
                names = set(zf.namelist())
            self.assertIn("settings.json", names)
            self.assertIn("projectionist.db", names)
            self.assertIn("README.txt", names)


class SyllabusHandoffTests(unittest.TestCase):
    def test_needs_confirm_before_plex_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.create_curated_list(
                list_id="course1",
                name="Noir 101",
                list_kind="course",
                user_id=None,
            )
            db.set_curated_list_visibility("course1", user_id=None, visibility="published")
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO library_items (
                        rating_key, media_type, title, year, added_at, updated_at
                    ) VALUES ('rk1', 'movie', 'Double Indemnity', 1944, 1, 1)
                    """
                )
                lib_id = int(
                    conn.execute(
                        "SELECT id FROM library_items WHERE rating_key = 'rk1'"
                    ).fetchone()["id"]
                )
            db.add_curated_list_item(
                item_id="i1",
                list_id="course1",
                user_id=None,
                tmdb_id=99,
                tvdb_id=None,
                media_type="movie",
                title="Double Indemnity",
                library_item_id=lib_id,
            )

            settings = Settings()
            with mock.patch(
                "projectionist.config_store.plex_collections_configuration_error",
                return_value=None,
            ), mock.patch(
                "projectionist.config_store.resolve_plex_section",
                return_value="1",
            ):
                preview = syllabus_publish_handoff(
                    db,
                    user_id="owner",
                    list_id="course1",
                    settings=settings,
                    confirm=False,
                    target="plex",
                )
                self.assertTrue(preview.get("needs_confirm"))
                confirmed = syllabus_publish_handoff(
                    db,
                    user_id="owner",
                    list_id="course1",
                    settings=settings,
                    confirm=True,
                    target="plex",
                )
            self.assertTrue(confirmed.get("ok"))
            self.assertTrue(confirmed.get("confirmation_token"))


class VillageQuestionBlockTests(unittest.TestCase):
    def test_quote_block_includes_question(self) -> None:
        from projectionist.agent.village import quote_block_from_consult

        block = quote_block_from_consult(
            {
                "quote_ok": True,
                "persona": "Scholar",
                "answer": "See footnote one.",
                "question": "How does the montage rhyme with the score?",
            }
        )
        assert block is not None
        self.assertEqual(
            block["payload"]["question"],
            "How does the montage rhyme with the score?",
        )


if __name__ == "__main__":
    unittest.main()
