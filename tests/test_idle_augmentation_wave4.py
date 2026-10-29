"""Wave 4: enrichment IdleScheduler tasks on BaseAugmentationTask."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks import register_all
from projectionist.scheduler.tasks.base_augmentation import BaseAugmentationTask
from projectionist.scheduler.tasks.gap_analysis import GapAnalysisAugmentation
from projectionist.scheduler.tasks.keyword_theme_tagging import KeywordThemeAugmentation
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    confidence_for_demand_hits,
)
from projectionist.scheduler.tasks.llm_logline_enrichment import LlmLoglineAugmentation
from projectionist.scheduler.tasks.long_synopsis_enrichment import LongSynopsisAugmentation
from projectionist.scheduler.tasks.metadata_enrichment import MetadataEnrichmentAugmentation
from projectionist.scheduler.tasks.plot_neighbors import PlotNeighborsAugmentation, run as plot_neighbors_run
from projectionist.scheduler.tasks.semantic_embeddings import SemanticEmbeddingsAugmentation
from projectionist.scheduler.tasks.summary_motifs import SummaryMotifsAugmentation
from projectionist.scheduler.tasks.taste_refresh import TasteRefreshAugmentation
from projectionist.scheduler.tasks.title_relations_refresh import TitleRelationsAugmentation
from projectionist.telemetry.ingestion import upsert_closed_loop_event_sync
from projectionist.telemetry.kinship_miss import EVENT_KINSHIP_MISS

MIGRATED_CLASSES = {
    "plot_neighbors": PlotNeighborsAugmentation,
    "semantic_embeddings": SemanticEmbeddingsAugmentation,
    "metadata_enrichment": MetadataEnrichmentAugmentation,
    "long_synopsis_enrichment": LongSynopsisAugmentation,
    "llm_logline_enrichment": LlmLoglineAugmentation,
    "gap_analysis": GapAnalysisAugmentation,
    "keyword_theme_tagging": KeywordThemeAugmentation,
    "summary_motifs": SummaryMotifsAugmentation,
    "taste_refresh": TasteRefreshAugmentation,
    "title_relations_refresh": TitleRelationsAugmentation,
}

LEFT_AS_TASK_DEFINITION = (
    "weekly_letter",
    "weekly_digest",
    "member_newsletter",
    "collection_gc",
    "anniversary_scanner",
    "watch_history_ingest",
    "live_guide_week",
    "whisper_inbox",
    "arrival_notifications",
    "data_retention",
    "year_in_review_tease",
    "year_in_review_drop",
    "enthusiast_nudge",
    "owner_monthly_curation",
    "seasonal_rail",
    "member_weekly_rail",
)

ALREADY_ON_BASE = (
    "facet_taxonomy_audit",
    "entity_memory_enrichment",
    "coverage_deficit_audit",
)


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 2015,
        "genres": ["Drama"],
        "keywords": ["revenge"],
        "summary": "A quiet story about bakers and rivalry.",
        "tmdb_overview": "Amateur bakers compete.",
        "directors": ["Alice Baker"],
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


def _seed_kinship_miss(db: Database, item_id: int, *, hits: int = 3) -> None:
    for _ in range(hits):
        upsert_closed_loop_event_sync(
            db,
            event_type=EVENT_KINSHIP_MISS,
            priority_tier="P2",
            entity_type="title",
            entity_key=str(item_id),
            payload={"item_id": item_id, "reason": "more_like_this_empty"},
        )


class KinshipHelperTests(unittest.TestCase):
    def test_confidence_never_reaches_direct_commit_floor(self) -> None:
        self.assertEqual(confidence_for_demand_hits(1), 0.0)
        self.assertGreaterEqual(confidence_for_demand_hits(2), 0.60)
        self.assertLess(confidence_for_demand_hits(100), 0.90)


class MigratedTaskContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "wave4.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_migrated_classes_are_p2_stage_only(self) -> None:
        for name, cls in MIGRATED_CLASSES.items():
            task = cls(self.db)
            self.assertIsInstance(task, BaseAugmentationTask, name)
            self.assertIsInstance(task, KinshipMissAugmentationTask, name)
            self.assertFalse(task.enable_direct_commit, name)
            self.assertEqual(task.target_priority, "P2", name)
            self.assertEqual(task.task_name, name)

    def test_full_pass_jobs_do_not_stage_kinship_miss(self) -> None:
        item_id = _title(self.db, rating_key="pass", tmdb_id=1, title="Pass")
        _seed_kinship_miss(self.db, item_id, hits=3)
        for cls in (
            GapAnalysisAugmentation,
            KeywordThemeAugmentation,
            SummaryMotifsAugmentation,
            TasteRefreshAugmentation,
        ):
            task = cls(self.db)
            stats = asyncio.run(task.execute_run())
            self.assertEqual(stats["direct_commits"], 0, cls.__name__)
            self.assertEqual(stats["staged"], 0, cls.__name__)
            self.assertGreaterEqual(stats["processed"], 1, cls.__name__)
            pending = self.db.list_staged_augmentations(
                status="pending", task_name=task.task_name
            )
            self.assertEqual(pending, [], cls.__name__)


class PlotNeighborsStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "neighbors.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_stages_missing_neighbors_never_direct_commits(self) -> None:
        a = _title(self.db, rating_key="a", tmdb_id=301, title="Alpha")
        b = _title(self.db, rating_key="b", tmdb_id=302, title="Beta")
        self.db.set_embeddings([(a, [1.0, 0.0]), (b, [0.0, 1.0])])
        _seed_kinship_miss(self.db, b, hits=3)

        task = PlotNeighborsAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)
        pending = self.db.list_staged_augmentations(
            status="pending", task_name="plot_neighbors"
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["priority_tier"], "P2")
        candidate = json.loads(pending[0]["candidate_data_json"])
        self.assertEqual(candidate["action"], "refresh_plot_neighbors")
        self.assertEqual(int(candidate["item_id"]), b)

    def test_skips_when_neighbors_already_cached(self) -> None:
        a = _title(self.db, rating_key="a", tmdb_id=301, title="Alpha")
        b = _title(self.db, rating_key="b", tmdb_id=302, title="Beta")
        self.db.set_embeddings([(a, [1.0, 0.0]), (b, [0.0, 1.0])])
        self.db.set_neighbors(b, [(a, 0.9, 0.1, 1)])
        _seed_kinship_miss(self.db, b, hits=3)
        stats = asyncio.run(PlotNeighborsAugmentation(self.db).execute_run())
        self.assertEqual(stats["staged"], 0)
        self.assertEqual(stats["skipped"], 1)

    def test_run_still_prefers_demand_seeds(self) -> None:
        a = _title(self.db, rating_key="a", tmdb_id=301, title="Alpha")
        b = _title(self.db, rating_key="b", tmdb_id=302, title="Beta")
        self.db.set_embeddings([(a, [1.0, 0.0]), (b, [0.0, 1.0])])
        _seed_kinship_miss(self.db, b, hits=1)

        result = asyncio.run(plot_neighbors_run(self.db, Settings(), lambda: False))
        self.assertEqual(result.get("demand_prioritized"), 1)
        self.assertEqual(result.get("stage_direct_commits"), 0)
        self.assertGreaterEqual(int(result.get("seeds") or 0), 1)


class MetadataAndSynopsisStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "meta.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmpdir.cleanup()

    def test_metadata_stages_gap_titles(self) -> None:
        item_id = _title(
            self.db,
            rating_key="gap",
            tmdb_id=78,
            title="Blade Runner",
            release_date="",
            tmdb_overview="",
        )
        _seed_kinship_miss(self.db, item_id, hits=3)
        task = MetadataEnrichmentAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)

    def test_synopsis_stages_empty_long_synopsis(self) -> None:
        item_id = _title(self.db, rating_key="syn", tmdb_id=79, title="Need Plot")
        _seed_kinship_miss(self.db, item_id, hits=3)
        task = LongSynopsisAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)

    def test_logline_stages_empty_llm_logline(self) -> None:
        item_id = _title(self.db, rating_key="log", tmdb_id=80, title="Need Logline")
        _seed_kinship_miss(self.db, item_id, hits=3)
        task = LlmLoglineAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)

    def test_embeddings_stages_missing_vector(self) -> None:
        item_id = _title(self.db, rating_key="emb", tmdb_id=81, title="Need Vector")
        _seed_kinship_miss(self.db, item_id, hits=3)
        task = SemanticEmbeddingsAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)

    def test_relations_stages_title_with_no_edges(self) -> None:
        item_id = _title(self.db, rating_key="rel", tmdb_id=82, title="Need Relations")
        _seed_kinship_miss(self.db, item_id, hits=3)
        task = TitleRelationsAugmentation(self.db)
        stats = asyncio.run(task.execute_run())
        self.assertEqual(stats["staged"], 1)
        self.assertEqual(stats["direct_commits"], 0)
        second = asyncio.run(task.execute_run())
        self.assertEqual(second["staged"], 0)

    def test_fetch_telemetry_offloads_via_run_db(self) -> None:
        task = MetadataEnrichmentAugmentation(self.db)
        with patch(
            "projectionist.scheduler.tasks.kinship_augmentation.run_db",
            new_callable=AsyncMock,
        ) as run_db_mock:
            run_db_mock.return_value = []
            signals = asyncio.run(task.fetch_telemetry_signals())
        self.assertEqual(signals, [])
        run_db_mock.assert_awaited()
        passed = run_db_mock.await_args.args[0]
        self.assertIs(passed.__self__, self.db)
        self.assertIs(passed.__func__, type(self.db).list_closed_loop_events)


class RegistryWave4Tests(unittest.TestCase):
    def test_register_all_keeps_migrated_and_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "sched.db")
            scheduler = IdleScheduler(db, Path(tmp))
            register_all(scheduler)
            names = set(scheduler._definitions)
            for name in MIGRATED_CLASSES:
                self.assertIn(name, names)
            for name in LEFT_AS_TASK_DEFINITION:
                self.assertIn(name, names)
            for name in ALREADY_ON_BASE:
                self.assertIn(name, names)

            plot = scheduler._definitions["plot_neighbors"]
            self.assertEqual(plot.run_interval_seconds, 43200)
            self.assertTrue(plot.off_loop)
            self.assertEqual(plot.catchup_gap_seconds, 180)
            self.assertEqual(plot.items_per_cycle, 15)

            logline = scheduler._definitions["llm_logline_enrichment"]
            self.assertFalse(logline.off_loop)
            self.assertIsNone(logline.catchup_gap_seconds)

            embeddings = scheduler._definitions["semantic_embeddings"]
            self.assertFalse(embeddings.off_loop)
            self.assertEqual(embeddings.catchup_gap_seconds, 300)


if __name__ == "__main__":
    unittest.main()
