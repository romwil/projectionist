"""Plot Lab hybrid multi-signal AND (motifs ∪ keywords ∪ live plot text)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from unittest.mock import MagicMock, patch

from curatorx.library.db import Database
from curatorx.library.query import (
    build_motif_why,
    compute_knowledge_coverage,
    filters_from_mapping,
    query_library,
)
from curatorx.library.titles import get_title_detail


class PlotMultiSignalTests(unittest.TestCase):
    def test_hybrid_bride_coma_finds_kill_bill_via_plot_text(self) -> None:
        """Even without motif facets, hybrid AND on plot text surfaces Kill Bill."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 1",
                    "year": 2003,
                    "summary": "The Bride awakens from a coma and seeks revenge.",
                    "keywords": ["revenge", "martial arts"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Only Bride",
                    "year": 1999,
                    "summary": "A bride walks down the aisle.",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "3",
                    "media_type": "movie",
                    "title": "Only Coma",
                    "year": 2001,
                    "summary": "A long coma changes everything.",
                }
            )

            hybrid = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,coma",
                        "plot_match_mode": "hybrid",
                        "limit": 20,
                    }
                ),
            )
            titles = [item["title"] for item in hybrid["items"]]
            self.assertEqual(titles, ["Kill Bill: Vol. 1"])
            item = hybrid["items"][0]
            self.assertEqual(item["matched_motifs"], ["bride", "coma"])
            layers = {entry["motif"]: entry["layers"] for entry in item["match_layers"]}
            self.assertIn("plot_text", layers["bride"])
            self.assertIn("plot_text", layers["coma"])
            self.assertIn("plot text", item["motif_why"])

    def test_pure_motifs_mode_requires_facet_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 1",
                    "year": 2003,
                    "summary": "The Bride awakens from a coma.",
                }
            )
            # No motif facets → pure mode misses; hybrid still hits via plot text.
            pure = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,coma",
                        "plot_match_mode": "motifs",
                        "limit": 20,
                    }
                ),
            )
            self.assertEqual(pure["total_matched"], 0)

            hybrid = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,coma",
                        "plot_match_mode": "hybrid",
                        "limit": 20,
                    }
                ),
            )
            self.assertEqual(hybrid["total_matched"], 1)

    def test_hybrid_can_match_via_keyword_facet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Revenge Tale",
                    "year": 2010,
                    "summary": "A quiet drama with no useful tokens.",
                }
            )
            item_id = int(db.all_library_items()[0]["id"])
            db.replace_facets_of_type(
                "keyword",
                [(item_id, "keyword", "revenge"), (item_id, "keyword", "coma")],
            )
            # One token via keyword, one via motif facet.
            db.replace_facets_of_type("motif", [(item_id, "motif", "bride")])

            result = query_library(
                db,
                filters_from_mapping(
                    {
                        "motifs": "bride,coma",
                        "plot_match_mode": "hybrid",
                        "limit": 20,
                    }
                ),
            )
            self.assertEqual(result["total_matched"], 1)
            layers = {
                entry["motif"]: entry["layers"]
                for entry in result["items"][0]["match_layers"]
            }
            self.assertIn("motif", layers["bride"])
            self.assertIn("keyword", layers["coma"])

    def test_build_motif_why_cites_layers(self) -> None:
        why = build_motif_why(
            ["bride", "coma"],
            ["coma"],
            plot_text="The Bride awakens from a coma.",
            item_keyword_values=["revenge"],
        )
        self.assertEqual(why["matched_motifs"], ["bride", "coma"])
        layers = {entry["motif"]: entry["layers"] for entry in why["match_layers"]}
        self.assertEqual(layers["bride"], ["plot_text"])
        self.assertEqual(layers["coma"], ["motif", "plot_text"])
        self.assertIn("plot text", why["summary"])
        self.assertIn("plot motif", why["summary"])

    def test_knowledge_coverage_reports_sparse_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Has Overview",
                    "year": 2003,
                    "summary": "A plot summary.",
                    "tmdb_overview": "TMDB overview text.",
                    "llm_logline": "Short logline.",
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "movie",
                    "title": "Empty",
                    "year": 2004,
                    "summary": "",
                }
            )
            ids = {
                str(row["title"]): int(row["id"]) for row in db.all_library_items()
            }
            item_id = ids["Has Overview"]
            other_id = ids["Empty"]
            db.replace_facets_of_type(
                "motif",
                [(item_id, "motif", "bride"), (item_id, "motif", "coma")],
            )
            db.replace_facets_of_type("keyword", [(item_id, "keyword", "revenge")])
            db.set_neighbors(item_id, [(other_id, 0.9, 0.1)])

            coverage = compute_knowledge_coverage(db)
            self.assertEqual(coverage["total_titles"], 2)
            self.assertEqual(coverage["with_overview_pct"], 50.0)
            self.assertEqual(coverage["with_motifs_pct"], 50.0)
            self.assertEqual(coverage["with_keywords_pct"], 50.0)
            self.assertEqual(coverage["with_themes_pct"], 0.0)
            self.assertEqual(coverage["with_neighbors_pct"], 50.0)
            self.assertEqual(coverage["with_loglines_pct"], 50.0)
            self.assertEqual(coverage["motif_rows"], 2)
            self.assertEqual(coverage["theme_rows"], 0)
            self.assertEqual(coverage["logline_count"], 1)
            # Phase C synopsis column may be absent — key must not crash consumers.
            self.assertTrue(
                "with_synopsis_pct" not in coverage or isinstance(coverage["with_synopsis_pct"], float)
            )

    @patch("curatorx.library.titles.cached_machine_identifier", return_value="")
    def test_title_detail_includes_plot_knowledge(self, _machine) -> None:
        settings = MagicMock()
        settings.tmdb_api_key = ""
        settings.fanart_api_key = ""
        settings.plex_url = ""
        settings.plex_token = ""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            db.upsert_library_item(
                {
                    "rating_key": "pk-1",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 1",
                    "year": 2003,
                    "tmdb_id": 24,
                    "summary": "The Bride awakens from a coma.",
                    "tagline": "Revenge is a dish best served cold.",
                    "keywords": ["revenge"],
                }
            )
            db.upsert_library_item(
                {
                    "rating_key": "pk-2",
                    "media_type": "movie",
                    "title": "Neighbor",
                    "year": 2004,
                    "summary": "Other title.",
                }
            )
            ids = {str(row["title"]): int(row["id"]) for row in db.all_library_items()}
            item_id = ids["Kill Bill: Vol. 1"]
            other_id = ids["Neighbor"]
            db.replace_facets_of_type(
                "motif",
                [(item_id, "motif", "bride"), (item_id, "motif", "coma")],
            )
            db.replace_facets_of_type("theme", [(item_id, "theme", "revenge")])
            db.set_neighbors(item_id, [(other_id, 0.9, 0.1)])

            detail = get_title_detail(
                db, settings, media_type="movie", tmdb_id=24, enrich=False
            )
            self.assertIsNotNone(detail.plot_knowledge)
            pk = detail.plot_knowledge
            self.assertTrue(pk.has_overview)
            self.assertTrue(pk.has_tagline)
            self.assertFalse(pk.has_logline)
            self.assertIn("bride", pk.motifs)
            self.assertIn("revenge", pk.themes)
            self.assertEqual(pk.neighbor_count, 1)


if __name__ == "__main__":
    unittest.main()
