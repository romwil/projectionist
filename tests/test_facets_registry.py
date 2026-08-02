"""Facet taxonomy registry + resolver — layered concepts/aliases/packs, fail-closed."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from projectionist.facets import (
    augment_gaps_args_from_query,
    filter_pack_keyword_hits,
    genres_match_pack,
    get_registry,
    is_descriptive_ask,
    match_facet_pack,
    motif_search_expansions,
    normalize_tv_type,
    reload_registry,
    reset_registry_cache,
    resolve_genre_ids,
)
from projectionist.facets.registry import registry_from_mapping


class FacetRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_registry_cache()
        # Isolate from caller DATA_DIR overlays.
        self._old_data = os.environ.pop("DATA_DIR", None)
        self._old_env = os.environ.pop("PROJECTIONIST_FACET_ALIASES", None)
        reload_registry()

    def tearDown(self) -> None:
        reset_registry_cache()
        if self._old_data is not None:
            os.environ["DATA_DIR"] = self._old_data
        else:
            os.environ.pop("DATA_DIR", None)
        if self._old_env is not None:
            os.environ["PROJECTIONIST_FACET_ALIASES"] = self._old_env
        else:
            os.environ.pop("PROJECTIONIST_FACET_ALIASES", None)

    def test_seed_is_layered_without_baked_genre_ids(self) -> None:
        reg = get_registry()
        self.assertIn("science_fiction", reg.concepts)
        self.assertIn("history", reg.concepts)
        self.assertEqual(reg.aliases.get("sci-fi"), "science_fiction")
        self.assertIn("history_tv", reg.facet_packs)
        pack = reg.facet_packs["history_tv"]
        self.assertTrue(pack.keep_genre_names)
        self.assertTrue(pack.reject_genre_names)
        # Packs must not carry trusted baked discover ids.
        self.assertFalse(hasattr(pack, "keep_genre_ids"))
        self.assertFalse(hasattr(pack, "reject_genre_ids"))
        seed = json.loads(
            (Path(__file__).resolve().parents[1]
             / "projectionist/facets/data/taxonomy.json").read_text(encoding="utf-8")
        )
        raw_pack = seed["packs"]["history_tv"]
        self.assertNotIn("keep_genre_ids", raw_pack)
        self.assertNotIn("reject_genre_ids", raw_pack)
        self.assertNotIn("tmdb_genre_ids", raw_pack)

    def test_seed_loads_genre_aliases_and_crosswalk(self) -> None:
        movie_genres = [
            {"id": 878, "name": "Science Fiction"},
            {"id": 99, "name": "Documentary"},
            {"id": 36, "name": "History"},
        ]
        meta = resolve_genre_ids(movie_genres, "Science")
        self.assertEqual(meta["genre_ids"], "878")
        self.assertEqual(meta["resolved"][0]["name"], "Science Fiction")
        self.assertFalse(meta["unresolved"])

        tv_genres = [
            {"id": 10765, "name": "Sci-Fi & Fantasy"},
            {"id": 10768, "name": "War & Politics"},
            {"id": 18, "name": "Drama"},
        ]
        tv_meta = resolve_genre_ids(tv_genres, "History")
        self.assertEqual(tv_meta["genre_ids"], "10768")
        self.assertEqual(tv_meta["resolved"][0]["name"], "War & Politics")

    def test_ambiguous_genre_returns_candidates_not_invented_ids(self) -> None:
        genres = [
            {"id": 1, "name": "Action"},
            {"id": 2, "name": "Action & Adventure"},
        ]
        meta = resolve_genre_ids(genres, "Act")
        self.assertEqual(meta["genre_ids"], "")
        self.assertTrue(meta["ambiguous"])
        names = {c["name"] for c in meta["genres_candidates"]}
        self.assertIn("Action", names)
        self.assertIn("Action & Adventure", names)

    def test_unresolved_genre_stays_empty(self) -> None:
        meta = resolve_genre_ids([{"id": 18, "name": "Drama"}], "NotAGenre")
        self.assertEqual(meta["genre_ids"], "")
        self.assertEqual(meta["unresolved"], ["NotAGenre"])
        self.assertFalse(meta["ambiguous"])

    def test_tv_type_normalization_from_seed(self) -> None:
        self.assertEqual(normalize_tv_type("miniseries"), "2")
        self.assertEqual(normalize_tv_type("limited series"), "2")
        self.assertEqual(normalize_tv_type("2"), "2")
        self.assertIsNone(normalize_tv_type("not-a-type"))

    def test_history_tv_pack_match_and_keyword_filter(self) -> None:
        self.assertTrue(genres_match_pack("History", "history_tv"))
        pack = match_facet_pack("historical drama", pack_id="history_tv")
        self.assertIsNotNone(pack)
        assert pack is not None
        self.assertIn("based on true story", pack.keyword_queries)

        items = [
            {
                "id": 1,
                "name": "Chernobyl",
                "genre_ids": [18],
                "overview": "Workers at the Chernobyl nuclear power plant",
            },
            {
                "id": 2,
                "name": "Pure Crime",
                "genre_ids": [80, 18],
                "overview": "A detective hunts a killer with no historical angle",
            },
            {
                "id": 3,
                "name": "War Room",
                "genre_ids": [10768],
                "overview": "Politics",
            },
        ]
        live_genres = [
            {"id": 10768, "name": "War & Politics"},
            {"id": 80, "name": "Crime"},
            {"id": 18, "name": "Drama"},
        ]
        kept = filter_pack_keyword_hits(items, pack, genre_list=live_genres)
        titles = {str(i["name"]) for i in kept}
        self.assertIn("Chernobyl", titles)
        self.assertIn("War Room", titles)
        self.assertNotIn("Pure Crime", titles)

    def test_intent_parser_history_miniseries_science_negation(self) -> None:
        out = augment_gaps_args_from_query(
            {
                "query": (
                    "any recent history miniseries that aren't science-focused"
                ),
                "media_type": "show",
            },
            now=datetime(2026, 8, 1),
        )
        self.assertEqual(out["genres"], "History")
        self.assertEqual(out["tv_type"], "miniseries")
        self.assertEqual(out["without_genres"], "Science Fiction")
        self.assertEqual(out["year_from"], 2018)
        self.assertEqual(out["query"], "")  # descriptive ask cleared
        self.assertTrue(is_descriptive_ask("any recent history miniseries"))
        self.assertFalse(is_descriptive_ask("Chernobyl"))

    def test_motif_search_expansions_from_seed(self) -> None:
        terms = motif_search_expansions("Late Night Sci-Fi")
        folded = {t.casefold() for t in terms}
        self.assertIn("science fiction", folded)
        self.assertIn("alien", folded)

    def test_data_dir_overlay_extends_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Flat v1 overlay still accepted and normalized into concepts.
            overlay = {
                "genre_aliases": {"space opera": "Science Fiction", "noirish": "Crime"},
                "genre_crosswalk": {"Crime": []},
            }
            path = Path(tmp) / "facet_aliases.json"
            path.write_text(json.dumps(overlay), encoding="utf-8")
            os.environ["DATA_DIR"] = tmp
            reset_registry_cache()
            reload_registry()
            genres = [
                {"id": 878, "name": "Science Fiction"},
                {"id": 80, "name": "Crime"},
            ]
            meta = resolve_genre_ids(genres, "noirish")
            self.assertEqual(meta["genre_ids"], "80")

    def test_registry_from_mapping_layered(self) -> None:
        reg = registry_from_mapping(
            {
                "version": 2,
                "concepts": {
                    "drama": {"label": "Drama", "names": ["Drama"]},
                },
                "aliases": {"zap": "drama"},
                "tv_types": {"miniseries": "2"},
                "packs": {},
                "intent": {"descriptive_ask_min_words": 3, "descriptive_ask_glue": []},
                "motif_search_aliases": {},
            }
        )
        self.assertEqual(reg.alias_canonical("ZAP"), "Drama")
        meta = resolve_genre_ids([{"id": 18, "name": "Drama"}], "zap", registry=reg)
        self.assertEqual(meta["genre_ids"], "18")


if __name__ == "__main__":
    unittest.main()
